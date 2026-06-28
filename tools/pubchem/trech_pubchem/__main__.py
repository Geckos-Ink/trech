"""CLI for the TRECH PubChem cache.

    python -m trech_pubchem fetch benzene "D-glucose"      # fetch + cache
    python -m trech_pubchem show benzene                    # print cached props
    python -m trech_pubchem list                            # list the cache

Run from ``tools/pubchem`` (or with ``PYTHONPATH=tools/pubchem``).
"""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from .client import CACHE_DIR, fetch_compound, load_compound, slugify


def _print_compound(c) -> None:
    print(f"{c.name}  (CID {c.cid})")
    print(f"  formula   : {c.molecular_formula}")
    print(f"  MW        : {c.molecular_weight} g/mol")
    print(f"  XLogP     : {c.xlogp}   (lipophilic: {c.lipophilic})")
    print(f"  TPSA      : {c.tpsa}")
    print(f"  H-bond D/A: {c.hbond_donors}/{c.hbond_acceptors}")
    print(f"  SMILES    : {c.smiles}")
    print(f"  PNG       : {c.png_path}")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m trech_pubchem",
                                 description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="fetch compounds from PubChem and cache them")
    f.add_argument("names", nargs="+")
    f.add_argument("--no-png", action="store_true", help="skip the 2D structure image")
    s = sub.add_parser("show", help="print a cached compound")
    s.add_argument("name")
    sub.add_parser("list", help="list cached compounds")
    args = ap.parse_args(argv)

    if args.cmd == "fetch":
        rc = 0
        for name in args.names:
            try:
                c = fetch_compound(name, png=not args.no_png)
                print(f"cached {name} -> {CACHE_DIR}/{slugify(name)}.json")
                _print_compound(c)
            except Exception as exc:  # pragma: no cover - network/parse guard
                sys.stderr.write(f"error: failed to fetch {name!r}: {exc}\n")
                rc = 1
        return rc

    if args.cmd == "show":
        c = load_compound(args.name)
        if c is None:
            sys.stderr.write(f"error: {args.name!r} not in cache ({CACHE_DIR})\n")
            return 1
        _print_compound(c)
        return 0

    if args.cmd == "list":
        items = sorted(CACHE_DIR.glob("*.json"))
        if not items:
            print(f"(empty cache at {CACHE_DIR})")
        for p in items:
            c = load_compound(p.stem)
            if c is not None:
                print(f"  {p.stem:20s} CID {c.cid:<8} XLogP {c.xlogp}")
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
