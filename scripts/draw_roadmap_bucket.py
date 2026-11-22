#!/usr/bin/env python3
"""Draw and check the root AGENTS.md "roadmap 12 implementations to do bucket".

The bucket holds 5 P1, 4 P2 and 3 P3 items drawn at random from every leaf
roadmap's Priority queue under AGENTS/. The owning queue stays the source of
truth; the bucket only points at it.

  python3 scripts/draw_roadmap_bucket.py --check      # every slot still open, at its key
  python3 scripts/draw_roadmap_bucket.py --draw P2    # one random replacement row

A draw skips gated items, one-line pointers ("owned by the ... queue"), items
already in the bucket and roadmaps that already hold a slot, so the bucket
stays spread across the project.
"""
from __future__ import annotations

import argparse
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AGENTS_MD = ROOT / "AGENTS.md"
HEADING = "## The roadmap 12 implementations to do bucket"
QUOTA = {"P1": 5, "P2": 4, "P3": 3}

ITEM = re.compile(r"^- \*\*(P[123])\*\* · (R\w+) · (.+)$")
ROW = re.compile(
    r"^\| *(\d+) *\| *\*\*(P[123])\*\* *\| *(R\w+) *\| *\[[^\]]+\]\(([^)#]+)#priority-queue\) *\| *(.+?) *\|$"
)


def queue_items() -> list[tuple[str, str, str, str]]:
    """(roadmap path, key, route, text) for every non-pointer queue item."""
    out = []
    for path in sorted((ROOT / "AGENTS").rglob("ROADMAP.md")):
        rel = path.relative_to(ROOT).as_posix()
        for line in path.read_text(encoding="utf-8").splitlines():
            m = ITEM.match(line)
            if m and "owned by the" not in m.group(3):
                out.append((rel, m.group(1), m.group(2), m.group(3)))
    return out


def bucket_rows() -> list[tuple[int, str, str, str, str]]:
    text = AGENTS_MD.read_text(encoding="utf-8")
    start = text.index(HEADING)
    end = text.find("\n## ", start + len(HEADING))
    section = text[start : end if end >= 0 else len(text)]
    rows = []
    for line in section.splitlines():
        m = ROW.match(line.strip())
        if m:
            rows.append((int(m.group(1)), m.group(2), m.group(3), m.group(4), m.group(5)))
    return rows


def find(items, path, text):
    return [it for it in items if it[0] == path and it[3].startswith(text)]


def check() -> int:
    items, rows, errors = queue_items(), bucket_rows(), []
    counts = {k: 0 for k in QUOTA}
    for n, key, route, path, text in rows:
        counts[key] += 1
        hits = find(items, path, text)
        if not hits:
            errors.append(f"slot {n}: not an open item of {path} (landed or reworded: redraw)")
        elif hits[0][1] != key:
            errors.append(f"slot {n}: {path} now keys it {hits[0][1]}, not {key} (redraw)")
    for key, want in QUOTA.items():
        if counts[key] != want:
            errors.append(f"{key}: {counts[key]} slots, want {want}")
    paths = [r[3] for r in rows]
    if len(set(paths)) != len(paths):
        errors.append("two slots share one roadmap")
    for e in errors:
        print(e)
    print("bucket ok" if not errors else f"{len(errors)} problem(s)")
    return 1 if errors else 0


def draw(key: str) -> int:
    rows = bucket_rows()
    used_paths = {r[3] for r in rows}
    pool = [it for it in queue_items() if it[1] == key and it[0] not in used_paths]
    if not pool:
        print(f"no eligible {key} item outside the roadmaps already in the bucket")
        return 1
    path, k, route, text = random.SystemRandom().choice(pool)
    label = path.removeprefix("AGENTS/").removesuffix("/ROADMAP.md")
    summary = re.split(r" \(\[(?:detail|study)\]", text)[0]
    print(f"| N | **{k}** | {route} | [{label}]({path}#priority-queue) | {summary} |")
    print("Replace N with the freed slot number; shorten the text only by cutting its end.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true")
    g.add_argument("--draw", choices=sorted(QUOTA))
    args = ap.parse_args()
    return check() if args.check else draw(args.draw)


if __name__ == "__main__":
    sys.exit(main())
