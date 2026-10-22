#!/usr/bin/env python3
"""Learn a shared CHNO atom -> molecule response from actual Geant4 interaction data.

Labels are G4EmCalculator photoelectric/Compton/Rayleigh cross sections, NOT QM,
PubChem, authored potentials or Monte Carlo event tallies. Their independent-atom
approximation does not determine ground-state polarization or torsion.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/torch"))
from trech_torch.train_surrogate import fit_linear, input_domain, write_generic_json

ELEMENTS = ["H", "C", "N", "O"]
Z = {"H": 1, "C": 6, "N": 7, "O": 8}
PROCESSES = ["phot", "compt", "Rayl"]
ORDER = 10
LOW, HIGH = 1000., 30000.
MOLECULES = ["ethane", "ethanol", "formamide", "butane", "dimethyl_ether", "acetamide"]


def feature_names():
    return [f"basis_{el}_{k}" for el in ELEMENTS for k in range(ORDER + 1)]


def atom_features(el, energy):
    t = 2 * math.log(energy / LOW) / math.log(HIGH / LOW) - 1
    basis = np.polynomial.chebyshev.chebvander(t, ORDER)[0]
    return np.array([float(value) if symbol == el else 0.
                     for symbol in ELEMENTS for value in basis])


def predict(model, x):
    value = (np.asarray(x) - np.array(model["input_mean"])) / np.array(model["input_std"])
    layers = model.get("network", model)["layers"]
    for layer in layers:
        value = value @ np.array(layer["weights"]).T + layer["bias"]
    value = value * model["output_std"] + model["output_mean"]
    return np.exp(value) if model.get("output_transforms") else value


def run_probe(binary, work, label, materials, energies):
    work.mkdir(parents=True, exist_ok=True)
    out = work / label
    if out.exists():
        shutil.rmtree(out)
    config = {"detector": {"worldSizeMm": 2, "worldMaterial": "G4_Galactic"},
              "beam": {"particle": "gamma", "energyMeV": .003, "direction": [0, 0, 1]},
              "run": {"nEvents": 1, "seed": 20261022, "threads": 1},
              "physics": {"list": "QBBC_LIV"}, "materials": materials,
              "materialProbe": {"enable": True, "materials": [m["name"] for m in materials],
                "interactions": {"particle": "gamma", "processes": PROCESSES,
                                 "energiesMeV": [float(e) / 1e6 for e in energies]}}}
    script = work / f"{label}.js"
    script.write_text("globalThis.TRECH_CONFIG = " + json.dumps(config) + ";\n")
    with (work / f"{label}.log").open("w") as log:
        subprocess.run([str(binary), "run", str(script), "--output", str(out)], cwd=ROOT,
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    scores_bytes = (out / "trech_scores.jsonl").read_bytes()
    scores = json.loads(scores_bytes.splitlines()[-1])
    provenance = json.loads((out / "trech_provenance.jsonl").read_text().splitlines()[-1])
    source = {"config_sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
              "scores_sha256": hashlib.sha256(scores_bytes).hexdigest(),
              "geant4_version": provenance["geant4_version"], "physics_list": "QBBC_LIV",
              "seed": 20261022, "kind": "Geant4 particle-interaction cross-section data; not MC tallies"}
    return {p["name"]: p for p in scores["material_probes"]}, source


def labels(probe, counts, energies):
    # Unit normalization only: mu / number density is the microscopic cross
    # section returned by Geant4. 1 barn = 1e-22 mm^2, 1 cm^3 = 1000 mm^3.
    per_molecule = [probe["numberDensityPerCm3"][el] / count for el, count in counts.items() if count]
    if max(per_molecule) / min(per_molecule) > 1.000001:
        raise RuntimeError("constructed Geant4 material does not match its stoichiometry")
    density = per_molecule[0]
    samples = probe["interactions"]
    if len(samples) != len(energies):
        raise RuntimeError("missing particle interaction labels")
    result = []
    for sample, energy in zip(samples, energies):
        if not sample["available"] or abs(sample["energy_mev"] * 1e6 - energy) > 1e-6:
            raise RuntimeError("invalid Geant4 response row")
        row = [sample["cross_sections_per_mm"][process] * 1e25 / density for process in PROCESSES]
        if not all(math.isfinite(v) and v > 0 for v in row):
            raise RuntimeError("missing/zero particle labels cannot be log-trained")
        result.append(row)
    return np.array(result)


def material(name, counts, masses):
    total = sum(masses[el] * count for el, count in counts.items())
    return {"name": name, "densityGcm3": 1,
            "components": [{"element": el, "fraction": masses[el] * count / total}
                           for el, count in counts.items() if count]}


def export(path, x, y, xh, yh, inputs, outputs, source, scale, log=False):
    targets = np.log(y) if log else y
    w, b, scalers = fit_linear(x, targets, 1e-10)
    if not log:
        # Fit relative errors per output. Absolute-error fitting lets the
        # large low-energy photoelectric values hide bad high-energy tails.
        xm, xs, _, _ = scalers
        design = np.column_stack([np.ones(len(x)), (x - xm) / xs])
        fitted = np.column_stack([np.linalg.lstsq(design / y[:, j, None],
                      np.ones(len(y)), rcond=None)[0] for j in range(y.shape[1])])
        b, w = fitted[0], fitted[1:].T
        scalers = (xm, xs, np.zeros(y.shape[1]), np.ones(y.shape[1]))
    model_stub = {"input_mean": scalers[0].tolist(), "input_std": scalers[1].tolist(),
                  "output_mean": scalers[2].tolist(), "output_std": scalers[3].tolist(),
                  "layers": [{"weights": w.tolist(), "bias": b.tolist()}]}
    if log:
        model_stub["output_transforms"] = ["exp"] * len(outputs)
    prediction = predict(model_stub, xh)
    if not np.all(prediction > 0):
        raise RuntimeError("non-positive inferred cross section")
    errors = prediction - yh
    rmse = np.sqrt(np.mean(errors ** 2, axis=0))
    relative = np.abs(errors) / yh
    r2 = 1 - np.sum(errors ** 2, axis=0) / np.sum((yh - yh.mean(0)) ** 2, axis=0)
    metrics = {"rmse": dict(zip(outputs, rmse.tolist())),
               "mae": dict(zip(outputs, np.mean(abs(errors), axis=0).tolist())),
               "r2": dict(zip(outputs, r2.tolist())), "r2_min": float(min(r2)), "n": len(yh)}
    write_generic_json(path, inputs, outputs, scalers,
                       [{"weights": w.tolist(), "bias": b.tolist(), "activation": "none"}],
                       source, domain=input_domain(x, scalers, joint_centers=48, joint_quantile=1),
                       scale_bands=[scale], holdout=metrics,
                       note={"geant4_trained": True, "measured": False,
                             "label_source": "Geant4 G4EmCalculator interaction tables",
                             "mc_sampled": False, "elements": ELEMENTS,
                             "scope": "CHNO photon response, 1-30 keV; independent-atom Geant4 approximation; not ground-state charges or torsion"},
                       output_transforms=["exp"] * len(outputs) if log else None)
    return json.loads(path.read_text()), {"relative_error_max": float(relative.max()),
             "relative_error_mean": float(relative.mean()), "holdout": metrics}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=ROOT / "build/rel/trech")
    parser.add_argument("--out", type=Path, default=ROOT / "data/particle_molecule")
    parser.add_argument("--work", type=Path, default=ROOT / "build/rel/particle_molecule_training")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    t_train = sorted(set(np.linspace(-1, 1, 41).tolist() +
                         [round(math.cos(j * math.pi / k), 12) for k in range(1, ORDER + 1) for j in range(k + 1)]))
    train_e = np.array([LOW * (HIGH / LOW) ** ((t + 1) / 2) for t in t_train])
    hold_e = np.geomspace(1010, 29700, 24)
    hold_e[np.argmin(abs(hold_e - 3000))] = 3000
    assert all(abs(a - b) > 1e-5 for a in train_e for b in hold_e)
    energies = np.concatenate([train_e, hold_e])
    n = len(train_e)
    pure = [{"name": "atom_" + el, "densityGcm3": 1,
             "components": [{"element": el, "fraction": 1}]} for el in ELEMENTS]
    probes, atom_source = run_probe(args.binary, args.work, "atomic", pure, energies)
    masses = {el: probes["atom_" + el]["elements"][0]["atomic_mass_amu"] for el in ELEMENTS}
    atom_labels = {el: labels(probes["atom_" + el], {el: 1}, energies) for el in ELEMENTS}
    x = np.array([atom_features(el, e) for el in ELEMENTS for e in train_e])
    y = np.concatenate([atom_labels[el][:n] for el in ELEMENTS])
    xh = np.array([atom_features(el, e) for el in ELEMENTS for e in hold_e])
    yh = np.concatenate([atom_labels[el][n:] for el in ELEMENTS])
    atom_model, atom_metrics = export(args.out / "atomic_response.json", x, y, xh, yh,
             feature_names(), ["set_" + p + "_barn" for p in PROCESSES],
             {"script": "tools/torch/build_particle_molecule_models.py", "source": atom_source,
              "holdout": "independent photon energies, no held-out table rows fitted"}, "atomic", log=True)
    print("Atomic stage:", atom_metrics, flush=True)

    refs = {name: json.loads((ROOT / f"data/molecular_series/{name}.reference.json").read_text()) for name in MOLECULES}
    held_counts = [r["counts"] for r in refs.values()]
    rng = np.random.default_rng(20261022)
    training_counts = []
    # Broad, independently declared compositions; all six showcased molecules
    # are excluded. The engine has no molecule-specific response branches.
    while len(training_counts) < 36:
        count = {el: int(rng.integers(0, maximum + 1))
                 for el, maximum in zip(ELEMENTS, [24, 12, 6, 8])}
        count = {el: value for el, value in count.items() if value}
        if count and count not in held_counts and count not in training_counts:
            training_counts.append(count)
    mixtures = [material(f"train_{i}", c, masses) for i, c in enumerate(training_counts)]
    mixtures += [material("held_" + name, r["counts"], masses) for name, r in refs.items()]
    mix_probes, molecule_source = run_probe(args.binary, args.work, "molecular", mixtures, energies)
    def pooled_features(counts, e):
        # Sum per-element embeddings (bookkeeping), not an authored response law.
        # The next learned stage sees contributions separately and learns how
        # Geant4 combines them; no sum-to-cross-section formula runs at inference.
        return np.concatenate([predict(atom_model, atom_features(el, e)) * counts.get(el, 0)
                               for el in ELEMENTS])
    pool_names = [f"{el}_{p}_barn" for el in ELEMENTS for p in PROCESSES]
    xs, ys, xhs, yhs = [], [], [], []
    source_rows = {}
    for i, counts in enumerate(training_counts):
        target = labels(mix_probes[f"train_{i}"], counts, energies)
        source_rows[f"train_{i}"] = {"counts": counts, "sigma_barn": target[:n].tolist()}
        for j, e in enumerate(train_e):
            xs.append(pooled_features(counts, e)); ys.append(target[j])
    runtime_refs = {}
    for name, ref in refs.items():
        target = labels(mix_probes["held_" + name], ref["counts"], energies)[n:]
        runtime_refs[name] = {"energies_ev": hold_e.tolist(), "sigma_barn": target.tolist()}
        for j, e in enumerate(hold_e):
            xhs.append(pooled_features(ref["counts"], e)); yhs.append(target[j])
    molecule_model, molecule_metrics = export(args.out / "molecular_response.json",
             np.array(xs), np.array(ys), np.array(xhs), np.array(yhs), pool_names,
             ["molecule_" + p + "_barn" for p in PROCESSES],
             {"script": "tools/torch/build_particle_molecule_models.py", "source": molecule_source,
              "holdout": "six whole molecular compositions AND independent photon energies excluded from fitting",
              "training_compositions": training_counts, "heldout_molecules": MOLECULES}, "nano")
    print("Molecular stage:", molecule_metrics, flush=True)
    if atom_metrics["relative_error_max"] > .03 or molecule_metrics["relative_error_max"] > .03:
        raise RuntimeError("particle response interpolation gate failed (3% maximum relative error)")
    summary = {"schema": "trech_particle_molecule_v1", "elements": ELEMENTS, "processes": PROCESSES,
               "atomic_numbers": Z, "atomic_masses": masses, "basis_order": ORDER,
               "energy_min_ev": LOW, "energy_max_ev": HIGH, "heldout": runtime_refs,
               "atomic_metrics": atom_metrics, "molecular_metrics": molecule_metrics,
               "atomic_heldout": {el: atom_labels[el][n:].tolist() for el in ELEMENTS},
               "atomic_source": atom_source, "molecular_source": molecule_source,
               "model_sha256": {p: hashlib.sha256((args.out / p).read_bytes()).hexdigest()
                                for p in ("atomic_response.json", "molecular_response.json")}}
    (args.out / "reference.json").write_text(json.dumps(summary, indent=2) + "\n")
    (args.out / "training.json").write_text(json.dumps({"energies_ev": train_e.tolist(),
                  "atomic_labels": {el: atom_labels[el][:n].tolist() for el in ELEMENTS},
                  "molecular_labels": source_rows}, separators=(",", ":")) + "\n")
    (args.out / "response.js").write_text("// Generated from Geant4 particle response; never QM/PubChem labels.\n"
                    "globalThis.TRECH_PARTICLE_MOLECULE = " + json.dumps(summary) + ";\n")


if __name__ == "__main__":
    main()
