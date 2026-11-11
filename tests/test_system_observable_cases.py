"""Offline checks of the system-observable validation cases on synthetic scores.

No Geant4 run is needed: each test feeds a hand-built ``trech_scores`` record
through the case's ``evaluate`` and checks that a consistent record passes and
that each corrupted invariant fails with the expected check name.
"""

from __future__ import annotations

from pathlib import Path
import copy
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "validation"))

from trech_validation.cases import (  # noqa: E402
    RUN_ANALYTIC_BEER_LAMBERT, RUN_GEOMETRY_ASSEMBLY, SECONDARY_SPECIES,
    SystemEventHistogramConsistent, SystemEventMultiplicityConsistent,
    SystemVolumeEventEdepConsistent)
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


def assembly_scores():
    # Three of the 19 volumes of a 400-event geometry_procedural_assembly run
    # (2026-11-11): the phantom, the hit centre dosimeter cell and an unhit NaI tube.
    n = 400
    shapes = {
        "phantom": {"mean_mev": 0.28464973860099296, "stddev_mev": 0.3999719562299595,
                    "stderr_mev": 0.020023643028339463, "min_mev": 0.0,
                    "max_mev": 1.2042516257008673, "zero_fraction": 0.585,
                    "shape_defined": True, "skewness": 0.9591701046815895,
                    "excess_kurtosis": -0.7390442860925899},
        "cell_1_1_0": {"mean_mev": 0.013444150073091814, "stddev_mev": 0.08007964651792729,
                       "stderr_mev": 0.0040089967077308695, "min_mev": 0.0,
                       "max_mev": 0.8050931701822427, "zero_fraction": 0.96,
                       "shape_defined": True, "skewness": 7.281997555751157,
                       "excess_kurtosis": 57.677467772155026},
        "nai_2": {"mean_mev": 0.0, "stddev_mev": 0.0, "stderr_mev": 0.0, "min_mev": 0.0,
                  "max_mev": 0.0, "zero_fraction": 1.0, "shape_defined": False,
                  "skewness": None, "excess_kurtosis": None},
    }
    return {
        "system_event_count": n,
        "total_edep_mev": 147.96084282462908,
        "system_event_edep_max_mev": 1.25,
        "volume_edep_mev": {"phantom": 113.85989544039718, "cell_1_1_0": 5.3776600292367265,
                            "nai_2": 0.0},
        "volume_event_edep": shapes,
    }


def evaluate_volumes(scores):
    ctx = RunContext()
    ctx.runs[RUN_GEOMETRY_ASSEMBLY] = RunOutputs(directory=Path("."), scores=scores)
    return SystemVolumeEventEdepConsistent().evaluate(ctx)


class VolumeEventEdepCaseTests(unittest.TestCase):
    def test_recorded_run_passes(self):
        result = evaluate_volumes(assembly_scores())
        self.assertEqual(result.status, "pass", result.summary)

    def test_missing_run_skips(self):
        result = SystemVolumeEventEdepConsistent().evaluate(RunContext())
        self.assertEqual(result.status, "skip")

    def test_older_run_without_block_fails_as_missing(self):
        scores = assembly_scores()
        del scores["volume_event_edep"]
        result = evaluate_volumes(scores)
        self.assertEqual(result.status, "fail")
        self.assertIn("missing volume_event_edep", result.summary)

    def test_each_corrupted_invariant_fails(self):
        def corrupt(volume=None, total=None, **fields):
            scores = assembly_scores()
            if volume is not None:
                scores["volume_event_edep"][volume].update(fields)
            if total is not None:
                scores.update(total)
            return scores

        missing_volume = assembly_scores()
        del missing_volume["volume_event_edep"]["nai_2"]
        extra_volume = assembly_scores()
        extra_volume["volume_event_edep"]["ghost"] = dict(
            extra_volume["volume_event_edep"]["nai_2"])
        cases = {
            "mean_times_events_is_total": corrupt("phantom", mean_mev=0.2847),
            "min_le_mean_le_max": corrupt("cell_1_1_0", max_mev=0.01),
            "non_negative": corrupt("phantom", min_mev=-0.1),
            "within_event_maximum": corrupt("phantom", max_mev=1.3),
            "zero_fraction_in_unit_interval": corrupt("phantom", zero_fraction=1.2),
            "empty_volume_all_zero": corrupt("nai_2", zero_fraction=0.99),
            "shape_values_iff_defined": corrupt("nai_2", shape_defined=True),
            "kurtosis_admissible": corrupt("cell_1_1_0", excess_kurtosis=40.0),
            "volumes_within_total": corrupt(total={"total_edep_mev": 100.0}),
            "same_volume_set": extra_volume,
            "nai_2:missing": missing_volume,
        }
        for check, scores in cases.items():
            with self.subTest(check=check):
                result = evaluate_volumes(scores)
                self.assertEqual(result.status, "fail")
                self.assertIn(check, result.summary)


# Histograms from the same 20,000-event 100 keV Beer-Lambert run (2026-11-11):
# 47 populated deposit bins starting at log bin 4 (2.51 eV), the last holding the
# 456 full-absorption events at exactly 0.1 MeV.
BEER_LAMBERT_EDEP_COUNTS = [
    1, 0, 0, 0, 3, 0, 0, 3, 0, 3, 1, 6, 5, 3, 8, 5, 4, 10, 11, 24, 26, 29, 34, 52, 59, 77, 100,
    114, 122, 164, 228, 245, 301, 369, 457, 583, 693, 862, 1183, 1777, 1874, 858, 501, 105, 0, 0,
    456]
BEER_LAMBERT_SECONDARY_COUNTS = [8682, 7193, 2767, 919, 305, 90, 30, 10, 4]


