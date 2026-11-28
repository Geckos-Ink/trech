"""Train, freeze and validate unlabelled response domains learned by the engine.

Scenarios: ``furnace`` (glass from sand, thermal operator; operating point =
furnace temperature; learn/evaluate/deploy), ``lamp`` (lava lamp, frame-scale parcel
response; operating point = heater temperature; learn/evaluate/deploy) and ``efflux``
(membrane efflux transport operator; operating point = run seed; learn/evaluate/deploy).

Campaign (all through the engine; nothing here decides a domain):

1. learn   -- whole furnace runs at the training operating points, in order. Each run
              warm-starts ctx.learnDomains from the previous run's state with its
              reservoir rows, so knowledge accumulates across operating points.
2. freeze  -- the final state without rows is the learned model; ``specialize`` trains
              capacity-sized PyTorch residual networks on the reservoir rows and keeps
              them only where a temporal holdout improves on the domain's ridge law.
3. held out -- at operating points never used for learning, three runs each:
              ``declared``  the scenario's own law (reference trajectory): the furnace's
                            per-material operators, the lamp's authored step laws, the
                            efflux transport operator;
              ``evaluate``  the frozen learner graded on that trajectory (state untouched);
              ``deploy``    the frozen learner drives the scenario's update, its own law
                            runs from the same state as a shadow.
              Deploy is repeated with the specialists. Each scenario's observers (furnace
              products and temperatures, lamp frame observers, efflux clearance) are
              compared with the declared run and the deploy samples are replayed through
              the NumPy twin.

The report is JSON plus a Markdown table in ``--out``.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "validation"))
from trech_torch import domain_learner as dl  # noqa: E402
from trech_validation import lamp_observers  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SCENARIOS = {
    "furnace": {"script": "examples/scenarios/glass_from_sand/glass_from_sand.js",
                "learner": "furnace_thermal", "summary": "glass_furnace_summary",
                "point": "furnace_temperature_k", "deploy": True, "base": {},
                "train": [1500, 1600, 1700, 1750, 1880], "test": [1560, 1820]},
    "lamp": {"script": "examples/scenarios/lava_lamp/lava_lamp.js",
             "learner": "lamp_parcels", "summary": "lava_lamp_summary",
             "point": "heater_temperature_k", "deploy": True, "base": {},
             "train": [325, 333.15, 345], "test": [318, 340]},
    "efflux": {"script": "examples/scenarios/testscenario_efflux/testscenario_efflux.js",
               "learner": "efflux_transport", "summary": "efflux_summary",
               "point": "seed", "deploy": True, "base": {"physics_source": "operator"},
               "train": [101, 102], "test": [201]},
}
SCENARIO = ROOT / SCENARIOS["furnace"]["script"]
LEARNER = "furnace_thermal"
DEPLOYED = "furnace_thermal_deployed"


def run(binary: Path, out: Path, params: dict, log: list) -> Path:
    if (out / "trech_hook_emits.jsonl").exists():
        log.append({"run": str(out), "cached": True})
        return out
    out.mkdir(parents=True, exist_ok=True)
    args = [str(binary), "run", str(SCENARIO), "--output", str(out)]
    for key, value in params.items():
        if key == "seed":
            args += ["--seed", str(int(value))]
        else:
            args += ["--param", f"{key}={json.dumps(value)}"]
    start = time.time()
    with open(out / "run.log", "w") as handle:
        subprocess.run(args, check=True, stdout=handle, stderr=subprocess.STDOUT, cwd=ROOT)
    log.append({"run": str(out), "params": params, "seconds": round(time.time() - start, 1)})
    print(f"  {out.name}: {time.time() - start:.0f}s", flush=True)
    return out


SUMMARY = "glass_furnace_summary"


def summary(run_dir: Path) -> dict:
    for payload in dl.iter_emits(run_dir, SUMMARY):
        return payload
    raise SystemExit(f"{run_dir}: no {SUMMARY}")


FURNACE_OBSERVERS = [
    ("glass_units", lambda s: s["product"]["glass_units"]),
    ("unreacted_sio2", lambda s: s["product"]["unreacted_sio2"]),
    ("remaining_carbonates", lambda s: s["product"]["remaining_carbonates"]),
    ("released_co2", lambda s: s["product"]["released_co2"]),
    ("first_glass_tick", lambda s: s["product"]["first_glass_tick"]),
    ("mean_temperature_k", lambda s: s["thermal"]["mean_temperature_k"]),
    ("max_temperature_k", lambda s: s["thermal"]["max_temperature_k"]),
    ("min_temperature_k", lambda s: s["thermal"]["min_temperature_k"]),
]


def compare_furnace(reference_dir: Path, candidate_dir: Path) -> dict:
    reference, candidate = summary(reference_dir), summary(candidate_dir)
    out = {}
    for name, get in FURNACE_OBSERVERS:
        a, b = get(reference), get(candidate)
        rel = abs(b - a) / max(abs(a), 1e-12) if a is not None and b is not None else None
        out[name] = {"declared": a, "learned": b, "relative_difference": rel}
    kinds_a, kinds_b = reference["product"]["final_kinds"], candidate["product"]["final_kinds"]
    out["final_kinds"] = {"declared": kinds_a, "learned": kinds_b}
    return out


def compare_lamp(reference_dir: Path, candidate_dir: Path) -> dict:
    """Frame observers of the authored and the deployed lamp (absolute gaps, gated tolerances)."""
    seen = [lamp_observers.observe(list(dl.iter_emits(d, "material_frame")))
            for d in (reference_dir, candidate_dir)]
    return lamp_observers.compare(*seen)


def compare_efflux(reference_dir: Path, candidate_dir: Path) -> dict:
    """Clearance observables against the scenario's own operator tolerances."""
    reference, candidate = summary(reference_dir), summary(candidate_dir)
    block_a = reference.get("operator_vs_reference") or {}
    block_b = candidate.get("operator_vs_reference") or {}
    obs_a, obs_b = block_a.get("observables") or {}, block_b.get("observables") or {}
    out = {}
    for key, limit in sorted((block_a.get("tolerances") or {}).items()):
        name = key.rsplit("_", 1)[0]
        a, b = obs_a.get(name), obs_b.get(name)
        gap = abs(b - a) if a is not None and b is not None else None
        out[name] = {"reference": a, "candidate": b, "gap": gap, "tolerance": limit,
                     "within": gap is not None and gap <= limit}
    return out


