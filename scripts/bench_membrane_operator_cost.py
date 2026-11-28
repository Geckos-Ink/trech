#!/usr/bin/env python3
"""Cost of a learned membrane-node operator in testscenario_osmotic, before choosing its granularity.

The osmotic membrane is the run's hot path: the authored `integrateMembrane` law moves 642
vertices in 6 substeps on each of 6,000 ticks. Migrating it to an engine operator (migration
ledger row 6) means one `ctx.evolve` call per substep or one per tick. This script measures both
on real serial `trech` runs, so the choice rests on numbers:

- A synthetic per-vertex operator (`generic_surrogate_v1`: 6 inputs -> `d_rho_dt`, two hidden
  SiLU layers of width 16, 32 or 64, fixed-seed weights) is evaluated over 642 elements through
  `ctx.evolve`, either 6 times per tick (per substep) or once (per tick). The hook also builds the
  state/aux arrays and copies the result back, as the scenario would.
- A run with the same hook and no `ctx.evolve` call is the baseline; its time is subtracted.
- Each configuration runs `--repeats` times; the minimum wall time is used.

The authored law's own cost comes from a debug trace of the real scenario: run
`trech run examples/scenarios/testscenario_osmotic/testscenario_osmotic.js --trace debug:osmotic_membrane`
and pass that run's trace file as `--authored-trace` (spans `integrateMembrane` per tick and
`membraneGeometry` per substep; several traces may be given).

The synthetic weights grade cost only, never accuracy. Usage:
  python3 scripts/bench_membrane_operator_cost.py --binary build/rel/trech --ticks 2000 \\
      --authored-trace build/osmo/trech_trace.jsonl --out build/membrane_cost.json
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERTICES = 642          # icosphere subdivision 3, as built by the scenario
SUBSTEPS = 6            # SCENARIO.membraneSubsteps
SCENARIO_TICKS = 6000   # TOTAL_TICKS
INPUTS = ["rho", "area_strain", "pressure_drive", "dvolume_drho", "darea_drho", "bend"]


def model(width: int, seed: int) -> dict:
    rng = random.Random(seed)
    sizes = [len(INPUTS), width, width, 1]
    layers = []
    for i in range(3):
        fan_in, fan_out = sizes[i], sizes[i + 1]
        scale = 0.1 / fan_in ** 0.5
        layers.append({"weights": [[rng.uniform(-scale, scale) for _ in range(fan_in)] for _ in range(fan_out)],
                       "bias": [0.0] * fan_out, "activation": "silu" if i < 2 else "none"})
    return {"model": "generic_surrogate_v1", "input_features": INPUTS, "output_features": ["d_rho_dt"],
            "input_mean": [0.0] * len(INPUTS), "input_std": [1.0] * len(INPUTS),
            "input_domain": {"standardized_radius": [1e6] * len(INPUTS)}, "layers": layers}


def experiment(model_path: str | None, calls_per_tick: int, ticks: int) -> str:
    models = [] if model_path is None else [{
        "name": "membrane_node", "scale": "micro", "operator_role": "membrane_node",
        "element_kind": "membrane_vertex", "path": model_path}]
    config = {
        "environment": {"worldSizeMm": 10, "worldMaterial": "G4_Galactic"},
        "beam": {"particle": "geantino", "energyMeV": 0.0, "direction": [0, 0, 1]},
        "run": {"nEvents": ticks, "seed": 7, "threads": 1},
        "determinism": {"mode": "predictive"},
        "hooks": {"registered": ["onEventStart"]},
        "models": models,
    }
    evolve = "" if model_path is None else """
      const report = ctx.evolve({dt: 0.05, fields: ["rho"], state: {rho: rho}, aux: aux,
                                 operator_role: "membrane_node"});
      if (!report || !report.inferenceCount) throw new Error("operator did not run");"""
    return f"""
