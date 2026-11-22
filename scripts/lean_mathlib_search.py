#!/usr/bin/env python3
"""Search Mathlib declaration headers before declaring a new theorem in TRECH.

Greps ``thirds/mathlib4/Mathlib/**/*.lean`` for declarations (theorem, lemma, def, abbrev,
structure, class, instance, inductive) whose header line matches a regular expression,
and prints ``path:line: header``. It finds names and statement text, not mathematically
equivalent statements; once the Lean toolchain is built, also try ``exact?``/``apply?``.

Run ``scripts/pull_lean.sh`` first so the checkout is current.

Examples::

    python3 scripts/lean_mathlib_search.py 'exp_add'
    python3 scripts/lean_mathlib_search.py --kind theorem 'inner.*self.*nonneg'
    python3 scripts/lean_mathlib_search.py --path Analysis/SpecialFunctions 'Real.exp'
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

KINDS = ("theorem", "lemma", "def", "abbrev", "structure", "class", "instance", "inductive")
MODIFIERS = r"(?:(?:@\[[^\]]*\]\s*)|(?:private|protected|noncomputable|nonrec|partial|unsafe)\s+)*"


def main(argv: list[str] | None = None) -> int:
    repo = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pattern", help="regular expression matched against the declaration header")
    parser.add_argument("--kind", action="append", choices=KINDS,
                        help="declaration kinds to search (repeatable; default: all)")
    parser.add_argument("--path", default="", help="restrict to a subdirectory of Mathlib/")
    parser.add_argument("--ignore-case", "-i", action="store_true")
    parser.add_argument("--limit", type=int, default=200, help="maximum matches to print (0: no limit)")
    parser.add_argument("--mathlib", type=Path, default=repo / "thirds" / "mathlib4",
                        help="Mathlib checkout (default: thirds/mathlib4)")
    args = parser.parse_args(argv)

    base = args.mathlib / "Mathlib" / args.path
    if not base.is_dir():
        print(f"error: {base} not found; run scripts/pull_lean.sh", file=sys.stderr)
        return 2

    kinds = "|".join(args.kind or KINDS)
    header = re.compile(rf"^\s*{MODIFIERS}(?:{kinds})\s+\S")
    flags = re.IGNORECASE if args.ignore_case else 0
    query = re.compile(args.pattern, flags)

    found = 0
    for path in sorted(base.rglob("*.lean")):
        with path.open(encoding="utf-8", errors="replace") as handle:
            for number, line in enumerate(handle, 1):
                if header.match(line) and query.search(line):
                    rel = path.relative_to(args.mathlib)
                    print(f"{rel}:{number}: {line.strip()}")
                    found += 1
                    if args.limit and found >= args.limit:
                        print(f"... stopped at --limit {args.limit}", file=sys.stderr)
                        return 0
    if not found:
        print("no matching declaration", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
