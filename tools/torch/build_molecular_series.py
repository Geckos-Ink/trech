#!/usr/bin/env python3
"""Build a bounded molecular comparison series; PubChem NEVER enters fitting.

Requires numpy, scipy, RDKit and PySCF (offline after PubChem cache acquisition).
RHF/STO-3G is an inexpensive quantum reference, not experimental electronic truth.
The independent MMFF-initialized scaffold is optimized with RHF analytic gradients;
subsequent scans rotate one fragment rigidly, without geometry relaxation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from rdkit import Chem, rdBase
from rdkit.Chem import AllChem, rdMolTransforms
import pyscf
from pyscf import gto, scf
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools" / "torch"))
from trech_torch.train_surrogate import input_domain, write_generic_json

SPECS = {
    "ethane": ("CC", [2, 0, 1, 5], "01 · Nonpolar / C–C rotation"),
    "ethanol": ("CCO", [0, 1, 2, 8], "02 · Polar / C–O rotation"),
    "formamide": ("NC=O", [2, 1, 0, 3], "03 · Amide / restricted C–N rotation"),
    "butane": ("CCCC", [0, 1, 2, 3], "04 · Alkane chain / central C–C rotation"),
    "dimethyl_ether": ("COC", [3, 0, 1, 2], "05 · Ether / C–O rotation"),
    "acetamide": ("CC(=O)N", [2, 1, 3, 7], "06 · Substituted amide / C–N rotation"),
}
ORDER = 6
HARTREE_KCAL = 627.509474


def features(angle, electrons, order=ORDER):
    a = np.deg2rad(angle)
    return np.array([electrons] + [v for k in range(1, order + 1)
                                  for v in (np.cos(k * a), np.sin(k * a))])


def quantum(mol, positions, gradient=False):
    system = gto.M(atom=[(a.GetSymbol(), p) for a, p in zip(mol.GetAtoms(), positions)],
                   basis="sto-3g", unit="Angstrom", verbose=0)
    solver = scf.RHF(system)
    solver.conv_tol = 1e-10
    solver.kernel()
    if not solver.converged:
        raise RuntimeError("RHF failed to converge; refusing an electronic label")
    if gradient:
        return solver.e_tot, solver.nuc_grad_method().kernel().ravel() / 0.529177210903
    _, charges = solver.mulliken_pop(verbose=0)
    return solver.e_tot, charges


def aligned_rmsd(moving, target):
    a = moving - moving.mean(axis=0)
    b = target - target.mean(axis=0)
    u, _, vt = np.linalg.svd(a.T @ b)
    correction = np.diag([1, 1, np.linalg.det(u @ vt)])
    return float(np.sqrt(np.mean(np.sum((a @ u @ correction @ vt - b) ** 2, axis=1))))


def compare_pubchem(mol, positions, charges, reference):
    other = Chem.RWMol()
    for z in reference["atomic_numbers"]:
        other.AddAtom(Chem.Atom(int(z)))
    for a, b, order in reference["bonds"]:
        other.AddBond(a, b, {1: Chem.BondType.SINGLE, 2: Chem.BondType.DOUBLE,
                              3: Chem.BondType.TRIPLE}[order])
    other = other.GetMol()
    Chem.SanitizeMol(other)
    matches = other.GetSubstructMatches(mol, uniquify=False, maxMatches=10000)
    if mol.GetNumAtoms() != other.GetNumAtoms() or not matches:
        raise ValueError("PubChem topology differs from the independent molecular graph")
    xyz = np.array(reference["positions_angstrom"])
    match = min(matches, key=lambda m: aligned_rmsd(positions, xyz[list(m)]))
    target = xyz[list(match)]
    heavy = np.array([a.GetAtomicNum() != 1 for a in mol.GetAtoms()])
    bond_errors = [abs(np.linalg.norm(positions[b.GetBeginAtomIdx()] - positions[b.GetEndAtomIdx()])
                       - np.linalg.norm(target[b.GetBeginAtomIdx()] - target[b.GetEndAtomIdx()]))
                   for b in mol.GetBonds()]
    mmff = reference["mmff94_charges_e"]
    return {"cid": reference["cid"], "topology_match": True,
            "atom_map_to_pubchem_index": list(match),
            "all_atom_rmsd_angstrom": aligned_rmsd(positions, target),
            "heavy_atom_rmsd_angstrom": aligned_rmsd(positions[heavy], target[heavy]),
            "bond_length_mae_angstrom": float(np.mean(bond_errors)),
            "charge_mae_e": None if mmff is None else float(np.mean(np.abs(charges - np.array(mmff)[list(match)]))),
            "scope": "Independent rigid-scan minimum vs PubChem default theoretical conformer; Mulliken vs MMFF94 charges are different definitions, so charge disagreement is not an accuracy score.",
            "source": reference["provenance"]}


def build(name, out, cache):
    smiles, torsion, group = SPECS[name]
    order = 10 if name == "butane" else ORDER
    mol = Chem.AddHs(Chem.MolFromSmiles(smiles))
    if AllChem.EmbedMolecule(mol, randomSeed=20261022) != 0:
        raise RuntimeError("independent conformer embedding failed")
    if AllChem.MMFFOptimizeMolecule(mol) != 0:
        raise RuntimeError("initial scaffold optimization failed")
    positions = mol.GetConformer().GetPositions()
    def objective(x):
        return quantum(mol, x.reshape(-1, 3), gradient=True)
    optimized = minimize(objective, positions.ravel(), method="L-BFGS-B", jac=True,
                         options={"gtol": 1e-5, "ftol": 1e-12, "maxiter": 120})
    if not optimized.success:
        raise RuntimeError(f"RHF geometry optimization failed: {optimized.message}")
    for i, p in enumerate(optimized.x.reshape(-1, 3)):
        mol.GetConformer().SetAtomPosition(i, p.tolist())
    electrons = sum(a.GetAtomicNum() for a in mol.GetAtoms())
    # Include each basis extremum in training so measured feature hulls include
    # the entire circle. Holdout angles are separately evaluated, never fitted.
    train = sorted(set(np.arange(0, 360, 10).tolist() +
                       [round(n * 90 / k, 8) for k in range(1, order + 1)
                        for n in range(4 * k)]))
    hold = [float(a) for a in np.arange(2.5, 360, 15)]
    assert not set(train) & set(hold)
    rows = []
    for i, angle in enumerate(train + hold):
        rdMolTransforms.SetDihedralDeg(mol.GetConformer(), *torsion, angle)
        pos = mol.GetConformer().GetPositions()
        energy, charges = quantum(mol, pos)
        if abs(sum(charges)) > 1e-7:
            raise RuntimeError("quantum charge budget is not neutral")
        rows.append({"angle_deg": angle, "energy_hartree": energy,
                     "charges_e": charges.tolist(), "positions_angstrom": pos.tolist(),
                     "split": "train" if i < len(train) else "holdout"})
    minimum = min(rows[:len(train)], key=lambda row: row["energy_hartree"])
    e0 = minimum["energy_hartree"]
    x = np.array([features(r["angle_deg"], electrons, order) for r in rows])
    y = np.array([[(r["energy_hartree"] - e0) * HARTREE_KCAL] + r["charges_e"] for r in rows])
    n = len(train)
    xm, xs = x[:n].mean(0), x[:n].std(0)
    xs[xs < 1e-9] = 1
    # Ordinary fitted periodic regression; Fourier terms are a coordinate basis,
    # not a textbook torsional potential or an authored charge-transfer law.
    design = np.column_stack([np.ones(n), (x[:n] - xm) / xs])
    coefficients = np.linalg.lstsq(design, y[:n], rcond=None)[0]
    predicted = np.column_stack([np.ones(len(hold)), (x[n:] - xm) / xs]) @ coefficients
    error = predicted - y[n:]
    outputs = ["relative_energy_kcal_mol"] + [f"charge_{i}_e" for i in range(mol.GetNumAtoms())]
    rmse = np.sqrt(np.mean(error ** 2, axis=0))
    mae = np.mean(abs(error), axis=0)
    sst = np.sum((y[n:] - y[n:].mean(0)) ** 2, axis=0)
    r2 = {key: float(1 - np.sum(error[:, j] ** 2) / sst[j])
          for j, key in enumerate(outputs) if sst[j] > 1e-8}
    model_path = out / f"{name}.json"
    notes = {"reference": "PySCF RHF/STO-3G, neutral isolated molecule, rigid unrelaxed torsion scan",
             "measured": False, "geant4_trained": False,
             "geant4_role": "live elemental identity and neutral electron-budget consistency only; transport does not determine this quantum energy surface",
             "scope": "molecule-specific fixed scaffold; not transferable to other geometries, ions, solvent or arbitrary molecules",
             "pubchem_policy": "comparison_only; never fitted", "fourier_order": order}
    write_generic_json(model_path, ["neutral_electrons"] + [f"{fn}_{k}" for k in range(1, order + 1)
                       for fn in ("cos", "sin")], outputs,
                       (xm, xs, np.zeros(y.shape[1]), np.ones(y.shape[1])),
                       [{"weights": coefficients[1:].T.tolist(), "bias": coefficients[0].tolist(), "activation": "none"}],
                       {"script": "tools/torch/build_molecular_series.py", "seed": 20261022,
                        "pyscf": pyscf.__version__, "rdkit": rdBase.rdkitVersion,
                        "train_angles_deg": train, "holdout_angles_deg": hold},
                       domain=input_domain(x[:n], (xm, xs, None, None), joint_centers=12, joint_quantile=1.0),
                       scale_bands=["atomic"], holdout={"n": len(hold), "r2_min": min(r2.values()),
                       "r2": r2, "mae": dict(zip(outputs, mae.tolist())), "rmse": dict(zip(outputs, rmse.tolist()))}, note=notes)
    # PubChem is intentionally read only AFTER the geometry, quantum labels and
    # model are fixed. Replacing the PubChem fixture cannot change their weights.
    reference = json.loads((cache / f"{name.replace('_', '-')}-3d.json").read_text())
    (out / f"{name}.pubchem.json").write_text(json.dumps(reference, indent=2) + "\n")
    comparison = compare_pubchem(mol, np.array(minimum["positions_angstrom"]),
                                np.array(minimum["charges_e"]), reference)
    validation = {"energy_holdout_rmse_kcal_mol": float(rmse[0]),
                  "charge_holdout_mae_e": float(mae[1:].mean()),
                  "rigid_barrier_kcal_mol": float(y[:n, 0].max()),
                  "pubchem": comparison, "holdout_count": len(hold), "train_count": n}
    document = {"schema": "trech_molecular_scan_v1", "name": name, "smiles": smiles,
                "group": group, "torsion_atoms": torsion,
                "elements": [a.GetSymbol() for a in mol.GetAtoms()],
                "atomic_numbers": [a.GetAtomicNum() for a in mol.GetAtoms()],
                "counts": dict(Counter(a.GetSymbol() for a in mol.GetAtoms())),
                "bonds": [[b.GetBeginAtomIdx(), b.GetEndAtomIdx()] for b in mol.GetBonds()],
                "fourier_order": order, "neutral_electrons": electrons,
                "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
                "notes": notes, "validation": validation, "rows": rows}
    (out / f"{name}.reference.json").write_text(json.dumps(document, indent=2) + "\n")
    # Shared JS fixture contains only scaffold geometry + reference comparisons.
    # Charge/energy predictions are always evaluated by the C++ runtime.
    public = {k: v for k, v in document.items() if k != "rows"}
    public["scan"] = [{"angle_deg": r["angle_deg"], "positions_angstrom": r["positions_angstrom"],
                       "reference_energy_kcal_mol": (r["energy_hartree"] - e0) * HARTREE_KCAL,
                       "reference_charges_e": r["charges_e"]} for r in rows[n:]]
    return public


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=ROOT / "build/pubchem_cache")
    parser.add_argument("--out", type=Path, default=ROOT / "data/molecular_series")
    parser.add_argument("--only", nargs="+", choices=list(SPECS), help="rebuild selected molecules, retaining other fixtures")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    series_path = args.out / "series.js"
    series = (json.loads(series_path.read_text().split(" = ", 1)[1].rstrip(";\n"))
              if args.only and series_path.exists() else {})
    for name in (args.only or SPECS):
        print(f"Building {name} independent quantum scan...", flush=True)
        series[name] = build(name, args.out, args.cache)
        print(json.dumps(series[name]["validation"], indent=2), flush=True)
    (args.out / "series.js").write_text("// Generated by tools/torch/build_molecular_series.py.\n"
                                        "globalThis.TRECH_MOLECULAR_SERIES = " + json.dumps(series) + ";\n")


if __name__ == "__main__":
    main()
