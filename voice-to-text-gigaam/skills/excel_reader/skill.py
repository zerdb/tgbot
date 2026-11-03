"""Read-only Excel inspection and tabular extraction."""
from pathlib import Path

from openpyxl import load_workbook

from skills_runtime.base import Skill, SkillContext
from skills_runtime.contracts import SkillMessage


class ExcelReaderSkill(Skill):
    name = "excel_reader"
    description = "Inspect workbook sheets and extract rows using the first non-empty row as headers."

    def handle(self, message: SkillMessage, context: SkillContext) -> dict:
        if message.action == "inspect":
            path = self._path(message.inputs["path"])
            workbook = load_workbook(path, read_only=True, data_only=True)
            try:
                return {"path": str(path), "sheets": [
                    {"name": sheet.title, "max_row": sheet.max_row, "max_column": sheet.max_column}
                    for sheet in workbook.worksheets
                ]}
            finally:
                workbook.close()
        if message.action == "read_table":
            path = self._path(message.inputs["path"])
            sheet_name = message.inputs.get("sheet")
            workbook = load_workbook(path, read_only=True, data_only=True)
            try:
                if sheet_name:
                    if sheet_name not in workbook.sheetnames:
                        raise ValueError(f"Worksheet not found: {sheet_name}")
                    sheet = workbook[sheet_name]
                else:
                    sheet = workbook.active
                rows = sheet.iter_rows(values_only=True)
                headers = None
                records = []
                for row in rows:
                    values = list(row)
                    if headers is None:
                        if any(value is not None for value in values):
                            headers = [str(value).strip() if value is not None else ""
                                       for value in values]
                        continue
                    if not any(value is not None for value in values):
                        continue
                    record = {header: values[index] if index < len(values) else None
                              for index, header in enumerate(headers) if header}
                    if record:
                        records.append(record)
                if headers is None:
                    raise ValueError("Worksheet contains no non-empty header row.")
                return {"path": str(path), "sheet": sheet.title,
                        "columns": [h for h in headers if h], "rows": records,
                        "row_count": len(records)}
            finally:
                workbook.close()
        raise ValueError(f"Unsupported action: {message.action}")

    @staticmethod
    def _path(value: str) -> Path:
        path = Path(value).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(str(path))
        if path.suffix.casefold() not in {".xlsx", ".xlsm"}:
            raise ValueError("Only .xlsx and .xlsm workbooks are supported in this version.")
        return path
