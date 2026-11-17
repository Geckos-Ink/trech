"""Evolvo GFSL-NN architecture search for a TRECH surrogate (offline tooling).

The model's *architecture* is a genome of the Evolvo GFSL-NN language (``thirds/evolvo``,
``papers/GFSL-NN.md``): primitives and macros (``mlp``, ``resmlp``, ``transformer`` over feature
tokens, ...) with enumerated arguments, valid by construction. The search learns slot weights,
size pressure and epoch stopping while it runs. ``--knowledge`` keeps those learned tendencies
across searches.

Splits follow the surrogate discipline: train on ``--runs``, select architectures (and stop
epochs) on ``--validation-runs``, report accuracy on untouched ``--test-runs``. The three sets
must be disjoint.

Export (honest about who can run it):

* a **dense chain** (linear/act/dropout only, activations silu/tanh/relu/sigmoid) becomes a
  ``generic_surrogate_v1`` JSON that the C++ engine runs natively, plus a TorchScript twin;
* anything else (attention, residuals, gates, GELU, set tokens) is exported only as
  TorchScript ``<out>.pt`` with its ``.pt.io.json`` sidecar. It needs an engine built with
  ``TRECH_ENABLE_TORCH``. Its metadata record ``<out>.arch.json`` (schema
  ``trech_evolved_arch_v1``) is deliberately not a loadable surrogate.

Genetic candidates are learned predictions selected on validation runs, never Geant4 truth.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

REPO = Path(__file__).resolve().parents[3]
DENSE_ACTIVATIONS = ("silu", "tanh", "relu", "sigmoid")
# Ops whose architectures can lower to a dense chain the C++ engine runs without LibTorch.
NATIVE_OPS = ("linear", "act", "dropout", "mlp")
ARCH_SCHEMA = "trech_evolved_arch_v1"


def evolvo_nnarch():
    """Import ``evolvo.nnarch`` from the pinned submodule (pull it first: AGENTS Evolvo workflow)."""
    source = REPO / "thirds" / "evolvo" / "src"
    if source.is_dir() and str(source) not in sys.path:
        sys.path.insert(0, str(source))
    try:
        import evolvo.nnarch as nnarch  # noqa: F401
        from evolvo.nnarch import build, train  # noqa: F401
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Initialize thirds/evolvo (git submodule update --init thirds/evolvo) "
                           "and install torch") from exc
    return nnarch


def _scalers(x: np.ndarray, y: np.ndarray):
    from .train_surrogate import _standardize

    xm, xs = _standardize(x)
    ym, ys = _standardize(y)
    return xm, xs, ym, ys


def search_architecture(
    x: np.ndarray, y: np.ndarray, x_val: np.ndarray, y_val: np.ndarray, *,
    max_rows: int = 6, max_params: int = 50_000, generations: int = 12, population: int = 10,
    patience: int = 4, max_evaluations: Optional[int] = None, seconds: float = 0.0, seed: int = 0,
    size_cost: float = 0.03, lr: float = 3e-3, weight_decay: float = 0.0,
    batch_size: Optional[int] = None, hard_max_epochs: int = 1000, ops: Optional[Sequence[str]] = None,
    knowledge_path: Optional[Path] = None, quiet: bool = True,
    seeds: Sequence[dict] = (), native_only: bool = False,
) -> Dict:
    """Search, train and return the best module with its genome, scalers and report.

    Inputs and targets are standardized with the training split's scalers, so losses are
    mean-squared errors in training-standardized units. ``seeds`` are genome dicts
    (``evolvo_arch_genome_v1``) evaluated first, e.g. the engine's classic reference family;
    the width window is widened to hold their widths so they enter unchanged.

    ``native_only`` serves an engine without LibTorch: the language is restricted to
    ``NATIVE_OPS`` and the activations the C++ loader evaluates, and the exported candidate is
    the best-scoring *dense chain* trained (its own weights, no retraining). The overall best
    stays in the report for comparison.
    """
    import torch

    arch = evolvo_nnarch()
    from evolvo.nnarch.train import TorchTask

    for name, a in (("x", x), ("y", y), ("x_val", x_val), ("y_val", y_val)):
        if a.ndim != 2 or len(a) < 2 or not np.all(np.isfinite(a)):
            raise ValueError(f"{name} must be a finite 2-D array with at least two rows")
    scalers = _scalers(x, y)
    xm, xs, ym, ys = scalers
    t = lambda a: torch.tensor(a, dtype=torch.float32)  # noqa: E731
    train = (t((x - xm) / xs), t((y - ym) / ys))
    val = (t((x_val - xm) / xs), t((y_val - ym) / ys))
    knowledge = None
    if knowledge_path is not None and Path(knowledge_path).exists():
        knowledge = arch.Knowledge.load(knowledge_path)
    extra = {}
    if native_only:
        ops = [o for o in (ops or NATIVE_OPS) if o in NATIVE_OPS]
        if not ops:
            raise ValueError("native_only leaves no op: allow some of " + ", ".join(NATIVE_OPS))
        extra["activations"] = DENSE_ACTIVATIONS
    space = arch.ArchSpace([("vec", x.shape[1])], y.shape[1], max_rows=max_rows, max_params=max_params,
                           ops=ops, task={"t_n": arch.log_bucket(len(x), 1)}, **extra)
    seed_genomes = [arch.ArchGenome.from_dict(g) for g in seeds]
    for genome in seed_genomes:
        for row in genome.rows:
            spec = space.registry.get(row.op) if row.op in space.registry else None
            for arg, value in zip(spec.args if spec else (), row.args):
                if arg.domain == "width" and value in space.ladder:
                    k = space.ladder.index(value)
                    space.window = [min(space.window[0], k), max(space.window[1], k)]
    task = TorchTask(train, val, lr=lr, weight_decay=weight_decay, batch_size=batch_size,
                     hard_max_epochs=hard_max_epochs)
    keeper = _NativeKeeper(task, size_cost) if native_only else None
    search = arch.ArchitectureSearch(space, keeper or task, seed=seed, population=population,
                                     size_cost=size_cost, knowledge=knowledge)
    progress = None if quiet else (lambda g: print(
        f"  gen {g['generation']}: best val loss {g['best_loss']:.5g} ({g['best_params']} params)",
        flush=True))
    report = search.run(generations=generations, patience=patience, max_evaluations=max_evaluations,
                        seconds=seconds, progress=progress, seeds=seed_genomes)
    if report["best"] is None or task.best_module is None:
        raise RuntimeError("no architecture trained to a finite validation loss")
    if keeper is not None:
        if keeper.best is None:
            raise RuntimeError("no engine-native (dense chain) architecture trained to a finite loss")
        score, loss, params, genome, module = keeper.best
        report["native_best"] = {"signature": space.signature(genome), "loss": loss, "params": params,
                                 "score": score, "describe": space.describe(genome)}
        if knowledge_path is not None:
            search.knowledge.save(knowledge_path)
        return {"module": module, "genome": genome, "space": space, "scalers": scalers, "report": report,
                "selected": {**report["native_best"], "genome": genome.to_dict(), "engine_native": True}}
    best = arch.ArchGenome.from_dict(report["best"]["genome"])
    module = task.best_module
    if space.signature(best) != task.best_signature:
        # The size-penalized winner is not the lowest-loss module the task kept: retrain it
        # with the winner's own seed so the exported weights are the selected architecture's.
        index = report["best"]["index"]
        retrain = TorchTask(train, val, lr=lr, weight_decay=weight_decay, batch_size=batch_size,
                            hard_max_epochs=hard_max_epochs, epoch_stats=search.knowledge.epochs)
        again = retrain(space, best, {"seed": seed * 1_000_003 + index, "signature": space.signature(best)})
        module = retrain.best_module
        report["best"]["retrained_for_export"] = True
        report["best"]["retrain_loss"] = again["loss"]
    if knowledge_path is not None:
        search.knowledge.save(knowledge_path)
    selected = {"signature": report["best"]["signature"], "loss": report["best"].get("retrain_loss", report["best"]["loss"]),
                "params": report["best"]["params"], "score": report["best"]["score"],
                "describe": report["best"]["describe"], "genome": report["best"]["genome"],
                "engine_native": is_dense_chain(space, best)}
    return {"module": module, "genome": best, "space": space, "scalers": scalers, "report": report,
            "selected": selected}


class _NativeKeeper:
    """Evaluator wrapper that keeps the best-scoring dense-chain candidate's trained module."""

    def __init__(self, task, size_cost: float) -> None:
        self.task = task
        self.size_cost = size_cost
        self.best = None  # (score, loss, params, genome, module)

    @property
    def epoch_stats(self):
        return self.task.epoch_stats

    @epoch_stats.setter
    def epoch_stats(self, value):
        self.task.epoch_stats = value

    def __call__(self, space, genome, info):
        result = self.task(space, genome, info)
        loss, params = result.get("loss", math.inf), result.get("params", 0)
        if math.isfinite(loss) and params > 0 and is_dense_chain(space, genome):
            score = math.log(max(loss, 1e-12)) + self.size_cost * math.log(params)
            if self.best is None or (score, params) < (self.best[0], self.best[2]):
                self.best = (score, loss, params, genome.copy(), self.task.last_module)
        return result


