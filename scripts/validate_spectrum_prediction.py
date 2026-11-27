#!/usr/bin/env python3
"""Validate the spectrum_prediction scenario against its JS-trained artifacts.

Checks (engine binary required; the JS subproject's own tests are `node --test projects/spectrum_prediction/test/*.test.js`):
  1. Export layout: every engine prediction equals an independent pure-Python evaluation of the
     committed generic_surrogate_v1 JSON (standardize -> layers -> destandardize).
  2. Agreement: engine metrics on the held-out split reproduce the trainer report's test metrics.
  3. Strict mode: no inference, null predictions, measured references still emitted.
  4. Studio mode: declared input schema, extension descriptor and leaderboard emit; trust traces.
  5. Intervals: the engine reports each model's calibrated per-bin half-width (prediction_interval)
     and holdout rmse unchanged, and the scenario's held-out coverage equals the trainer's.
"""
import argparse
import json
import math
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "examples/scenarios/spectrum_prediction/spectrum_prediction.js"
DATA = ROOT / "data/spectrum_prediction"
ACT = {"none": lambda x: x, "relu": lambda x: max(0.0, x), "tanh": math.tanh,
       "sigmoid": lambda x: 1 / (1 + math.exp(-x)), "silu": lambda x: x / (1 + math.exp(-x))}


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def run(binary, out, *params):
    if out.exists():
        shutil.rmtree(out)
    args = [str(binary), "run", str(SCENARIO)]
    for key, value in params:
        args += ["--param", f"{key}={json.dumps(value)}"]
    with (out.parent / (out.name + ".log")).open("w") as log:
        subprocess.run(args + ["--output", str(out)], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
    emits = rows(out / "trech_hook_emits.jsonl")
    provenance = rows(out / "trech_provenance.jsonl")[-1]
    return emits, provenance


def forward(model, inputs):
    h = [(inputs[name] - m) / (s if abs(s) >= 1e-12 else 1.0)
         for name, m, s in zip(model["input_features"], model["input_mean"], model["input_std"])]
    for layer in model["layers"]:
        f = ACT[layer.get("activation", "none")]
        h = [f(b + sum(w * v for w, v in zip(row, h))) for row, b in zip(layer["weights"], layer["bias"])]
    return [v * s + m for v, s, m in zip(h, model["output_std"], model["output_mean"])]


def tagged(emits, tag):
    return [e["payload"] for e in emits if e["tag"] == tag]


def live_geant4_features(out, energies, process):
    """g4_* inputs recomputed here from the run's own material_probes (independent of the JS library)."""
    probes = next(r["material_probes"] for r in rows(out / "trech_scores.jsonl") if "material_probes" in r)
    features = {}
    for probe in probes:
        if not probe["name"].startswith("G4_") or len(probe.get("elements", [])) != 1:
            continue
        atoms_per_mm3 = probe["elements"][0]["atoms_per_cm3"] * 1e-3
        by_energy = {round(i["energy_mev"] * 1e6, 6): i["cross_sections_per_mm"][process] for i in probe["interactions"]}
        row = {"g4_ln_mean_excitation_ev": math.log(probe["mean_excitation_energy_ev"])}
        for e in energies:
            row[f"g4_ln_photoabs_barn_{e}ev"] = math.log(max(by_energy[round(float(e), 6)] / atoms_per_mm3 / 1e-22, 1e-6))
        features[probe["elements"][0]["symbol"]] = row
    return features


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--trech", default=str(ROOT / "build/dev/trech"))
    parser.add_argument("--out", default=str(ROOT / "build/spectrum_prediction_validation"))
    args = parser.parse_args()
    binary, out = Path(args.trech), Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    dataset = json.loads((DATA / "dataset.json").read_text())
    report = json.loads((DATA / "report.json").read_text())
    models = {name: json.loads((DATA / "models" / f"{name}.json").read_text()) for name in ("spectrum_atomic", "spectrum_molecular")}
    facts = dataset["element_facts"]
    geant4_inputs = [n for n in models["spectrum_atomic"]["input_features"] if n.startswith("g4_")]
    probe_def = (dataset.get("geant4_atomic") or {}).get("probe") or {}

    # 1 + 2: held-out split through the engine.
    emits, prov = run(binary, out / "test_split", ("selection", "test_split"))
    records = tagged(emits, "spectrum_prediction")
    assert prov["hook_emit_dropped_count"] == 0 and prov["predictive_mode"] is True
    assert {r["split"] for r in records} == {"test"}
    assert len(records) == len(models["spectrum_atomic"]["trained_from"]["test_ids"]) + len(models["spectrum_molecular"]["trained_from"]["test_ids"])
    live = live_geant4_features(out / "test_split", probe_def.get("energies_ev", []), probe_def.get("process")) if geant4_inputs else {}
    worst = worst_g4 = worst_catalog = 0.0
    for r in records:
        model = models[r["model"]]
        if r["kind"] == "atom":
            symbol = r["id"].split("_", 1)[1]
            trained = facts[symbol]["features"]
            # Independent input sources for the atomic rung: the dataset's PubChem facts, and the
            # Geant4 inputs recomputed from this run's own probe (not the committed catalogue).
            assert {k: v for k, v in r["model_inputs"].items() if not k.startswith("g4_")} == \
                {k: v for k, v in trained.items() if not k.startswith("g4_")}, symbol
            if geant4_inputs:
                assert r["geant4_atomic_inputs"]["source"].startswith("live Geant4 material probe G4_" + symbol)
                for name in geant4_inputs:
                    worst_g4 = max(worst_g4, abs(r["model_inputs"][name] - live[symbol][name]))
                    worst_catalog = max(worst_catalog, abs(trained[name] - live[symbol][name]))
        else:
            molecule = next(m for m in dataset["molecules"] if m["id"] == r["id"])
            assert molecule["smiles"] == r["smiles"]
            assert [s["model"] for s in r["stages"]][-1] == "spectrum_molecular"
            assert all(s["ran"] for s in r["stages"])
        expected = forward(model, r["model_inputs"])
        worst = max(worst, max(abs(a - b) for a, b in zip(expected, r["predicted"])))
        interval, block = r["interval"], model["prediction_interval"]
        assert interval["nominal_coverage"] == block["nominal_coverage"]
        assert interval["half_width"] == [block["half_width"][n] for n in model["output_features"]], r["id"]
        assert interval["holdout_rmse"] == [model["holdout"]["rmse"][n] for n in model["output_features"]], r["id"]
        for p, lo, hi, w in zip(r["predicted"], interval["lower"], interval["upper"], interval["half_width"]):
            assert abs(hi - (p + w)) < 1e-12 and abs(lo - max(0.0, p - w)) < 1e-12
    assert worst < 1e-9, f"engine vs Python dense forward differs by {worst}"
    if geant4_inputs:
        assert prov["physics_list"] == probe_def["physics_list"], prov["physics_list"]
        assert worst_g4 < 1e-12, f"atomic Geant4 inputs differ from the run's probe by {worst_g4}"
        assert worst_catalog < 1e-12, f"live Geant4 probe differs from the training catalogue by {worst_catalog}"
        print(f"atomic Geant4 inputs: {len(geant4_inputs)} per element from the live probe (max |Δ| {worst_g4:.1e}; "
              f"vs training catalogue {worst_catalog:.1e})")
    summary = tagged(emits, "spectrum_summary")[0]["models"]
    for name, stats in summary.items():
        trainer = next(a for a in report["architectures"] if a["exported"] == name)["test"]
        for key in ("rmse", "cosine"):
            assert abs(stats[key] - trainer[key]) < 1e-6, (name, key, stats[key], trainer[key])
        assert stats["n"] == trainer["n"]
        expected_cov = next(a for a in report["architectures"] if a["exported"] == name)["interval"]["test"]
        for key in ("cells", "min_bin", "samples_all_bins"):
            assert abs(stats["interval_coverage"][key] - expected_cov[key]) < 1e-6, (name, key)  # report: 8 significant figures
    print(f"held-out split: {len(records)} records; engine == trainer test metrics; engine vs Python forward max |Δ| {worst:.2e}")
    print("interval coverage (held-out cells): " + ", ".join(
        f"{name} {stats['interval_coverage']['cells']:.3f} at nominal {stats['interval_coverage']['nominal']}" for name, stats in summary.items()))

    # 1 for the molecular rung: a single molecule's full input vector is reconstructed from the emit.
    emits, prov = run(binary, out / "single", ("molecule", "naphthalene"), ("studio_mode", True))
    record = tagged(emits, "spectrum_prediction")[0]
    assert prov["hook_predict_count"] == 3, prov["hook_predict_count"]  # C, H atomic + molecular
    if geant4_inputs:
        assert sorted(record["geant4_atomic_inputs"]) == ["C", "H"], record["geant4_atomic_inputs"]
    assert record["inference"] == "predicted" and record["predicted"] is not None
    molecular_stage = record["stages"][-1]
    assert molecular_stage["model"] == "spectrum_molecular" and molecular_stage["holdoutR2"] is not None
    report_emit = tagged(emits, "spectrum_model_report")
    assert report_emit and report_emit[0]["ranking"] == report["ranking"]
    context = tagged(emits, "spectrum_geant4_context")[0]
    assert context["available"] and context["mean_excitation_energy_ev"] > 0
    for studio in (True, False):
        inspected = json.loads(subprocess.run([str(binary), "inspect", str(SCENARIO), "--param", f"studio_mode={json.dumps(studio)}"],
                                              cwd=ROOT, capture_output=True, text=True, check=True).stdout)
        declared = inspected["authoring"]["studio"]
        schema = inspected["config"].get("hooks", {}).get("inputs", {}).get("schema")
        assert declared["panels"]["spectra"] is studio and ("spectrum_prediction" in declared["extensions"]) is studio
        assert schema == ("trech_spectrum_inputs_v1" if studio else None), schema
    print(f"single target {record['label']}: RMSE {record['metrics']['rmse']:.3f}, Studio report emitted, Geant4 context I = {context['mean_excitation_energy_ev']:.1f} eV")

    # 3: strict mode.
    emits, prov = run(binary, out / "strict", ("mode", "strict"), ("element", "Na"), ("target_kind", "atom"))
    record = tagged(emits, "spectrum_prediction")[0]
    assert prov["hook_predict_count"] == 0 and prov["predictive_mode"] is False
    assert record["predicted"] is None and record["inference"] == "disabled_strict" and record["measured"]
    assert record["interval"] is None and record["interval_covered_fraction"] is None
    print("strict mode: inference disabled, measured reference retained")
    print("spectrum_prediction validation passed")


if __name__ == "__main__":
    main()
