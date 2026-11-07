#!/usr/bin/env python3
"""Validate the spectrum_prediction scenario against its JS-trained artifacts.

Checks (engine binary required; the JS subproject's own tests are `node --test projects/spectrum_prediction/test/*.test.js`):
  1. Export layout: every engine prediction equals an independent pure-Python evaluation of the
     committed generic_surrogate_v1 JSON (standardize -> layers -> destandardize).
  2. Agreement: engine metrics on the held-out split reproduce the trainer report's test metrics.
  3. Strict mode: no inference, null predictions, measured references still emitted.
  4. Studio mode: declared input schema, extension descriptor and leaderboard emit; trust traces.
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

    # 1 + 2: held-out split through the engine.
    emits, prov = run(binary, out / "test_split", ("selection", "test_split"))
    records = tagged(emits, "spectrum_prediction")
    assert prov["hook_emit_dropped_count"] == 0 and prov["predictive_mode"] is True
    assert {r["split"] for r in records} == {"test"}
    assert len(records) == len(models["spectrum_atomic"]["trained_from"]["test_ids"]) + len(models["spectrum_molecular"]["trained_from"]["test_ids"])
    worst = 0.0
    for r in records:
        model = models[r["model"]]
        if r["kind"] == "atom":
            # Independent input source for the atomic rung: the dataset's element facts.
            assert r["model_inputs"] == facts[r["id"].split("_", 1)[1]]["features"]
        else:
            molecule = next(m for m in dataset["molecules"] if m["id"] == r["id"])
            assert molecule["smiles"] == r["smiles"]
            assert [s["model"] for s in r["stages"]][-1] == "spectrum_molecular"
            assert all(s["ran"] for s in r["stages"])
        expected = forward(model, r["model_inputs"])
        worst = max(worst, max(abs(a - b) for a, b in zip(expected, r["predicted"])))
    assert worst < 1e-9, f"engine vs Python dense forward differs by {worst}"
    summary = tagged(emits, "spectrum_summary")[0]["models"]
    for name, stats in summary.items():
        trainer = next(a for a in report["architectures"] if a["exported"] == name)["test"]
        for key in ("rmse", "cosine"):
            assert abs(stats[key] - trainer[key]) < 1e-6, (name, key, stats[key], trainer[key])
        assert stats["n"] == trainer["n"]
    print(f"held-out split: {len(records)} records; engine == trainer test metrics; engine vs Python forward max |Δ| {worst:.2e}")

    # 1 for the molecular rung: a single molecule's full input vector is reconstructed from the emit.
    emits, prov = run(binary, out / "single", ("molecule", "naphthalene"), ("studio_mode", True))
    record = tagged(emits, "spectrum_prediction")[0]
    assert prov["hook_predict_count"] == 3, prov["hook_predict_count"]  # C, H atomic + molecular
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
    print("strict mode: inference disabled, measured reference retained")
    print("spectrum_prediction validation passed")


if __name__ == "__main__":
    main()
