"""Re-check committed models against FRESH test runs (trech_ml_recheck_v1).

Most committed models under `data/` do not keep the runs they were trained and tested on
(those live under `build/` and are not source). The static audit (`validate_model --scan`) can
only read back what a model carries. This tool closes the loop where a model's data producer is
reproducible: a recipe says how to PRODUCE new runs for the model's domain, the tool produces
them with seeds the model never saw, and the independent validator grades the committed model on
them (test accuracy, linear baseline, leakage, sigma calibration, domain coverage).

Recipes (`data/ml_recheck_recipes.json`, schema `trech_ml_recheck_recipes_v1`):

    {"model": "data/.../x.json",
     "producer": {"kind": "python", "script": "tools/torch/....py", "function": "fresh_run",
                  "args": {...}}                     # called as fn(out_dir, seed, rows, **args)
               | {"kind": "engine", "scenario": "examples/.../x.js", "binary": "build/rel/trech",
                  "events": N, "params": {"name": json},   # `trech run` with --seed/--output
                  "seed_params": {"<seed>": {"name": json}},  # per-run operating point (merged
                                                              # over params): fresh runs at NEW
                                                              # conditions, not just new seeds
                  "env": {"NAME": "value"}},              # e.g. a PubChem cache directory
     "harvest": {"source": "...", "tag": "...", "expand": "..."},
     "used_seeds": [...],        # seeds of the runs the model was trained/held out on: refused
     "fresh_seeds": [...],       # the new test runs
     "rows": 4000,               # python producers: rows per fresh run
     "training": {"seed": s, "rows": n},  # optional: regenerate the training run (leakage +
                                          # linear-baseline gates); python producers
               | {"seeds": [s, ...]},     # engine producers: regenerate these recorded training
                                          # runs (each with its seed_params)
     "holdout": {"seed": s, "rows": n}    # optional: regenerate the ORIGINAL holdout run; its
                                          # metrics must reproduce the carried ones, proving the
                                          # producer has not drifted since the model was trained
    }

`--check` (CTest `trech_ml_model_recheck`) is cheap and needs no NumPy: it fails when a recipe's
model or recipe changed since the committed report was produced, i.e. the report is stale. A
fresh-run verdict never upgrades a trust label: a distilled operator re-checked against fresh
TEACHER runs is still `measured:false`; the check grades the distillation, not the physics.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from .validate_model import _round, load_model, validate

SCHEMA = "trech_ml_recheck_v1"
RECIPES_SCHEMA = "trech_ml_recheck_recipes_v1"
REGENERATE = ("PYTHONPATH=tools/torch python3 -m trech_torch.recheck_models "
              "--recipes data/ml_recheck_recipes.json --json docs/ml_model_recheck.json "
              "--md docs/ml_model_recheck.md (needs NumPy)")


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def recipe_hash(recipe: dict) -> str:
    return "sha256:" + hashlib.sha256(_canonical(recipe).encode()).hexdigest()[:16]


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_recipes(path: Path) -> List[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema") != RECIPES_SCHEMA or not isinstance(data.get("recipes"), list):
        raise SystemExit(f"{path}: not a {RECIPES_SCHEMA} file")
    for recipe in data["recipes"]:
        problems = recipe_problems(recipe)
        if problems:
            raise SystemExit(f"{path}: recipe for {recipe.get('model')}: " + "; ".join(problems))
    return data["recipes"]


def recipe_problems(recipe: dict) -> List[str]:
    problems = []
    producer = recipe.get("producer") or {}
    if not isinstance(recipe.get("model"), str):
        problems.append("model path missing")
    if producer.get("kind") not in ("python", "engine"):
        problems.append("producer.kind must be python or engine")
    if producer.get("kind") == "python" and not (producer.get("script") and producer.get("function")):
        problems.append("python producers need script + function")
    if producer.get("kind") == "engine" and not producer.get("scenario"):
        problems.append("engine producers need a scenario")
    fresh = recipe.get("fresh_seeds")
    used = set(recipe.get("used_seeds") or [])
    if not isinstance(fresh, list) or not fresh or not all(isinstance(s, int) for s in fresh):
        problems.append("fresh_seeds must be a non-empty list of integers")
    elif used & set(fresh):
        problems.append(f"fresh seeds {sorted(used & set(fresh))} were used to train or hold out the model "
                        "(they would replay the same rows)")
    elif len(set(fresh)) != len(fresh):
        problems.append("fresh_seeds repeat a seed")
    for key in ("training", "holdout"):
        block = recipe.get(key)
        if block is not None and block.get("seed") not in used and key == "holdout":
            problems.append("holdout.seed must be one of used_seeds (it regenerates the original holdout)")
    training = recipe.get("training")
    if training is not None:
        if producer.get("kind") == "engine":
            seeds = training.get("seeds")
            if not isinstance(seeds, list) or not seeds or not all(isinstance(t, int) for t in seeds):
                problems.append("engine training regeneration needs training.seeds (a list of integers)")
            elif set(seeds) - used:
                problems.append("training.seeds must be among used_seeds (they regenerate the training runs)")
            elif isinstance(fresh, list) and set(seeds) & set(fresh):
                problems.append("a training seed is also a fresh seed")
        elif training.get("seed") in set(fresh):
            problems.append("the training seed is also a fresh seed")
    if producer.get("kind") == "engine":
        seed_params = producer.get("seed_params") or {}
        if not isinstance(seed_params, dict) or not all(
                isinstance(v, dict) and str(k).lstrip("-").isdigit() for k, v in seed_params.items()):
            problems.append("producer.seed_params must map seed strings to parameter objects")
        if isinstance(fresh, list) and len(fresh) > 1 and seed_params:
            points = [_canonical(seed_params.get(str(f), {})) for f in fresh]
            if len(set(points)) != len(points):
                problems.append("fresh runs share an operating point (seed_params): vary the conditions")
    if not isinstance(recipe.get("harvest"), dict) or not recipe["harvest"].get("source"):
        problems.append("harvest.source missing")
    return problems


def _python_producer(root: Path, producer: dict):
    script = (root / producer["script"]).resolve()
    spec = importlib.util.spec_from_file_location(f"_trech_recheck_{script.stem}", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return getattr(module, producer["function"])


def produce(root: Path, recipe: dict, out_dir: Path, seed: int, rows: Optional[int]) -> Path:
    producer = recipe["producer"]
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    if producer["kind"] == "python":
        fn = _python_producer(root, producer)
        fn(str(out_dir), int(seed), int(rows or recipe.get("rows") or 1000), **(producer.get("args") or {}))
    else:
        binary = root / producer.get("binary", "build/rel/trech")
        cmd = engine_command(root, producer, out_dir, seed)
        env = dict(os.environ)
        env.update({k: str(v) for k, v in (producer.get("env") or {}).items()})
        log = out_dir.with_suffix(".log")
        with log.open("w", encoding="utf-8") as sink:
            subprocess.run(cmd, cwd=root, stdout=sink, stderr=subprocess.STDOUT, check=True,
                           timeout=int(producer.get("timeout_s", 900)), env=env)
    return out_dir


def engine_command(root: Path, producer: dict, out_dir: Path, seed: int) -> List[str]:
    """The exact `trech run` command of one engine run: base params, then that seed's point."""
    binary = root / producer.get("binary", "build/rel/trech")
    cmd = [str(binary), "run", str(root / producer["scenario"]), "--seed", str(seed), "--output", str(out_dir)]
    if producer.get("events"):
        cmd += ["--events", str(producer["events"])]
    params = dict(producer.get("params") or {})
    params.update((producer.get("seed_params") or {}).get(str(seed), {}))
    for name, value in sorted(params.items()):
        cmd += ["--param", f"{name}={json.dumps(value)}"]
    return cmd


