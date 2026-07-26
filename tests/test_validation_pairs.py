"""Focused tests for the reusable operator/reference validation contract."""

from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "validation"))

from trech_validation.cases import (  # noqa: E402
    OperatorReferencePairCase,
    POLYURETHANE_OPERATOR_PAIR,
)
from trech_validation.runner import RunContext, RunOutputs  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
