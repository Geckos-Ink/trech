"""Validate the suite's PubChem inputs using local files only.

This module deliberately does not import the network-capable PubChem client.
It checks the selected cache itself, without the runtime's legacy fallback.
"""

from __future__ import annotations

import argparse
import hashlib
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


SNAPSHOT_SCHEMA = "trech_pubchem_input_snapshot_v1"


def _digest(records: dict) -> str:
    canonical = json.dumps(records, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def snapshot(cache_dir: Path, names: Iterable[str]) -> dict:
    """Content hashes of the selected cache records (call after ``cache_errors``).

    The snapshot pins exact bytes; it does not authenticate where they came
    from. A later cache-only run compares against it with ``snapshot_errors``.
    """
    records = {}
    for name in sorted(dict.fromkeys(names)):
        data = (cache_dir / f"{_slug(name)}.json").read_bytes()
        records[name] = {"file": f"{_slug(name)}.json", "bytes": len(data),
                         "sha256": hashlib.sha256(data).hexdigest()}
    return {"schema": SNAPSHOT_SCHEMA, "records": records, "snapshot_sha256": _digest(records)}


def snapshot_summary(path: Path) -> dict:
    """Report-ready identity of a recorded snapshot file, verified against itself.

    ``status`` is ``recorded`` (schema and self-digest agree), ``invalid`` (the
    manifest was edited, truncated or unreadable) or ``absent`` (no snapshot:
    network/refresh mode, or a runs directory produced before snapshots).
    A recorded digest identifies the bytes that were read; it does not prove
    they match PubChem itself.
    """
    if not path.is_file():
        return {"status": "absent"}
    try:
        pinned = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"status": "invalid", "reason": f"unreadable: {exc}"}
    records = pinned.get("records") if isinstance(pinned, dict) else None
    if not isinstance(pinned, dict) or pinned.get("schema") != SNAPSHOT_SCHEMA or not isinstance(records, dict):
        return {"status": "invalid", "reason": f"expected schema {SNAPSHOT_SCHEMA}"}
    if pinned.get("snapshot_sha256") != _digest(records):
        return {"status": "invalid", "reason": "snapshot_sha256 does not match its records"}
    return {"status": "recorded", "snapshot_sha256": pinned["snapshot_sha256"], "records": len(records)}


def snapshot_errors(cache_dir: Path, names: Iterable[str], pinned: object) -> list[str]:
    """Every selected record whose bytes differ from, or are absent in, ``pinned``."""
    if not isinstance(pinned, dict) or pinned.get("schema") != SNAPSHOT_SCHEMA:
        return [f"snapshot: expected schema {SNAPSHOT_SCHEMA}"]
    records = pinned.get("records")
    if not isinstance(records, dict) or pinned.get("snapshot_sha256") != _digest(records):
        return ["snapshot: snapshot_sha256 does not match its records (edited or truncated manifest)"]
    errors = []
    for name in dict.fromkeys(names):
        expected = records.get(name)
        if not isinstance(expected, dict) or not isinstance(expected.get("sha256"), str):
            errors.append(f"{name!r}: not pinned by the snapshot")
            continue
        path = cache_dir / f"{_slug(name)}.json"
        try:
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as exc:
            errors.append(f"{name!r}: {path}: {exc}")
            continue
        if actual != expected["sha256"]:
            errors.append(f"{name!r}: {path}: sha256 {actual[:12]}... differs from pinned "
                          f"{expected['sha256'][:12]}...")
    return errors


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--all", action="store_true", help="Check all suite PubChem inputs")
    parser.add_argument("--snapshot", type=Path,
                        help="Fail unless each selected record matches this pinned snapshot")
    parser.add_argument("--write-snapshot", type=Path,
                        help="After a successful check, write the selected records' hashes here")
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
    if args.snapshot is not None:
        try:
            pinned = json.loads(args.snapshot.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            pinned = None
            errors = [f"snapshot: {args.snapshot}: {exc}"]
        else:
            errors = snapshot_errors(root, names, pinned)
        if errors:
            print(f"error: PubChem inputs at {root} do not match snapshot {args.snapshot}:",
                  file=sys.stderr)
            for error in errors:
                print(f"  - {error}", file=sys.stderr)
            print("No network request was attempted. Restore the pinned records or "
                  "deliberately write a new snapshot.", file=sys.stderr)
            return 3
    record = snapshot(root, names)
    if args.write_snapshot is not None:
        args.write_snapshot.parent.mkdir(parents=True, exist_ok=True)
        args.write_snapshot.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n",
                                       encoding="utf-8")
    pinned_note = " (match pinned snapshot)" if args.snapshot is not None else ""
    print(f"cache-only PubChem inputs: {len(set(names))} records checked at {root}{pinned_note}; "
          f"snapshot_sha256={record['snapshot_sha256']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
