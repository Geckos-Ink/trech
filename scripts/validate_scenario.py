#!/usr/bin/env python3
"""Evaluate a scenario bundle's declared output checks against an existing run."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess


def evaluate(contracts: dict, output: Path) -> list[dict]:
    """Return explicit pass/fail records. Absent files/fields never silently pass."""
    results = []
    for name, contract in contracts.items():
        if contract.get("schema") != "trech_scenario_validation_v1":
            raise ValueError(f"{name}: unsupported validation schema")
        for check in contract.get("checks", []):
            # Contracts read only files in the supplied run directory.
            relative = Path(check["file"])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("validation file must be relative to the run directory")
            target = output / relative
            rows = [json.loads(line) for line in target.read_text().splitlines() if line.strip()] if target.is_file() else []
            rows = [row for row in rows if row.get("phase") == check["phase"]]
            row = rows[-1] if rows else {}
            value = row.get(check["field"], check.get("missing")) if rows else None
            op = check["op"]
            if op not in {"eq", "gt"}:
                raise ValueError(f"Unsupported validation operation: {op}")
            expected = check["expected"]
            passed = value is not None and (value == expected if op == "eq" else value > expected)
            results.append({"scenario": name, "field": check["field"], "actual": value,
                            "op": op, "expected": expected, "passed": passed})
    if not results:
        raise ValueError("scenario declares no output checks")
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--trech", type=Path, default=Path("build/dev/trech"))
    parser.add_argument("--param", action="append", default=[])
    args = parser.parse_args()
    command = [str(args.trech.resolve()), "inspect", str(args.scenario.resolve())]
    for param in args.param:
        command.extend(["--param", param])
    inspection = json.loads(subprocess.check_output(command, text=True))
    results = evaluate(inspection.get("authoring", {}).get("validation", {}), args.output)
    print(json.dumps({"checks": results, "passed": all(r["passed"] for r in results)}, indent=2))
    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
