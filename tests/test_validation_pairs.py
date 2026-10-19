"""Focused tests for the reusable operator/reference validation contract."""

from __future__ import annotations

import copy
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "validation"))

from trech_validation.cases import (  # noqa: E402
    OperatorReferencePairCase,
    POLYURETHANE_OPERATOR_PAIR,
    FOAM_MECHANICS_CANDIDATE_CASES,
)
from trech_validation.runner import RunContext, RunOutputs, required_run_names  # noqa: E402
from trech_validation.__main__ import main as validation_main  # noqa: E402


OBSERVABLES = {
    "final_expansion_factor": 30.0,
    "cream_time_s": 10.0,
    "rise_time_s": 20.0,
    "gel_time_s": 30.0,
    "solid_time_s": 90.0,
    "exotherm_rise_k": 60.0,
    "core_skin_gap_k": 20.0,
    "trapped_gas_fraction": 0.95,
}
TOLERANCES = {
    "final_expansion_factor_relative": 0.02,
    "cream_time_s_absolute": 1.5,
    "rise_time_s_absolute": 2.0,
    "gel_time_s_absolute": 2.0,
    "solid_time_s_absolute": 5.0,
    "exotherm_rise_k_absolute": 2.0,
    "core_skin_gap_k_absolute": 3.0,
    "trapped_gas_fraction_absolute": 0.01,
}


def pair_payload(source: str) -> dict:
    trust = {
        "authored_state_law": source == "reference",
        "selection": {
            "mode": "contextual",
            "status": "selected",
            "selectedModels": ["meso_reaction_operator"],
        },
        "domain_measured": True,
        "trained_scale": "meso",
        "scale_mismatch": False,
        "missing_inputs": [],
        "starved_inputs": [],
        "holdout_r2": 0.995,
        "holdout_samples": 40000,
        "inference_count": 100,
        "out_of_domain_count": 1,
        "out_of_domain_fraction": 0.01,
        "non_operator_inference_count": 2,
        "non_operator_out_of_domain_count": 0,
    }
    return {
        "schema": "trech_operator_reference_pair_v1",
        "comparison_key": {"seed": 7, "temperature_k": 296.15},
        "source": source,
        "teacher": "distilled reference law",
        "measured": False,
        "tolerances": copy.deepcopy(TOLERANCES),
        "trust": trust,
        "observables": copy.deepcopy(OBSERVABLES),
    }


def run_with_pair(source: str) -> RunOutputs:
    run = RunOutputs(directory=ROOT)
    run.hook_emits = [{
        "tag": "polyurethane_foam_summary",
        "payload": {"operator_vs_reference": pair_payload(source)},
    }]
    run.scores = {
        "hook_predict_count": 102 if source == "operator" else 2,
        "hook_predict_out_of_domain_count": 1 if source == "operator" else 0,
    }
    return run


class OperatorReferencePairTests(unittest.TestCase):
    def setUp(self) -> None:
        self.case = OperatorReferencePairCase(POLYURETHANE_OPERATOR_PAIR)
        self.reference = run_with_pair("reference")
        self.operator = run_with_pair("operator")

    def context(self) -> RunContext:
        return RunContext(runs={
            POLYURETHANE_OPERATOR_PAIR.runs.reference: self.reference,
            POLYURETHANE_OPERATOR_PAIR.runs.operator: self.operator,
        })

    def test_valid_pair_passes_all_common_checks(self) -> None:
        result = self.case.evaluate(self.context())
        self.assertEqual(result.status, "pass", result.summary)
        self.assertTrue(result.measured["run_inference_accounting"])
        self.assertTrue(result.measured["contextual_selection"])

    def test_inference_accounting_mismatch_fails(self) -> None:
        self.operator.scores["hook_predict_count"] = 101
        result = self.case.evaluate(self.context())
        self.assertEqual(result.status, "fail")
        self.assertIn("run_inference_accounting", result.summary)

    def test_comparison_key_mismatch_fails(self) -> None:
        payload = self.operator.hook_emits[0]["payload"]["operator_vs_reference"]
        payload["comparison_key"]["seed"] = 8
        result = self.case.evaluate(self.context())
        self.assertEqual(result.status, "fail")
        self.assertIn("identical_comparison_key", result.summary)

    def test_missing_observable_tolerance_fails_cleanly(self) -> None:
        payload = self.operator.hook_emits[0]["payload"]["operator_vs_reference"]
        payload["tolerances"].pop("gel_time_s_absolute")
        result = self.case.evaluate(self.context())
        self.assertEqual(result.status, "fail")
        self.assertIn("needs exactly one", result.summary)

    def test_experimental_suite_has_separate_run_aliases(self) -> None:
        candidate_runs = required_run_names(FOAM_MECHANICS_CANDIDATE_CASES)
        self.assertEqual(len(candidate_runs), 6)
        self.assertTrue(set(candidate_runs).isdisjoint(required_run_names()))
        self.assertEqual(required_run_names([]), [])

    def test_missing_candidate_runs_cannot_promote_or_overwrite_default_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(validation_main([
                "--suite", "foam-mechanics-candidate", "--runs-dir", tmp]), 1)
            self.assertTrue((Path(tmp) / "promotion_report.md").is_file())
            self.assertTrue((Path(tmp) / "promotion_report.json").is_file())

    def test_mechanics_observer_gap_rejects_high_holdout_accuracy(self) -> None:
        case = FOAM_MECHANICS_CANDIDATE_CASES[0]
        observables = dict(final_expansion_factor=30, max_height_mm=120, max_lean_deg=5,
                           broken_bond_fraction=0.1, detached_fraction=0.1,
                           ground_fraction=0.05, late_vs_peak_motion_ratio=0.01)
        tolerances = dict(final_expansion_factor_relative=0.02, max_height_mm_relative=0.05,
                          max_lean_deg_absolute=1.5, broken_bond_fraction_absolute=0.06,
                          detached_fraction_absolute=0.05, ground_fraction_absolute=0.03,
                          late_vs_peak_motion_ratio_absolute=0.05)
        for source, run in [("reference", self.reference), ("operator", self.operator)]:
            payload = pair_payload(source)
            payload.update(observables=observables.copy(), tolerances=tolerances.copy())
            payload["trust"].update(holdout_r2=0.999, out_of_domain_count=0,
                                    out_of_domain_fraction=0.0)
            run.hook_emits[0]["payload"] = {"mechanics_operator_vs_reference": payload}
            run.scores["hook_predict_out_of_domain_count"] = 0
        ctx = RunContext(runs={case.spec.runs.reference: self.reference,
                               case.spec.runs.operator: self.operator})
        self.assertEqual(case.evaluate(ctx).status, "pass")
        self.operator.hook_emits[0]["payload"]["mechanics_operator_vs_reference"][
            "observables"]["max_lean_deg"] = 8
        result = case.evaluate(ctx)
        self.assertEqual(result.status, "fail")
        self.assertIn("max_lean_deg_absolute", result.summary)


if __name__ == "__main__":
    unittest.main()