const N = {VERTICES};
const membrane = new Float64Array(N);
for (let i = 0; i < N; i += 1) membrane[i] = 1 + 0.01 * Math.sin(i);
globalThis.TRECH_CONFIG = {json.dumps(config)};
globalThis.TRECH_HOOKS = {{
  onEventStart: function(ctx) {{
    for (let c = 0; c < {calls_per_tick}; c += 1) {{
      // Build the call exactly as the scenario would: state + per-vertex geometry aux.
      const rho = new Array(N), aux = {{area_strain: [], pressure_drive: [], dvolume_drho: [],
                                         darea_drho: [], bend: []}};
      for (let i = 0; i < N; i += 1) {{
        rho[i] = membrane[i];
        aux.area_strain.push(0.001); aux.pressure_drive.push(-0.02);
        aux.dvolume_drho.push(0.0196 * membrane[i]); aux.darea_drho.push(0.039 * membrane[i]);
        aux.bend.push(membrane[i] - 1);
      }}{evolve}
      for (let i = 0; i < N; i += 1) membrane[i] = rho[i];
    }}
  }}
}};
"""


def timed_run(binary: Path, script: Path, out: Path) -> float:
    start = time.perf_counter()
    proc = subprocess.run([str(binary), "run", str(script), "--output", str(out)],
                          capture_output=True, text=True, timeout=3600)
    elapsed = time.perf_counter() - start
    if proc.returncode:
        raise RuntimeError(f"{script.name} failed: {proc.stderr[-600:]}")
    return elapsed


def authored_cost(trace: Path) -> dict:
    """integrateMembrane spans (one per tick) and the membraneGeometry spans inside them (one per
    substep): what the law costs, and how much of it is mesh geometry an operator still needs.

    The trace keeps at most 20,000 records per category, so a full 6,000-tick run records every
    law span (6,000) but not every geometry span (36,000). The geometry share is computed over the
    ticks whose law span and all six geometry spans were recorded (matched by event id); the
    suppressed count is reported."""
    law, geometry, suppressed = {}, {}, 0
    for line in trace.read_text().splitlines():
        record = json.loads(line)
        if record.get("msg") == "run attribution summary":
            suppressed = int(((record.get("data") or {}).get("suppressed_records") or {}).get("osmotic_membrane", 0))
        if record.get("cat") != "osmotic_membrane":
            continue
        ms = (record.get("data") or {}).get("duration_ms")
        if ms is None:
            continue
        if record.get("msg") == "integrateMembrane":
            law[record.get("event")] = float(ms)
        elif record.get("msg") == "membraneGeometry":
            geometry.setdefault(record.get("event"), []).append(float(ms))
    if not law:
        raise SystemExit(f"no integrateMembrane spans in {trace}")
    values = list(law.values())
    out = {"ticks": len(law), "mean_ms_per_tick": statistics.fmean(values),
           "median_ms_per_tick": statistics.median(values), "total_s": sum(values) / 1000.0,
           "suppressed_records": suppressed,
           # The run directory and file name only: committed reports carry no local paths.
           "source": f"{trace.parent.name}/{trace.name}"}
    complete = [e for e in law if len(geometry.get(e, [])) == SUBSTEPS]
    if complete:
        g = sum(sum(geometry[e]) for e in complete)
        t = sum(law[e] for e in complete)
        out.update({"geometry_ticks": len(complete), "geometry_ms_per_tick": g / len(complete),
                    "update_ms_per_tick": (t - g) / len(complete), "geometry_share": g / t})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--binary", type=Path, default=ROOT / "build/rel/trech")
    ap.add_argument("--ticks", type=int, default=2000)
    ap.add_argument("--widths", type=int, nargs="+", default=[16, 32, 64])
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--authored-trace", type=Path, nargs="+",
                    help="debug:osmotic_membrane trace(s) of the real scenario")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    report = {"schema": "trech_membrane_operator_cost_v1", "vertices": VERTICES, "substeps": SUBSTEPS,
              "ticks_measured": args.ticks, "scenario_ticks": SCENARIO_TICKS, "binary": args.binary.name,
              "note": "synthetic weights: cost only, not accuracy", "operator": [], "baseline": {}}
    with tempfile.TemporaryDirectory(prefix="membrane_cost_") as tmp:
        work = Path(tmp)
        base = {}
        # Warm-up: the first run pays cold-cache Geant4/data loading; time nothing from it.
        warm = work / "warmup.js"
        warm.write_text(experiment(None, 1, 10))
        timed_run(args.binary, warm, work / "out_warm")
        for calls in (1, SUBSTEPS):
            script = work / f"baseline_{calls}.js"
            script.write_text(experiment(None, calls, args.ticks))
            base[calls] = min(timed_run(args.binary, script, work / f"out_b{calls}") for _ in range(args.repeats))
            report["baseline"][f"{calls}_builds_per_tick_s"] = base[calls]
        for width in args.widths:
            path = work / f"node_{width}.json"
            path.write_text(json.dumps(model(width, 1000 + width)))
            for granularity, calls in (("per_tick", 1), ("per_substep", SUBSTEPS)):
                script = work / f"op_{width}_{calls}.js"
                script.write_text(experiment(str(path), calls, args.ticks))
                t = min(timed_run(args.binary, script, work / f"out_{width}_{calls}") for _ in range(args.repeats))
                per_call_ms = (t - base[calls]) / (args.ticks * calls) * 1000.0
                row = {"width": width, "granularity": granularity, "calls_per_tick": calls,
                       "wall_s": t, "inference_ms_per_call": per_call_ms,
                       "inference_us_per_vertex": per_call_ms * 1000.0 / VERTICES,
                       "projected_inference_s_per_scenario_run": per_call_ms * calls * SCENARIO_TICKS / 1000.0}
                report["operator"].append(row)
                print(f"width {width:3d} {granularity:11s}: {per_call_ms:.3f} ms/call, "
                      f"{row['projected_inference_s_per_scenario_run']:.1f} s per 6,000-tick run", flush=True)
    if args.authored_trace:
        report["authored"] = [authored_cost(trace) for trace in args.authored_trace]
        for a in report["authored"]:
            print(f"authored integrateMembrane ({a['source']}): {a['mean_ms_per_tick']:.3f} ms/tick (6 substeps), "
                  f"{a['total_s']:.1f} s over {a['ticks']} ticks"
                  + (f"; mesh geometry {a['geometry_ms_per_tick']:.3f} ms/tick ({100 * a['geometry_share']:.0f}%, "
                     f"over {a['geometry_ticks']} fully recorded ticks)" if "geometry_share" in a else ""))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + "\n")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
