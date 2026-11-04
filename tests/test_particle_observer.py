#!/usr/bin/env python3
"""Offline whole-material/energy/geometry MC observer gates; standard library only."""
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import unittest
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/particle_observer"


def predict(model, raw):
    values = [(value - mean) / std for value, mean, std in
              zip(raw, model["input_mean"], model["input_std"])]
    for layer in model["network"]["layers"]:
        values = [bias + sum(weight * value for weight, value in zip(weights, values))
                  for weights, bias in zip(layer["weights"], layer["bias"])]
        if layer["activation"] == "silu":
            values = [value / (1 + math.exp(-value)) for value in values]
    encoded = [value * std + mean for value, std, mean in
               zip(values, model["output_std"], model["output_mean"])]
    return [1 / (1 + math.exp(-value)) for value in encoded]


def composition_signature(counts):
    divisor = math.gcd(*counts.values())
    return tuple((symbol, count // divisor) for symbol, count in sorted(counts.items()))


class ParticleObserverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((DATA / "manifest.json").read_text())
        cls.model = json.loads((DATA / "observer_response.json").read_text())
        cls.data = json.loads((DATA / "rows.json").read_text())

    def test_byte_identity_and_actual_mc_labels(self):
        self.assertEqual(hashlib.sha256((DATA / "observer_response.json").read_bytes()).hexdigest(),
                         self.manifest["model_sha256"])
        self.assertEqual(hashlib.sha256((DATA / "rows.json").read_bytes()).hexdigest(),
                         self.manifest["rows_sha256"])
        for filename, expected in self.manifest["lower_model_sha256"].items():
            self.assertEqual(hashlib.sha256((ROOT / "data/particle_molecule" / filename).read_bytes()).hexdigest(), expected)
        # Calibration metrics are added only after freezing/opening the test.
        frozen = dict(self.model)
        del frozen["holdout"]
        if "post_test_band_metadata_correction" in self.manifest:
            frozen["trained_scale_bands"] = self.manifest["post_test_band_metadata_correction"]["original_bands"]
        self.assertEqual(hashlib.sha256((json.dumps(frozen, indent=2) + "\n").encode()).hexdigest(),
                         self.manifest["frozen_before_test_sha256"])
        self.assertTrue(self.model["note"]["geant4_trained"])
        self.assertTrue(self.model["note"]["mc_sampled"])
        self.assertFalse(self.model["note"]["measured"])
        self.assertEqual(self.model["output_transforms"], ["sigmoid", "sigmoid"])
        self.assertEqual(self.model["trained_scale_bands"], ["meso"])
        for row in self.data["rows"]:
            label = row["labels"]
            self.assertEqual(label["primaries_emitted"], row["events"])
            self.assertEqual(label["uncollided_fraction"], label["primaries_uncollided"] / row["events"])
            self.assertTrue(0 <= label["deposited_energy_fraction"] <= 1)
            self.assertAlmostEqual(row["inputs"][3], row["molecules_per_cm3"] * row["path_length_mm"] * 1e-25)
            self.assertEqual(row["inputs"][4], row["energy_kev"])
            self.assertEqual(row["source"]["physics_list"], "QBBC_LIV")
            self.assertTrue(row["source"]["geant4_version"])
            for name in ["script_sha256", "scores_sha256", "provenance_sha256"]:
                self.assertEqual(len(row["source"][name]), 64)

    def test_split_has_no_material_energy_or_geometry_leakage(self):
        train = [row for row in self.data["rows"] if row["split"] == "train"]
        test = [row for row in self.data["rows"] if row["split"] == "test"]
        campaign = self.manifest.get("campaign", 1)
        self.assertEqual(len(train), 192 if campaign == 2 else 96)
        self.assertEqual(len(test), 18 if campaign == 2 else 12)
        for key in ["energy_kev", "half_length_mm"]:
            self.assertFalse({row[key] for row in train} & {row[key] for row in test})
        self.assertFalse({composition_signature(row["counts"]) for row in train} &
                         {composition_signature(row["counts"]) for row in test})
        expected = {"hexane", "acetone", "urea"} if campaign == 2 else {"butane", "dimethyl_ether", "acetamide"}
        self.assertEqual({row["material"] for row in test}, expected)
        self.assertEqual(self.model["trained_from"]["training_only_validation_runs"], 0 if campaign == 2 else 16)
        if campaign == 2:
            development = [row for row in self.data["rows"] if row["split"] == "development"]
            self.assertEqual(len(development), 12)
            self.assertFalse({composition_signature(row["counts"]) for row in development} &
                             {composition_signature(row["counts"]) for row in test})
            for key in ["energy_kev", "half_length_mm"]:
                self.assertFalse({row[key] for row in development} & {row[key] for row in test})
        self.assertGreater(self.model["trained_from"]["selected_epochs"], 0)

    def test_untouched_observer_cases_report_unchanged_noise_gates(self):
        names = self.data["output_features"]
        test = [row for row in self.data["rows"] if row["split"] == "test"]
        train = [row for row in self.data["rows"] if row["split"] == "train"]
        squared = [0., 0.]
        passed = True
        for row, result in zip(test, self.manifest["test_results"]):
            self.assertEqual(row["id"], result["id"])
            inferred = predict(self.model, row["inputs"])
            p = row["labels"]["uncollided_fraction"]
            standard_errors = [math.sqrt(p * (1 - p) / row["events"]),
                               row["labels"]["deposited_energy_fraction_stddev"] / math.sqrt(row["events"])]
            thresholds = [max(.03, 5 * standard_errors[0]), max(.04, 5 * standard_errors[1])]
            for index, name in enumerate(names):
                self.assertAlmostEqual(result["standard_error"][index], standard_errors[index], places=14)
                self.assertAlmostEqual(result["tolerance"][index], thresholds[index], places=14)
                self.assertTrue(0 < inferred[index] < 1)
                self.assertAlmostEqual(inferred[index], result["prediction"][index], places=11)
                gap = abs(inferred[index] - row["labels"][name])
                squared[index] += gap ** 2
            case_pass = all(abs(inferred[index] - row["labels"][name]) <= result["tolerance"][index]
                            for index, name in enumerate(names))
            self.assertEqual(case_pass, result["pass"])
            passed &= case_pass
        for index, name in enumerate(names):
            rmse = math.sqrt(squared[index] / len(test))
            self.assertAlmostEqual(rmse, self.model["holdout"]["rmse"][name], places=11)
            train_mean = sum(row["labels"][name] for row in train) / len(train)
            baseline_rmse = math.sqrt(sum((row["labels"][name] - train_mean) ** 2 for row in test) / len(test))
            self.assertAlmostEqual(baseline_rmse, self.manifest["constant_training_mean_baseline_rmse"][name], places=11)
            self.assertLess(rmse, baseline_rmse)
        self.assertEqual(self.manifest["status"], "pass" if passed else "candidate_failed")
        # This first candidate must remain explicitly unpromoted after its
        # independent test revealed thick-volume energy-deposition errors.
        if self.manifest.get("campaign", 1) == 1:
            self.assertEqual(self.manifest["status"], "candidate_failed")
            self.assertEqual(sum(not result["pass"] for result in self.manifest["test_results"]), 3)
        else:
            self.assertEqual(self.manifest["status"], "pass")
            self.assertEqual(len(self.manifest["test_results"]), 18)
            self.assertTrue(all(result["pass"] for result in self.manifest["test_results"]))
        self.assertTrue(self.model["input_domain"]["joint"]["centers"])

    def test_first_failed_attempt_remains_auditable(self):
        path = DATA / "attempt1"
        manifest = json.loads((path / "manifest.json").read_text())
        self.assertEqual(manifest["status"], "candidate_failed")
        self.assertEqual(sum(not row["pass"] for row in manifest["test_results"]), 3)
        self.assertEqual(hashlib.sha256((path / "observer_response.json").read_bytes()).hexdigest(), manifest["model_sha256"])
        self.assertEqual(hashlib.sha256((path / "rows.json").read_bytes()).hexdigest(), manifest["rows_sha256"])


class ObserverHarvestCacheTests(unittest.TestCase):
    def test_execution_identity_rejects_legacy_changed_and_partial_inputs(self):
        spec = importlib.util.spec_from_file_location("observer_cache", ROOT / "tools/torch/particle_observer_cache.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            engine, atomic, molecular = [root / name for name in ["engine", "atomic.json", "molecular.json"]]
            engine.write_bytes(b"engine v1")
            atomic.write_bytes(b"atomic v1")
            molecular.write_bytes(b"molecular v1")
            models = {"atomic_response.json": atomic, "molecular_response.json": molecular}
            identity = module.capture_identity(b"script v1", engine, models)
            manifest = root / "cache_identity.json"
            self.assertFalse(module.cache_matches(manifest, identity), "missing legacy identity cannot be trusted")
            module.write_identity(manifest, identity)
            self.assertTrue(module.cache_matches(manifest, identity))
            self.assertFalse(module.cache_matches(manifest, module.capture_identity(b"script v2", engine, models)))
            engine.write_bytes(b"engine v2")
            self.assertFalse(module.cache_matches(manifest, module.capture_identity(b"script v1", engine, models)))
            engine.write_bytes(b"engine v1")
            for path in [atomic, molecular]:
                previous = path.read_bytes()
                path.write_bytes(previous + b" changed")
                self.assertFalse(module.cache_matches(manifest, module.capture_identity(b"script v1", engine, models)))
                path.write_bytes(previous)
            # Including every lower model is part of the cache contract.
            self.assertFalse(module.cache_matches(manifest, module.capture_identity(b"script v1", engine, {"atomic_response.json": atomic})))
            manifest.write_text("{")
            self.assertFalse(module.cache_matches(manifest, identity))
            manifest.write_text(json.dumps({"script_sha256": identity["script_sha256"]}))
            self.assertFalse(module.cache_matches(manifest, identity), "script-only legacy manifests must miss")
            source = root / "feature_builder.py"
            source.write_bytes(b"feature logic v1")
            with_source = module.capture_identity(b"script v1", engine, models, {"builder": source})
            module.write_identity(manifest, with_source)
            self.assertTrue(module.cache_matches(manifest, with_source))
            source.write_bytes(b"feature logic v2")
            self.assertFalse(module.cache_matches(manifest,
                module.capture_identity(b"script v1", engine, models, {"builder": source})))


if __name__ == "__main__":
    unittest.main()
