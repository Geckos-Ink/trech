#!/usr/bin/env python3
"""Run/grade all molecular groups, strict gates and deterministic replays (no network)."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def grade(out, mode):
    provenance = read_rows(out / "trech_provenance.jsonl")[-1]
    records = read_rows(out / "trech_hook_emits.jsonl")
    predictions = [r["payload"] for r in records if r["tag"] == "molecular_prediction"]
    frames = [r["payload"] for r in records if r["tag"] == "material_frame"]
    assert len(predictions) == len(frames) == 24
    assert provenance["determinism_mode"] == mode
    assert provenance["hook_emit_dropped_count"] == 0
    assert provenance["hook_predict_count"] == (24 if mode == "predictive" else 0)
    assert provenance["hook_predict_out_of_domain_count"] == 0
    errors, starved = [], 0
    for row in predictions:
        assert row["inputs"]["neutral_electrons"] > 0
        assert math.isfinite(row["geant4_edep_mev"])
        if mode == "strict":
            assert row["charges_e"] is row["relative_energy_kcal_mol"] is None
            assert row["coverage"] is None
            continue
        assert abs(sum(row["charges_e"])) < 1e-7
        assert row["coverage"]["domainMeasured"] and row["coverage"]["inDomain"]
        assert row["coverage"]["jointMeasured"]
        assert not row["coverage"]["jointStarved"]
        starved += len(row["coverage"]["starvedInputs"])
        errors.append((row["relative_energy_kcal_mol"] - row["reference_energy_kcal_mol"]) ** 2)
        assert max(abs(a - b) for a, b in zip(row["charges_e"], row["reference_charges_e"])) < 0.001
    rmse = math.sqrt(sum(errors) / len(errors)) if errors else None
    assert rmse is None or rmse < 0.01
    for frame in frames:
        assert frame["physical_time_s"] == 0
        assert frame["length_unit"] == "angstrom"
        assert len(frame["positions"]) == len(frame["radii"])
        assert ("parameter scan" in frame["clock_text"])
    return {"mode": mode, "frames": len(frames), "predictions": provenance["hook_predict_count"],
            "energy_rmse_kcal_mol": rmse, "per_feature_starvation_flags": starved,
            "out_of_domain": provenance["hook_predict_out_of_domain_count"],
            "comparison": next(r["payload"]["validation"] for r in records if r["tag"] == "molecular_summary")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=ROOT / "build/rel/trech")
    parser.add_argument("--out", type=Path, default=ROOT / "build/rel/molecular_series_validation")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    results = {}
    for i, name in enumerate(("ethane", "ethanol", "formamide"), 1):
        reference = json.loads((ROOT / f"data/molecular_series/{name}.reference.json").read_text())
        assert hashlib.sha256((ROOT / f"data/molecular_series/{name}.json").read_bytes()).hexdigest() == reference["model_sha256"]
        experiment = ROOT / f"examples/scenarios/molecular_0{i}_{name}/molecular_0{i}_{name}.js"
        for mode in ("predictive", "strict"):
            previous = None
            for repeat in range(2):
                # Use identical CLI arguments, including output_dir, so the
                # provenance bytes can be compared without normalization.
                out = args.out / f"{name}_{mode}"
                if out.exists():
                    shutil.rmtree(out)
                with (args.out / f"{out.name}_{repeat}.log").open("w") as log:
                    subprocess.run([str(args.binary), "run", str(experiment), "--param",
                                    f'mode="{mode}"', "--output", str(out)], cwd=ROOT,
                                   stdout=log, stderr=subprocess.STDOUT, check=True)
                result = grade(out, mode)
                current = {filename: (out / filename).read_bytes() for filename in
                           ("trech_hook_emits.jsonl", "trech_scores.jsonl", "trech_provenance.jsonl")}
                if previous is not None:
                    for filename in current:
                        assert current[filename] == previous[filename], filename
                previous = current
            result["byte_reproducible"] = True
            results[f"{name}_{mode}"] = result
            print(f"PASS {name} {mode}: {result['predictions']} predictions, 24 frames, byte-identical rerun", flush=True)
    (args.out / "report.json").write_text(json.dumps({"status": "pass", "runs": 12, "results": results}, indent=2) + "\n")


if __name__ == "__main__":
    main()
