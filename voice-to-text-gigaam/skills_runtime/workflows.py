"""Explicit multi-skill workflows; every hand-off uses the shared message contract."""
from pathlib import Path
from uuid import uuid4

from .contracts import SkillMessage
from .registry import SkillRegistry


def build_default_registry() -> SkillRegistry:
    from skills.files import FilesSkill
    from skills.excel_reader import ExcelReaderSkill
    from skills.calculations import CalculationsSkill
    from skills.excel_writer import ExcelWriterSkill

    registry = SkillRegistry()
    for skill in (FilesSkill(), ExcelReaderSkill(), CalculationsSkill(), ExcelWriterSkill()):
        registry.register(skill)
    return registry


def _send(registry: SkillRegistry, task_id: str, sender: str, recipient: str,
          action: str, inputs: dict):
    message = SkillMessage.create(
        to_skill=recipient, action=action, inputs=inputs,
        from_skill=sender, task_id=task_id,
    )
    result = registry.dispatch(message)
    if result.status != "completed":
        raise RuntimeError(f"{recipient} failed: {result.error}")
    return result


def create_sales_summary(registry: SkillRegistry, source: str, destination: str,
                         group_by: str, sum_column: str, sheet: str | None = None) -> dict:
    """Find source -> read workbook -> calculate grouped totals -> write new report."""
    task_id = uuid4().hex
    source_path = Path(source).expanduser().resolve()
    found = _send(registry, task_id, "assistant", "files", "find", {
        "folder": str(source_path.parent), "pattern": source_path.name, "limit": 2,
    })
    if found.result["count"] != 1:
        raise ValueError(
            f"Expected exactly one source workbook, found {found.result['count']}."
        )

    read = _send(registry, task_id, "files", "excel_reader", "read_table", {
        "path": found.result["files"][0]["path"], "sheet": sheet,
    })
    calculation = _send(registry, task_id, "excel_reader", "calculations", "group_sum", {
        "rows": read.result["rows"], "group_by": group_by, "sum_column": sum_column,
    })
    written = _send(registry, task_id, "calculations", "excel_writer", "write_group_report", {
        "destination": destination, "groups": calculation.result["groups"],
        "group_by": group_by, "sum_column": sum_column,
        "grand_total": calculation.result["grand_total"],
    })
    return {
        "task_id": task_id, "source": found.result["files"][0]["path"],
        "report": written.result["path"], "rows_read": read.result["row_count"],
        "groups": calculation.result["groups_count"],
        "grand_total": calculation.result["grand_total"],
    }
