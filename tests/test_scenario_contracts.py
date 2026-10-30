"""Output contract failures must remain visible after scenario-file separation."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from validate_scenario import evaluate


class ScenarioContracts(unittest.TestCase):
    def test_missing_or_dropped_output_fails(self):
        contract = {"sample": {"schema": "trech_scenario_validation_v1", "checks": [
            {"file": "trech_scores.jsonl", "phase": "run_end", "field": "n_events", "op": "gt", "expected": 0},
            {"file": "trech_scores.jsonl", "phase": "run_end", "field": "hook_emit_dropped_count", "op": "eq", "expected": 0, "missing": 0},
        ]}}
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            self.assertFalse(any(r["passed"] for r in evaluate(contract, output)))
            scores = output / "trech_scores.jsonl"
            scores.write_text(json.dumps({"phase": "run_start", "n_events": 3}) + "\n")
            self.assertFalse(any(r["passed"] for r in evaluate(contract, output)))
            scores.write_text(json.dumps({"phase": "run_end", "n_events": 3, "hook_emit_dropped_count": 2}) + "\n")
            self.assertEqual([r["passed"] for r in evaluate(contract, output)], [True, False])
            scores.write_text(json.dumps({"phase": "run_end", "n_events": 3}) + "\n")
            self.assertTrue(all(r["passed"] for r in evaluate(contract, output)))

    def test_no_declarations_do_not_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "no output checks"):
                evaluate({}, Path(tmp))


if __name__ == "__main__":
    unittest.main()
