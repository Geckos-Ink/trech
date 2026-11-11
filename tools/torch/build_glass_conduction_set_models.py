"""Build the glass_from_sand set-network conduction models (generic_surrogate_v3, DeepSets).

Reproducible end to end: every engine run below is a recorded (scenario, seed, params) triple,
and the exact commands are written to `data/glass_furnace_conduction_set/build_record.json`
next to the models, so the training data can be regenerated (the glass-furnace per-material
operators were trained from runs whose commands were lost; this builder exists so that does not
happen again).

Teacher: the scenario's own PAIR conduction operator (`ctx.interact` over the six per-pair-
material maps in data/glass_furnace_operators/, `conduction_source=pair`). With
`emit_training_rows=true` the scenario emits, per sampled cell, its face-neighbour SET (present,
temperature offset, one-hot material per neighbour) and the conduction rate the pair operator
actually applied (`conduction_set_sample_<cell material>`). One DeepSets model per cell material
learns that rate from the neighbour set; slot order is irrelevant by construction.

Runs are split by WHOLE RUN into train / validation (trainer holdout + model selection) /
calibration (split-conformal error bars) / test (independent validator) operating points.

    PYTHONPATH=tools/torch build/render-venv/bin/python tools/torch/build_glass_conduction_set_models.py

Needs torch (the trainer's set networks) and a built engine (`--binary`, default build/rel/trech).
The models are measured:false distillations of an illustrative teacher: they demonstrate a set
network driving a scenario operator, not glass-making metrology.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

SCENARIO = "examples/scenarios/glass_from_sand/glass_from_sand.js"
OUT_DIR = "data/glass_furnace_conduction_set"
KINDS = ("batch_solid", "melt", "glass")
SLOTS = 6
FEATURES = ("present", "delta_temperature_k", "is_batch_solid", "is_melt", "is_glass")
BASE_PARAMS = {"emit_training_rows": True, "conduction_source": "pair"}

# (name, seed, params). Every operating point is a distinct furnace / ambient / lattice so the
# splits differ by run conditions, not just by seed.
RUNS = {
    "train": [
        ("train_1500", 20261101, {"furnace_temperature_k": 1500.0}),
        ("train_1600", 20261102, {"furnace_temperature_k": 1600.0}),
        ("train_1700_c8", 20261103, {"furnace_temperature_k": 1700.0, "cells_per_side": 8}),
        ("train_1750", 20261104, {"furnace_temperature_k": 1750.0}),
        ("train_1880_a350", 20261105, {"furnace_temperature_k": 1880.0, "ambient_temperature_k": 350.0}),
        ("train_1650_c5", 20261106, {"furnace_temperature_k": 1650.0, "cells_per_side": 5}),
    ],
    "validation": [
        ("valid_1560_c5", 20261111, {"furnace_temperature_k": 1560.0, "cells_per_side": 5}),
        ("valid_1820_a400", 20261112, {"furnace_temperature_k": 1820.0, "ambient_temperature_k": 400.0}),
    ],
    # Nine calibration runs: the run-level (grouped) conformal interval needs R >= c/(1-c) = 9
    # independent runs before its 90% guarantee holds (runs, not rows, are exchangeable).
    "calibration": [
        ("calib_1620", 20261121, {"furnace_temperature_k": 1620.0}),
        ("calib_1790_c7", 20261122, {"furnace_temperature_k": 1790.0, "cells_per_side": 7}),
        ("calib_1520_c5", 20261123, {"furnace_temperature_k": 1520.0, "cells_per_side": 5}),
        ("calib_1680_a330", 20261124, {"furnace_temperature_k": 1680.0, "ambient_temperature_k": 330.0}),
        ("calib_1730_c8", 20261125, {"furnace_temperature_k": 1730.0, "cells_per_side": 8}),
        ("calib_1850", 20261126, {"furnace_temperature_k": 1850.0}),
        ("calib_1580_a420", 20261127, {"furnace_temperature_k": 1580.0, "ambient_temperature_k": 420.0}),
        ("calib_1770_c5", 20261128, {"furnace_temperature_k": 1770.0, "cells_per_side": 5}),
        ("calib_1660_c7", 20261129, {"furnace_temperature_k": 1660.0, "cells_per_side": 7}),
    ],
    "test": [
        ("test_1530", 20261131, {"furnace_temperature_k": 1530.0}),
        ("test_1720_c7", 20261132, {"furnace_temperature_k": 1720.0, "cells_per_side": 7}),
    ],
}

NETWORK = {"network": "deepsets", "pool": "sum", "phi_widths": "32,32", "rho_widths": "16",
           "activation": "silu", "epochs": 600, "lr": 0.01, "lr_final_factor": 0.05,
           "l2": 0.0, "seed": 20261101}


def inputs() -> list:
    return [f"nb{k}_{f}" for k in range(SLOTS) for f in FEATURES]


def engine_command(binary: str, out: Path, seed: int, params: dict) -> list:
    cmd = [binary, "run", SCENARIO, "--seed", str(seed), "--output", str(out)]
    for name, value in sorted({**BASE_PARAMS, **params}.items()):
        cmd += ["--param", f"{name}={json.dumps(value)}"]
    return cmd


def train_command(python: str, kind: str, runs: dict, work: Path) -> list:
    paths = {split: [str(work / name) for name, _s, _p in runs[split]] for split in runs}
    n = NETWORK
    return [python, "-m", "trech_torch.train_surrogate",
            "--runs", *paths["train"], "--validation-runs", *paths["validation"],
            "--calibration-runs", *paths["calibration"],
            "--source", "hook_emits", "--tag", f"conduction_set_sample_{kind}", "--expand", "samples",
            "--inputs", ",".join(inputs()), "--outputs", "d_temperature_k_dt",
            "--network", n["network"], "--set-elements", str(SLOTS), "--set-context", "0",
            "--mask-feature", "0", "--pool", n["pool"], "--phi-widths", n["phi_widths"],
            "--rho-widths", n["rho_widths"], "--activation", n["activation"],
            "--epochs", str(n["epochs"]), "--lr", str(n["lr"]),
            "--lr-final-factor", str(n["lr_final_factor"]), "--l2", str(n["l2"]),
            "--seed", str(n["seed"]),
            "--out-json", f"{OUT_DIR}/conduction_set_{kind}.json",
            "--manifest", f"{OUT_DIR}/conduction_set_{kind}.manifest.json",
            "--teacher", "glass_from_sand pair conduction operator (data/glass_furnace_operators/conduction_*)",
            "--measured", "false",
            "--note", (f"Per-cell conduction rate of a {kind} cell from its face-neighbour SET "
                       "(DeepSets, sum pool, mask = present). Distilled from the scenario's pair "
                       "conduction operator; not exactly equal-and-opposite. Illustrative teacher: "
                       "demonstrates a set-network operator, not glass metrology.")]


def validate_command(python: str, kind: str, runs: dict, work: Path) -> list:
    return [python, "-m", "trech_torch.validate_model", "--model", f"{OUT_DIR}/conduction_set_{kind}.json",
            "--test-runs", *[str(work / name) for name, _s, _p in runs["test"]],
            "--training-runs", *[str(work / name) for name, _s, _p in runs["train"]],
            "--source", "hook_emits", "--tag", f"conduction_set_sample_{kind}", "--expand", "samples",
            "--out", f"{work}/validation_{kind}.json"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--binary", default="build/rel/trech")
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("--work", default="build/glass_conduction_set")
    ap.add_argument("--reuse-runs", action="store_true", help="skip engine runs whose output exists")
    ap.add_argument("--skip-validate", action="store_true")
    args = ap.parse_args(argv)
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    Path(OUT_DIR).mkdir(parents=True, exist_ok=True)
    record = {"schema": "trech_model_build_record_v1", "builder": "tools/torch/build_glass_conduction_set_models.py",
              "scenario": SCENARIO, "base_params": BASE_PARAMS, "runs": {}, "engine_commands": [],
              "train_commands": {}, "network": NETWORK,
              "env": {"PYTHONPATH": "tools/torch"}, "cwd": "repository root"}
    for split, runs in RUNS.items():
        record["runs"][split] = [{"name": n, "seed": s, "params": p} for n, s, p in runs]
        for name, seed, params in runs:
            out = work / name
            cmd = engine_command(args.binary, out, seed, params)
            record["engine_commands"].append(" ".join(cmd))
            if args.reuse_runs and (out / "trech_hook_emits.jsonl").exists():
                continue
            print("engine:", name, flush=True)
            with (work / f"{name}.log").open("w") as log:
                subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=True)
    for kind in KINDS:
        cmd = train_command(args.python, kind, RUNS, work)
        record["train_commands"][kind] = " ".join(cmd)
        print("train:", kind, flush=True)
        subprocess.run(cmd, check=True)
        if not args.skip_validate:
            subprocess.run(validate_command(args.python, kind, RUNS, work), check=False)
    # Commands are recorded relative to the repository root with the default work directory.
    Path(OUT_DIR, "build_record.json").write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
