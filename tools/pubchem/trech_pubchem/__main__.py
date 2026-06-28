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

from .client import cache_dir, fetch_compound, load_compound, slugify


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
    f.add_argument("--cache-dir", help="write/read a specific PubChem cache directory")
    s = sub.add_parser("show", help="print a cached compound")
    s.add_argument("name")
    s.add_argument("--cache-dir", help="read a specific PubChem cache directory")
    l = sub.add_parser("list", help="list cached compounds")
    l.add_argument("--cache-dir", help="read a specific PubChem cache directory")
    args = ap.parse_args(argv)

    if args.cmd == "fetch":
        rc = 0
        root = cache_dir(args.cache_dir)
        for name in args.names:
            try:
                c = fetch_compound(name, png=not args.no_png, cache_root=root)
                print(f"cached {name} -> {root}/{slugify(name)}.json")
                _print_compound(c)
            except Exception as exc:  # pragma: no cover - network/parse guard
                sys.stderr.write(f"error: failed to fetch {name!r}: {exc}\n")
                rc = 1
        return rc

    if args.cmd == "show":
        c = load_compound(args.name, cache_root=args.cache_dir)
        if c is None:
            sys.stderr.write(
                f"error: {args.name!r} not in cache ({cache_dir(args.cache_dir)})\n")
            return 1
        _print_compound(c)
        return 0

    if args.cmd == "list":
        root = cache_dir(args.cache_dir)
        items = sorted(root.glob("*.json"))
        if not items:
            print(f"(empty cache at {root})")
        for p in items:
            c = load_compound(p.stem, cache_root=root)
            if c is not None:
                print(f"  {p.stem:20s} CID {c.cid:<8} XLogP {c.xlogp}")
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
