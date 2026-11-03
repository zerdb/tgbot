"""Deterministic table calculations; no guessed columns or formulas."""
from decimal import Decimal, InvalidOperation

from skills_runtime.base import Skill, SkillContext
from skills_runtime.contracts import SkillMessage


class CalculationsSkill(Skill):
    name = "calculations"
    description = "Group numeric values by a chosen column and calculate exact totals."

    def handle(self, message: SkillMessage, context: SkillContext) -> dict:
        if message.action != "group_sum":
            raise ValueError(f"Unsupported action: {message.action}")
        rows = message.inputs.get("rows")
        group_by = message.inputs.get("group_by")
        sum_column = message.inputs.get("sum_column")
        if not isinstance(rows, list) or not rows:
            raise ValueError("No data rows were provided.")
        if not group_by or not sum_column:
            raise ValueError("Both group_by and sum_column must be specified.")
        totals: dict[str, Decimal] = {}
        for index, row in enumerate(rows, start=1):
            if group_by not in row or sum_column not in row:
                raise ValueError(f"Required column missing in data row {index}.")
            raw = row[sum_column]
            if raw is None or raw == "":
                continue
            try:
                amount = Decimal(str(raw).replace(" ", "").replace(",", "."))
            except (InvalidOperation, ValueError):
                raise ValueError(f"Non-numeric value in {sum_column!r}, row {index}: {raw!r}")
            if not amount.is_finite():
                raise ValueError(f"Non-finite value in row {index}.")
            key = str(row[group_by] if row[group_by] is not None else "(пусто)")
            totals[key] = totals.get(key, Decimal("0")) + amount
        result = [{"group": key, "total": str(value)}
                  for key, value in sorted(totals.items(), key=lambda item: item[0].casefold())]
        grand_total = sum(totals.values(), Decimal("0"))
        return {"group_by": group_by, "sum_column": sum_column,
                "groups": result, "grand_total": str(grand_total),
                "groups_count": len(result)}
