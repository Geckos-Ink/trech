#!/usr/bin/env python3
"""Evaluate a scenario bundle's declared output and family checks against an existing run.

With ``--sweep CASE --run ID=DIR ...`` it instead grades the multi-run
``family_sweeps`` gate CASE over the given run directories (the positional
output is then omitted); every declared run id must be mapped or its checks fail.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "validation"))
from trech_validation.declarative import evaluate_contracts, evaluate_sweep  # noqa: E402


def evaluate(contracts: dict, output: Path, include_family: bool = True) -> list[dict]:
    """Return explicit pass/fail records. Absent files/fields never silently pass."""
    results = evaluate_contracts(contracts, output, include_family=include_family)
    if not any("family_case" not in result for result in results):
        raise ValueError("scenario declares no output checks")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", type=Path)
    parser.add_argument("output", type=Path, nargs="?")
    parser.add_argument("--trech", type=Path, default=Path("build/dev/trech"))
    parser.add_argument("--param", action="append", default=[])
    parser.add_argument("--output-only", action="store_true",
                        help="Skip exported family checks; grade output integrity only.")
    parser.add_argument("--sweep", metavar="CASE", help="Grade the family_sweeps gate CASE.")
    parser.add_argument("--run", action="append", default=[], metavar="ID=DIR",
                        help="Map a declared sweep run id to its output directory (repeatable).")
    args = parser.parse_args()
    if (args.sweep is None) == (args.output is None):
        parser.error("give either an output directory or --sweep CASE with --run ID=DIR")
    if args.sweep is None and args.run:
        parser.error("--run applies only with --sweep")
    runs = {}
    for item in args.run:
        run_id, sep, directory = item.partition("=")
        if not sep or not run_id or not directory or run_id in runs:
            parser.error(f"invalid or duplicate --run {item!r}")
        runs[run_id] = Path(directory)
    command = [str(args.trech.resolve()), "inspect", str(args.scenario.resolve())]
    for param in args.param:
        command.extend(["--param", param])
    inspection = json.loads(subprocess.check_output(command, text=True))
    contracts = inspection.get("authoring", {}).get("validation", {})
    if args.sweep is not None:
        results = evaluate_sweep(contracts, args.sweep, runs)
    else:
        results = evaluate(contracts, args.output, include_family=not args.output_only)
    passed = all(r["passed"] for r in results)
    print(json.dumps({"checks": results, "passed": passed}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
