#!/usr/bin/env python3
"""Check that every decimal constant in the deterministic math source matches its IEEE words.

src/js/DeterministicMath.c writes each fdlibm constant twice: as a decimal literal (what the
compiler uses) and as its two 32-bit IEEE-754 words in a comment (the fdlibm reference
spelling). A typo in either breaks cross-host identity silently, so this script parses every
`<decimal> ... /* ... 0xHHHHHHHH, 0xLLLLLLLL */` pair and fails on any disagreement.
"""
from __future__ import annotations

import argparse
import re
import struct
import sys
from pathlib import Path

PAIR = re.compile(
    r"(?P<dec>-?\d+\.\d+e[+-]\d+)[,;]?\s*(?:\}[,;]?\s*)?/\*[^*]*?"
    r"0x(?P<hi>[0-9A-Fa-f]{8}),\s*0x(?P<lo>[0-9A-Fa-f]{8})\s*\*/"
)


def bits(value: float) -> int:
    return struct.unpack(">Q", struct.pack(">d", value))[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    default = Path(__file__).resolve().parents[1] / "src" / "js" / "DeterministicMath.c"
    parser.add_argument("source", nargs="?", type=Path, default=default)
    args = parser.parse_args()
    text = args.source.read_text(encoding="utf-8")
    checked = 0
    failures = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for match in PAIR.finditer(line):
            checked += 1
            want = (int(match["hi"], 16) << 32) | int(match["lo"], 16)
            got = bits(float(match["dec"]))
            if got != want:
                failures.append(
                    f"{args.source.name}:{lineno}: {match['dec']} is 0x{got:016X}, "
                    f"comment says 0x{want:016X}"
                )
    for failure in failures:
        print(failure, file=sys.stderr)
    print(f"checked {checked} constants, {len(failures)} mismatches")
    if checked < 100:
        print("too few constants parsed; the pattern no longer matches the source", file=sys.stderr)
        return 1
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
