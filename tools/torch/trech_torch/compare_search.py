"""Compare architecture-search strategies on one table with the same splits, trainer and budget.

Search quality, not trainer quality, is what is compared. Every strategy proposes architectures
in the Evolvo GFSL-NN language and every candidate is trained by the same ``TorchTask``
(full-batch Adam on training-standardized data, Evolvo's learned plateau stop, best-selection
weights restored). Strategies differ only in which architectures they propose:

- ``grid``: uniform MLPs, widths {6, 11, 23, 45} x depth {1, 2, 3} x {silu, tanh} (24 points);
- ``random_mlp``: seeded random uniform MLPs (ladder width 4-128, depth 1-4, any activation);
- ``evolvo_mlp``: the bounded Evolvo width/depth search (``evolve_structure.search_structure``);
- ``random_gfsl``: seeded random genomes from the whole GFSL-NN language;
- ``gfsl``: the learned GFSL-NN search (``evolvo.nnarch.ArchitectureSearch``), and
  ``gfsl_reuse``, the same search warm-started from the knowledge earlier seeds saved.

Each strategy gets the same number of distinct trained candidates. The winner is the
candidate with the lowest selection loss (size cost 0, so every strategy selects the same way);
its held-out test metrics are computed once. Test rows never enter training or selection.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np

STRATEGIES = ("grid", "random_mlp", "evolvo_mlp", "random_gfsl", "gfsl", "gfsl_reuse")
GRID = [(w, d, a) for a in ("silu", "tanh") for d in (1, 2, 3) for w in (6, 11, 23, 45)]
SCHEMA = "trech_search_comparison_v1"


def load_rows_table(path: Path, train: str, selection: str, test: str):
    """A rows table (``input_features``/``output_features``/``rows[{split, inputs, labels}]``)."""
    data = json.loads(Path(path).read_text())
    inputs, outputs = list(data["input_features"]), list(data["output_features"])
    split = {}
    for name in (train, selection, test):
        rows = [r for r in data["rows"] if r["split"] == name]
        if len(rows) < 2:
            raise ValueError(f"split {name!r} has fewer than two rows")
        x = np.array([r["inputs"] for r in rows], dtype=float)
        y = np.array([[r["labels"][o] for o in outputs] for r in rows], dtype=float)
        if not (np.all(np.isfinite(x)) and np.all(np.isfinite(y))):
            raise ValueError(f"split {name!r} has non-finite values")
        split[name] = (x, y, [r.get("id") for r in rows])
    ids = [set(split[n][2]) for n in (train, selection, test)]
    if (ids[0] & ids[1]) or (ids[0] & ids[2]) or (ids[1] & ids[2]):
        raise ValueError("train, selection and test rows must be disjoint")
    return inputs, outputs, split[train][:2], split[selection][:2], split[test][:2], data.get("schema")


class Recorder:
    """Wraps one TorchTask: counts distinct evaluations and epochs, enforces the budget."""

    def __init__(self, task, budget: int) -> None:
        object.__setattr__(self, "_task", task)
        object.__setattr__(self, "budget", budget)
        object.__setattr__(self, "trials", [])

    def __getattr__(self, name):
        return getattr(self._task, name)

    def __setattr__(self, name, value) -> None:
        setattr(self._task, name, value)

    def __call__(self, space, genome, info):
        if len(self.trials) >= self.budget:
            raise BudgetExhausted()
        result = self._task(space, genome, info)
        self.trials.append({"signature": space.signature(genome), "describe": space.describe(genome),
                            "loss": float(result["loss"]), "params": int(result["params"]),
                            "epochs": int(result.get("epochs", 0)), "stop_reason": result.get("stop_reason"),
                            "seconds": float(result.get("seconds", 0.0))})
        return result


class BudgetExhausted(Exception):
    """Not a RuntimeError: the searches treat those as failed candidates and keep going."""


def mlp_genome(nnarch, width: int, depth: int, act: str):
    return nnarch.ArchGenome.from_dict({"schema": "evolvo_arch_genome_v1", "rows": [["mlp", 0, -1, [width, depth, act]]]})


def _evaluate_list(space, recorder, genomes, seed: int) -> int:
    """Train listed genomes in order, skipping duplicates and genomes the space refuses
    (e.g. over the parameter budget); returns how many were refused."""
    seen, refused = set(), 0
    for index, genome in enumerate(genomes):
        try:
            signature = space.signature(genome)
            if signature in seen:
                continue
            seen.add(signature)
            recorder(space, genome, {"seed": seed * 1_000_003 + index, "signature": signature})
        except BudgetExhausted:
            break
        except ValueError:
            refused += 1
    return refused


def run_strategy(name: str, nnarch, make_space: Callable, make_task: Callable, budget: int, seed: int,
                 knowledge_load: Optional[Path] = None, knowledge_save: Optional[Path] = None) -> Dict:
    space = make_space()
    recorder = Recorder(make_task(), budget)
    rng = random.Random(f"{name}:{seed}")
    started = time.perf_counter()
    note, refused = None, 0
    if name == "grid":
        refused = _evaluate_list(space, recorder, [mlp_genome(nnarch, w, d, a) for w, d, a in GRID], seed)
    elif name == "random_mlp":
        ladder = [w for w in space.ladder if 4 <= w <= 128]
        acts = list(space.activations) if hasattr(space, "activations") else ["relu", "silu", "gelu", "tanh"]
        genomes = [mlp_genome(nnarch, rng.choice(ladder), rng.randint(1, 4), rng.choice(acts)) for _ in range(budget * 20)]
        refused = _evaluate_list(space, recorder, genomes, seed)
    elif name == "random_gfsl":
        chooser = nnarch.Chooser(rng)
        genomes = []
        for _ in range(budget * 40):
            try:
                genomes.append(space.random_genome(chooser))
            except ValueError:
                continue
        refused = _evaluate_list(space, recorder, genomes, seed)
    elif name == "evolvo_mlp":
        from .evolve_structure import search_structure
        ladder = [w for w in space.ladder if 4 <= w <= 128]
        counter = [0]

        def score(shape):
            width = min(ladder, key=lambda w: abs(w - shape.width))
            genome = mlp_genome(nnarch, width, min(shape.depth, 4), "silu")
            signature = space.signature(genome)
            done = next((t for t in recorder.trials if t["signature"] == signature), None)
            if done is not None:
                return done["loss"]
            counter[0] += 1
            # A ValueError (structure the space refuses) is a rejected candidate for the search.
            result = recorder(space, genome, {"seed": seed * 1_000_003 + counter[0], "signature": signature})
            return float(result["loss"])

        try:
            search_structure(score, seed=seed, generations=400, population=8, max_depth=4, max_width=128)
            note = "generation limit reached before the evaluation budget"
        except BudgetExhausted:
            pass
    elif name in ("gfsl", "gfsl_reuse"):
        loaded = None
        if name == "gfsl_reuse":
            if knowledge_load is None or not knowledge_load.exists():
                return {"strategy": name, "seed": seed, "skipped": "no knowledge saved by an earlier seed"}
            loaded = nnarch.Knowledge.load(knowledge_load)
        search = nnarch.ArchitectureSearch(space, recorder, seed=seed, population=8, size_cost=0.0, knowledge=loaded)
        try:
            # The recorder ends the search at the budget of distinct trained candidates
            # (cache hits do not count); generations and patience never stop it first.
            report = search.run(generations=1000, patience=1000)
            note = f"stop {report.get('stop_reason')}"
        except BudgetExhausted:
            note = "evaluation budget"
        if knowledge_save is not None:
            search.knowledge.save(knowledge_save)
    else:
        raise ValueError("unknown strategy " + name)
    trials = recorder.trials
    if not trials:
        raise RuntimeError(f"{name} trained no candidate")
    best_index = min(range(len(trials)), key=lambda i: trials[i]["loss"])
    return {"strategy": name, "seed": seed, "evaluations": len(trials), "epochs": sum(t["epochs"] for t in trials),
            "seconds": time.perf_counter() - started, "best": dict(trials[best_index], index=best_index),
            "module": recorder.best_module, "note": note, "refused_proposals": refused, "trials": trials,
            "loss_curve": [min(t["loss"] for t in trials[:k + 1]) for k in range(len(trials))]}


def test_metrics(module, x_test, y_test, scalers, outputs) -> Dict:
    import torch
    xm, xs, ym, ys = scalers
    with torch.no_grad():
        pred = module(torch.tensor((x_test - xm) / xs, dtype=torch.float32)).numpy() * ys + ym
    std_mse = float(np.mean(((pred - y_test) / ys) ** 2))
    r2 = {}
    for j, name in enumerate(outputs):
        ss_res = float(np.sum((pred[:, j] - y_test[:, j]) ** 2))
        ss_tot = float(np.sum((y_test[:, j] - y_test[:, j].mean()) ** 2))
        r2[name] = 1.0 - ss_res / ss_tot if ss_tot > 0 else None
    return {"mse_standardized": std_mse, "r2": r2, "rmse": {name: float(np.sqrt(np.mean((pred[:, j] - y_test[:, j]) ** 2)))
                                                            for j, name in enumerate(outputs)}}


def ridge_reference(x, y, x_val, y_val, x_test, y_test, scalers, outputs) -> Dict:
    """Closed-form ridge on standardized data, lambda picked on the selection split."""
    xm, xs, ym, ys = scalers
    a, b = (x - xm) / xs, (y - ym) / ys
    av, bv, at = (x_val - xm) / xs, (y_val - ym) / ys, (x_test - xm) / xs
    design = lambda m: np.hstack([m, np.ones((len(m), 1))])  # noqa: E731
    best = None
    for lam in (1e-4, 1e-3, 1e-2, 1e-1, 1, 10):
        reg = lam * np.eye(a.shape[1] + 1)
        reg[-1, -1] = 0
        w = np.linalg.solve(design(a).T @ design(a) + reg, design(a).T @ b)
        loss = float(np.mean((design(av) @ w - bv) ** 2))
        if best is None or loss < best[0]:
            best = (loss, lam, w)
    pred = design(at) @ best[2] * ys + ym
    r2 = {name: 1.0 - float(np.sum((pred[:, j] - y_test[:, j]) ** 2)) / float(np.sum((y_test[:, j] - y_test[:, j].mean()) ** 2))
          for j, name in enumerate(outputs)}
    return {"selection_loss": best[0], "lambda": best[1], "test": {"mse_standardized": float(np.mean(((pred - y_test) / ys) ** 2)), "r2": r2}}


def summarize(results: List[Dict]) -> Dict:
    out = {}
    for name in STRATEGIES:
        rows = [r for r in results if r["strategy"] == name and "skipped" not in r]
        if not rows:
            continue
        col = lambda f: [f(r) for r in rows]  # noqa: E731
        stat = lambda v: {"mean": float(np.mean(v)), "std": float(np.std(v)), "min": float(np.min(v)), "max": float(np.max(v))}  # noqa: E731
        out[name] = {"seeds": len(rows), "selection_loss": stat(col(lambda r: r["best"]["loss"])),
                     "test_mse_standardized": stat(col(lambda r: r["test"]["mse_standardized"])),
                     "evaluations": stat(col(lambda r: r["evaluations"])), "epochs": stat(col(lambda r: r["epochs"])),
                     "seconds": stat(col(lambda r: r["seconds"])), "best_params": stat(col(lambda r: r["best"]["params"])),
                     "evaluations_to_within_5pct": stat(col(lambda r: next(
                         k + 1 for k, v in enumerate(r["loss_curve"]) if v <= 1.05 * r["loss_curve"][-1])))}
    # Paired by seed against grid: log test MSE difference (negative = better than grid).
    grid = {r["seed"]: r for r in results if r["strategy"] == "grid" and "skipped" not in r}
    for name, entry in out.items():
        pairs = [(math.log(r["test"]["mse_standardized"]) - math.log(grid[r["seed"]]["test"]["mse_standardized"]),
                  math.log(r["best"]["loss"]) - math.log(grid[r["seed"]]["best"]["loss"]))
                 for r in results if r["strategy"] == name and "skipped" not in r and r["seed"] in grid]
        if name == "grid" or len(pairs) < 2:
            continue
        test_d, sel_d = np.array([p[0] for p in pairs]), np.array([p[1] for p in pairs])
        entry["vs_grid"] = {"seeds": len(pairs),
                            "log_test_mse_diff": {"mean": float(test_d.mean()), "se": float(test_d.std(ddof=1) / math.sqrt(len(pairs)))},
                            "log_selection_loss_diff": {"mean": float(sel_d.mean()), "se": float(sel_d.std(ddof=1) / math.sqrt(len(pairs)))},
                            "seeds_better_on_test": int((test_d < 0).sum())}
    return out


def compare(x, y, x_val, y_val, x_test, y_test, outputs, *, strategies: Sequence[str] = STRATEGIES,
            seeds: Sequence[int] = (0, 1, 2), budget: int = 24, max_params: int = 20000, max_rows: int = 4,
            lr: float = 3e-3, hard_max_epochs: int = 1500, knowledge: Optional[Path] = None, log=print) -> Dict:
    import torch
    from .evolve_architecture import _scalers, evolvo_nnarch
    nnarch = evolvo_nnarch()
    from evolvo.nnarch.train import TorchTask
    scalers = _scalers(x, y)
    xm, xs, ym, ys = scalers
    t = lambda a: torch.tensor(a, dtype=torch.float32)  # noqa: E731
    train = (t((x - xm) / xs), t((y - ym) / ys))
    val = (t((x_val - xm) / xs), t((y_val - ym) / ys))
    make_space = lambda: nnarch.ArchSpace([("vec", x.shape[1])], y.shape[1], max_rows=max_rows,  # noqa: E731
                                          max_params=max_params, width_window=(4, 128),
                                          task={"t_n": nnarch.log_bucket(len(x), 1)})
    make_task = lambda: TorchTask(train, val, lr=lr, hard_max_epochs=hard_max_epochs)  # noqa: E731
    # gfsl saves its knowledge per seed; gfsl_reuse at a seed loads the previous seed's, so a
    # reuse run never sees knowledge from its own seed's search.
    path = lambda s: None if knowledge is None else knowledge.with_name(f"{knowledge.stem}.seed{s}.json")  # noqa: E731
    for s in seeds:
        if path(s) is not None and path(s).exists():
            path(s).unlink()
    results = []
    for k, seed in enumerate(seeds):
        torch.manual_seed(seed)
        for name in strategies:
            r = run_strategy(name, nnarch, make_space, make_task, budget, seed,
                             knowledge_load=path(seeds[k - 1]) if k else None,
                             knowledge_save=path(seed) if name == "gfsl" else None)
            if "skipped" not in r:
                r["test"] = test_metrics(r.pop("module"), x_test, y_test, scalers, outputs)
                log(f"seed {seed} {name:12s} evals {r['evaluations']:3d} epochs {r['epochs']:6d} "
                    f"sel {r['best']['loss']:.5f} test {r['test']['mse_standardized']:.5f} "
                    f"({r['best']['params']} params, {r['seconds']:.0f} s) {' '.join(r['best']['describe'])[:80]}")
            results.append(r)
    return {"results": results, "summary": summarize(results),
            "ridge": ridge_reference(x, y, x_val, y_val, x_test, y_test, scalers, outputs)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--table", type=Path, required=True, help="rows table with input/output features and splits")
    parser.add_argument("--train-split", default="train")
    parser.add_argument("--selection-split", default="development")
    parser.add_argument("--test-split", default="test")
    parser.add_argument("--strategies", default=",".join(STRATEGIES))
    parser.add_argument("--seeds", default="0,1,2")
    parser.add_argument("--budget", type=int, default=24, help="distinct trained candidates per strategy and seed")
    parser.add_argument("--max-params", type=int, default=20000)
    parser.add_argument("--max-rows", type=int, default=4)
    parser.add_argument("--max-epochs", type=int, default=1500)
    parser.add_argument("--lr", type=float, default=3e-3)
    parser.add_argument("--knowledge", type=Path, help="scratch knowledge file for gfsl_reuse (rewritten)")
    parser.add_argument("--keep-trials", action="store_true", help="keep every trained candidate in the report")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    strategies = [s.strip() for s in args.strategies.split(",") if s.strip()]
    unknown = [s for s in strategies if s not in STRATEGIES]
    if unknown or args.budget < 1:
        parser.error("unknown strategies " + ",".join(unknown) if unknown else "budget must be positive")
    inputs, outputs, (x, y), (xv, yv), (xt, yt), schema = load_rows_table(args.table, args.train_split, args.selection_split, args.test_split)
    knowledge = args.knowledge or args.out.with_suffix(".knowledge.json")
    started = time.perf_counter()
    out = compare(x, y, xv, yv, xt, yt, outputs, strategies=strategies, seeds=[int(s) for s in args.seeds.split(",") if s.strip()],
                  budget=args.budget, max_params=args.max_params, max_rows=args.max_rows, lr=args.lr,
                  hard_max_epochs=args.max_epochs, knowledge=knowledge if "gfsl_reuse" in strategies else None)
    if not args.keep_trials:
        for r in out["results"]:
            r.pop("trials", None)
    from .train_surrogate import _portable_path
    report = {"schema": SCHEMA, "table": _portable_path(args.table), "table_schema": schema,
              "inputs": inputs, "outputs": outputs,
              "rows": {"train": len(x), "selection": len(xv), "test": len(xt)},
              "protocol": {"trainer": "evolvo.nnarch.train.TorchTask (shared by every strategy)",
                           "budget_distinct_candidates": args.budget, "max_params": args.max_params, "max_rows": args.max_rows,
                           "hard_max_epochs": args.max_epochs, "lr": args.lr, "size_cost": 0.0,
                           "selection": "lowest selection-split MSE in training-standardized outputs",
                           "test": "computed once per strategy and seed for its selected candidate",
                           "grid": [list(g) for g in GRID]},
              "strategies": strategies, "seconds": time.perf_counter() - started, **out}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=1, default=float) + "\n")
    print(json.dumps(report["summary"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