def _dense_plan(graph) -> Optional[List[tuple]]:
    """[(linear node, activation)] when the lowered graph is a plain dense chain, else None."""
    plan: List[list] = []
    previous = graph.inputs[0]
    for i, node in enumerate(graph.nodes):
        if node.op == "input":
            continue
        if node.srcs[0] != previous or node.op not in ("linear", "act", "dropout"):
            return None
        previous = i
        if node.op == "dropout":
            continue
        if node.op == "act":
            if not plan or plan[-1][1] != "none" or node.args["fn"] not in DENSE_ACTIVATIONS:
                return None
            plan[-1][1] = node.args["fn"]
            continue
        plan.append([i, "none"])
    if previous != graph.output or graph.head_pool:
        return None
    return [tuple(p) for p in plan]


def is_dense_chain(space, genome) -> bool:
    return _dense_plan(space.lower(genome)) is not None


def dense_layers(space, genome, module) -> Optional[List[dict]]:
    """``generic_surrogate_v1`` layers when the architecture is a plain dense chain, else None."""
    plan = _dense_plan(space.lower(genome))
    if plan is None:
        return None
    layers: List[dict] = []
    for i, activation in plan:
        lin = module.layers[f"n{i}"]
        layers.append({"weights": lin.weight.detach().cpu().double().numpy().tolist(),
                       "bias": lin.bias.detach().cpu().double().numpy().tolist(), "activation": activation})
    layers.append({"weights": module.head.weight.detach().cpu().double().numpy().tolist(),
                   "bias": module.head.bias.detach().cpu().double().numpy().tolist(), "activation": "none"})
    return layers


