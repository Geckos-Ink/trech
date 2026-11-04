#!/usr/bin/env python3
"""Learn a finite CHNO photon-volume observer from actual Geant4 Monte Carlo.

Existing Geant4-table-trained atom/molecule models supply every lower response.
No attenuation formula supplies observer targets or runtime predictions. The
fixed whole-material/energy/geometry test panel is opened only after fitting.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
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
from build_particle_molecule_models import atom_features, material, predict as lower_predict
from trech_torch.train_surrogate import input_domain, write_generic_json, _mlp_layers_json
from particle_observer_cache import capture_identity, cache_matches, write_identity

INPUTS = ["molecule_phot_barn", "molecule_compt_barn", "molecule_Rayl_barn",
          "molecule_areal_density_barn_inv", "photon_energy_kev"]
OUTPUTS = ["uncollided_fraction", "deposited_energy_fraction"]
TRAIN_MATERIALS = {"panel_a": {"H": 2, "O": 1},
                   "panel_b": {"H": 12, "C": 6, "N": 2, "O": 1},
                   "panel_c": {"H": 4, "C": 1},
                   "panel_d": {"H": 16, "C": 8, "O": 1}}
TRAIN_ENERGIES_KEV = [10., 12., 17., 21., 26., 30.]
TRAIN_HALF_LENGTHS_MM = [.25, 1.5, 4., 9.]
TEST_ENERGIES_KEV = [15., 29.7]
TEST_HALF_LENGTHS_MM = [.75, 6.]
EXTRA_TRAIN_MATERIALS = {
    "ethanol_proxy": {"C": 2, "H": 6, "O": 1},
    "ethylene_proxy": {"C": 2, "H": 4},
    "ammonia_proxy": {"N": 1, "H": 3},
    "nitrogen_dioxide_proxy": {"N": 1, "O": 2},
    "carbon_dioxide_proxy": {"C": 1, "O": 2},
    "methanol_proxy": {"C": 1, "H": 4, "O": 1},
    "acetic_acid_proxy": {"C": 2, "H": 4, "O": 2},
    "glycine_proxy": {"C": 2, "H": 5, "N": 1, "O": 2}}
FINAL_MATERIALS = {"hexane": {"C": 6, "H": 14}, "acetone": {"C": 3, "H": 6, "O": 1},
                   "urea": {"C": 1, "H": 4, "N": 2, "O": 1}}
EXTRA_ENERGIES_KEV = [11., 15., 22., 29.]
EXTRA_HALF_LENGTHS_MM = [.75, 3., 7.5]
FINAL_ENERGIES_KEV = [13.3, 19.3, 28.7]
FINAL_HALF_LENGTHS_MM = [1., 7.]
SEED = 20261104


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_json(path):
    return json.loads(path.read_text())


def cases(split):
    original_test = {
        name: load_json(ROOT / f"data/molecular_series/{name}.reference.json")["counts"]
        for name in ["butane", "dimethyl_ether", "acetamide"]}
    if split == "train":
        materials, energies, lengths, offset = TRAIN_MATERIALS, TRAIN_ENERGIES_KEV, TRAIN_HALF_LENGTHS_MM, 0
    elif split == "test":
        materials, energies, lengths, offset = original_test, TEST_ENERGIES_KEV, TEST_HALF_LENGTHS_MM, 1000
    elif split == "train2":
        materials, energies, lengths, offset = EXTRA_TRAIN_MATERIALS, EXTRA_ENERGIES_KEV, EXTRA_HALF_LENGTHS_MM, 2000
    elif split == "test2":
        materials, energies, lengths, offset = FINAL_MATERIALS, FINAL_ENERGIES_KEV, FINAL_HALF_LENGTHS_MM, 3000
    else:
        raise ValueError("unknown campaign split: " + split)
    return [{"id": f"{split}_{name}_{energy:g}kev_{length:g}mm", "split": split,
             "material": name, "counts": counts, "energy_kev": energy,
             "half_length_mm": length, "seed": SEED + offset + index}
            for index, (name, counts, energy, length) in enumerate(
                (name, count, energy, length) for name, count in materials.items()
                for energy in energies for length in lengths)]


def lower_features(counts, energy_kev, number_density, half_length):
    atomic = load_json(ROOT / "data/particle_molecule/atomic_response.json")
    molecular = load_json(ROOT / "data/particle_molecule/molecular_response.json")
    pooled = np.concatenate([lower_predict(atomic, atom_features(el, energy_kev * 1000)) * counts.get(el, 0)
                             for el in ["H", "C", "N", "O"]])
    sigma = lower_predict(molecular, pooled)
    # Pure unit/count conversion: the cube's central +z path contains N*L
    # molecules per transverse area. No response/attenuation law is applied.
    return np.array([*sigma, number_density * half_length * 1e-25, energy_kev])


def harvest(binary, work, case, events, masses):
    directory = work / case["id"]
    directory.mkdir(parents=True, exist_ok=True)
    config = {"detector": {"worldSizeMm": 2 * case["half_length_mm"], "worldMaterial": "molecular_probe"},
              "materials": [material("molecular_probe", case["counts"], masses)],
              "beam": {"particle": "gamma", "energyMeV": case["energy_kev"] / 1000,
                       "originMm": [0, 0, 0], "direction": [0, 0, 1]},
              "run": {"nEvents": events, "seed": case["seed"], "threads": 1},
              "physics": {"list": "QBBC_LIV"}, "determinism": {"mode": "strict"},
              "materialProbe": {"enable": True, "materials": ["molecular_probe"]}}
    script_bytes = ("globalThis.TRECH_CONFIG=" + json.dumps(config, sort_keys=True) + ";\n").encode()
    script = directory / "input.js"
    script.write_bytes(script_bytes)
    cache = directory / "row.json"
    identity_path = directory / "cache_identity.json"
    lower_paths = {name: ROOT / "data/particle_molecule" / name
                   for name in ["atomic_response.json", "molecular_response.json"]}
    feature_sources = {"observer_builder": Path(__file__),
                       "lower_features": ROOT / "tools/torch/build_particle_molecule_models.py"}
    identity = capture_identity(script_bytes, binary, lower_paths, feature_sources)
    if cache.exists() and cache_matches(identity_path, identity):
        row = load_json(cache)
        if row["source"]["script_sha256"] == sha(script_bytes):
            return row
    out = directory / "run"
    # Invalidate the previous row before storing a new pre-execution identity:
    # a failed run must never make an older row reusable under a new engine.
    cache.unlink(missing_ok=True)
    write_identity(identity_path, identity)
    if out.exists():
        shutil.rmtree(out)
    with (directory / "run.log").open("w") as sink:
        subprocess.run([str(binary), "run", str(script), "--output", str(out)], cwd=ROOT,
                       stdout=sink, stderr=subprocess.STDOUT, check=True, timeout=300)
    score_bytes = (out / "trech_scores.jsonl").read_bytes()
    provenance_bytes = (out / "trech_provenance.jsonl").read_bytes()
    score = json.loads(score_bytes.splitlines()[-1])
    provenance = json.loads(provenance_bytes.splitlines()[-1])
    assert score["primaries_emitted"] == events
    assert provenance["hook_predict_count"] == 0
    probe = next(p for p in score["material_probes"] if p["name"] == "molecular_probe")
    element = next(iter(case["counts"]))
    density = probe["numberDensityPerCm3"][element] / case["counts"][element]
    features = lower_features(case["counts"], case["energy_kev"], density, case["half_length_mm"])
    if capture_identity(script_bytes, binary, lower_paths, feature_sources) != identity:
        raise RuntimeError("Engine, model or feature source changed during harvest; refusing cache publication")
    energy_mev = case["energy_kev"] / 1000
    row = {**case, "events": events, "density_g_cm3": 1., "molecules_per_cm3": density,
           "path_length_mm": case["half_length_mm"], "inputs": features.tolist(),
           "labels": {"primaries_emitted": int(score["primaries_emitted"]),
                      "primaries_uncollided": int(score["primaries_uncollided"]),
                      "uncollided_fraction": score["primaries_uncollided_fraction"],
                      "deposited_energy_fraction": score["system_event_edep_mean_mev"] / energy_mev,
                      "deposited_energy_fraction_stddev": score["system_event_edep_stddev_mev"] / energy_mev},
           "source": {"script_sha256": sha(script_bytes), "scores_sha256": sha(score_bytes),
                      "engine_sha256": identity["engine_sha256"],
                      "lower_model_sha256": identity["lower_model_sha256"],
                      "feature_source_sha256": identity["feature_source_sha256"],
                      "provenance_sha256": sha(provenance_bytes),
                      "geant4_version": provenance["geant4_version"], "physics_list": "QBBC_LIV"}}
    cache.write_text(json.dumps(row, indent=2) + "\n")
    print(f"HARVEST {case['id']}: {row['labels']['uncollided_fraction']:.5f}, "
          f"{row['labels']['deposited_energy_fraction']:.5f}", flush=True)
    return row


def arrays(rows):
    return np.array([r["inputs"] for r in rows]), np.array([[r["labels"][name] for name in OUTPUTS] for r in rows])


def model_predict(model, raw):
    values = (np.asarray(raw) - model["input_mean"]) / model["input_std"]
    for layer in model["network"]["layers"]:
        values = values @ np.asarray(layer["weights"]).T + layer["bias"]
        if layer["activation"] == "silu":
            values = values / (1 + np.exp(-values))
    encoded = values * model["output_std"] + model["output_mean"]
    return 1 / (1 + np.exp(-encoded))


def fit(rows, validation_rows=None, epochs=16000, hidden=48):
    import torch
    torch.set_num_threads(1)
    torch.manual_seed(SEED)
    x, y = arrays(rows)
    xm, xs = x.mean(0), x.std(0)
    xs[xs < 1e-12] = 1
    # Jeffreys continuity correction affects fit coordinates only, never raw
    # tally labels: finite logit coordinates for a run with zero/all successes.
    n = np.array([r["events"] for r in rows])[:, None]
    corrected = (y * n + .5) / (n + 1)
    encoded = np.log(corrected / (1 - corrected))
    ym, ys = encoded.mean(0), encoded.std(0)
    ys[ys < 1e-12] = 1
    xx = torch.tensor((x - xm) / xs, dtype=torch.float64)
    yy = torch.tensor(y, dtype=torch.float64)
    mean = torch.tensor(ym, dtype=torch.float64)
    std = torch.tensor(ys, dtype=torch.float64)
    net = torch.nn.Sequential(torch.nn.Linear(5, hidden), torch.nn.SiLU(),
                              torch.nn.Linear(hidden, hidden), torch.nn.SiLU(),
                              torch.nn.Linear(hidden, 2)).double()
    optimizer = torch.optim.Adam(net.parameters(), lr=.004, weight_decay=1e-6)
    validation = arrays(validation_rows) if validation_rows else None
    best_loss, best_epoch, best_weights = float("inf"), epochs, None
    for epoch in range(epochs):
        rate = .004 * .025 ** (epoch / max(1, epochs - 1))
        for group in optimizer.param_groups:
            group["lr"] = rate
        optimizer.zero_grad()
        prediction = torch.sigmoid(net(xx) * std + mean)
        loss = ((prediction - yy) ** 2).mean()
        loss.backward()
        optimizer.step()
        if (epoch + 1) % 100 == 0 and validation is not None:
            with torch.no_grad():
                vx, vy = validation
                vp = torch.sigmoid(net(torch.tensor((vx - xm) / xs, dtype=torch.float64)) * std + mean).numpy()
            vloss = float(np.mean((vp - vy) ** 2))
            if vloss < best_loss:
                best_loss, best_epoch = vloss, epoch + 1
                best_weights = {key: value.detach().clone() for key, value in net.state_dict().items()}
        if (epoch + 1) % 4000 == 0:
            print(f"FIT {len(rows)} rows epoch {epoch + 1}: training MSE={loss.item():.6g}", flush=True)
    if best_weights is not None:
        net.load_state_dict(best_weights)
    return net, (xm, xs, ym, ys), best_epoch, best_loss


def metrics(prediction, truth):
    residual = prediction - truth
    r2 = 1 - np.sum(residual ** 2, axis=0) / np.sum((truth - truth.mean(0)) ** 2, axis=0)
    return {"r2": dict(zip(OUTPUTS, r2.tolist())), "r2_min": float(min(r2)), "n": len(truth),
            "rmse": dict(zip(OUTPUTS, np.sqrt(np.mean(residual ** 2, axis=0)).tolist())),
            "mae": dict(zip(OUTPUTS, np.mean(abs(residual), axis=0).tolist()))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=ROOT / "build/rel/trech")
    parser.add_argument("--work", type=Path, default=ROOT / "build/rel/particle_observer_training")
    parser.add_argument("--out", type=Path, default=ROOT / "data/particle_observer")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--train-events", type=int, default=8192)
    parser.add_argument("--test-events", type=int, default=None,
                        help="default: 30000 in campaign1, 20000 in campaign2")
    parser.add_argument("--campaign", type=int, choices=[1, 2], default=2)
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    args.out.mkdir(parents=True, exist_ok=True)
    reference = load_json(ROOT / "data/particle_molecule/reference.json")
    binary = args.binary.resolve()
    def collect(split, events):
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            return list(pool.map(lambda case: harvest(binary, args.work, case, events,
                                                       reference["atomic_masses"]), cases(split)))
    training = collect("train", args.train_events)
    if args.campaign == 1:
        validation = [r for r in training if r["energy_kev"] == 12]
        fitting = [r for r in training if r["energy_kev"] != 12]
        _, _, selected_epochs, validation_mse = fit(fitting, validation)
        net, scalers, _, _ = fit(training, epochs=selected_epochs)
    else:
        previous = load_json(args.out / "attempt1/rows.json")
        validation = [{**row, "split": "development"} for row in previous["rows"] if row["split"] == "test"]
        training += [{**row, "split": "train"} for row in collect("train2", args.train_events)]
        net, scalers, selected_epochs, validation_mse = fit(training, validation, epochs=40000, hidden=64)
    print(f"DEVELOPMENT SELECTION campaign={args.campaign} epoch={selected_epochs} validation MSE={validation_mse:.6g}", flush=True)
    path = args.out / "observer_response.json"
    write_generic_json(path, INPUTS, OUTPUTS, scalers, _mlp_layers_json(net),
        {"script": "tools/torch/build_particle_observer_models.py", "kind": "actual Geant4 Monte Carlo event tallies",
         "seed": SEED, "campaign": args.campaign, "fit_runs": len(training), "development_runs": len(validation),
         "training_only_validation_runs": len(validation) if args.campaign == 1 else 0,
         "selected_epochs": selected_epochs, "validation_mse": validation_mse,
         "continuity_correction": "Jeffreys (n*p+0.5)/(n+1) only for fit-coordinate initialization; decoded probability loss uses raw labels"},
        domain=input_domain(arrays(training)[0], scalers, joint_centers=48, joint_quantile=1),
        scale_bands=["meso"], output_transforms=["sigmoid", "sigmoid"],
        note={"geant4_trained": True, "measured": False, "mc_sampled": True,
              "maturity": "experimental", "scope": "CHNO independent-atom composition proxy, 10-30 keV central +z gamma in unit-density cube; not chemical bonding or experimental accuracy"})
    # The model is frozen before independent test MC outcomes are collected.
    frozen_hash = sha(path.read_bytes())
    test_events = args.test_events or (30000 if args.campaign == 1 else 20000)
    testing = collect("test", test_events) if args.campaign == 1 else collect("test2", test_events)
    if args.campaign == 2:
        testing = [{**row, "split": "test"} for row in testing]
    model = load_json(path)
    prediction = model_predict(model, arrays(testing)[0])
    truth = arrays(testing)[1]
    holdout = metrics(prediction, truth)
    # Calibration metadata does not alter weights, scalers, domain or predictions.
    model["holdout"] = holdout
    path.write_text(json.dumps(model, indent=2) + "\n")
    passed = True
    results = []
    for row, values in zip(testing, prediction):
        labels = row["labels"]
        se = math.sqrt(labels["uncollided_fraction"] * (1 - labels["uncollided_fraction"]) / row["events"])
        energy_se = labels["deposited_energy_fraction_stddev"] / math.sqrt(row["events"])
        gaps = abs(values - np.array([labels[name] for name in OUTPUTS]))
        tolerances = np.array([max(.03, 5 * se), max(.04, 5 * energy_se)])
        case_pass = bool(np.all(gaps <= tolerances))
        passed &= case_pass
        results.append({"id": row["id"], "prediction": values.tolist(), "absolute_gap": gaps.tolist(),
                        "standard_error": [se, energy_se], "tolerance": tolerances.tolist(), "pass": case_pass})
    baseline = arrays(training)[1].mean(0)
    baseline_rmse = np.sqrt(np.mean((truth - baseline) ** 2, axis=0))
    passed &= all(holdout["rmse"][name] < base for name, base in zip(OUTPUTS, baseline_rmse))
    data = {"schema": "trech_particle_observer_rows_v1", "label_source": "actual Geant4 Monte Carlo tallies; no analytic labels",
            "input_features": INPUTS, "output_features": OUTPUTS,
            "rows": training + (validation if args.campaign == 2 else []) + testing}
    rows_path = args.out / "rows.json"
    rows_path.write_text(json.dumps(data, separators=(",", ":")) + "\n")
    manifest = {"schema": "trech_particle_observer_manifest_v1", "status": "pass" if passed else "candidate_failed",
        "maturity": "experimental", "geant4_trained": True, "measured": False, "mc_sampled": True,
        "geometry": {"shape": "homogeneous cube", "density_g_cm3": 1, "source": "center", "direction": [0, 0, 1],
                     "path_length_mm": "cube half-length", "areal_density_conversion": "molecules_per_cm3 * path_length_mm * 1e-25, multiplying barns gives a dimensionless collision count; no attenuation law"},
        "campaign": args.campaign,
        "fixed_split": {"training_materials": {**TRAIN_MATERIALS, **(EXTRA_TRAIN_MATERIALS if args.campaign == 2 else {})},
                        "train_energies_kev": sorted(set(TRAIN_ENERGIES_KEV + (EXTRA_ENERGIES_KEV if args.campaign == 2 else []))),
                        "train_half_lengths_mm": sorted(set(TRAIN_HALF_LENGTHS_MM + (EXTRA_HALF_LENGTHS_MM if args.campaign == 2 else []))),
                        "test_half_lengths_mm": TEST_HALF_LENGTHS_MM if args.campaign == 1 else FINAL_HALF_LENGTHS_MM,
                        "test_materials": ["butane", "dimethyl_ether", "acetamide"] if args.campaign == 1 else list(FINAL_MATERIALS),
                        "test_energies_kev": TEST_ENERGIES_KEV if args.campaign == 1 else FINAL_ENERGIES_KEV,
                        "selection": "12 keV training rows" if args.campaign == 1 else "previous campaign12 test cases explicitly reused as development, never fresh test; selected weights retained without refit",
                        "test_opening": "new final outcomes collected only after selected weights frozen"},
        "frozen_before_test_sha256": frozen_hash, "model_sha256": sha(path.read_bytes()), "rows_sha256": sha(rows_path.read_bytes()),
        "lower_model_sha256": reference["model_sha256"], "holdout": holdout,
        "constant_training_mean_baseline_rmse": dict(zip(OUTPUTS, baseline_rmse.tolist())), "test_results": results,
        "limits": ["independent Geant4 MC validation, not physical measurements", "bounded cube/source/material/energy domain",
                   "no bonded/isomer distinction", "finite test Monte Carlo uncertainty", "global heldout RMSE is not conditional physical uncertainty"]}
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"status": manifest["status"], "holdout": holdout, "test_results": results}, indent=2), flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
