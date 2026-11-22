"""Read an engine trace (``trech_trace.jsonl``) while the run is still writing it.

The engine flushes one JSON object per line (schema ``trech_trace_v1``, see
``docs/engine/engine_trace.md``). :class:`TraceTail` returns only the complete lines added
since the last poll. It keeps a partial last line for the next poll, and it starts again from
the top if the file is truncated or replaced by a new run. Qt-free, so it is unit-testable.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

LEVELS: Sequence[str] = ("off", "summary", "info", "debug", "trace")
LEVEL_RANK: Dict[str, int] = {name: rank for rank, name in enumerate(LEVELS)}
TRACE_FILE = "trech_trace.jsonl"


def level_rank(name: str) -> int:
    return LEVEL_RANK.get(str(name).lower(), LEVEL_RANK["info"])


def trace_spec(level: str, categories: Sequence[str] = ()) -> str:
    """``--trace`` value: ``<level>[:<cat>,...]``."""
    level = str(level).lower()
    if level not in LEVEL_RANK:
        raise ValueError(f"unknown trace level {level!r}")
    cats = [c.strip() for c in categories if c and c.strip()]
    return level + (":" + ",".join(cats) if cats else "")


def trace_args(level: str, categories: Sequence[str], path: Path) -> List[str]:
    """CLI arguments that request a trace at ``level`` into ``path`` (none when off)."""
    if str(level).lower() == "off":
        return []
    return ["--trace", trace_spec(level, categories), "--trace-file", str(path)]


def parse_categories(text: str) -> List[str]:
    return [c.strip() for c in str(text or "").replace(";", ",").split(",") if c.strip()]


@dataclass
class TraceTail:
    """Incremental reader of one trace file."""

    path: Path
    offset: int = 0
    _partial: bytes = b""
    _identity: Optional[tuple] = None
    bad_lines: int = 0
    resets: int = 0

    def reset(self) -> None:
        self.offset = 0
        self._partial = b""
        self._identity = None

    def poll(self) -> List[Dict[str, Any]]:
        """New complete records since the last call (empty while the file does not exist)."""
        try:
            stat = os.stat(self.path)
        except OSError:
            return []
        identity = (stat.st_dev, stat.st_ino)
        if self._identity is not None and (identity != self._identity or stat.st_size < self.offset):
            self.reset()
            self.resets += 1
        self._identity = identity
        if stat.st_size <= self.offset:
            return []
        try:
            with open(self.path, "rb") as handle:
                handle.seek(self.offset)
                chunk = handle.read(stat.st_size - self.offset)
        except OSError:
            return []
        self.offset += len(chunk)
        data = self._partial + chunk
        *lines, self._partial = data.split(b"\n")
        records: List[Dict[str, Any]] = []
        for raw in lines:
            raw = raw.strip()
            if not raw:
                continue
            try:
                record = json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                self.bad_lines += 1
                continue
            if isinstance(record, dict):
                records.append(record)
        return records


@dataclass
class TraceFilter:
    """What the panel shows: records up to ``level``, in ``categories`` (empty = all),
    whose text contains ``search``. The summary record and warnings/errors always pass the
    level check, as they do in the engine."""

    level: str = "info"
    categories: List[str] = field(default_factory=list)
    search: str = ""

    def accepts(self, record: Dict[str, Any]) -> bool:
        cat = str(record.get("cat", ""))
        loud = record.get("severity") in ("warn", "error")
        if cat != "summary" and not loud:
            if level_rank(record.get("level", "info")) > level_rank(self.level):
                return False
            if self.categories and cat not in self.categories:
                return False
        if self.search:
            needle = self.search.lower()
            return needle in describe(record).lower() or needle in json.dumps(record.get("data", "")).lower()
        return True


def where(record: Dict[str, Any]) -> str:
    hook = record.get("hook")
    if not hook:
        return ""
    event = record.get("event")
    return f"{hook}#{event}" if event is not None else str(hook)


def describe(record: Dict[str, Any]) -> str:
    """One-line rendering, like the engine's ``--trace-stderr`` copy."""
    parts = [f"[{record.get('level', '?')}]"]
    if record.get("severity"):
        parts.append(str(record["severity"]))
    parts.append(str(record.get("cat", "")))
    loc = where(record)
    if loc:
        parts.append(loc)
    parts.append(str(record.get("msg", "")))
    return " ".join(parts)


def compact(data: Any, limit: int = 240) -> str:
    if data is None:
        return ""
    text = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    return text if len(text) <= limit else text[: limit - 1] + "…"