def predict(module, x: np.ndarray, scalers) -> np.ndarray:
    import torch

    xm, xs, ym, ys = scalers
    module.eval()
    with torch.no_grad():
        out = module(torch.tensor((x - xm) / xs, dtype=torch.float32)).double().numpy()
    return out * ys + ym


def export(out: Path, found: Dict, inputs: List[str], outputs: List[str], x_train: np.ndarray, *,
           meta: dict, holdout: Optional[dict] = None, scale_bands: Optional[List[str]] = None) -> Dict[str, str]:
    """Write the native JSON (dense chains) or the arch record, plus TorchScript + sidecar."""
    import torch

    from .torchscript_io import write_torchscript_io
    from .train_surrogate import export_torchscript, input_domain, write_generic_json

    evolvo_nnarch()
    from evolvo.nnarch.build import trace_module

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    module, genome, space, scalers = found["module"], found["genome"], found["space"], found["scalers"]
    domain = input_domain(x_train, scalers)
    layers = dense_layers(space, genome, module)
    paths: Dict[str, str] = {}
    note = {"description": "Evolvo GFSL-NN architecture; selected on validation runs, accuracy on "
                           "untouched test runs; a learned prediction, not a Geant4 tally"}
    meta = {**meta, "genome": genome.to_dict(), "architecture": space.describe(genome)}
    if layers is not None:
        twin = out.with_suffix(".json")
        write_generic_json(twin, inputs, outputs, scalers, layers, meta, domain=domain,
                           scale_bands=scale_bands, holdout=holdout, note=note)
        paths["json"] = str(twin)
    else:
        twin = out.with_suffix(".arch.json")
        record = {"schema": ARCH_SCHEMA, "input_features": list(inputs), "output_features": list(outputs),
                  "runtime": "torchscript", "trained_from": meta, "input_domain": domain, "note": note}
        if holdout is not None:
            record["holdout"] = holdout
        if scale_bands:
            record["trained_scale_bands"] = list(scale_bands)
        twin.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        paths["arch"] = str(twin)
    example = torch.zeros(2, len(inputs))
    traced = trace_module(module, [example])
    pt = out.with_suffix(".pt")
    if not export_torchscript(traced, scalers, pt):
        raise RuntimeError("TorchScript export failed")
    paths["torchscript"] = str(pt)
    paths["sidecar"] = str(write_torchscript_io(pt, twin))
    return paths


