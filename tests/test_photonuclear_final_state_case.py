"""Offline checks of ``analytic_photonuclear_final_state`` on synthetic run outputs.

No Geant4 run is needed: each test builds the three graded pair-sweep runs
(15/23/30 MeV) plus the threshold points, with the photonuclear check entry and
the secondary-class score fields the case reads. Figures come from 50,000-event
Release runs of 2026-11-14.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "validation"))

from trech_validation.cases import (  # noqa: E402
    PHOTONUCLEAR_SWEEP_MIN_KEV, PhotonuclearFinalState, _pair_sweep_series)
from trech_validation.runner import RunContext, RunOutputs  # noqa: E402

# energy keV -> (absorptions, final-state n/p/alpha/other, secondary classes n/p/alpha/ion)
RECORDED = {
    15000: (86, (0, 0, 86, 86), (0, 0, 88, 88)),
    23000: (779, (5, 75, 1947, 364), (5, 84, 1962, 369)),
    30000: (205, (0, 23, 497, 100), (0, 25, 520, 105)),
}
EDGES = {15000: 10.335, 23000: 17.979, 30000: 24.686}


def run_scores(kev):
    n = 50000
    if kev not in RECORDED:
        check = {"type": "photonuclear_fraction", "available": True,
                 "primaries_photonuclear_first": 0}
        return {"system_event_count": n, "analytic_checks": [check]}
    absorptions, (fn, fp, fa, fo), (sn, sp, sa, si) = RECORDED[kev]
    final_state = {
        "absorptions": absorptions, "energy_closure_abs_max": 2.1e-12,
        "momentum_closure_max": 4.2e-10, "target_unmatched": 0, "edge_excess_max": -2.4e-05,
        "edge_tested": fp + fa + fn, "neutrons": fn, "protons": fp, "alphas": fa, "others": fo,
        "neutron_max_kinetic_mev": 5.676 if fn else 0.0,
        "neutrons_per_absorption": fn / absorptions, "protons_per_absorption": fp / absorptions,
        "alphas_per_absorption": fa / absorptions,
    }
    check = {"type": "photonuclear_fraction", "available": True,
             "primaries_photonuclear_first": absorptions, "neutron_edge_mev": EDGES[kev],
             "photoneutron_channels": [{"target": "O16", "open": kev > 15672}],
             "final_state": final_state}
    scores = {"system_event_count": n, "analytic_checks": [check]}
    for cls, count in (("neutron", sn), ("proton", sp), ("alpha", sa), ("ion", si)):
        scores[f"system_event_secondaries_{cls}_mean"] = count / n
    return scores


def evaluate(patch=None):
    runs = {}
    for kev, name in _pair_sweep_series(PHOTONUCLEAR_SWEEP_MIN_KEV):
        scores = run_scores(kev)
        if patch:
            patch(kev, scores)
        runs[name] = RunOutputs(directory=Path("."), scores=scores)
    return PhotonuclearFinalState().evaluate(RunContext(runs=runs))


class PhotonuclearFinalStateCaseTests(unittest.TestCase):
    def test_recorded_runs_pass(self):
        result = evaluate()
        self.assertEqual(result.status, "pass", result.notes)
        joined = "\n".join(result.notes)
        self.assertIn("secondary classes n/p/alpha 5/84/1962 cover 5/75/1947", joined)
        self.assertIn("ions 369 vs final-state other products 364", joined)
        measured = {m["energy_kev"]: m for m in result.measured}
        self.assertEqual(measured[23000]["secondary_class_counts"],
                         {"neutron": 5, "proton": 84, "alpha": 1962})

    def test_class_count_below_final_state_fails(self):
        def short_alphas(kev, scores):
            if kev == 23000:
                scores["system_event_secondaries_alpha_mean"] = 1900 / 50000

        result = evaluate(short_alphas)
        self.assertEqual(result.status, "fail")
        self.assertIn("1900 cover 5/75/1947", "\n".join(result.notes))

    def test_runs_without_new_classes_fail(self):
        def drop_proton(kev, scores):
            scores.pop("system_event_secondaries_proton_mean", None)

        result = evaluate(drop_proton)
        self.assertEqual(result.status, "fail")
        self.assertIn("n/p/alpha 5/None/1962", "\n".join(result.notes))

    def test_closure_gate_still_applies(self):
        def bad_closure(kev, scores):
            if kev == 30000:
                scores["analytic_checks"][0]["final_state"]["energy_closure_abs_max"] = 1e-3

        self.assertEqual(evaluate(bad_closure).status, "fail")


if __name__ == "__main__":
    unittest.main()
