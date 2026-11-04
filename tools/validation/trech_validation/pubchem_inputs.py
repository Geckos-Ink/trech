"""Validate the suite's PubChem inputs using local files only.

This module deliberately does not import the network-capable PubChem client.
It checks the selected cache itself, without the runtime's legacy fallback.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import re
import sys
from typing import Iterable, Optional


# These are input contracts of the scenarios run by run_validation_suite.sh,
# not physical reference values or inferred response models.
COMPOUNDS = (
    "benzene", "D-glucose", "water", "n-pentane", "hydrogen", "oxygen",
    "glycerol", "toluene 2,4-diisocyanate", "hydrogen peroxide", "potassium iodide",
)
FORMULAS = {"water": "H2O", "hydrogen": "H2", "oxygen": "O2"}
EFFLUX_COMPOUNDS = {"benzene", "D-glucose"}


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")


def _finite_number(value: object, *, positive: bool = False) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    try:
        number = float(value)
        return math.isfinite(number) and (not positive or number > 0)
    except (TypeError, ValueError, OverflowError):
        return False


def cache_errors(cache_dir: Path, names: Iterable[str]) -> list[str]:
    """Return every absent/malformed scenario input; never fetch or write data."""
    errors = []
    for name in dict.fromkeys(names):
        path = cache_dir / f"{_slug(name)}.json"
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            errors.append(f"{name!r}: {path}: {exc}")
            continue
        if not isinstance(record, dict):
            errors.append(f"{name!r}: {path}: expected a JSON object")
            continue
        missing = []
        cid = record.get("cid")
        if isinstance(cid, bool) or not isinstance(cid, int) or cid <= 0:
            missing.append("positive integer cid")
        for field in ("smiles", "molecular_formula"):
            if not isinstance(record.get(field), str) or not record[field].strip():
                missing.append(f"nonempty {field}")
        if name in FORMULAS and record.get("molecular_formula") != FORMULAS[name]:
            missing.append(f"molecular_formula={FORMULAS[name]}")
        if name in EFFLUX_COMPOUNDS:
            if not _finite_number(record.get("xlogp")):
                missing.append("finite xlogp")
            if not _finite_number(record.get("molecular_weight"), positive=True):
                missing.append("positive finite molecular_weight")
        if missing:
            errors.append(f"{name!r}: {path}: requires {', '.join(missing)}")
    return errors


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--all", action="store_true", help="Check all suite PubChem inputs")
    parser.add_argument("names", nargs="*")
    args = parser.parse_args(argv)
    if args.all and args.names:
        parser.error("use --all or compound names, not both")
    names = COMPOUNDS if args.all else args.names
    if not names:
        parser.error("provide compound names or --all")
    # Match TRECH_PUBCHEM_CACHE_DIR exactly: the C++ cache reader does not
    # expand a literal '~' embedded in an environment-variable value.
    root = args.cache_dir.resolve()
    errors = cache_errors(root, names)
    if errors:
        print(f"error: cache-only validation requires complete PubChem inputs at {root}:",
              file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        print("No network request was attempted. Populate this cache with "
              "PUBCHEM_MODE=refresh while online, or select a complete PUBCHEM_CACHE.",
              file=sys.stderr)
        return 2
    print(f"cache-only PubChem inputs: {len(set(names))} records checked at {root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
