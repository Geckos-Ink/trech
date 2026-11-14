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
    # Whole-event deposit and step length by stepping-particle class (a 20,000-event
    # rerun, 2026-11-14): the photon primaries step in every event, electrons exactly
    # where one was created, and gammas deposit their sub-cut binding energies.
    scores["system_event_edep_mean_mev"] = 0.012557292100328396
    scores["system_event_edep_max_mev"] = 0.1
    scores["system_event_edep_zero_fraction"] = 0.4322
    electron_mm = 0.010658711945456246
    scores["system_event_edep_species"] = class_block("mev", {
        "electron": (0.012545475652565722, 0.09997152000000001, 0.4341),
        "gamma": (1.1816447762654421e-05, 0.0005426954662225873, 0.97205)})
    scores["system_event_track_length_species"] = class_block("mm", {
        "electron": (electron_mm, 77.61253424981038, 0.4341),
        "gamma": (scores["system_event_track_length_mean_mm"] - electron_mm,
                  367.3067336054484, 0.0)})
    for key, value in list(overrides.items()):
        if isinstance(value, dict) and isinstance(scores.get(key), dict):
            # Nested override: {"class": {"field": value}} merges into the block.
            for sp, fields in value.items():
                scores[key][sp].update(fields)
            del overrides[key]
    scores.update(overrides)
    return scores


