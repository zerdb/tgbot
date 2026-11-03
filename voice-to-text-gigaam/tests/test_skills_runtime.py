"""Contract, routing and Excel skill integration tests."""
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook, load_workbook

from skills_runtime.contracts import SkillMessage
from skills_runtime.registry import SkillRegistry
from skills_runtime.workflows import build_default_registry, create_sales_summary


class RuntimeTests(unittest.TestCase):
    def test_message_round_trip_shape(self):
        message = SkillMessage.create("calculations", "group_sum", {"rows": []},
                                      from_skill="excel_reader", task_id="t1")
        self.assertEqual(message.to_dict(), {
            "task_id": "t1", "from_skill": "excel_reader", "to_skill": "calculations",
            "action": "group_sum", "inputs": {"rows": []},
        })

    def test_unknown_skill_returns_failure_not_crash(self):
        result = SkillRegistry().execute("missing", "run")
        self.assertEqual(result.status, "failed")
        self.assertIn("not registered", result.error)


class ExcelWorkflowTests(unittest.TestCase):
    def test_four_skills_create_grouped_report_without_overwriting_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "sales.xlsx"
            destination = root / "reports" / "sales_summary.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.append(["Менеджер", "Сумма"])
            sheet.append(["Анна", 100])
            sheet.append(["Борис", 250])
            sheet.append(["Анна", 50])
            workbook.save(source)
            workbook.close()

            result = create_sales_summary(
                build_default_registry(), str(source), str(destination),
                group_by="Менеджер", sum_column="Сумма",
            )
            self.assertEqual(result["rows_read"], 3)
            self.assertEqual(result["groups"], 2)
            self.assertEqual(result["grand_total"], "400")
            self.assertTrue(source.exists())
            report = load_workbook(destination, data_only=True)
            try:
                values = list(report.active.values)
                self.assertEqual(values[1], ("Анна", 150))
                self.assertEqual(values[2], ("Борис", 250))
                self.assertEqual(values[3], ("Общий итог", 400))
            finally:
                report.close()

    def test_writer_refuses_to_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            destination = Path(tmp) / "existing.xlsx"
            destination.write_text("keep", encoding="utf-8")
            result = build_default_registry().execute(
                "excel_writer", "write_group_report",
                {"destination": str(destination), "groups": [], "grand_total": "0"},
            )
            self.assertEqual(result.status, "failed")
            self.assertEqual(destination.read_text(encoding="utf-8"), "keep")


if __name__ == "__main__":
    unittest.main()