def recheck(recipe: dict, *, root: Path, work: Path) -> dict:
    model_path = root / recipe["model"]
    model = load_model(model_path)
    stem = model_path.stem
    harvest = recipe["harvest"]
    fresh_dirs = [produce(root, recipe, work / stem / f"fresh_{seed}", seed, recipe.get("rows"))
                  for seed in recipe["fresh_seeds"]]
    training_dirs: List[Path] = []
    if recipe.get("training"):
        t = recipe["training"]
        for seed in (t["seeds"] if "seeds" in t else [t["seed"]]):
            training_dirs.append(produce(root, recipe, work / stem / f"train_{seed}", seed, t.get("rows")))
    reproduced = None
    if recipe.get("holdout"):
        h = recipe["holdout"]
        reproduced = producer_reproduces(model, produce(root, recipe, work / stem / f"holdout_{h['seed']}",
                                                        h["seed"], h.get("rows")), harvest)
    report = validate(model_path, test_runs=[str(p) for p in fresh_dirs],
                      training_runs=[str(p) for p in training_dirs], source=harvest["source"],
                      tag=harvest.get("tag"), expand=harvest.get("expand"),
                      min_r2=float(recipe.get("min_r2", 0.0)))
    carried = (model.get("holdout") or {}).get("r2") or {}
    test_metrics = (report.get("test") or {}).get("metrics") or {}
    note = model.get("note") if isinstance(model.get("note"), dict) else {}
    return {
        "model": recipe["model"],
        "sha256": _sha256(model_path),
        "recipe_hash": recipe_hash(recipe),
        "producer": recipe["producer"]["kind"],
        "measured": note.get("measured") if isinstance(note.get("measured"), bool) else None,
        "fresh_seeds": list(recipe["fresh_seeds"]),
        "fresh_conditions": {str(s): (recipe["producer"].get("seed_params") or {}).get(str(s))
                             for s in recipe["fresh_seeds"]} if recipe["producer"].get("seed_params") else None,
        "fresh_rows": (report.get("test") or {}).get("rows"),
        "training_regenerated": bool(training_dirs),
        "producer_reproduces_holdout": reproduced,
        "status": "fail" if reproduced is not None and not reproduced["ok"] else report["status"],
        "gates": {g["name"]: g["status"] for g in report["gates"]},
        "details": {g["name"]: g["detail"] for g in report["gates"] if g["status"] in ("fail", "warn")},
        "r2": {o: {"carried": _round(carried.get(o), 6) if isinstance(carried.get(o), (int, float)) else None,
                   "fresh": test_metrics.get(o, {}).get("r2")} for o in model.get("output_features") or []},
        "sigma": next((g.get("calibration") for g in report["gates"] if g["name"] == "sigma_calibration"), None),
    }