def class_block(unit, present):
    keys = (f"mean_{unit}", f"max_{unit}", "zero_fraction")
    return {sp: dict(zip(keys, present.get(sp, (0.0, 0.0, 1.0)))) for sp in SECONDARY_SPECIES}


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

    def test_run_without_class_split_fails_by_name(self):
        scores = beer_lambert_scores()
        del scores["system_event_edep_species"]
        result = evaluate(scores)
        self.assertEqual(result.status, "fail")
        self.assertIn("class_split_present", result.summary)

    def test_each_corrupted_invariant_fails(self):
        edep = "system_event_edep_species"
        length = "system_event_track_length_species"
        corruptions = {
            "edep_class_sum_to_total": {edep: {"gamma": {"mean_mev": 1e-4}}},
            "edep_class_non_negative": {edep: {"neutron": {"mean_mev": -1e-6}}},
            "edep_class_within_event": {edep: {"electron": {"max_mev": 0.2}}},
            "track_length_class_sum_to_total": {length: {"electron": {"mean_mm": 1.0}}},
            "track_length_class_within_event": {length: {"electron": {"zero_fraction": -0.1}}},
            "edep_class_need_steps": {edep: {"electron": {"zero_fraction": 0.433}}},
            "track_length_class_covers_created": {length: {"electron": {"zero_fraction": 0.5}}},
            "primary_class_steps_every_event": {length: {"gamma": {"zero_fraction": 0.01}}},
            "other_classes_step_iff_created": {length: {"electron": {"zero_fraction": 0.43}}},
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


def log_histogram(unit, first, counts, zero_count, underflow=0, overflow=0):
    """A fixed-grid log10 histogram as the engine writes it (EventHistogram.hpp)."""
    edges = [10.0 ** (-6 + (first + i) / 10) for i in range(len(counts) + 1)] if counts else []
    return {
        "scheme": "log10", "bins_per_decade": 10, f"low_{unit}": 1e-06,
        f"high_{unit}": 1000000.0, "zero_count": zero_count, "underflow_count": underflow,
        "overflow_count": overflow, f"edges_{unit}": edges, "counts": list(counts),
    }


ASSEMBLY_VOLUME_HISTOGRAMS = {
    "phantom": (34, [1, 1, 0, 0, 1, 1, 0, 0, 1, 0, 0, 1, 2, 0, 1, 1, 4, 1, 2, 7, 6, 8, 13, 13,
                     23, 44, 35], 234),
    "cell_1_1_0": (47, [1, 1, 0, 0, 0, 3, 4, 1, 0, 3, 0, 2, 1], 384),
    "nai_2": (0, [], 400),
}


# Same 400-event assembly run, rerun 2026-11-12 (deposit fields unchanged):
# per-volume step length (mm) and created secondaries, pre-step attribution.
ASSEMBLY_VOLUME_TRACK_LENGTH = {'cell_1_1_0': {'excess_kurtosis': 2.627800662362998,
                'histogram': {'bins_per_decade': 10,
                              'counts': [1, 1, 0, 0, 0, 1, 1, 1, 279, 23, 8, 2, 5, 2, 1],
                              'edges_mm': [0.6309573444801932,
                                           0.7943282347242815,
                                           1.0,
                                           1.2589254117941673,
                                           1.5848931924611136,
                                           1.9952623149688795,
                                           2.51188643150958,
                                           3.1622776601683795,
                                           3.9810717055349722,
                                           5.011872336272722,
                                           6.309573444801933,
                                           7.943282347242816,
                                           10.0,
                                           12.589254117941675,
                                           15.848931924611133,
                                           19.952623149688797],
                              'high_mm': 1000000.0,
                              'low_mm': 1e-06,
                              'overflow_count': 0,
                              'scheme': 'log10',
                              'underflow_count': 0,
                              'zero_count': 75},
                'max_mm': 16.37388649348387,
                'mean_mm': 4.252938715036325,
                'min_mm': 0.0,
                'shape_defined': True,
                'skewness': -0.17319740171348505,
                'stddev_mm': 2.342949906403615,
                'stderr_mm': 0.11729420482703647,
                'zero_fraction': 0.1875},
 'nai_2': {'excess_kurtosis': 395.0025062656643,
           'histogram': {'bins_per_decade': 10,
                         'counts': [1],
                         'edges_mm': [19.952623149688797, 25.118864315095795],
                         'high_mm': 1000000.0,
                         'low_mm': 1e-06,
                         'overflow_count': 0,
                         'scheme': 'log10',
                         'underflow_count': 0,
                         'zero_count': 399},
           'max_mm': 20.747797092408366,
           'mean_mm': 0.051869492731020914,
           'min_mm': 0.0,
           'shape_defined': True,
           'skewness': 19.924921738006006,
           'stddev_mm': 1.0360923058266571,
           'stderr_mm': 0.051869492731020914,
           'zero_fraction': 0.9975},
 'phantom': {'excess_kurtosis': 14.776063671740136,
             'histogram': {'bins_per_decade': 10,
                           'counts': [1, 0, 0, 3, 2, 5, 2, 11, 21, 267, 44, 11, 6, 1, 0, 1],
                           'edges_mm': [10.0,
                                        12.589254117941675,
                                        15.848931924611133,
                                        19.952623149688797,
                                        25.118864315095795,
                                        31.622776601683793,
                                        39.810717055349734,
                                        50.11872336272722,
                                        63.09573444801933,
                                        79.43282347242814,
                                        100.0,
                                        125.89254117941675,
                                        158.48931924611142,
                                        199.52623149688787,
                                        251.18864315095797,
                                        316.22776601683796,
                                        398.1071705534973],
                           'high_mm': 1000000.0,
                           'low_mm': 1e-06,
                           'overflow_count': 0,
                           'scheme': 'log10',
                           'underflow_count': 0,
                           'zero_count': 25},
             'max_mm': 365.9529215430629,
             'mean_mm': 83.86605444354059,
             'min_mm': 0.0,
             'shape_defined': True,
             'skewness': 0.9887376845004086,
             'stddev_mm': 33.013685384899745,
             'stderr_mm': 1.6527515014504524,
             'zero_fraction': 0.0625}}
ASSEMBLY_VOLUME_SECONDARIES = {'cell_1_1_0': {'dispersion_index': 1.1078571428571429,
                'excess_kurtosis': 39.0947601036082,
                'histogram': {'counts': [387, 12, 1],
                              'edges': [0, 1, 2, 3],
                              'exact_below': 16,
                              'overflow_at': 2147483648,
                              'overflow_count': 0,
                              'scheme': 'integer_then_log2'},
                'max': 2.0,
                'mean': 0.035,
                'min': 0.0,
                'shape_defined': True,
                'skewness': 6.00966308102091,
                'stddev': 0.1969136866751522,
                'stderr': 0.009858014563177494,
                'zero_fraction': 0.9675},
 'nai_2': {'dispersion_index': None,
           'excess_kurtosis': None,
           'histogram': {'counts': [400],
                         'edges': [0, 1],
                         'exact_below': 16,
                         'overflow_at': 2147483648,
                         'overflow_count': 0,
                         'scheme': 'integer_then_log2'},
           'max': 0.0,
           'mean': 0.0,
           'min': 0.0,
           'shape_defined': False,
           'skewness': None,
           'stddev': 0.0,
           'stderr': 0.0,
           'zero_fraction': 1.0},
 'phantom': {'dispersion_index': 2.0747118959107804,
             'excess_kurtosis': 24.155308623362973,
             'histogram': {'counts': [236, 111, 28, 13, 8, 2, 0, 0, 0, 0, 1, 1],
                           'edges': [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
                           'exact_below': 16,
                           'overflow_at': 2147483648,
                           'overflow_count': 0,
                           'scheme': 'integer_then_log2'},
             'max': 11.0,
             'mean': 0.6725,
             'min': 0.0,
             'shape_defined': True,
             'skewness': 3.8399224915663,
             'stddev': 1.18120436419783,
             'stderr': 0.059134182194052524,
             'zero_fraction': 0.59}}
ASSEMBLY_SYSTEM_SHAPE = {'system_event_secondaries_max': 11.0,
 'system_event_secondaries_mean': 0.8875,
 'system_event_track_length_max_mm': 659.2176071465806,
 'system_event_track_length_mean_mm': 362.95962558598933}

# Same run's created-secondary species split per volume (mean, max, zero fraction;
# unlisted species are absent: mean 0, max 0, zero fraction 1) and event species means.
ASSEMBLY_VOLUME_SPECIES = {
    "phantom": {"electron": (0.655, 11.0, 0.59), "gamma": (0.0175, 1.0, 0.9825)},
    "cell_1_1_0": {"electron": (0.035, 2.0, 0.9675)},
    "nai_2": {},
}
ASSEMBLY_SYSTEM_SPECIES_MEAN = {"gamma": 0.0275, "electron": 0.86}


# Same run's deposit (MeV) and step length (mm) per volume split by the stepping
# particle's class (mean, max, zero fraction; unlisted classes are all-zero).
ASSEMBLY_VOLUME_EDEP_CLASSES = {
    "phantom": {"electron": (0.2846428542845808, 1.2042516257008673, 0.585),
                "gamma": (6.884316412098597e-06, 0.000538, 0.985)},
    "cell_1_1_0": {"electron": (0.013444150073091814, 0.8050931701822427, 0.96)},
    "nai_2": {},
}
ASSEMBLY_VOLUME_LENGTH_CLASSES = {
    "phantom": {"electron": (1.1205369872317086, 5.001147305190997, 0.585),
                "gamma": (82.74551745630885, 361.5187125683258, 0.0625)},
    "cell_1_1_0": {"electron": (0.05119978716012996, 3.3761274312868115, 0.96),
                   "gamma": (4.201738927876195, 13.493916975899179, 0.19)},
    "nai_2": {"gamma": (0.051869492731020914, 20.747797092408366, 0.9975)},
}


def class_split(present, unit):
    keys = (f"mean_{unit}", f"max_{unit}", "zero_fraction")
    return {sp: dict(zip(keys, present.get(sp, (0.0, 0.0, 1.0)))) for sp in SECONDARY_SPECIES}


def species_split(present):
    return {sp: dict(zip(("mean", "max", "zero_fraction"), present.get(sp, (0.0, 0.0, 1.0))))
            for sp in SECONDARY_SPECIES}


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
    # Same run's per-volume fixed-grid histograms (first populated log bin, counts, zeros).
    for volume, (first, counts, zeros) in ASSEMBLY_VOLUME_HISTOGRAMS.items():
        shapes[volume]["histogram"] = log_histogram("mev", first, counts, zeros)
        shapes[volume]["species"] = class_split(ASSEMBLY_VOLUME_EDEP_CLASSES[volume], "mev")
    lengths = copy.deepcopy(ASSEMBLY_VOLUME_TRACK_LENGTH)
    for volume, entry in lengths.items():
        entry["species"] = class_split(ASSEMBLY_VOLUME_LENGTH_CLASSES[volume], "mm")
    return {
        "system_event_count": n,
        "total_edep_mev": 147.96084282462908,
        "system_event_edep_max_mev": 1.25,
        "volume_edep_mev": {"phantom": 113.85989544039718, "cell_1_1_0": 5.3776600292367265,
                            "nai_2": 0.0},
        "volume_event_edep": shapes,
        "volume_event_track_length": lengths,
        "volume_event_secondaries": {
            volume: dict(copy.deepcopy(entry), species=species_split(
                ASSEMBLY_VOLUME_SPECIES[volume]))
            for volume, entry in ASSEMBLY_VOLUME_SECONDARIES.items()},
        **ASSEMBLY_SYSTEM_SHAPE,
        **{f"system_event_secondaries_{sp}_mean": ASSEMBLY_SYSTEM_SPECIES_MEAN.get(sp, 0.0)
           for sp in SECONDARY_SPECIES},
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

        def corrupt_block(block, volume, **fields):
            scores = assembly_scores()
            scores[block][volume].update(fields)
            return scores

        def corrupt_histogram(volume, **fields):
            scores = assembly_scores()
            scores["volume_event_edep"][volume]["histogram"].update(fields)
            return scores

        no_histogram = assembly_scores()
        del no_histogram["volume_event_edep"]["cell_1_1_0"]["histogram"]
        missing_volume = assembly_scores()
        del missing_volume["volume_event_edep"]["nai_2"]
        extra_volume = assembly_scores()
        extra_volume["volume_event_edep"]["ghost"] = dict(
            extra_volume["volume_event_edep"]["nai_2"])
        without_length = assembly_scores()
        del without_length["volume_event_track_length"]["phantom"]
        without_secondaries = assembly_scores()
        del without_secondaries["volume_event_secondaries"]["cell_1_1_0"]
        without_species = assembly_scores()
        del without_species["volume_event_secondaries"]["phantom"]["species"]["neutron"]

        def species_corrupt(volume, species, **fields):
            scores = assembly_scores()
            scores["volume_event_secondaries"][volume]["species"][species].update(fields)
            return scores

        def class_corrupt(block, volume, species, **fields):
            scores = assembly_scores()
            scores[block][volume]["species"][species].update(fields)
            return scores

        without_edep_class = assembly_scores()
        del without_edep_class["volume_event_edep"]["cell_1_1_0"]["species"]["positron"]
        without_length_classes = assembly_scores()
        del without_length_classes["volume_event_track_length"]["nai_2"]["species"]

        cell_overflow = assembly_scores()
        cell_overflow["volume_event_secondaries"]["cell_1_1_0"]["histogram"][
            "overflow_count"] = 1
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
            "phantom:histogram_counts_every_event": corrupt_histogram(
                "phantom", zero_count=233),
            "cell_1_1_0:histogram_zero_count_matches_fraction": corrupt_histogram(
                "cell_1_1_0", zero_count=383, underflow_count=1),
            "phantom:histogram_max_in_last_bin": corrupt("phantom", max_mev=0.9),
            "phantom:histogram_edges_on_fixed_grid": corrupt_histogram(
                "phantom", edges_mev=[e * 1.01 for e in assembly_scores()["volume_event_edep"][
                    "phantom"]["histogram"]["edges_mev"]]),
            "nai_2:histogram_scheme": corrupt_histogram("nai_2", scheme="linear"),
            "cell_1_1_0:histogram_present": no_histogram,
            "same_volume_set": extra_volume,
            "nai_2:missing": missing_volume,
            "phantom:track_length_present": without_length,
            "cell_1_1_0:secondaries_present": without_secondaries,
            "phantom:track_length_within_event_maximum": corrupt_block(
                "volume_event_track_length", "phantom", max_mm=700.0),
            "cell_1_1_0:track_length_non_negative": corrupt_block(
                "volume_event_track_length", "cell_1_1_0", min_mm=-1.0),
            "phantom:track_length_histogram_mean_within_bin_edges": corrupt_block(
                "volume_event_track_length", "phantom", mean_mm=200.0),
            "cell_1_1_0:track_length_histogram_zero_count_matches_fraction": corrupt_block(
                "volume_event_track_length", "cell_1_1_0", zero_fraction=0.2),
            "phantom:secondaries_count_valued": corrupt_block(
                "volume_event_secondaries", "phantom", mean=0.67251),
            "phantom:secondaries_within_event_maximum": corrupt_block(
                "volume_event_secondaries", "phantom", max=12.0),
            "cell_1_1_0:secondaries_histogram_counts_every_event": cell_overflow,
            "secondaries_need_steps": corrupt_block(
                "volume_event_secondaries", "nai_2", zero_fraction=0.99),
            "track_length_volumes_within_total": corrupt(
                total={"system_event_track_length_mean_mm": 80.0}),
            "secondaries_volumes_within_total": corrupt(
                total={"system_event_secondaries_mean": 0.7}),
            "phantom:species_present": without_species,
            "phantom:species_sum_to_total": species_corrupt("phantom", "gamma", mean=0.02),
            "cell_1_1_0:species_count_valued": species_corrupt(
                "cell_1_1_0", "electron", max=1.5),
            "phantom:species_within_volume": species_corrupt("phantom", "gamma", max=12.0),
            "species_volumes_within_total": corrupt(
                total={"system_event_secondaries_gamma_mean": 0.01}),
            "cell_1_1_0:edep_species_present": without_edep_class,
            "nai_2:track_length_species_present": without_length_classes,
            "edep_species_sum_to_total": class_corrupt(
                "volume_event_edep", "phantom", "gamma", mean_mev=0.001),
            "edep_species_non_negative": class_corrupt(
                "volume_event_edep", "cell_1_1_0", "gamma", mean_mev=-0.01),
            "edep_species_within_volume": class_corrupt(
                "volume_event_edep", "phantom", "gamma", max_mev=1.3),
            "track_length_species_sum_to_total": class_corrupt(
                "volume_event_track_length", "cell_1_1_0", "gamma", mean_mm=4.0),
            "track_length_species_within_volume": class_corrupt(
                "volume_event_track_length", "nai_2", "gamma", zero_fraction=0.99),
            "edep_species_need_steps": class_corrupt(
                "volume_event_track_length", "cell_1_1_0", "electron", zero_fraction=0.97),
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
# Same run's summed event track length: 9 bins from log bin 77 (50.1 mm) to 398 mm.
BEER_LAMBERT_TRACK_LENGTH_FIRST_BIN = 77
BEER_LAMBERT_TRACK_LENGTH_COUNTS = [52, 108, 150, 105, 395, 13526, 5240, 421, 3]


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
    # Species split: every secondary is an electron, so the electron histogram
    # equals the total and every other species sits in the zero bin.
    species = {}
    for sp in SECONDARY_SPECIES:
        species[f"system_event_secondaries_{sp}_histogram"] = (
            copy.deepcopy(secondaries) if sp == "electron" else {
                "scheme": "integer_then_log2", "exact_below": 16, "overflow_at": 2147483648,
                "overflow_count": 0, "edges": [0, 1], "counts": [20000]})
    return beer_lambert_scores(
        **species,
        system_event_edep_mean_mev=0.01255729210032839,
        system_event_edep_min_mev=0.0,
        system_event_edep_max_mev=0.1,
        system_event_edep_zero_fraction=0.4322,
        system_event_edep_histogram=edep,
        system_event_secondaries_histogram=secondaries,
        system_event_track_length_histogram=log_histogram(
            "mm", BEER_LAMBERT_TRACK_LENGTH_FIRST_BIN, BEER_LAMBERT_TRACK_LENGTH_COUNTS, 0),
    )


def evaluate_histograms(scores, provenance=None):
    ctx = RunContext()
    ctx.runs[RUN_ANALYTIC_BEER_LAMBERT] = RunOutputs(
        directory=Path("."), scores=scores, provenance=provenance or [])
    return SystemEventHistogramConsistent().evaluate(ctx)


def run_end_copy(scores):
    return [{"phase": "run_start"},
            {"phase": "run_end",
             **{key: copy.deepcopy(value) for key, value in scores.items()
                if key.endswith("_histogram")}}]


class EventHistogramCaseTests(unittest.TestCase):
    def test_recorded_run_passes(self):
        scores = histogram_scores()
        result = evaluate_histograms(scores, run_end_copy(scores))
        self.assertEqual(result.status, "pass", result.summary)
        self.assertIn("fullest [0.02512, 0.03162) MeV x1874", result.summary)
        self.assertIn("species with non-zero bins: electron", result.summary)

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
        def corrupt(edep=None, secondaries=None, length=None, **top):
            scores = histogram_scores()
            scores["system_event_edep_histogram"].update(edep or {})
            scores["system_event_track_length_histogram"].update(length or {})
            scores["system_event_secondaries_histogram"].update(secondaries or {})
            scores.update(top)
            return scores

        edep_counts = list(BEER_LAMBERT_EDEP_COUNTS)
        edep_counts[10] += 1
        shifted_edges = [e * 1.01 for e in histogram_scores()["system_event_edep_histogram"][
            "edges_mev"]]
        without_track_length = histogram_scores()
        del without_track_length["system_event_track_length_histogram"]
        sec_counts = list(BEER_LAMBERT_SECONDARY_COUNTS)
        sec_counts[0] -= 1
        sec_counts[1] += 1
        sec_shift = list(BEER_LAMBERT_SECONDARY_COUNTS)
        sec_shift[1] -= 4000
        sec_shift[3] += 4000
        without_gamma = histogram_scores()
        del without_gamma["system_event_secondaries_gamma_histogram"]
        electron_extra = copy.deepcopy(histogram_scores()["system_event_secondaries_histogram"])
        electron_extra["overflow_count"] = 1
        gamma_short_zero = {
            "scheme": "integer_then_log2", "exact_below": 16, "overflow_at": 2147483648,
            "overflow_count": 0, "edges": [0, 1, 2], "counts": [100, 19900]}
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
            "track_length_scheme": corrupt(length={"low_mm": 1e-3}),
            "track_length_counts_every_event": corrupt(length={"overflow_count": 1}),
            "track_length_zero_count_matches_fraction": corrupt(length={
                "zero_count": 3, "counts": BEER_LAMBERT_TRACK_LENGTH_COUNTS[:-1] + [0]}),
            "track_length_max_in_last_bin": corrupt(system_event_track_length_max_mm=420.0),
            "track_length_min_in_first_bin": corrupt(system_event_track_length_min_mm=40.0),
            "track_length_mean_within_bin_edges": corrupt(
                system_event_track_length_mean_mm=320.0),
            "track_length_histogram_present": without_track_length,
            "species_gamma_histogram_present": without_gamma,
            "species_electron_counts_every_event": corrupt(
                system_event_secondaries_electron_histogram=electron_extra),
            "species_electron_mean_within_bin_edges": corrupt(
                system_event_secondaries_electron_mean=1.5),
            "species_electron_extremes_in_end_bins": corrupt(
                system_event_secondaries_electron_max=12.0),
            "species_positron_zero_bin_matches_fraction": corrupt(
                system_event_secondaries_positron_zero_fraction=0.9),
            "species_zero_bins_cover_total_zero": corrupt(
                system_event_secondaries_gamma_histogram=gamma_short_zero),
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
        provenance = run_end_copy(scores)
        provenance[1]["system_event_track_length_histogram"]["counts"][0] += 1
        result = evaluate_histograms(scores, provenance)
        self.assertEqual(result.status, "fail")
        self.assertIn("provenance_copy_verbatim", result.summary)
        provenance = run_end_copy(scores)
        del provenance[1]["system_event_secondaries_neutron_histogram"]
        result = evaluate_histograms(scores, provenance)
        self.assertEqual(result.status, "fail")
        self.assertIn("provenance_copy_verbatim", result.summary)


if __name__ == "__main__":
    unittest.main()
