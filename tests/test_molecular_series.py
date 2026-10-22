#!/usr/bin/env python3
"""Offline electronic-reference and PubChem atom-identity regression gates."""
import copy
import hashlib
import json
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/pubchem"))
from trech_pubchem import parse_conformer


class PubChemConformerTests(unittest.TestCase):
    def setUp(self):
        self.payload = {"PC_Compounds": [{"id": {"id": {"cid": 1}},
            "atoms": {"aid": [4, 9], "element": [8, 1]},
            "bonds": {"aid1": [4], "aid2": [9], "order": [1]},
            "coords": [{"type": [2], "aid": [9, 4],
                        "conformers": [{"x": [1, 0], "y": [0, 0], "z": [0, 0]}]}]}]}

    def test_coordinate_ids_join_to_atoms(self):
        parsed = parse_conformer(self.payload)
        self.assertEqual(parsed["positions_angstrom"], [[0, 0, 0], [1, 0, 0]])
        self.assertEqual(parsed["bonds"], [[0, 1, 1]])
        self.assertIsNone(parsed["mmff94_charges_e"])

    def test_missing_or_corrupt_3d_rejected(self):
        for edit in (lambda p: p.update(coords=[]),
                     lambda p: p["coords"][0].update(aid=[4, 4]),
                     lambda p: p["coords"][0]["conformers"][0].update(z=[math.nan, 0])):
            payload = copy.deepcopy(self.payload)
            edit(payload["PC_Compounds"][0])
            with self.assertRaises(ValueError):
                parse_conformer(payload)

    def test_sparse_mmff_charges_only_when_present(self):
        compound = self.payload["PC_Compounds"][0]
        prop = {"urn": {"label": "Charge", "name": "MMFF94 Partial"},
                "value": {"slist": ["1", "4 -0.5"]}}
        compound["props"] = [prop]
        self.assertEqual(parse_conformer(self.payload)["mmff94_charges_e"], [-0.5, 0])
        prop["value"]["slist"][0] = "2"
        with self.assertRaises(ValueError):
            parse_conformer(self.payload)


class QuantumInterpolationTests(unittest.TestCase):
    def test_independent_angles_error_and_charge_budget(self):
        barriers = {}
        for name in ("ethane", "ethanol", "formamide", "butane", "dimethyl_ether", "acetamide"):
            with self.subTest(molecule=name):
                root = ROOT / "data/molecular_series"
                model = json.loads((root / f"{name}.json").read_text())
                ref = json.loads((root / f"{name}.reference.json").read_text())
                self.assertEqual(hashlib.sha256((root / f"{name}.json").read_bytes()).hexdigest(),
                                 ref["model_sha256"])
                self.assertFalse(model["note"]["measured"])
                self.assertFalse(model["note"]["geant4_trained"])
                train = [r for r in ref["rows"] if r["split"] == "train"]
                held = [r for r in ref["rows"] if r["split"] == "holdout"]
                self.assertEqual(len(held), 24)
                self.assertFalse({r["angle_deg"] for r in train} & {r["angle_deg"] for r in held})
                zero = min(r["energy_hartree"] for r in train)
                squared_errors = []
                for row in held:
                    angle = math.radians(row["angle_deg"])
                    raw = [ref["neutral_electrons"]] + [v for k in range(1, ref["fourier_order"] + 1)
                          for v in (math.cos(k * angle), math.sin(k * angle))]
                    x = [(v - mean) / std for v, mean, std in
                         zip(raw, model["input_mean"], model["input_std"])]
                    layer = model["layers"][0]
                    y = [bias + sum(w * v for w, v in zip(weights, x))
                         for weights, bias in zip(layer["weights"], layer["bias"])]
                    expected = (row["energy_hartree"] - zero) * 627.509474
                    squared_errors.append((y[0] - expected) ** 2)
                    self.assertLess(abs(sum(y[1:])), 1e-7)
                    self.assertLess(max(abs(a - b) for a, b in zip(y[1:], row["charges_e"])), 0.001)
                rmse = math.sqrt(sum(squared_errors) / len(held))
                self.assertLess(rmse, 0.01)  # interpolation fidelity, NOT physical accuracy
                self.assertAlmostEqual(rmse, ref["validation"]["energy_holdout_rmse_kcal_mol"], places=8)
                barriers[name] = ref["validation"]["rigid_barrier_kcal_mol"]
                pc = json.loads((root / f"{name}.pubchem.json").read_text())
                self.assertEqual(sorted(pc["atomic_numbers"]), sorted(ref["atomic_numbers"]))
                self.assertTrue(ref["validation"]["pubchem"]["topology_match"])
                self.assertLess(ref["validation"]["pubchem"]["bond_length_mae_angstrom"], 0.03)
        self.assertGreater(barriers["formamide"], 3 * barriers["ethane"])


if __name__ == "__main__":
    unittest.main()
