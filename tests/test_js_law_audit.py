#!/usr/bin/env python3
"""Guard the repository-wide JavaScript material-law migration ledger."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "tools" / "validation" / "js_law_audit.json"
EXPERIMENTS = ROOT / "examples" / "experiments"
ALLOWED = {
    "operator_backed",
    "operator_partial",
    "reference_only",
    "no_active_material_law",
}


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    document = json.loads(AUDIT.read_text(encoding="utf-8"))
    entries = document.get("experiments") or {}
    actual = {
        str(path.relative_to(ROOT))
        for path in EXPERIMENTS.glob("*.js")
        if "TRECH_HOOKS" in path.read_text(encoding="utf-8")
    }
    registered = set(entries)
    if actual != registered:
        fail(
            "JS-law audit inventory mismatch; "
            f"missing={sorted(actual - registered)} "
            f"stale={sorted(registered - actual)}"
        )

    for relative, entry in sorted(entries.items()):
        status = entry.get("status")
        operators = entry.get("operators") or []
        residual = entry.get("residual") or ""
        text = (ROOT / relative).read_text(encoding="utf-8")
        if status not in ALLOWED:
            fail(f"{relative}: invalid audit status {status!r}")
        if status in {"operator_partial", "reference_only"} and not residual:
            fail(f"{relative}: unresolved status requires a named residual")
        if status in {"operator_backed", "no_active_material_law"} and residual:
            fail(f"{relative}: completed/no-law status must not carry a residual")
        for operator in operators:
            if operator not in text:
                fail(f"{relative}: declares {operator} but does not call it")
        if status == "operator_backed":
            if not re.search(r'default\s*:\s*"operator"', text):
                fail(f"{relative}: operator-backed normal path is not the default")
            if "reference" not in text.lower():
                fail(f"{relative}: distilled teacher is not labelled reference-only")

    # The two migrations unlocked by DiscreteTransition must never regress to
    # their old unqualified normal-path function names.
    forbidden = {
        "examples/experiments/testscenario_h2o_electrolysis_combustion.js": [
            "function electrolysisProbability(",
            "function combustionProbability(",
            "function inferElectrolysisStep(",
            "function inferCombustionStep(",
        ],
        "examples/experiments/testscenario_efflux.js": [
            "function advectionVelocity(",
            "function stepRandomVelocity(",
            "function stepInside(",
            "function stepCleared(",
        ],
    }
    for relative, needles in forbidden.items():
        text = (ROOT / relative).read_text(encoding="utf-8")
        for needle in needles:
            if needle in text:
                fail(f"{relative}: retired law escaped its reference-only name: {needle}")

    print(
        f"JS-law audit covers {len(actual)} hook experiments: "
        f"{sum(1 for e in entries.values() if e['status'] == 'operator_backed')} "
        "fully operator-backed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
