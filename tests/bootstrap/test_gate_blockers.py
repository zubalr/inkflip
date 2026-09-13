"""Gate receipts must honor live Beads blockers added after the static plan."""
from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import gate


class GateBlockerTests(unittest.TestCase):
    def setUp(self):
        self.definition = {"id": "G1", "title": "G1", "task": "T18",
                           "required_task_ids": [], "scenario_commands": []}
        self.open = [{"id": "pdf-composition", "status": "open", "dependency_type": "blocks"}]

    def test_open_followup_blocks_gate_owner(self):
        with patch.object(gate.coordination, "bd", return_value=self.open) as bd:
            with self.assertRaisesRegex(gate.GateError, "pdf-composition"):
                gate.require_unblocked_owner(self.definition)
        bd.assert_called_once_with(["dep", "list", "pdf-t18", "--type", "blocks"])

    def test_closed_or_absent_dependencies_allow_run(self):
        for records in ([], [{**self.open[0], "status": "closed"}]):
            with self.subTest(records=records), patch.object(gate.coordination, "bd", return_value=records):
                gate.require_unblocked_owner(self.definition)

    def test_unavailable_or_malformed_state_fails_closed(self):
        for records in (None, {}, [None], [{}], [{"id": "pdf-x"}],
                        [{"id": "pdf-x", "status": "closed", "dependency_type": "related"}]):
            with self.subTest(records=records), patch.object(gate.coordination, "bd", return_value=records):
                with self.assertRaises(gate.GateError):
                    gate.require_unblocked_owner(self.definition)
        with patch.object(gate.coordination, "bd", side_effect=ValueError("Beads unavailable")):
            with self.assertRaises(ValueError):
                gate.require_unblocked_owner(self.definition)

    def test_blockers_prevent_scenarios_and_late_success_receipt(self):
        for states, calls in (([self.open], 0), ([[], self.open], 1)):
            with self.subTest(states=states), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                receipt = root / "receipt.json"
                counts = {"collected": 1, "passed": 1, "failed": 0, "skipped": 0}
                with patch.object(sys, "argv", ["gate.py", "G1", "--receipt", str(receipt)]), \
                     patch.object(gate, "ROOT", root), \
                     patch.object(gate, "load_gates", return_value={"G1": self.definition}), \
                     patch.object(gate.coordination, "issues_by_id", return_value={}), \
                     patch.object(gate.coordination, "bd", side_effect=states), \
                     patch.object(gate.coordination, "load_contracts", return_value=({}, {})), \
                     patch.object(gate.task_acceptance, "load_registry", return_value={}), \
                     patch.object(gate.acceptance_receipts, "require_clean_inputs", return_value="a" * 40), \
                     patch.object(gate, "run_scenarios", return_value=([{"tests": counts}], [])) as scenarios, \
                     redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    self.assertNotEqual(gate.main(), 0)
                self.assertEqual(scenarios.call_count, calls)
                self.assertFalse(receipt.exists())


if __name__ == "__main__":
    unittest.main()
