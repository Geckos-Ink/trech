#!/usr/bin/env python3
"""Refuse the JavaScript exponent operator (`**`, `**=`) in TRECH scripts.

Why: QuickJS computes `a ** b` and `Math.pow(a, b)` with the same deterministic `js_pow`
(TRECH's fdlibm `trech_dmath_pow`), so the two are bit-identical there. V8 lets
`js/trech_dmath_v8.js` replace `Math.pow`, but its `**` operator always uses V8's own pow,
which can differ in the last bit. A script that writes `Math.pow` therefore replays bit for bit
on both engines; one that writes `**` may not. See docs/engine/v8.md.

The scan is a small JavaScript tokenizer: it skips line and block comments, string literals,
template literal text (but scans `${...}` expressions) and regular-expression literals, so only
real operators are reported.

Usage:
  scripts/check_js_pow_operator.py [PATH ...]   # default: js examples projects tests/fixtures
Exit status 1 lists every `file:line:column` that uses the operator.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterator, List, Tuple

DEFAULT_ROOTS = ("js", "examples", "projects", "tests/fixtures")
SKIP_DIRS = {"node_modules", ".git"}
# After one of these characters (or a keyword below) a `/` starts a regular expression.
REGEX_AFTER = set("(,=:[!&|?{};+-*%<>~^")
REGEX_KEYWORDS = {"return", "typeof", "instanceof", "in", "of", "new", "delete", "void",
                  "throw", "case", "do", "else", "yield", "await"}


def find_pow_operators(text: str) -> List[Tuple[int, int]]:
    """(line, column) of every `**` / `**=` operator, 1-based."""
    hits: List[Tuple[int, int]] = []
    n = len(text)
    line_starts = [0]
    for index, char in enumerate(text):
        if char == "\n":
            line_starts.append(index + 1)

    def position(index: int) -> Tuple[int, int]:
        lo, hi = 0, len(line_starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if line_starts[mid] <= index:
                lo = mid
            else:
                hi = mid - 1
        return lo + 1, index - line_starts[lo] + 1

    def skip_string(i: int, quote: str) -> int:
        i += 1
        while i < n and text[i] != quote:
            i += 2 if text[i] == "\\" else 1
        return i + 1

    def skip_regex(i: int) -> int:
        i += 1
        in_class = False
        while i < n and text[i] != "\n":
            char = text[i]
            if char == "\\":
                i += 2
                continue
            if char == "[":
                in_class = True
            elif char == "]":
                in_class = False
            elif char == "/" and not in_class:
                i += 1
                while i < n and (text[i].isalnum() or text[i] == "_"):
                    i += 1  # flags
                return i
            i += 1
        return i

    def scan(i: int, closing: str) -> int:
        """Scan code from i until an unmatched `closing` brace (or the end); return its index."""
        depth = 0
        previous = ""  # last significant character, or a word token
        while i < n:
            char = text[i]
            if char.isspace():
                i += 1
                continue
            if text.startswith("//", i):
                end = text.find("\n", i)
                i = n if end < 0 else end
                continue
            if text.startswith("/*", i):
                end = text.find("*/", i + 2)
                i = n if end < 0 else end + 2
                continue
            if char in "\"'":
                i = skip_string(i, char)
                previous = "a"
                continue
            if char == "`":
                i += 1
                while i < n and text[i] != "`":
                    if text[i] == "\\":
                        i += 2
                    elif text.startswith("${", i):
                        i = scan(i + 2, "}") + 1
                    else:
                        i += 1
                i += 1
                previous = "a"
                continue
            if char == "/":
                if previous == "" or previous in REGEX_AFTER or previous in REGEX_KEYWORDS:
                    i = skip_regex(i)
                    previous = "a"
                    continue
            if text.startswith("**", i):
                hits.append(position(i))
                i += 3 if text.startswith("**=", i) else 2
                previous = "*"
                continue
            if char.isalnum() or char in "_$":
                start = i
                while i < n and (text[i].isalnum() or text[i] in "_$"):
                    i += 1
                previous = text[start:i] if text[start:i] in REGEX_KEYWORDS else "a"
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                if depth == 0 and closing == "}":
                    return i
                depth -= 1
            previous = char if char not in ")]" else "a"
            i += 1
        return i

    scan(0, "")
    return hits


def iter_scripts(paths: List[Path]) -> Iterator[Path]:
    for path in paths:
        if path.is_file():
            yield path
            continue
        for script in sorted(path.rglob("*.js")):
            if not SKIP_DIRS.intersection(script.parts):
                yield script


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="*", type=Path,
                        help="files or directories (default: js examples projects tests/fixtures)")
    args = parser.parse_args(argv)
    paths = args.paths or [Path(root) for root in DEFAULT_ROOTS if Path(root).exists()]
    found = 0
    scanned = 0
    for script in iter_scripts(paths):
        scanned += 1
        for line, column in find_pow_operators(script.read_text(encoding="utf-8", errors="replace")):
            print(f"{script}:{line}:{column}: use Math.pow(a, b) instead of `**` "
                  "(V8 cannot replace the operator; see docs/engine/v8.md)")
            found += 1
    if found:
        print(f"{found} exponent operator(s) in {scanned} script(s)", file=sys.stderr)
        return 1
    print(f"no exponent operator in {scanned} script(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
