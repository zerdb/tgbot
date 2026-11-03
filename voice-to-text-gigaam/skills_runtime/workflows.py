"""Explicit multi-skill workflows; each hand-off uses the shared message contract."""
from pathlib import Path

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


def create_sales_summary(registry: SkillRegistry, source: str, destination: str,
                         group_by: str, sum_column: str, sheet: str | None = None) -> dict:
    """Read source -> calculate grouped totals -> create a separate report file."""
    task_id = None
    read = registry.execute("excel_reader", "read_table",
                            {"path": source, "sheet": sheet})
    if read.status != "completed":
        raise RuntimeError(f"excel_reader failed: {read.error}")
    task_id = read.task_id
    calculation = registry.dispatch_from_result(
        read, "calculations", "group_sum",
        {"rows": read.result["rows"], "group_by": group_by, "sum_column": sum_column},
        from_skill="excel_reader",
    ) if hasattr(registry, "dispatch_from_result") else registry.execute(
        "calculations", "group_sum",
        {"rows": read.result["rows"], "group_by": group_by, "sum_column": sum_column})
    if calculation.status != "completed":
        raise RuntimeError(f"calculations failed: {calculation.error}")
    written = registry.execute("excel_writer", "write_group_report", {
        "destination": destination, "groups": calculation.result["groups"],
        "group_by": group_by, "sum_column": sum_column,
        "grand_total": calculation.result["grand_total"],
    })
    if written.status != "completed":
        raise RuntimeError(f"excel_writer failed: {written.error}")
    return {"source": str(Path(source).resolve()), "report": written.result["path"],
            "rows_read": read.result["row_count"],
            "groups": calculation.result["groups_count"],
            "grand_total": calculation.result["grand_total"]}
