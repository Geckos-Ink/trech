"""Offline checks of the system-observable validation cases on synthetic scores.

No Geant4 run is needed: each test feeds a hand-built ``trech_scores`` record
through the case's ``evaluate`` and checks that a consistent record passes and
that each corrupted invariant fails with the expected check name.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "validation"))

from trech_validation.cases import (  # noqa: E402
    RUN_ANALYTIC_BEER_LAMBERT, SECONDARY_SPECIES, SystemEventMultiplicityConsistent)
from trech_validation.runner import RunContext, RunOutputs  # noqa: E402


def beer_lambert_scores(**overrides):
    # Figures from a 20,000-event 100 keV Beer-Lambert run (2026-11-10).
    n = 20000
    mean = 0.8718
    std = 1.0071567703192983
    scores = {
        "system_event_count": n,
        "primaries_uncollided": 8433,
        "primaries_photoelectric_first": 213,
        "system_event_secondaries_mean": mean,
        "system_event_secondaries_stddev": std,
        "system_event_secondaries_min": 0.0,
        "system_event_secondaries_max": 8.0,
        "system_event_secondaries_zero_fraction": 0.4341,
        "system_event_secondaries_dispersion_index": std * std / mean,
        "system_event_secondaries_shape_defined": True,
        "system_event_secondaries_skewness": 1.4955905328505241,
        "system_event_secondaries_excess_kurtosis": 3.26261120043867,
        "system_event_track_length_mean_mm": 190.36543610933447,
        "system_event_track_length_min_mm": 55.434841756997535,
        "system_event_track_length_max_mm": 367.32897419069934,
        "system_event_track_length_zero_fraction": 0.0,
    }
    # Same run's species split: every secondary is an electron.
    for species in SECONDARY_SPECIES:
        electron = species == "electron"
        prefix = f"system_event_secondaries_{species}"
        scores[prefix + "_mean"] = mean if electron else 0.0
        scores[prefix + "_max"] = 8.0 if electron else 0.0
        scores[prefix + "_zero_fraction"] = 0.4341 if electron else 1.0
    scores.update(overrides)
    return scores


def evaluate(scores):
    ctx = RunContext()
    ctx.runs[RUN_ANALYTIC_BEER_LAMBERT] = RunOutputs(directory=Path("."), scores=scores)
    return SystemEventMultiplicityConsistent().evaluate(ctx)


class MultiplicityCaseTests(unittest.TestCase):
    def test_recorded_run_passes(self):
        result = evaluate(beer_lambert_scores())
        self.assertEqual(result.status, "pass", result.summary)

    def test_missing_run_skips(self):
        result = SystemEventMultiplicityConsistent().evaluate(RunContext())
        self.assertEqual(result.status, "skip")

    def test_older_run_without_fields_fails_as_missing(self):
        scores = beer_lambert_scores()
        del scores["system_event_secondaries_dispersion_index"]
        result = evaluate(scores)
        self.assertEqual(result.status, "fail")
        self.assertIn("missing multiplicity observables", result.summary)

    def test_run_without_species_split_fails_as_missing(self):
        scores = beer_lambert_scores()
        del scores["system_event_secondaries_optical_photon_mean"]
        result = evaluate(scores)
        self.assertEqual(result.status, "fail")
        self.assertIn("system_event_secondaries_optical_photon_mean", result.summary)

    def test_each_corrupted_invariant_fails(self):
        corruptions = {
            "count_valued": {"system_event_secondaries_mean": 0.87183},
            "dispersion_matches_moments": {"system_event_secondaries_dispersion_index": 1.0},
            "kurtosis_admissible": {"system_event_secondaries_excess_kurtosis": -1.9},
            "zero_secondaries_cover_uncollided": {"system_event_secondaries_zero_fraction": 0.40},
            "secondaries_cover_photoelectric": {"primaries_photoelectric_first": 20000},
            "every_event_has_track_length": {"system_event_track_length_zero_fraction": 0.01},
            "track_length_ordered": {"system_event_track_length_min_mm": 200.0},
            "species_sum_to_total": {"system_event_secondaries_gamma_mean": 0.01},
            "species_count_valued": {"system_event_secondaries_electron_max": 7.5},
            "photoelectrons_cover_photoelectric": {
                "system_event_secondaries_electron_zero_fraction": 0.995},
            "no_positrons_below_pair_threshold": {
                "system_event_secondaries_positron_mean": 0.0001,
                "system_event_secondaries_electron_mean": 0.8717},
        }
        for check, override in corruptions.items():
            with self.subTest(check=check):
                result = evaluate(beer_lambert_scores(**override))
                self.assertEqual(result.status, "fail")
                self.assertIn(check, result.summary)


if __name__ == "__main__":
    unittest.main()
