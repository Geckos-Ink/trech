#!/usr/bin/env python3
"""Report committed media that no tracked Markdown page shows.

`previews.md` is the gallery for committed GIFs and images that no other page
displays. It is hand-written, so a newly committed preview can silently go
missing from every page. This check lists every tracked image/animation and
every tracked Markdown file, resolves each Markdown reference (inline links and
images, reference definitions and HTML ``src``/``href`` attributes) relative to
its page, and reports media that nothing references.

Rules:

* a PNG/JPG is covered when a GIF with the same stem in the same directory is
  covered (it is that GIF's poster frame, see ``previews.md``);
* vendored documentation trees (``docs/geant4-docs/``) are exempt.

``--include-untracked`` also checks new, non-ignored files, so the media
refresh can flag a preview it just wrote before it is committed.

Exit status: 0 when every committed medium is shown, 1 otherwise. ``--json``
prints the report as JSON. Read-only; it never edits Markdown.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from urllib.parse import unquote

MEDIA_SUFFIXES = {".gif", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".mp4", ".webm"}
POSTER_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
EXEMPT_PREFIXES = ("docs/geant4-docs/",)

# Inline [text](target "title") and ![alt](target); the target ends at
# whitespace or the closing parenthesis.
_INLINE = re.compile(r"\]\(\s*<?([^)\s>]+)>?(?:\s+[\"'][^)]*[\"'])?\s*\)")
# Reference definitions: [label]: target
_REFDEF = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*<?(\S+?)>?(?:\s|$)", re.MULTILINE)
# HTML attributes: <img src="...">, <a href='...'>, <source srcset=...>
_HTML = re.compile(r"\b(?:src|href|poster)\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)


def tracked_files(root: Path, include_untracked: bool = False) -> list[str]:
    """Tracked paths; with include_untracked also new, non-ignored files (a fresh refresh)."""
    command = ["git", "-C", str(root), "ls-files", "-z", "--cached"]
    if include_untracked:
        command += ["--others", "--exclude-standard"]
    out = subprocess.run(command, check=True, capture_output=True).stdout
    return [p for p in out.decode("utf-8").split("\0") if p]


def markdown_targets(text: str) -> list[str]:
    targets = []
    for pattern in (_INLINE, _REFDEF, _HTML):
        targets.extend(m.group(1) for m in pattern.finditer(text))
    return targets


def resolve(page: str, target: str) -> str | None:
    """Repository-relative path a Markdown target names, or None if external."""
    if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.IGNORECASE) or target.startswith("//"):
        return None  # http(s):, mailto:, data: ...
    target = unquote(target.split("#", 1)[0].split("?", 1)[0])
    if not target:
        return None
    if target.startswith("/"):
        path = PurePosixPath(target.lstrip("/"))
    else:
        path = PurePosixPath(page).parent / target
    parts: list[str] = []
    for part in path.parts:
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                return None  # escapes the repository
            parts.pop()
        else:
            parts.append(part)
    return "/".join(parts)


def coverage(root: Path, files: list[str] | None = None, include_untracked: bool = False) -> dict:
    files = tracked_files(root, include_untracked) if files is None else files
    files = sorted(set(files))
    media = sorted(f for f in files if PurePosixPath(f).suffix.lower() in MEDIA_SUFFIXES
                   and not f.startswith(EXEMPT_PREFIXES))
    pages = sorted(f for f in files if f.lower().endswith(".md")
                   and not f.startswith(EXEMPT_PREFIXES))
    referenced: dict[str, list[str]] = {}
    for page in pages:
        try:
            text = (root / page).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for target in markdown_targets(text):
            path = resolve(page, target)
            if path is not None:
                referenced.setdefault(path, []).append(page)

    shown = {m for m in media if m in referenced}
    posters = set()
    for m in media:
        p = PurePosixPath(m)
        if m not in shown and p.suffix.lower() in POSTER_SUFFIXES:
            if str(p.with_suffix(".gif")) in shown:
                posters.add(m)
    missing = [m for m in media if m not in shown and m not in posters]
    return {
        "schema": "trech_media_coverage_v1",
        "media": len(media),
        "pages": len(pages),
        "shown": len(shown),
        "posters": len(posters),
        "missing": missing,
        "pass": not missing,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    parser.add_argument("--include-untracked", action="store_true",
                        help="also check new, non-ignored files (media just written by a refresh)")
    args = parser.parse_args(argv)
    report = coverage(args.root, include_untracked=args.include_untracked)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"{report['media']} committed media, {report['pages']} Markdown pages: "
              f"{report['shown']} shown, {report['posters']} poster frames of shown GIFs, "
              f"{len(report['missing'])} not shown")
        for path in report["missing"]:
            print(f"  not shown by any Markdown page: {path}")
        if report["missing"]:
            print("Embed each in the page that owns it, or in previews.md.")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