def producer_reproduces(model: dict, run_dir: Path, harvest: dict) -> dict:
    """Re-evaluate the committed model on a REGENERATED copy of its original holdout run.

    The recomputed per-output RMSE must equal the carried one (relative 1e-6): otherwise the
    producer no longer makes the data the model was graded on, and its 'fresh' runs would test
    a drifted source instead of the model's own one.
    """
    import numpy as np

    from .dataset import harvest_table
    from .train_surrogate import build_xy, evaluate, predict_np
    from .validate_model import model_layers, output_links, scalers

    rows, _metas = harvest_table([str(run_dir)], source=harvest["source"], tag=harvest.get("tag"),
                                 expand=harvest.get("expand"))
    x, y, _dropped = build_xy(rows, list(model["input_features"]), list(model["output_features"]))
    pred = predict_np(x, model_layers(model), tuple(np.asarray(v, dtype=float) for v in scalers(model)),
                      output_links(model))
    metrics = evaluate(y, pred, list(model["output_features"]))
    carried = (model.get("holdout") or {}).get("rmse") or {}
    worst = 0.0
    for o, m in metrics.items():
        if isinstance(carried.get(o), (int, float)):
            worst = max(worst, abs(m["rmse"] - carried[o]) / max(1e-12, abs(carried[o])))
    ok = bool(carried) and worst <= 1e-6 and len(x) == (model.get("holdout") or {}).get("n")
    return {"ok": ok, "rows": int(len(x)), "max_relative_rmse_difference": _round(worst)}


