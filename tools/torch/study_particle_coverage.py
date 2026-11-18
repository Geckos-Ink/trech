"""Harvest whole Geant4 runs between the discrete CHNO observer training conditions.

Each block stratifies photon energy and path length separately for every composition.
Blocks and splits have independent seeds. Fit, selection and test use disjoint
composition inventories. Run the test split after freezing the candidate model.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from build_particle_observer_models import ROOT, INPUTS, TRAIN_MATERIALS, EXTRA_TRAIN_MATERIALS, harvest, lower_features


PANELS = {
    "train": {**TRAIN_MATERIALS, **EXTRA_TRAIN_MATERIALS},
    "selection": {"propanol_proxy": {"C": 3, "H": 8, "O": 1},
                  "formamide_proxy": {"C": 1, "H": 3, "N": 1, "O": 1}},
    "test": {"propylene_glycol_proxy": {"C": 3, "H": 8, "O": 2},
             "alanine_proxy": {"C": 3, "H": 7, "N": 1, "O": 2},
             "heptane_proxy": {"C": 7, "H": 16}},
    "targeted": {**TRAIN_MATERIALS, **EXTRA_TRAIN_MATERIALS},
    "calibration": {"ethylene_glycol_proxy": {"C": 2, "H": 6, "O": 2},
                    "butanol_proxy": {"C": 4, "H": 10, "O": 1},
                    "ethanolamine_proxy": {"C": 2, "H": 7, "N": 1, "O": 1}},
}


def conditions(split, block, n=4):
    index = list(PANELS).index(split)
    rng = np.random.default_rng(np.random.SeedSequence([20261118, index, block]))
    for material, counts in PANELS[split].items():
        energies = 10 + 20 * (rng.permutation(n) + rng.random(n)) / n
        lengths = .25 + 8.75 * (rng.permutation(n) + rng.random(n)) / n
        for j, (energy, length) in enumerate(zip(energies, lengths)):
            yield {"id": f"{split}_{block:04d}_{material}_{j}", "split": split,
                   "material": material, "counts": counts, "energy_kev": float(energy),
                   "half_length_mm": float(length), "seed": int(rng.integers(1, 2**31))}


def choose_targets(meta, density_rows, block):
    from study_particle_observer import coverage_flags

    if meta["input_features"] != INPUTS:
        raise ValueError("Incompatible observer layout")
    candidates = list(conditions("targeted", block, n=48))
    accepted, audit = [], []
    density = {r["material"]: r["molecules_per_cm3"] for r in density_rows}
    for name, counts in PANELS["targeted"].items():
        cases = [row for row in candidates if row["material"] == name]
        x = np.array([lower_features(counts, r["energy_kev"], density[name], r["half_length_mm"]) for r in cases])
        z, distance, out, starved, joint = coverage_flags(meta, x)
        priority = 2 * out.astype(int) + starved.sum(1) + joint.astype(int)
        novelty = distance.copy()
        for _ in range(4):
            i = max(range(len(cases)), key=lambda k: (priority[k], novelty[k]))
            accepted.append(cases[i])
            audit.append({"id": cases[i]["id"], "old_joint_distance": float(distance[i]),
                          "old_in_domain": bool(not out[i]), "old_joint_starved": bool(joint[i]),
                          "old_starved_inputs": [column for column, missing in zip(INPUTS, starved[i]) if missing]})
            # Avoid selecting the same local gap repeatedly.
            novelty = np.minimum(novelty, np.linalg.norm(z - z[i], axis=1))
            redundant = novelty <= meta["input_domain"]["joint"]["radius"] / 2
            priority[redundant] = 0
            priority[i] = -1
    return accepted, audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--split", choices=PANELS, required=True)
    parser.add_argument("--block", type=int, required=True)
    parser.add_argument("--events", type=int, required=True)
    parser.add_argument("--focus", type=Path, help="measured observer manifest for targeted sampling")
    parser.add_argument("--density-rows", type=Path, help="existing Geant4 labels for training-material densities")
    args = parser.parse_args()
    if args.events <= 0 or args.block < 0:
        parser.error("events must be positive and block nonnegative")
    masses = json.loads((ROOT / "data/particle_molecule/reference.json").read_text())["atomic_masses"]
    if args.split == "targeted":
        if not args.focus or not args.density_rows:
            parser.error("targeted sampling requires --focus and --density-rows")
        focus = args.focus.read_bytes()
        prior = json.loads(args.density_rows.read_text())
        selected, audit = choose_targets(json.loads(focus), prior, args.block)
        args.work.mkdir(parents=True, exist_ok=True)
        plan = {"checkpoint_manifest_sha256": hashlib.sha256(focus).hexdigest(),
                "events": args.events, "cases": selected, "prior_coverage": audit}
        (args.work / f"target_plan_{args.block:04d}.json").write_text(json.dumps(plan, indent=2) + "\n")
    else:
        selected = conditions(args.split, args.block)
    rows = [harvest(args.binary.resolve(), args.work, case, args.events, masses) for case in selected]
    result = args.work / f"{args.split}_{args.block:04d}.json"
    temp = result.with_suffix(".tmp")
    temp.write_text(json.dumps(rows, allow_nan=False) + "\n")
    temp.replace(result)


if __name__ == "__main__":
    main()
