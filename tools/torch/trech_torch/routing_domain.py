"""Measure a model's ``routing_domain`` from the rows it was (or would be) trained on.

Domain routing (``include/trech/ml/DomainRouting.hpp``) lets the engine decide, per element and
band by band, which of several rival laws applies, without labels. It uses each law's own input
coverage, but laws often read the same inputs over overlapping ranges: what separated their
training populations was a per-element fact the law does not consume (a phase fraction, a
composition ratio). This tool measures, from the harvested training rows, the range of such facts
and writes it into the model as

    "routing_domain": {"features": [...], "min": [...], "max": [...], "scale": [...],
                       "n_rows": N, "source": {...}}

``scale`` is the rows' standard deviation (floored at 1 % of the span, or 1e-9 when constant), so
the engine measures a gap element's overflow in units of the population's own spread. The block
is measured, never authored: every number comes from the rows, and the source runs, tag and
row count are recorded beside it. The model's weights and every other key are left unchanged.

    trech-measure-routing-domain --runs build/glass_routing/run_* --source hook_emits \\
        --tag thermal_sample_melt --expand samples --features melt_fraction,glass_silica_fraction \\
        --model data/glass_furnace_operators_trained/thermal_melt.json
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from .dataset import harvest_table

SCHEMAS = ("generic_surrogate_v1", "generic_surrogate_v2", "generic_surrogate_v3")


def _portable(path: str) -> str:
    """A run path relative to the working directory when it lies inside it (no home paths)."""
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return resolved.name


def measure(rows: Sequence[Dict[str, float]], features: Sequence[str]) -> dict:
    """Min/max/scale of each feature over the rows that carry all of them."""
    usable = [row for row in rows if all(isinstance(row.get(f), (int, float)) and math.isfinite(row[f])
                                         for f in features)]
    if not usable:
        raise ValueError(f"no row carries every routing feature {list(features)}")
    block = {"features": list(features), "min": [], "max": [], "scale": [], "n_rows": len(usable)}
    for feature in features:
        values = [float(row[feature]) for row in usable]
        lo, hi = min(values), max(values)
        mean = sum(values) / len(values)
        sd = math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))
        block["min"].append(lo)
        block["max"].append(hi)
        block["scale"].append(max(sd, 0.01 * (hi - lo), 1e-9))
    return block


def write_block(model_path: Path, block: dict) -> None:
    data = json.loads(model_path.read_text(encoding="utf-8"))
    if data.get("model") not in SCHEMAS:
        raise ValueError(f"{model_path} is not a generic_surrogate model")
    overlap = sorted(set(block["features"]) & set(data.get("input_features") or []))
    if overlap:
        raise ValueError(f"routing features {overlap} are already inputs of {model_path}; "
                         "input coverage covers them")
    data["routing_domain"] = block
    model_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", nargs="+", required=True, help="run directories or globs")
    parser.add_argument("--source", default="hook_emits", choices=["hook_emits", "scores", "event_features"])
    parser.add_argument("--tag")
    parser.add_argument("--expand")
    parser.add_argument("--features", required=True, help="comma-separated per-element fact names")
    parser.add_argument("--model", nargs="+", required=True, help="model JSON file(s) to annotate")
    parser.add_argument("--dry-run", action="store_true", help="print the block, write nothing")
    args = parser.parse_args(argv)
    features = [f.strip() for f in args.features.split(",") if f.strip()]
    rows, metas = harvest_table(args.runs, source=args.source, tag=args.tag, expand=args.expand)
    block = measure(rows, features)
    block["source"] = {"runs": sorted(_portable(m.run_dir) for m in metas), "source": args.source,
                       "tag": args.tag, "expand": args.expand}
    print(json.dumps(block, indent=2))
    if not args.dry_run:
        for model in args.model:
            write_block(Path(model), block)
            print(f"wrote routing_domain into {model}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