COMPARE = {"furnace": compare_furnace, "lamp": compare_lamp, "efflux": compare_efflux}


def observer_cells(scenario: str, observers: dict, shadow: dict) -> list:
    if scenario == "furnace":
        worst = max((v["relative_difference"] or 0.0) for k, v in observers.items() if k != "final_kinds")
        rmse = shadow.get("rmse", {})
        return [f"shadow T {rmse.get('temperature_k', float('nan')):.3g} K",
                f"glass {observers['glass_units']['declared']} / {observers['glass_units']['learned']}",
                f"max observer diff {worst:.3g}"]
    rmse = shadow.get("rmse", {})
    gated = [v for v in observers.values() if "within" in v]
    cells = ["shadow " + ", ".join(f"{k} {v:.3g}" for k, v in sorted(rmse.items()))]
    cells.append(f"observers within tolerance {sum(v['within'] for v in gated)}/{len(gated)}")
    return cells


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--binary", type=Path, default=ROOT / "build/dev/trech")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="furnace")
    parser.add_argument("--train", type=float, nargs="+", help="training operating points (scenario default)")
    parser.add_argument("--test", type=float, nargs="+", help="held-out operating points (scenario default)")
    parser.add_argument("--params", default="{}", help="JSON object of extra scenario parameters for every run")
    parser.add_argument("--test-params", default="{}", help="extra parameters for held-out runs only")
    parser.add_argument("--passes", type=int, default=1, help="passes over the training points")
    parser.add_argument("--no-specialists", action="store_true")
    parser.add_argument("--reuse-models", action="store_true",
                        help="keep existing learned.json / learned_specialists.json (re-grade only)")
    args = parser.parse_args(argv)
    global SCENARIO, LEARNER, SUMMARY
    spec = SCENARIOS[args.scenario]
    SCENARIO, LEARNER, SUMMARY = ROOT / spec["script"], spec["learner"], spec["summary"]
    point = spec["point"]
    args.train = args.train or spec["train"]
    args.test = args.test or spec["test"]
    if set(args.train) & set(args.test):
        parser.error("training and held-out operating points must be disjoint")
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    extra = dict(spec["base"], **json.loads(args.params))
    test_extra = dict(extra, **json.loads(args.test_params))
    log: list = []
    report = {"schema": "trech_domain_learning_study_v1", "scenario": args.scenario, "operating_point": point,
              "train": args.train, "test": args.test,
              "params": extra, "test_params": test_extra, "passes": args.passes,
              "budget": None}

    print("1) learning across training operating points", flush=True)
    state_path = None
    train_runs = []
    for p in range(args.passes):
        for temperature in args.train:
            params = dict(extra, learn_domains="learn", **{point: temperature})
            if state_path:
                params["domain_learner_model"] = str(state_path)
            run_dir = run(args.binary, out / f"train_p{p}_{int(temperature)}", params, log)
            train_runs.append(run_dir)
            state_path = out / f"state_p{p}_{int(temperature)}.json"
            dl.extract(train_runs, LEARNER, state_path, keep_rows=True)
            report.setdefault("training", []).append({
                "run": run_dir.name,
                "learning": summary(run_dir).get("domain_learning")})

    print("2) freezing and training specialists", flush=True)
    rows_state = json.loads(state_path.read_text())
    report["budget"] = dl.engine_budget(args.binary, len(rows_state["features"]), len(rows_state["targets"]))
    learned = out / "learned.json"
    reuse = args.reuse_models and learned.exists()
    if reuse:
        frozen = json.loads(learned.read_text())
    else:
        frozen = dl.strip_rows(rows_state)
        frozen["provenance"] = dict(rows_state.get("provenance", {}), rows_kept=False)
        learned.write_text(json.dumps(frozen, separators=(",", ":")) + "\n")
    models = {"learned": learned}
    if reuse and (out / "learned_specialists.json").exists():
        specialized = json.loads((out / "learned_specialists.json").read_text())
        report["specialists"] = specialized.get("provenance", {}).get("specialists", {}).get("domains")
        if any(entry["accepted"] for entry in report["specialists"] or []):
            models["specialists"] = out / "learned_specialists.json"
    elif not args.no_specialists:
        budget = report["budget"]["capacity"]
        specialized, spec_report = dl.specialize(rows_state, budget["specialist_width"],
                                                 budget["specialist_epochs"], 20261118, 128)
        specialized = dl.strip_rows(specialized)
        specialized.setdefault("provenance", {})["specialists"] = {
            "width": budget["specialist_width"], "epochs": budget["specialist_epochs"], "domains": spec_report}
        path = out / "learned_specialists.json"
        path.write_text(json.dumps(specialized, separators=(",", ":")) + "\n")
        report["specialists"] = spec_report
        if any(entry["accepted"] for entry in spec_report):
            models["specialists"] = path
    report["learned_domains"] = [{"id": leaf["id"], "depth": leaf["depth"], "model": leaf.get("model")}
                                 for leaf in frozen["leaves"]]
    report["lineage"] = frozen["lineage"]

    print("3) held-out operating points", flush=True)
    for temperature in args.test:
        base = dict(test_extra, **{point: temperature})
        entry = {point: temperature}
        declared_dir = run(args.binary, out / f"declared_{int(temperature)}", base, log) \
            if spec["deploy"] else None
        for label, model in models.items():
            evaluate = run(args.binary, out / f"evaluate_{label}_{int(temperature)}",
                           dict(base, learn_domains="evaluate", domain_learner_model=str(model)), log)
            state = json.loads(model.read_text())
            samples = [p["samples"] for p in dl.iter_emits(evaluate, "domain_learning") if p.get("samples")]
            entry[label] = {"evaluate": summary(evaluate).get("domain_learning"),
                            "evaluate_parity": dl.replay(state, samples) if samples else None}
            if spec["deploy"]:
                deploy = run(args.binary, out / f"deploy_{label}_{int(temperature)}",
                             dict(base, learn_domains="deploy", domain_learner_model=str(model)), log)
                deployed = summary(deploy)
                samples = [p["samples"] for p in dl.iter_emits(deploy, "domain_learning") if p.get("samples")]
                entry[label].update({
                    "deploy": deployed.get("domain_learning"),
                    "observers": COMPARE[args.scenario](declared_dir, deploy),
                    "deploy_validation": deployed.get("validation"),
                    "numpy_parity": dl.replay(state, samples),
                })
        report.setdefault("held_out", []).append(entry)

    report["runs"] = log
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    lines = []
    for entry in report["held_out"]:
        for label in models:
            e = entry[label]
            online = (e["evaluate"] or {}).get("online") or {}
            cells = [f"{entry[point]:g}", label]
            for target in sorted(online.get("routed_rmse", {})):
                cells.append(f"{target}: {online['routed_rmse'][target]:.3g} / {online['pooled_rmse'][target]:.3g}")
            agreement = online.get("agreement") or {}
            cells.append(f"ARI {agreement.get('ari', float('nan')):.3f}")
            if spec["deploy"]:
                shadow = (e["deploy"] or {}).get("shadow") or {}
                cells += observer_cells(args.scenario, e["observers"], shadow)
                parity = e["numpy_parity"]
                cells.append(f"parity {parity['max_relative_difference']:.2g} over {parity['rows']} rows"
                             if parity.get("rows") else "parity n/a (no deploy samples)")
            elif e.get("evaluate_parity"):
                cells.append(f"parity {e['evaluate_parity']['max_relative_difference']:.2g}")
            lines.append("| " + " | ".join(cells) + " |")
    (out / "report.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
