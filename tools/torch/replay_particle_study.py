"""Compare frozen particle-study checkpoints with native QuickJS and LibTorch runs."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
import torch

from build_particle_observer_models import ROOT, OUTPUTS, arrays
from study_particle_observer import grade, load_rows, model_output
from study_particle_hierarchy import PLAN, hierarchy, make_samples

SCENARIO = ROOT / "examples/scenarios/particle_observer_cascade/particle_observer_cascade.js"


def records(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def run(binary, work, index, case, mode, observer, hierarchy_dir):
    name = f"{index:04d}_{mode}"
    out = work / name
    params = {"material": case["material"], "energy_kev": case["energy_kev"],
              "half_length_mm": case["half_length_mm"], "mode": mode, "events": 8,
              "observer_model": str(observer), "lift_checkpoint": str(hierarchy_dir)}
    cmd = [str(binary), "run", str(SCENARIO), "--strict-config", "--output", str(out)]
    for key, value in params.items():
        cmd.extend(["--param", f"{key}={json.dumps(value)}"])
    with (work / f"{name}.log").open("w") as log:
        subprocess.run(cmd, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=120)
    emits = {r["tag"]: r["payload"] for r in records(out / "trech_hook_emits.jsonl")}
    provenance = records(out / "trech_provenance.jsonl")[-1]
    obs = emits["observer_prediction"]
    lift = emits["observer_hierarchy_prediction"]
    if obs["counts"] != case["counts"]:
        raise RuntimeError(f"{case['id']}: replay changed composition")
    if provenance["hook_emit_dropped_count"]:
        raise RuntimeError(f"{case['id']}: dropped diagnostic outputs")
    if mode == "strict":
        if provenance["hook_predict_count"] or obs["prediction_available"] or lift["predicted"] is not None:
            raise RuntimeError("Strict mode ran model inference")
        return None
    groups = len(case["counts"])
    if obs["inference_count"] != sum(case["counts"].values()) + 2:
        raise RuntimeError("Atomic/cascade stage did not run")
    if lift["inference_count"] != groups + 1 or provenance["hook_predict_count"] != obs["inference_count"] + groups + 1:
        raise RuntimeError("Unexpected native hierarchy evaluation count")
    if [level["groups"] for level in lift["lift"]["levels"]] != [groups, 1]:
        raise RuntimeError("Unexpected group hierarchy shape")
    expected_phase = "onRunStart_before_Monte_Carlo_events"
    if obs["prediction_phase"] != expected_phase or lift["prediction_phase"] != expected_phase:
        raise RuntimeError("The scenario inferred after transport")
    return obs, lift, provenance["hook_predict_count"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--observer", type=Path, required=True)
    parser.add_argument("--hierarchy", type=Path, required=True)
    parser.add_argument("--rows", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    binary, observer, hierarchy_dir, work = [p.resolve() for p in
                                             (args.binary, args.observer, args.hierarchy, args.out)]
    work.mkdir(parents=True)
    rows = load_rows(args.rows)
    torch.set_num_threads(1)
    obs_predictions = model_output(torch.jit.load(str(observer)), arrays(rows)[0])
    models = [json.loads((hierarchy_dir / f"{level['name']}.json").read_text()) for level in PLAN["levels"]]
    lift_predictions = np.array([hierarchy.lift_np(sample, PLAN, models)[-1]["features"][0]
                                 for sample in make_samples(rows)])
    checkpoints = [observer, Path(str(observer) + ".io.json")] + [
        hierarchy_dir / f"{level['name']}.json" for level in PLAN["levels"]]
    identities = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in checkpoints}
    cases, deployed_obs, deployed_lift = [], [], []
    run(binary, work, 0, rows[0], "strict", observer, hierarchy_dir)
    for i, case in enumerate(rows):
        obs, lift, count = run(binary, work, i, case, "predictive", observer, hierarchy_dir)
        obs_result = [obs["predicted"][name] for name in OUTPUTS]
        lift_result = [lift["predicted"][name] for name in OUTPUTS]
        np.testing.assert_allclose(obs_result, obs_predictions[i], rtol=1e-6, atol=1e-6, err_msg=case["id"])
        np.testing.assert_allclose(lift_result, lift_predictions[i], rtol=1e-8, atol=1e-8, err_msg=case["id"])
        trace = obs["cascade_trace"]["trace"][-1]
        if not trace["domainMeasured"] or any(not x["domainMeasured"] for x in lift["lift"]["levels"]):
            raise RuntimeError("Missing fitted input domains in native trace")
        cases.append({"id": case["id"], "inference_count": count,
                      "cascade_trust": {k: trace[k] for k in ("inDomain", "starved", "jointStarved", "starvedInputs")},
                      "hierarchy_groups": [{k: level[k] for k in ("groups", "evaluated", "outOfDomain", "starved")}
                                           for level in lift["lift"]["levels"]]})
        deployed_obs.append(obs_result)
        deployed_lift.append(lift_result)
        print(f"PASS {case['id']} ({count} native evaluations)", flush=True)
    report = {"model_hashes": identities, "strict_predict_count": 0, "cases": cases,
              "observer_accuracy": grade(rows, np.array(deployed_obs)),
              "hierarchy_accuracy": grade(rows, np.array(deployed_lift)),
              "observer_max_parity_error": float(np.max(abs(obs_predictions - deployed_obs))),
              "hierarchy_max_parity_error": float(np.max(abs(lift_predictions - deployed_lift)))}
    (work / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(work / "report.json")


if __name__ == "__main__":
    main()
