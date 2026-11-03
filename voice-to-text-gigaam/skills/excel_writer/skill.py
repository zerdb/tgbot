"""Create a new report workbook; never overwrite an existing file."""
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from skills_runtime.base import Skill, SkillContext
from skills_runtime.contracts import SkillMessage


class ExcelWriterSkill(Skill):
    name = "excel_writer"
    description = "Create a formatted summary workbook at a new, non-existing path."

    def handle(self, message: SkillMessage, context: SkillContext) -> dict:
        if message.action != "write_group_report":
            raise ValueError(f"Unsupported action: {message.action}")
        destination = Path(message.inputs["destination"]).expanduser().resolve()
        if destination.suffix.casefold() != ".xlsx":
            raise ValueError("Report destination must end with .xlsx.")
        if destination.exists():
            raise FileExistsError(f"Refusing to overwrite existing file: {destination}")
        groups = message.inputs.get("groups")
        group_by = str(message.inputs.get("group_by", "Группа"))
        sum_column = str(message.inputs.get("sum_column", "Сумма"))
        if not isinstance(groups, list):
            raise ValueError("groups must be a list.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Сводка"
        sheet.append([group_by, f"Итого: {sum_column}"])
        for cell in sheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="245A81")
        for item in groups:
            sheet.append([item["group"], float(item["total"])])
        sheet.append(["Общий итог", float(message.inputs.get("grand_total", 0))])
        for cell in sheet[sheet.max_row]:
            cell.font = Font(bold=True)
        for column in sheet.columns:
            width = min(max(max(len(str(cell.value or "")) for cell in column) + 2, 12), 42)
            sheet.column_dimensions[get_column_letter(column[0].column)].width = width
        try:
            workbook.save(destination)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        finally:
            workbook.close()
        return {"path": str(destination), "rows_written": len(groups),
                "grand_total": str(message.inputs.get("grand_total", "0"))}
