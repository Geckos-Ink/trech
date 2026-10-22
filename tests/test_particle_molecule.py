#!/usr/bin/env python3
"""Offline held-out particle -> atom -> molecule model gates (stdlib only)."""
import hashlib
import json
import math
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/particle_molecule"


def predict(model, raw):
    x = [(v - mean) / std for v, mean, std in
         zip(raw, model["input_mean"], model["input_std"])]
    for layer in model.get("network", model)["layers"]:
        x = [b + sum(a * v for a, v in zip(row, x)) for row, b in zip(layer["weights"], layer["bias"])]
    y = [value * std + mean for value, std, mean in
         zip(x, model["output_std"], model["output_mean"])]
    return [math.exp(v) if transform == "exp" else v for v, transform in
            zip(y, model.get("output_transforms", ["identity"] * len(y)))]


def atom_input(reference, element, energy):
    t = 2 * math.log(energy / reference["energy_min_ev"]) / math.log(
        reference["energy_max_ev"] / reference["energy_min_ev"]) - 1
    basis = [1., t]
    for k in range(2, reference["basis_order"] + 1):
        basis.append(2 * t * basis[k - 1] - basis[k - 2])
    return [v if el == element else 0. for el in reference["elements"] for v in basis]


class ParticleMoleculeTests(unittest.TestCase):
    def test_independent_energy_and_whole_molecule_holdouts(self):
        ref = json.loads((DATA / "reference.json").read_text())
        atomic = json.loads((DATA / "atomic_response.json").read_text())
        molecular = json.loads((DATA / "molecular_response.json").read_text())
        energies = ref["heldout"]["ethane"]["energies_ev"]
        for filename, model in [("atomic_response.json", atomic), ("molecular_response.json", molecular)]:
            self.assertEqual(hashlib.sha256((DATA / filename).read_bytes()).hexdigest(), ref["model_sha256"][filename])
            self.assertTrue(model["note"]["geant4_trained"])
            self.assertFalse(model["note"]["measured"])
            self.assertFalse(model["note"]["mc_sampled"])
            self.assertTrue(model["input_domain"]["joint"]["centers"])
        for el in ref["elements"]:
            for energy, truth in zip(energies, ref["atomic_heldout"][el]):
                inferred = predict(atomic, atom_input(ref, el, energy))
                self.assertLess(max(abs(a - b) / b for a, b in zip(inferred, truth)), .03)
        training = json.loads((DATA / "training.json").read_text())
        self.assertFalse(set(energies) & set(training["energies_ev"]))
        for name, held in ref["heldout"].items():
            molecule = json.loads((ROOT / f"data/molecular_series/{name}.reference.json").read_text())
            counts = molecule["counts"]
            self.assertNotIn(counts, molecular["trained_from"]["training_compositions"])
            for energy, truth in zip(held["energies_ev"], held["sigma_barn"]):
                pooled = [sigma * counts.get(el, 0) for el in ref["elements"]
                          for sigma in predict(atomic, atom_input(ref, el, energy))]
                inferred = predict(molecular, pooled)
                self.assertTrue(all(v > 0 for v in inferred))
                self.assertLess(max(abs(a - b) / b for a, b in zip(inferred, truth)), .03)


if __name__ == "__main__":
    unittest.main()
