"""Model definitions and checkpoint store, as Studio shows them (pure: no Qt, no IO).

The registry (``trech_model_registry_v1``) and definition inspections
(``trech_ml_inspection_v1``) are written by ``tools/ml/bin/trech-ml.cjs``; Studio only parses
them. A checkpoint is a learned comparison model: nothing here ranks, trains or predicts, and
every number shown (uses, sizes, carried metrics) is a recorded value, never a Studio estimate.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REGISTRY_SCHEMA = "trech_model_registry_v1"
INSPECTION_SCHEMA = "trech_ml_inspection_v1"
DEFINITION_SUFFIXES = (".model.js", ".search.js")
SORT_KEYS = ("uses", "recent", "name", "size")

MODEL_TEMPLATE = """// Fixed-structure model definition (see ml/README.md).
TRECH_ML.defineModel({
  name: "%(name)s",
  description: "",
  scale: "meso",
  inputs: ["input_a", "input_b"],
  outputs: ["output_y"],
  structure: { family: "mlp", width: 16, depth: 2 },
  training: {
    source: "scores",
    runs: ["build/runs/train_*"],
    validationRuns: [],
    testRuns: []
  }
});
"""

SEARCH_TEMPLATE = """// Structure search (see ml/README.md). Candidates rank on validationRuns;
// the winner is re-trained with testRuns as its carried holdout.
TRECH_ML.defineSearch({
  name: "%(name)s",
  scale: "meso",
  inputs: ["input_a", "input_b"],
  outputs: ["output_y"],
  training: {
    source: "scores",
    runs: ["build/runs/train_*"],
    validationRuns: ["build/runs/valid_*"],
    testRuns: ["build/runs/test_*"]
  },
  strategy: "grid",
  space: { families: ["linear", "mlp"], width: [8, 16, 32], depth: [1, 2] },
  budget: { maxCandidates: 12, maxParameters: 20000 },
  objective: "r2_min"
});
"""


def human_bytes(value: Optional[int]) -> str:
    if value is None:
        return "–"
    size, unit = float(value), 0
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    while size >= 1024 and unit < len(units) - 1:
        size /= 1024
        unit += 1
    return f"{int(size)} B" if unit == 0 else f"{size:.1f} {units[unit]}"


def parse_time(text: Optional[str]) -> Optional[datetime]:
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def relative_time(text: Optional[str], now: Optional[datetime] = None) -> str:
    """'never' for an unrecorded use; otherwise a coarse age of the recorded timestamp."""
    when = parse_time(text)
    if when is None:
        return "never"
    now = now or datetime.now(timezone.utc)
    seconds = max(0.0, (now - when).total_seconds())
    for limit, size, unit in ((60, 1, "s"), (3600, 60, "min"), (86400, 3600, "h"), (86400 * 60, 86400, "d")):
        if seconds < limit:
            return f"{int(seconds // size)} {unit} ago"
    return when.date().isoformat()


@dataclass(frozen=True)
class Checkpoint:
    id: str
    name: str
    version: int
    role: str
    structure_id: str
    structure_label: str
    parameter_count: Optional[int]
    inputs: Tuple[str, ...]
    outputs: Tuple[str, ...]
    scale: Optional[str]
    size_bytes: int
    created_at: Optional[str]
    last_used_at: Optional[str]
    use_count: int
    pinned: bool
    active: bool
    holdout_source: Optional[str]
    metrics: Optional[Dict[str, Any]]
    files: Tuple[Dict[str, Any], ...]
    definition_file: Optional[str]
    search: Optional[Dict[str, Any]]
    note: Optional[str]

    @property
    def formats(self) -> Tuple[str, ...]:
        return tuple(str(f.get("format")) for f in self.files)

    def metric_summary(self) -> str:
        """Carried held-out accuracy in words; absent stays absent (never a 0)."""
        metrics = self.metrics
        if not isinstance(metrics, dict) or not metrics:
            return "no carried accuracy"
        if "r2_min" in metrics:
            r2 = metrics.get("r2_min")
            return f"R²min {r2:.3f}" if isinstance(r2, (int, float)) else "no carried accuracy"
        r2s = [m.get("r2") for m in metrics.values() if isinstance(m, dict) and isinstance(m.get("r2"), (int, float))]
        return f"R²min {min(r2s):.3f}" if r2s else "no carried accuracy"

    def holdout_note(self) -> str:
        return {
            "test_runs": "held-out test runs",
            "validation_runs": "independent validation runs",
            "selection_runs": "selection runs (optimistic: used to rank)",
            "random_rows": "random row split",
            "carried": "as carried by the imported file",
        }.get(self.holdout_source or "", "unrecorded holdout")


@dataclass(frozen=True)
class RegisteredModel:
    name: str
    active: Optional[str]
    checkpoints: Tuple[Checkpoint, ...]

    @property
    def use_count(self) -> int:
        return sum(c.use_count for c in self.checkpoints)

    @property
    def last_used_at(self) -> Optional[str]:
        times = sorted(c.last_used_at for c in self.checkpoints if c.last_used_at)
        return times[-1] if times else None

    @property
    def size_bytes(self) -> int:
        return sum(c.size_bytes for c in self.checkpoints)

    @property
    def latest_version(self) -> int:
        return max((c.version for c in self.checkpoints), default=0)

    @property
    def structures(self) -> int:
        return len({c.structure_id for c in self.checkpoints})


@dataclass(frozen=True)
class Registry:
    store: Optional[Path]
    models: Tuple[RegisteredModel, ...] = ()
    searches: Tuple[Dict[str, Any], ...] = ()
    updated_at: Optional[str] = None
    error: Optional[str] = None

    @property
    def total_bytes(self) -> int:
        return sum(m.size_bytes for m in self.models)

    @property
    def is_empty(self) -> bool:
        return not self.models

    def checkpoint(self, checkpoint_id: str) -> Optional[Checkpoint]:
        for model in self.models:
            for checkpoint in model.checkpoints:
                if checkpoint.id == checkpoint_id:
                    return checkpoint
        return None

    def sorted_models(self, key: str = "uses") -> List[RegisteredModel]:
        if key not in SORT_KEYS:
            raise ValueError(f"sort key must be one of {SORT_KEYS}")
        models = list(self.models)
        models.sort(key=lambda m: m.name)
        if key == "uses":
            models.sort(key=lambda m: m.last_used_at or "", reverse=True)
            models.sort(key=lambda m: m.use_count, reverse=True)
        elif key == "recent":
            models.sort(key=lambda m: m.last_used_at or "", reverse=True)
        elif key == "size":
            models.sort(key=lambda m: m.size_bytes, reverse=True)
        return models


def _checkpoint(raw: Dict[str, Any], active: Optional[str]) -> Checkpoint:
    definition = raw.get("definition") or {}
    return Checkpoint(
        id=str(raw["id"]), name=str(raw.get("name", "")), version=int(raw.get("version", 0)), role=str(raw.get("role", "")),
        structure_id=str(raw.get("structure_id", "")), structure_label=str(raw.get("structure_label", "")),
        parameter_count=raw.get("parameter_count") if isinstance(raw.get("parameter_count"), int) else None,
        inputs=tuple(raw.get("inputs") or ()), outputs=tuple(raw.get("outputs") or ()), scale=raw.get("scale"),
        size_bytes=int(raw.get("size_bytes") or 0), created_at=raw.get("created_at"), last_used_at=raw.get("last_used_at"),
        use_count=int(raw.get("use_count") or 0), pinned=bool(raw.get("pinned")), active=raw.get("id") == active,
        holdout_source=raw.get("holdout_source"), metrics=raw.get("metrics") if isinstance(raw.get("metrics"), dict) else None,
        files=tuple(f for f in (raw.get("files") or ()) if isinstance(f, dict)),
        definition_file=definition.get("file") if isinstance(definition, dict) else None,
        search=raw.get("search") if isinstance(raw.get("search"), dict) else None, note=raw.get("note"),
    )


def parse_registry(data: Any, store: Optional[Path] = None) -> Registry:
    """A registry index (or None for an absent store) → Registry; malformed input → error, never a guess."""
    if data is None:
        return Registry(store=store)
    if not isinstance(data, dict) or data.get("schema") != REGISTRY_SCHEMA:
        return Registry(store=store, error=f"not a {REGISTRY_SCHEMA} index")
    models = []
    try:
        for name, entry in sorted((data.get("models") or {}).items()):
            active = entry.get("active")
            checkpoints = tuple(sorted((_checkpoint(c, active) for c in entry.get("checkpoints") or ()),
                                       key=lambda c: c.version, reverse=True))
            models.append(RegisteredModel(name=name, active=active, checkpoints=checkpoints))
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        return Registry(store=store, error=f"malformed registry: {error}")
    return Registry(store=store, models=tuple(models), searches=tuple(s for s in data.get("searches") or () if isinstance(s, dict)),
                    updated_at=data.get("updated_at"))


@dataclass(frozen=True)
class InspectionError:
    message: str
    line: Optional[int] = None
    column: Optional[int] = None
    warning: bool = False

    def describe(self) -> str:
        where = f"line {self.line}: " if self.line else ""
        return ("warning: " if self.warning else "") + where + self.message


@dataclass(frozen=True)
class Inspection:
    file: Optional[str]
    ok: bool
    definitions: Tuple[Dict[str, Any], ...] = ()
    searches: Tuple[Dict[str, Any], ...] = ()
    errors: Tuple[InspectionError, ...] = ()
    logs: Tuple[str, ...] = ()

    def summary_lines(self) -> List[str]:
        lines = []
        for d in self.definitions:
            io = f"[{', '.join(d.get('inputs', []))}] → [{', '.join(d.get('outputs', []))}]"
            lines.append(f"model {d.get('name')}: {d.get('structure_label')} · {d.get('structure_id')} · "
                         f"{d.get('parameter_count')} params · {io}" + (f" @ {d['scale']}" if d.get("scale") else ""))
        for s in self.searches:
            lines.append(f"search {s.get('name')}: {s.get('strategy')} · objective {s.get('objective')} · "
                         f"{len(s.get('candidates') or [])} candidates" +
                         (f" ({len(s.get('skipped') or [])} skipped)" if s.get("skipped") else "") +
                         (f" · {s['candidate_note']}" if s.get("candidate_note") else ""))
        return lines


def parse_inspection(data: Any) -> Inspection:
    if not isinstance(data, dict):
        return Inspection(file=None, ok=False, errors=(InspectionError("inspector returned no JSON"),))
    if data.get("event") == "error":
        return Inspection(file=None, ok=False, errors=(InspectionError(str(data.get("message"))),))
    if data.get("schema") != INSPECTION_SCHEMA:
        return Inspection(file=None, ok=False, errors=(InspectionError(f"not a {INSPECTION_SCHEMA} result"),))
    errors = tuple(InspectionError(str(e.get("message")), e.get("line"), e.get("column"), bool(e.get("warning")))
                   for e in data.get("errors") or () if isinstance(e, dict))
    return Inspection(file=data.get("file"), ok=bool(data.get("ok")), definitions=tuple(data.get("definitions") or ()),
                      searches=tuple(data.get("searches") or ()), errors=errors, logs=tuple(map(str, data.get("logs") or ())))


def definition_kind(path: Path) -> Optional[str]:
    name = path.name
    if name.endswith(".model.js"):
        return "model"
    if name.endswith(".search.js"):
        return "search"
    return None


def discover_definition_files(ml_root: Path) -> List[Path]:
    """Every *.model.js / *.search.js under the ml/ tree, sorted by relative path."""
    if not ml_root.is_dir():
        return []
    files = [p for p in ml_root.rglob("*.js") if definition_kind(p)]
    return sorted(files, key=lambda p: p.relative_to(ml_root).as_posix())


def new_definition_source(kind: str, name: str) -> str:
    if kind not in ("model", "search"):
        raise ValueError("kind must be 'model' or 'search'")
    return (MODEL_TEMPLATE if kind == "model" else SEARCH_TEMPLATE) % {"name": name}


@dataclass(frozen=True)
class PrunePlan:
    delete: Tuple[Dict[str, Any], ...] = ()
    keep: Tuple[Dict[str, Any], ...] = ()
    total_bytes: int = 0
    bytes_freed: int = 0
    fits: Optional[bool] = None
    dry_run: bool = True
    removed: Tuple[Dict[str, Any], ...] = field(default_factory=tuple)

    def describe(self) -> str:
        verb = "Would delete" if self.dry_run else "Deleted"
        text = f"{verb} {len(self.delete)} checkpoint(s), freeing {human_bytes(self.bytes_freed)} of {human_bytes(self.total_bytes)}."
        if self.fits is False:
            text += " The size limit cannot be met without deleting pinned/active/newest checkpoints."
        return text


def parse_prune(data: Any) -> PrunePlan:
    if not isinstance(data, dict) or "delete" not in data:
        raise ValueError("not a prune plan")
    return PrunePlan(delete=tuple(data.get("delete") or ()), keep=tuple(data.get("keep") or ()),
                     total_bytes=int(data.get("total_bytes") or 0), bytes_freed=int(data.get("bytes_freed") or 0),
                     fits=data.get("fits"), dry_run=bool(data.get("dry_run")), removed=tuple(data.get("removed") or ()))
