"""CLI entry point for the TRECH validation suite."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from .report import write_report
from .runner import required_run_names, run_all
from .cases import FOAM_MECHANICS_CANDIDATE_CASES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m trech_validation",
        description="Run TRECH validation cases and write docs/validation_report.{md,json}.",
    )
    parser.add_argument(
        "--suite", choices=("default", "foam-mechanics-candidate"), default="default",
        help="Default promoted checks, or the experimental foam mechanics promotion gates.",
    )
    parser.add_argument(
        "--runs-dir",
        required=True,
        help="Directory containing per-scenario output sub-directories (e.g. build/dev).",
    )
    parser.add_argument(
        "--report",
        help="Markdown path (default: docs/validation_report.md; candidate: RUNS_DIR/promotion_report.md).",
    )
    parser.add_argument(
        "--json",
        help="JSON path (default: docs/validation_report.json; candidate: RUNS_DIR/promotion_report.json).",
    )
    parser.add_argument(
        "--list-required-runs",
        action="store_true",
        help="Print the run-directory names the cases will look for under --runs-dir and exit.",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cases = FOAM_MECHANICS_CANDIDATE_CASES if args.suite == "foam-mechanics-candidate" else None

    if args.list_required_runs:
        for name in required_run_names(cases):
            print(name)
        return 0

    runs_dir = Path(args.runs_dir).expanduser().resolve()
    if not runs_dir.exists():
        parser.error(f"runs-dir not found: {runs_dir}")
        return 2
    args.report = args.report or str(runs_dir / "promotion_report.md" if cases is not None
                                    else Path("docs/validation_report.md"))
    args.json = args.json or str(runs_dir / "promotion_report.json" if cases is not None
                                else Path("docs/validation_report.json"))

    results = run_all(runs_dir, cases)
    write_report(
        results,
        markdown_path=Path(args.report).expanduser().resolve(),
        json_path=Path(args.json).expanduser().resolve(),
        runs_dir=runs_dir,
    )

    fail_count = sum(1 for r in results if r.status in ("fail", "error"))
    print(
        f"validation: {len(results)} cases, "
        f"{sum(1 for r in results if r.status == 'pass')} pass, "
        f"{fail_count} fail/error, "
        f"{sum(1 for r in results if r.status == 'skip')} skip"
    )
    print(f"report: {args.report}")
    print(f"sidecar: {args.json}")
    # A skipped candidate gate is not evidence for promotion.
    candidate_incomplete = cases is not None and any(r.status != "pass" for r in results)
    return 1 if fail_count > 0 or candidate_incomplete else 0


if __name__ == "__main__":
    sys.exit(main())
