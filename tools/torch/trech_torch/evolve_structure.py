"""Evolvo search over bounded MLP structure, selected and tested on separate runs.

Search is offline. Only the exported, held-out-tested GenericSurrogate enters
TRECH inference; genetic candidates never become Geant4 truth.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
from pathlib import Path
import random
import sys
import time
from typing import Callable

import numpy as np


@dataclass(frozen=True)
class Structure:
    width: int
    depth: int

    def parameter_count(self, inputs: int, outputs: int) -> int:
        return ((inputs + 1) * self.width + (self.depth - 1) *
                (self.width + 1) * self.width + (self.width + 1) * outputs)


def search_structure(score: Callable[[Structure], float], *, seed: int = 1234,
                     generations: int = 8, population: int = 12,
                     max_depth: int = 16, max_width: int = 128,
                     seconds: float = 0.0) -> dict:
    """Minimize a caller's measured validation loss; finite bounded definitions.

    Zero seconds means fixed work. A positive budget stops between candidates;
    candidate evaluation is atomic. The returned loss is selection data, never
    an independent test metric. Callback failures reject that candidate.
    """
    if min(generations, population, max_depth, max_width) < 1 or not math.isfinite(seconds) or seconds < 0:
        raise ValueError("search bounds must be positive; seconds must be finite and non-negative")
    if not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a non-negative integer")
    source = Path(__file__).resolve().parents[3] / "thirds" / "evolvo" / "src"
    if source.is_dir() and str(source) not in sys.path:
        sys.path.insert(0, str(source))
    try:
        from evolvo import DataType, GFSLExecutor, GFSLEvolver, GFSLGenome, Operation
    except ImportError as exc:
        raise RuntimeError("Initialize thirds/evolvo with git submodule update --init thirds/evolvo") from exc

    random_state, numpy_state = random.getstate(), np.random.get_state()
    random.seed(seed)
    np.random.seed(seed % 2**32)
    started = time.monotonic()
    cache = {}
    best = None
    rejected = 0
    executor = GFSLExecutor(compute_backend="cpu")
    # Decode only straight-line decimal definitions. Reject control flow before
    # execution so search can never spend its budget in an evolved loop.
    allowed = {Operation.ADD, Operation.SUB, Operation.MUL, Operation.DIV,
               Operation.ABS, Operation.SQRT, Operation.MOD, Operation.SIN, Operation.COS}
    try:
        evolver = GFSLEvolver(population_size=max(2, population), max_instruction_count=32)
        for _ in range(max(2, population)):
            genome = GFSLGenome("algorithm")
            for index in range(2):
                value = random.choice([0.0, 0.5, 1.0, 2.0, 3.14159, 10.0])
                (genome.expression().target_var(DataType.DECIMAL, index)
                 .op(Operation.ADD).source1_value(value).source2_value(0.0).commit())
                genome.mark_output(DataType.DECIMAL, index)
            evolver.population.append(genome)

        def evaluate(genome):
            nonlocal best, rejected
            if seconds and cache and time.monotonic() - started >= seconds:
                return 1e-100
            try:
                if any(instr.operation not in allowed for instr in genome.instructions):
                    return 1e-100
                values = executor.execute(genome)
                width, depth = float(values["d$0"]), float(values["d$1"])
                if not math.isfinite(width) or not math.isfinite(depth):
                    return 1e-100
                shape = Structure(max(1, min(max_width, round(abs(width) * 16))),
                                  max(1, min(max_depth, round(abs(depth)) + 1)))
                if shape not in cache:
                    loss = float(score(shape))
                    if not math.isfinite(loss) or loss < 0:
                        raise ValueError("score must be a finite non-negative loss")
                    cache[shape] = loss
                loss = cache[shape]
                if best is None or loss < best[0]:
                    best = (loss, shape, genome.get_signature())
                return 1.0 / (1.0 + loss)
            except (ValueError, TypeError, KeyError, OverflowError, RuntimeError):
                rejected += 1
                return 1e-100

        evolver.evolve(generations, evaluate,
                       should_stop=lambda *_: bool(seconds and time.monotonic() - started >= seconds))
        if best is None:
            raise RuntimeError("No valid structure was evaluated")
        elapsed = time.monotonic() - started
        return {"backend": "evolvo", "seed": seed, "width": best[1].width,
                "depth": best[1].depth, "selection_loss": best[0],
                "generations": generations, "population": max(2, population),
                "genome_signature": best[2], "evaluated_structures": len(cache),
                "rejected_candidates": rejected, "max_depth": max_depth,
                "max_width": max_width, "stop_reason":
                "time_budget" if seconds and elapsed >= seconds else "generation_limit",
                "time_budget_seconds": seconds}
    finally:
        random.setstate(random_state)
        np.random.set_state(numpy_state)


def main(argv=None) -> int:
    from .dataset import harvest_table
    from .train_surrogate import (build_xy, fit_mlp, _mlp_layers_json, predict_np,
                                  evaluate, input_domain, holdout_block, write_generic_json,
                                  _portable_path)
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", nargs="+", required=True)
    parser.add_argument("--validation-runs", nargs="+", required=True)
    parser.add_argument("--test-runs", nargs="+", required=True)
    parser.add_argument("--inputs", required=True)
    parser.add_argument("--outputs", required=True)
    parser.add_argument("--source", choices=["scores", "event_features", "hook_emits"], default="scores")
    parser.add_argument("--tag")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--generations", type=int, default=8)
    parser.add_argument("--population", type=int, default=12)
    parser.add_argument("--max-depth", type=int, default=16)
    parser.add_argument("--max-width", type=int, default=128)
    parser.add_argument("--max-parameters", type=int, default=200000)
    parser.add_argument("--time-budget", type=float, default=0)
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument("--out-json", required=True)
    args = parser.parse_args(argv)
    if args.epochs < 1 or args.max_parameters < 1:
        parser.error("epochs and max-parameters must be positive")
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
    scale = np.maximum(y.std(axis=0), 1e-12)
    best = {}

    def score(shape):
        count = shape.parameter_count(len(inputs), len(outputs))
        if count > args.max_parameters:
            raise ValueError("parameter budget")
        net, scalers = fit_mlp(x, y, shape.width, args.epochs, 0.01, args.seed,
                               depth=shape.depth, quiet=True)
        layers = _mlp_layers_json(net)
        residual = (predict_np(x_val, layers, scalers) - y_val) / scale
        loss = float(np.mean(residual ** 2))
        if not math.isfinite(loss):
            raise ValueError("candidate produced non-finite validation loss")
        if not best or loss < best["loss"]:
            best.update(loss=loss, layers=layers, scalers=scalers)
        return loss

    report = search_structure(score, seed=args.seed, generations=args.generations,
                              population=args.population, max_depth=args.max_depth,
                              max_width=args.max_width, seconds=args.time_budget)
    report["selection_objective"] = "mean_squared_error_in_training_standardized_outputs"
    report["parameter_count"] = Structure(report["width"], report["depth"]).parameter_count(len(inputs), len(outputs))
    layers, scalers = best["layers"], best["scalers"]
    metrics = evaluate(y_test, predict_np(x_test, layers, scalers), outputs)
    meta = {"runs": [_portable_path(m.run_dir) for m in metadata[0]],
            "selection_runs": [_portable_path(m.run_dir) for m in metadata[1]],
            "test_runs": [_portable_path(m.run_dir) for m in metadata[2]],
            "structure_search": report, "source": args.source, "tag": args.tag,
            "seed": args.seed, "epochs": args.epochs, "max_parameters": args.max_parameters}
    path = Path(args.out_json).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    write_generic_json(path, inputs, outputs, scalers, layers, meta,
                       domain=input_domain(x, scalers),
                       scale_bands=sorted({m.dimension_scale for m in metadata[0]
                                           if m.dimension_scale not in ("", "unknown")}),
                       holdout=holdout_block(metrics, len(x_test)),
                       note={"description": "Evolvo-selected structure; accuracy measured on untouched test runs"})
    print(json.dumps({"model": str(path), "search": report, "metrics_test": metrics}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
