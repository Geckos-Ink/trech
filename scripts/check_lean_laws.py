#!/usr/bin/env python3
"""Build the optional Lean law package and audit the axioms of every listed theorem.

Runs ``lake build`` in ``formal/`` and then ``#print axioms`` for each declaration listed in
``formal/laws.json``. A theorem passes only if it depends on nothing beyond Lean's standard
axioms (``propext``, ``Classical.choice``, ``Quot.sound``); ``sorryAx`` or any added axiom
fails the check. Needs ``lake`` matching ``formal/lean-toolchain`` and the Mathlib cache
(``lake exe cache get``). Used by the opt-in CTest ``trech_formal_lean_build``
(``-DTRECH_ENABLE_LEAN_CHECK=ON``).

    python3 scripts/check_lean_laws.py [--lake PATH]
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FORMAL = ROOT / "formal"
STANDARD = {"propext", "Classical.choice", "Quot.sound"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--lake", default="lake", help="lake executable (default: lake on PATH)")
    args = parser.parse_args(argv)

    build = subprocess.run([args.lake, "build"], cwd=FORMAL, text=True, capture_output=True)
    if build.returncode != 0:
        print(build.stdout[-8000:], build.stderr[-8000:], sep="\n", file=sys.stderr)
        print("lake build failed", file=sys.stderr)
        return 1
    warnings = [line for line in build.stdout.splitlines() if line.startswith("warning:")]
    for line in warnings:
        print(line)

    laws = json.loads((FORMAL / "laws.json").read_text(encoding="utf-8"))["laws"]
    declarations = [d for law in laws for d in law["lean"]["declarations"]]
    with tempfile.TemporaryDirectory() as scratch:
        probe = Path(scratch) / "Axioms.lean"
        probe.write_text("import Trech\n" + "".join(f"#print axioms {d}\n" for d in declarations),
                         encoding="utf-8")
        result = subprocess.run([args.lake, "env", "lean", str(probe)], cwd=FORMAL, text=True,
                                capture_output=True)
    output = result.stdout + result.stderr
    if result.returncode != 0:
        print(output, file=sys.stderr)
        return 1

    found: dict[str, set[str]] = {}
    for match in re.finditer(r"'([^']+)' depends on axioms: \[([^\]]*)\]", output):
        found[match.group(1)] = {a.strip() for a in match.group(2).split(",") if a.strip()}
    for match in re.finditer(r"'([^']+)' does not depend on any axioms", output):
        found[match.group(1)] = set()

    failures = 0
    for declaration in declarations:
        if declaration not in found:
            print(f"FAIL {declaration}: no axiom report", file=sys.stderr)
            failures += 1
            continue
        extra = found[declaration] - STANDARD
        status = "FAIL" if extra else "ok"
        print(f"{status:4} {declaration}  axioms: {sorted(found[declaration])}")
        if extra:
            print(f"     non-standard axioms: {sorted(extra)}", file=sys.stderr)
            failures += 1
    print(f"{len(declarations) - failures}/{len(declarations)} theorems proved from standard axioms only")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