def main(argv=None) -> int:
    from .dataset import harvest_table
    from .train_surrogate import _portable_path, build_xy, evaluate, holdout_block

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", nargs="+", required=True)
    parser.add_argument("--validation-runs", nargs="+", required=True)
    parser.add_argument("--test-runs", nargs="+", required=True)
    parser.add_argument("--inputs", required=True)
    parser.add_argument("--outputs", required=True)
    parser.add_argument("--source", choices=["scores", "event_features", "hook_emits"], default="scores")
    parser.add_argument("--tag")
    parser.add_argument("--generations", type=int, default=12)
    parser.add_argument("--population", type=int, default=10)
    parser.add_argument("--patience", type=int, default=4, help="generations without gain before stopping")
    parser.add_argument("--max-evaluations", type=int)
    parser.add_argument("--time-budget", type=float, default=0.0)
    parser.add_argument("--max-rows", type=int, default=6)
    parser.add_argument("--max-params", type=int, default=50_000)
    parser.add_argument("--size-cost", type=float, default=0.03,
                        help="score = ln(loss) + size_cost * ln(params)")
    parser.add_argument("--ops", help="comma list of allowed ops/macros (default: all)")
    parser.add_argument("--lr", type=float, default=3e-3)
    parser.add_argument("--weight-decay", type=float, default=0.0)
    parser.add_argument("--batch-size", type=int)
    parser.add_argument("--max-epochs", type=int, default=1000, help="hard cap; stopping is learned")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--knowledge", help="JSON of learned tendencies to start from and update")
    parser.add_argument("--out", required=True, help="output path prefix (.json/.arch.json/.pt)")
    parser.add_argument("--report", help="write the full search report here")
    args = parser.parse_args(argv)
    inputs, outputs = args.inputs.split(","), args.outputs.split(",")
    splits, metadata, seen = [], [], set()
    for paths in (args.runs, args.validation_runs, args.test_runs):
        rows, metas = harvest_table(paths, source=args.source, tag=args.tag)
        run_ids = {str(Path(m.run_dir).resolve()) for m in metas}
        if seen & run_ids:
            parser.error("training, selection and test runs must be disjoint")
        seen |= run_ids
        x, y, _ = build_xy(rows, inputs, outputs)
        if len(x) < 2 or not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
            parser.error("each split needs at least two complete, finite rows")
        splits.append((x, y))
        metadata.append(metas)
    (x, y), (x_val, y_val), (x_test, y_test) = splits
    found = search_architecture(
        x, y, x_val, y_val, max_rows=args.max_rows, max_params=args.max_params,
        generations=args.generations, population=args.population, patience=args.patience,
        max_evaluations=args.max_evaluations, seconds=args.time_budget, seed=args.seed,
        size_cost=args.size_cost, lr=args.lr, weight_decay=args.weight_decay, batch_size=args.batch_size,
        hard_max_epochs=args.max_epochs, ops=args.ops.split(",") if args.ops else None,
        knowledge_path=Path(args.knowledge) if args.knowledge else None, quiet=False)
    metrics = evaluate(y_test, predict(found["module"], x_test, found["scalers"]), outputs)
    report = found["report"]
    meta = {"runs": [_portable_path(m.run_dir) for m in metadata[0]],
            "selection_runs": [_portable_path(m.run_dir) for m in metadata[1]],
            "test_runs": [_portable_path(m.run_dir) for m in metadata[2]],
            "architecture_search": {k: report[k] for k in ("schema", "seed", "stop_reason", "evaluations",
                                                           "unique_architectures", "size_cost")},
            "selection_loss": report["best"]["loss"],
            "selection_objective": "mean_squared_error_in_training_standardized_outputs",
            "parameter_count": report["best"]["params"], "source": args.source, "tag": args.tag}
    bands = sorted({m.dimension_scale for m in metadata[0] if m.dimension_scale not in ("", "unknown")})
    paths = export(Path(args.out), found, inputs, outputs, x, meta=meta,
                   holdout=holdout_block(metrics, len(x_test)), scale_bands=bands)
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2, default=float) + "\n", encoding="utf-8")
    print(json.dumps({"paths": paths, "architecture": report["best"]["describe"],
                      "metrics_test": metrics, "stop_reason": report["stop_reason"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