def histogram_scores():
    first = 4
    edges = [10.0 ** (-6 + (first + i) / 10) for i in range(len(BEER_LAMBERT_EDEP_COUNTS) + 1)]
    edep = {
        "scheme": "log10", "bins_per_decade": 10, "low_mev": 1e-06, "high_mev": 1000000.0,
        "zero_count": 8644, "underflow_count": 0, "overflow_count": 0,
        "edges_mev": edges, "counts": list(BEER_LAMBERT_EDEP_COUNTS),
    }
    secondaries = {
        "scheme": "integer_then_log2", "exact_below": 16, "overflow_at": 2147483648,
        "overflow_count": 0, "edges": list(range(10)),
        "counts": list(BEER_LAMBERT_SECONDARY_COUNTS),
    }
    return beer_lambert_scores(
        system_event_edep_mean_mev=0.01255729210032839,
        system_event_edep_min_mev=0.0,
        system_event_edep_max_mev=0.1,
        system_event_edep_zero_fraction=0.4322,
        system_event_edep_histogram=edep,
        system_event_secondaries_histogram=secondaries,
    )


def evaluate_histograms(scores, provenance=None):
    ctx = RunContext()
    ctx.runs[RUN_ANALYTIC_BEER_LAMBERT] = RunOutputs(
        directory=Path("."), scores=scores, provenance=provenance or [])
    return SystemEventHistogramConsistent().evaluate(ctx)


def run_end_copy(scores):
    return [{"phase": "run_start"},
            {"phase": "run_end",
             "system_event_edep_histogram": copy.deepcopy(scores["system_event_edep_histogram"]),
             "system_event_secondaries_histogram":
                 copy.deepcopy(scores["system_event_secondaries_histogram"])}]


class EventHistogramCaseTests(unittest.TestCase):
    def test_recorded_run_passes(self):
        scores = histogram_scores()
        result = evaluate_histograms(scores, run_end_copy(scores))
        self.assertEqual(result.status, "pass", result.summary)
        self.assertIn("fullest [0.02512, 0.03162) MeV x1874", result.summary)

    def test_without_provenance_passes_and_says_so(self):
        result = evaluate_histograms(histogram_scores())
        self.assertEqual(result.status, "pass", result.summary)
        self.assertIn("no run_end provenance", result.summary)

    def test_missing_run_skips(self):
        self.assertEqual(SystemEventHistogramConsistent().evaluate(RunContext()).status, "skip")

    def test_older_run_without_histograms_fails_as_missing(self):
        scores = histogram_scores()
        del scores["system_event_secondaries_histogram"]
        result = evaluate_histograms(scores)
        self.assertEqual(result.status, "fail")
        self.assertIn("missing system_event_edep_histogram", result.summary)

    def test_each_corrupted_invariant_fails(self):
        def corrupt(edep=None, secondaries=None, **top):
            scores = histogram_scores()
            scores["system_event_edep_histogram"].update(edep or {})
            scores["system_event_secondaries_histogram"].update(secondaries or {})
            scores.update(top)
            return scores

        edep_counts = list(BEER_LAMBERT_EDEP_COUNTS)
        edep_counts[10] += 1
        shifted_edges = [e * 1.01 for e in histogram_scores()["system_event_edep_histogram"][
            "edges_mev"]]
        sec_counts = list(BEER_LAMBERT_SECONDARY_COUNTS)
        sec_counts[0] -= 1
        sec_counts[1] += 1
        sec_shift = list(BEER_LAMBERT_SECONDARY_COUNTS)
        sec_shift[1] -= 4000
        sec_shift[3] += 4000
        cases = {
            "edep_scheme": corrupt(edep={"bins_per_decade": 20}),
            "edep_counts_every_event": corrupt(edep={"counts": edep_counts}),
            "edep_counts_non_negative": corrupt(edep={"underflow_count": -1, "zero_count": 8645}),
            "edep_edges_on_fixed_grid": corrupt(edep={"edges_mev": shifted_edges}),
            "edep_populated_span_trimmed": corrupt(edep={
                "counts": BEER_LAMBERT_EDEP_COUNTS + [0],
                "edges_mev": histogram_scores()["system_event_edep_histogram"]["edges_mev"]
                + [10.0 ** (-6 + 52 / 10)]}),
            "edep_zero_count_matches_fraction": corrupt(system_event_edep_zero_fraction=0.43),
            "edep_max_in_last_bin": corrupt(system_event_edep_max_mev=0.2),
            "edep_mean_within_bin_edges": corrupt(system_event_edep_mean_mev=0.02),
            "secondaries_scheme": corrupt(secondaries={"exact_below": 8}),
            "secondaries_counts_every_event": corrupt(secondaries={"overflow_count": 1}),
            "secondaries_edges_on_fixed_grid": corrupt(secondaries={
                "edges": [0, 1, 2, 3, 4, 5, 6, 7, 8, 10]}),
            "secondaries_zero_bin_matches_fraction": corrupt(secondaries={"counts": sec_counts}),
            "secondaries_extremes_in_end_bins": corrupt(system_event_secondaries_max=9.0),
            "secondaries_mean_within_bin_edges": corrupt(secondaries={"counts": sec_shift}),
        }
        for check, scores in cases.items():
            with self.subTest(check=check):
                result = evaluate_histograms(scores)
                self.assertEqual(result.status, "fail")
                self.assertIn(check, result.summary)

    def test_provenance_copy_must_be_verbatim(self):
        scores = histogram_scores()
        provenance = run_end_copy(scores)
        provenance[1]["system_event_edep_histogram"]["counts"][5] += 1
        result = evaluate_histograms(scores, provenance)
        self.assertEqual(result.status, "fail")
        self.assertIn("provenance_copy_verbatim", result.summary)


if __name__ == "__main__":
    unittest.main()
