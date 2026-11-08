#!/usr/bin/env python3
"""Evaluate a scenario bundle's declared output and family checks against an existing run."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "validation"))
from trech_validation.declarative import evaluate_contracts  # noqa: E402


def evaluate(contracts: dict, output: Path, include_family: bool = True) -> list[dict]:
    """Return explicit pass/fail records. Absent files/fields never silently pass."""
    results = evaluate_contracts(contracts, output, include_family=include_family)
    if not any("family_case" not in result for result in results):
        raise ValueError("scenario declares no output checks")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--trech", type=Path, default=Path("build/dev/trech"))
    parser.add_argument("--param", action="append", default=[])
    parser.add_argument("--output-only", action="store_true",
                        help="Skip exported family checks; grade output integrity only.")
    args = parser.parse_args()
    command = [str(args.trech.resolve()), "inspect", str(args.scenario.resolve())]
    for param in args.param:
        command.extend(["--param", param])
    inspection = json.loads(subprocess.check_output(command, text=True))
    results = evaluate(inspection.get("authoring", {}).get("validation", {}), args.output,
                       include_family=not args.output_only)
    passed = all(r["passed"] for r in results)
    print(json.dumps({"checks": results, "passed": passed}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
