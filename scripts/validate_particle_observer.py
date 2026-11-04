#!/usr/bin/env python3
"""Exercise the candidate atom→nano→meso observer against independent photon MC.

Prediction/replay/strict checks are separate from scientific acceptance. A failed
observer accuracy gate stays failed in the report and gives a nonzero exit code.
No classical attenuation formula is used for targets, inference or acceptance.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = ROOT / "examples/scenarios/particle_observer_cascade/particle_observer_cascade.js"


def records(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def execute(binary, out, material, energy, length, events, mode):
    if out.exists():
        shutil.rmtree(out)
    command = [str(binary), "run", str(SCENARIO), "--output", str(out)]
    for key, value in {"material": material, "energy_kev": energy, "half_length_mm": length,
                       "events": events, "mode": mode}.items():
        command.extend(["--param", key + "=" + json.dumps(value)])
    with (out.parent / (out.name + ".log")).open("w") as sink:
        subprocess.run(command, cwd=ROOT, stdout=sink, stderr=subprocess.STDOUT, check=True)
    score = records(out / "trech_scores.jsonl")[-1]
    provenance = records(out / "trech_provenance.jsonl")[-1]
    emits = records(out / "trech_hook_emits.jsonl")
    predictions = [record["payload"] for record in emits if record["tag"] == "observer_prediction"]
    assert len(predictions) == 1
    prediction = predictions[0]
    assert prediction["prediction_phase"] == "onRunStart_before_Monte_Carlo_events"
    assert prediction["measured"] is False and prediction["mc_sampled"] is False
    assert provenance["hook_emit_dropped_count"] == 0
    expected = prediction["atom_count"] + 2 if mode == "predictive" else 0
    assert provenance["hook_predict_count"] == prediction["inference_count"] == expected
    assert prediction["expected_inference_count"] == expected
    if mode == "strict":
        assert prediction["predicted"] == {"uncollided_fraction": None, "deposited_energy_fraction": None}
        assert prediction["atomic_trace"] is prediction["cascade_trace"] is None
    else:
        assert prediction["cascade_trace"]["stagesRun"] == 2
        assert [stage["model"] for stage in prediction["cascade_trace"]["trace"]] == ["particle_molecular", "particle_observer"]
        assert prediction["cascade_trace"]["trace"][1]["scale"] == "meso"
        assert "edep_mev" not in prediction["cascade_trace"]["seedKeys"]
        assert all(0 < value < 1 for value in prediction["predicted"].values())
        model = json.loads((ROOT / "data/particle_observer/observer_response.json").read_text())
        assert prediction["heldout_residual_rmse"] == model["holdout"]["rmse"]
    return score, prediction, provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=ROOT / "build/rel/trech")
    parser.add_argument("--out", type=Path, default=ROOT / "build/rel/particle_observer_validation")
    parser.add_argument("--events", type=int, default=30000)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((ROOT / "data/particle_observer/manifest.json").read_text())
    model_path = ROOT / "data/particle_observer/observer_response.json"
    assert hashlib.sha256(model_path.read_bytes()).hexdigest() == manifest["model_sha256"]
    software_cases = []
    for material in manifest["fixed_split"]["test_materials"]:
        for mode in ["predictive", "strict"]:
            out = args.out / f"{material}_{mode}_replay"
            snapshots = []
            for _ in range(2):
                execute(args.binary, out, material, 15., 6., 128, mode)
                snapshots.append({name: (out / name).read_bytes() for name in
                                  ["trech_scores.jsonl", "trech_provenance.jsonl", "trech_hook_emits.jsonl"]})
            assert snapshots[0] == snapshots[1]
            software_cases.append({"material": material, "mode": mode, "byte_identical_replay": True})
            print(f"PASS software {material} {mode}: counts/strict/replay", flush=True)
    accuracy_cases = []
    for material in manifest["fixed_split"]["test_materials"]:
        for energy in manifest["fixed_split"]["test_energies_kev"]:
            for length in manifest["fixed_split"]["test_half_lengths_mm"]:
                out = args.out / f"{material}_{energy:g}kev_{length:g}mm"
                score, prediction, provenance = execute(args.binary, out, material, energy, length, args.events, "predictive")
                actual = {"uncollided_fraction": score["primaries_uncollided_fraction"],
                          "deposited_energy_fraction": score["system_event_edep_mean_mev"] / (energy / 1000)}
                p = actual["uncollided_fraction"]
                errors = {"uncollided_fraction": math.sqrt(p * (1 - p) / args.events),
                          "deposited_energy_fraction": score["system_event_edep_stddev_mev"] / (energy / 1000) / math.sqrt(args.events)}
                tolerance = {"uncollided_fraction": max(.03, 5 * errors["uncollided_fraction"]),
                             "deposited_energy_fraction": max(.04, 5 * errors["deposited_energy_fraction"])}
                gaps = {name: abs(prediction["predicted"][name] - value) for name, value in actual.items()}
                passed = all(gaps[name] <= tolerance[name] for name in gaps)
                accuracy_cases.append({"material": material, "energy_kev": energy, "half_length_mm": length,
                    "events": args.events, "prediction": prediction["predicted"], "actual_mc": actual,
                    "standard_errors": errors, "tolerances": tolerance, "absolute_gaps": gaps, "pass": passed,
                    "hook_out_of_domain_count": provenance["hook_predict_out_of_domain_count"],
                    "observer_trust": prediction["cascade_trace"]["trace"][1]})
                print(f"{'PASS' if passed else 'FAIL'} accuracy {material} {energy:g}keV {length:g}mm: {gaps}", flush=True)
    accepted = all(case["pass"] for case in accuracy_cases)
    coverage = {"hook_out_of_domain_evaluations": sum(case["hook_out_of_domain_count"] for case in accuracy_cases),
                "observer_out_of_domain_cases": sum(not case["observer_trust"]["inDomain"] for case in accuracy_cases),
                "observer_scale_mismatch_cases": sum(case["observer_trust"]["scaleMismatch"] for case in accuracy_cases),
                "observer_starved_cases": sum(case["observer_trust"]["starved"] for case in accuracy_cases),
                "observer_joint_starved_cases": sum(bool(case["observer_trust"]["jointStarved"]) for case in accuracy_cases),
                "observer_per_feature_starved_cases": sum(bool(case["observer_trust"]["starvedInputs"]) for case in accuracy_cases)}
    report = {"status": "pass" if accepted else "candidate_failed", "software_status": "pass",
              "committed_candidate_status": manifest["status"], "measured": False,
              "model_sha256": manifest["model_sha256"], "software_cases": software_cases,
              "accuracy_cases": accuracy_cases, "coverage_summary": coverage,
              "scope": "independent Geant4 MC realization; no independent physical measurement validation"}
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    return 0 if accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