def markdown(data: dict) -> str:
    lines = [
        "# Committed ML models re-checked on fresh runs",
        "",
        "<!-- Generated; do not edit. Regenerate with:",
        f"     {REGENERATE}",
        "     CTest `trech_ml_model_recheck` fails when a model or recipe changed since. -->",
        "",
        "Each model below has a reproducible data producer recorded in "
        "[`data/ml_recheck_recipes.json`](../data/ml_recheck_recipes.json). "
        "[`recheck_models.py`](../tools/torch/trech_torch/recheck_models.py) produced new runs with seeds the "
        "model was never trained or held out on and graded the **committed** model on them with the independent "
        "validator ([gates](ml_models.md#validating-a-model)). Models without a recipe are only statically audited "
        "([audit](ml_model_audit.md)). A re-check grades what the model learned from its own data source: for "
        "`measured:false` operators that source is an authored teacher, so a pass says the distillation "
        "generalises to new operating points, not that the teacher is physically right.",
        "",
        "| Model | Holdout regenerated | Fresh seeds (operating point); rows | Carried R² → fresh R² | σ check | Status |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for m in data["models"]:
        r2 = "; ".join(f"{o} {v['carried'] if v['carried'] is not None else '—'} → {v['fresh']}" for o, v in m["r2"].items())
        sigma = m["gates"].get("sigma_calibration", "—")
        rep = m.get("producer_reproduces_holdout")
        regen = "—" if rep is None else ("reproduces carried RMSE" if rep["ok"] else
                                         f"DRIFT ({rep['max_relative_rmse_difference']})")
        cond = m.get("fresh_conditions") or {}
        seeds = ", ".join(str(sd) + (" (" + ", ".join(f"{k}={v}" for k, v in sorted((cond.get(str(sd)) or {}).items())) + ")"
                                     if cond.get(str(sd)) else "") for sd in m["fresh_seeds"])
        lines.append(f"| `{m['model']}` | {regen} | {seeds}; {m['fresh_rows']} rows | {r2} | "
                     f"{sigma} | {m['status']} |")
    flagged = [(m["model"], name, d) for m in data["models"] for name, d in m["details"].items()]
    lines += ["", "## Warnings and failures", ""]
    lines += [f"- `{path}` — `{name}`: {d}" for path, name, d in flagged] if flagged else ["None."]
    lines += ["", "## Not re-checked", "", data["not_rechecked"]]
    return "\n".join(lines) + "\n"


NOT_RECHECKED = (
    "Every other committed model: the illustrative cascade maps and untrained teachers have no data "
    "producer; the particle observer (`tools/torch/build_particle_observer_models.py`, strict serial "
    "Geant4 harvests with frozen final cases) and the spectrum models (`projects/spectrum_prediction`) "
    "have their own builders and no fresh-run recipe yet (open work in the training roadmap). The "
    "glass-furnace and polyurethane operators ARE re-checked above on fresh operating points of the "
    "current scenarios, but their ORIGINAL runs (`build/glass_train/*`, `build/dev/operator_harvest/*`) "
    "cannot be regenerated: the glass operators were harvested from the 2D revision of glass_from_sand "
    "(36e979d, `CELL_COUNT = SIDE*SIDE`, today 3D) with unrecorded holdout knobs, so no holdout "
    "reproduction is claimed for them.")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--recipes", default="data/ml_recheck_recipes.json")
    ap.add_argument("--root", default=".")
    ap.add_argument("--work", default="build/ml_recheck", help="where fresh runs are written")
    ap.add_argument("--only", action="append", default=None, help="re-check only models whose path contains this")
    ap.add_argument("--json", default=None, help="write the report JSON here")
    ap.add_argument("--md", default=None, help="write the Markdown report here")
    ap.add_argument("--check", action="store_true",
                    help="fail when the committed report (--json) is stale for any recipe (no NumPy needed)")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    recipes = load_recipes(root / args.recipes)
    if args.check:
        if not args.json:
            ap.error("--check needs --json (the committed report)")
        committed = json.loads((root / args.json).read_text(encoding="utf-8"))
        by_model = {m["model"]: m for m in committed.get("models", [])}
        stale = []
        for recipe in recipes:
            entry = by_model.get(recipe["model"])
            if entry is None:
                stale.append(f"{recipe['model']}: no entry in the report")
            elif entry["sha256"] != _sha256(root / recipe["model"]):
                stale.append(f"{recipe['model']}: model changed since its re-check")
            elif entry["recipe_hash"] != recipe_hash(recipe):
                stale.append(f"{recipe['model']}: recipe changed since its re-check")
        extra = sorted(set(by_model) - {r["model"] for r in recipes})
        stale += [f"{m}: in the report but has no recipe" for m in extra]
        if stale:
            print("stale fresh-run re-check report; regenerate with:\n  " + REGENERATE, file=sys.stderr)
            for line in stale:
                print("  " + line, file=sys.stderr)
            return 1
        print(f"fresh-run re-check report is current for {len(recipes)} model(s)")
        return 0
    chosen = [r for r in recipes if not args.only or any(o in r["model"] for o in args.only)]
    models = []
    for recipe in chosen:
        print(f"re-checking {recipe['model']} on fresh seeds {recipe['fresh_seeds']}")
        entry = recheck(recipe, root=root, work=(root / args.work))
        print(f"  -> {entry['status']}: " + ", ".join(f"{k}={v}" for k, v in entry["gates"].items()))
        models.append(entry)
    data = {"schema": SCHEMA, "recipes": args.recipes, "models": models, "not_rechecked": NOT_RECHECKED}
    if args.json:
        Path(root / args.json).write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    if args.md:
        Path(root / args.md).write_text(markdown(data), encoding="utf-8")
    return 1 if any(m["status"] == "fail" for m in models) else 0


if __name__ == "__main__":
    raise SystemExit(main())
