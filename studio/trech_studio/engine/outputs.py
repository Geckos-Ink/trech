"""Parse a TRECH run output directory into typed Python objects.

Studio never interprets the on-disk JSONL layout outside this module. The field names and
files below track ``docs/output_schema.md`` at the repo root — if the schema changes there,
update the parsing here in the same change (see studio/AGENTS.md "Output contracts").

Files consumed:
  trech_provenance.jsonl      run_start / run_end provenance (seed, determinism, physics list)
  trech_scores.jsonl          run_end tallies (edep, optics, primaries, analytic_checks, cascade)
  trech_hook_emits.jsonl      scenario sideband emits (fluid_frame, md_snapshot, ...)
  trech_viz_scene.json        geometry + materials + derived optics (parsed by scene.loader)
  trech_viz_trajectories.jsonl sampled photon/particle polylines
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional


# --- filenames (single source of truth) ------------------------------------------------

PROVENANCE_FILE = "trech_provenance.jsonl"
SCORES_FILE = "trech_scores.jsonl"
EMITS_FILE = "trech_hook_emits.jsonl"
VIZ_SCENE_FILE = "trech_viz_scene.json"
VIZ_TRAJECTORIES_FILE = "trech_viz_trajectories.jsonl"
EVENT_SCORES_FILE = "trech_event_scores.jsonl"


def _iter_jsonl(path: Path) -> Iterator[Dict[str, Any]]:
    """Yield parsed objects from a JSONL file, skipping blank/comment/garbage lines.

    The engine appends to some files (e.g. hook emits) across reruns, so tolerate a stray
    unparseable line rather than aborting the whole load.
    """
    if not path.is_file():
        return
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                yield obj


@dataclass
class HookEmit:
    """One ``ctx.emit(tag, payload)`` record from trech_hook_emits.jsonl."""

    hook: str
    tag: str
    event_id: int
    step_index: int
    payload: Any

    @classmethod
    def from_raw(cls, raw: Dict[str, Any]) -> "HookEmit":
        return cls(
            hook=str(raw.get("hook") or ""),
            tag=str(raw.get("tag") or ""),
            event_id=int(raw.get("event_id", -1)),
            step_index=int(raw.get("step_index", -1)),
            payload=raw.get("payload"),
        )


@dataclass
class RunResult:
    """Everything Studio needs to view one run, parsed from an output directory."""

    output_dir: Path
    provenance: List[Dict[str, Any]] = field(default_factory=list)
    scores: List[Dict[str, Any]] = field(default_factory=list)
    emits: List[HookEmit] = field(default_factory=list)
    viz_scene_path: Optional[Path] = None
    trajectories_path: Optional[Path] = None

    # --- convenience accessors -----------------------------------------------------------

    def run_end_scores(self) -> Optional[Dict[str, Any]]:
        for rec in self.scores:
            if rec.get("phase") == "run_end":
                return rec
        return self.scores[-1] if self.scores else None

    def run_start_provenance(self) -> Optional[Dict[str, Any]]:
        for rec in self.provenance:
            if rec.get("phase") == "run_start":
                return rec
        return self.provenance[0] if self.provenance else None

    def summary(self) -> Dict[str, Any]:
        """A compact, honest run header for the UI (seed / determinism / physics list / tallies)."""
        prov = self.run_start_provenance() or {}
        scores = self.run_end_scores() or {}
        return {
            "seed": scores.get("seed", prov.get("seed")),
            "n_events": scores.get("n_events", prov.get("n_events")),
            "determinism_mode": scores.get("determinism_mode", prov.get("determinism_mode")),
            "predictive_mode": scores.get("predictive_mode", prov.get("predictive_mode")),
            "physics_list": scores.get("physics_list", prov.get("physics_list")),
            "geant4_version": prov.get("geant4_version"),
            "total_edep_mev": scores.get("total_edep_mev"),
            "primaries_transmitted_fraction": scores.get("primaries_transmitted_fraction"),
            "primaries_uncollided_fraction": scores.get("primaries_uncollided_fraction"),
            "analytic_checks_within_tolerance": scores.get("analytic_checks_within_tolerance"),
            "hook_emit_count": scores.get("hook_emit_count", prov.get("hook_emit_count")),
        }

    def emit_tags(self) -> List[str]:
        seen: Dict[str, None] = {}
        for e in self.emits:
            seen.setdefault(e.tag, None)
        return list(seen.keys())

    def emits_by_tag(self, tag: str) -> List[HookEmit]:
        return [e for e in self.emits if e.tag == tag]


def load_run_result(output_dir: Path) -> RunResult:
    """Parse an output directory. Missing files are tolerated (partial runs still view)."""
    output_dir = Path(output_dir)
    result = RunResult(output_dir=output_dir)
    result.provenance = list(_iter_jsonl(output_dir / PROVENANCE_FILE))
    result.scores = list(_iter_jsonl(output_dir / SCORES_FILE))
    result.emits = [HookEmit.from_raw(r) for r in _iter_jsonl(output_dir / EMITS_FILE)]

    viz_scene = output_dir / VIZ_SCENE_FILE
    if viz_scene.is_file():
        result.viz_scene_path = viz_scene
    trajectories = output_dir / VIZ_TRAJECTORIES_FILE
    if trajectories.is_file():
        result.trajectories_path = trajectories
    return result
