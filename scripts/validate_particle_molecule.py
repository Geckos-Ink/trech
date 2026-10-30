#!/usr/bin/env python3
"""Grade learned molecular response, strict gates, replays and actual photon MC."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
NAMES = ["butane", "dimethyl_ether", "acetamide"]


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def execute(binary, script, out, log, extra=()):
    if out.exists():
        shutil.rmtree(out)
    with log.open("w") as sink:
        subprocess.run([str(binary), "run", str(script), *extra, "--output", str(out)], cwd=ROOT,
                       stdout=sink, stderr=subprocess.STDOUT, check=True)


def grade(out, mode, atom_count):
    provenance = rows(out / "trech_provenance.jsonl")[-1]
    records = rows(out / "trech_hook_emits.jsonl")
    predictions = [r["payload"] for r in records if r["tag"] == "molecular_prediction"]
    frames = [r["payload"] for r in records if r["tag"] == "material_frame"]
    assert len(predictions) == len(frames) == 48
    assert provenance["hook_predict_count"] == (48 * (atom_count + 2) if mode == "predictive" else 0)
    assert provenance["hook_predict_out_of_domain_count"] == provenance["hook_emit_dropped_count"] == 0
    assert {f["stream"] for f in frames} == {"torsion", "particle_response"}
    response_rows = []
    worst = 0.
    for prediction in predictions:
        if mode == "strict":
            assert prediction["particle_response"] is prediction["charges_e"] is None
            continue
        assert abs(sum(prediction["charges_e"])) < 1e-7
        response = prediction["particle_response"]
        assert response["atomic_inference_count"] == atom_count
        assert response["molecular_trace"]["stagesRun"] == 1
        assert response["molecular_trace"]["stagesScaleMismatched"] == 0
        assert response["geant4_trained"]
        truth = prediction["particle_reference_sigma_barn"]
        error = max(abs(a - b) / b for a, b in zip(response["sigma_barn"], truth))
        worst = max(worst, error)
        assert error < .03
        if prediction["stream"] == "particle_response":
            response_rows.append(prediction)
    for frame in frames:
        assert frame["physical_time_s"] == 0
        assert "parameter scan" in frame["clock_text"]
    if mode == "predictive":
        # In-distribution counterfactual: changing particle energy must change
        # the learned atom/molecule response and halo sizes, while the frozen
        # quantum scaffold and charges stay fixed. No synthetic bond response.
        assert response_rows[0]["particle_response"]["sigma_barn"][0] > 100 * response_rows[-1]["particle_response"]["sigma_barn"][0]
        assert all(r["charges_e"] == response_rows[0]["charges_e"] for r in response_rows)
        response_frames = [f for f in frames if f["stream"] == "particle_response"]
        assert response_frames[0]["positions"] == response_frames[-1]["positions"]
        assert response_frames[0]["radii"] != response_frames[-1]["radii"]
    return {"predictions": provenance["hook_predict_count"], "frames": len(frames),
            "maximum_particle_relative_error": worst,
            "last_particle_prediction": response_rows[-1]["particle_response"] if response_rows else None}


def monte_carlo(binary, work, name, molecular, reference, response):
    counts = molecular["counts"]
    masses = reference["atomic_masses"]
    mass = sum(counts[e] * masses[e] for e in counts)
    energy = response["energy_ev"]
    config = {"detector": {"worldSizeMm": 20, "worldMaterial": "molecular_probe"},
      "materials": [{"name": "molecular_probe", "densityGcm3": 1,
                     "components": [{"element": e, "fraction": counts[e] * masses[e] / mass} for e in counts]}],
      "beam": {"particle": "gamma", "energyMeV": energy / 1e6, "direction": [0, 0, 1]},
      "run": {"nEvents": 30000, "seed": 20261023, "threads": 1}, "physics": {"list": "QBBC_LIV"},
      "materialProbe": {"enable": True, "materials": ["molecular_probe"]},
      "analytic": {"enable": True, "checks": [{"type": "beer_lambert", "particle": "gamma",
          "material": "molecular_probe", "energyMeV": energy / 1e6, "pathLengthMm": 10, "toleranceRel": .04}]}}
    script = work / f"{name}_mc.js"
    script.write_text("globalThis.TRECH_CONFIG = " + json.dumps(config) + ";\n")
    out = work / f"{name}_mc"
    execute(binary, script, out, work / f"{name}_mc.log")
    scores = rows(out / "trech_scores.jsonl")[-1]
    probe = next(p for p in scores["material_probes"] if p["name"] == "molecular_probe")
    el = next(iter(counts))
    molecules_per_cm3 = probe["numberDensityPerCm3"][el] / counts[el]
    mu = sum(response["sigma_barn"]) * molecules_per_cm3 * 1e-25
    # Classical attenuation is a validation-only comparison, never a production
    # state law or a label used to fit either learned model.
    predicted = math.exp(-mu * 10)
    measured = scores["primaries_uncollided_fraction"]
    sigma = math.sqrt(max(1e-12, measured * (1 - measured)) / 30000)
    assert abs(predicted - measured) < max(.015, 5 * sigma)
    return {"events": 30000, "energy_ev": energy, "learned_transmission_comparison": predicted,
            "geant4_uncollided_fraction": measured, "absolute_gap": abs(predicted - measured)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=ROOT / "build/rel/trech")
    parser.add_argument("--out", type=Path, default=ROOT / "build/rel/particle_molecule_validation")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    reference = json.loads((ROOT / "data/particle_molecule/reference.json").read_text())
    for filename, expected in reference["model_sha256"].items():
        assert hashlib.sha256((ROOT / "data/particle_molecule" / filename).read_bytes()).hexdigest() == expected
    results = {}
    for i, name in enumerate(NAMES, 4):
        molecular = json.loads((ROOT / f"data/molecular_series/{name}.reference.json").read_text())
        for mode in ["predictive", "strict"]:
            previous = None
            for repeat in range(2):
                out = args.out / f"{name}_{mode}"
                execute(args.binary, ROOT / f"examples/scenarios/molecular_0{i}_{name}/molecular_0{i}_{name}.js", out,
                        args.out / f"{name}_{mode}_{repeat}.log", ["--param", f'mode="{mode}"'])
                result = grade(out, mode, len(molecular["elements"]))
                artifacts = {filename: (out / filename).read_bytes() for filename in
                             ["trech_hook_emits.jsonl", "trech_scores.jsonl", "trech_provenance.jsonl"]}
                assert previous is None or artifacts == previous
                previous = artifacts
            results[f"{name}_{mode}"] = result
            print(f"PASS {name} {mode}: {result['predictions']} evaluations; byte-identical rerun", flush=True)
        results[name + "_monte_carlo"] = monte_carlo(args.binary, args.out, name, molecular, reference,
            results[name + "_predictive"]["last_particle_prediction"])
        print(f"PASS {name} 30000-photon Monte Carlo comparison", flush=True)
    (args.out / "report.json").write_text(json.dumps({"status": "pass", "runs": 15, "results": results}, indent=2) + "\n")


if __name__ == "__main__":
    main()
