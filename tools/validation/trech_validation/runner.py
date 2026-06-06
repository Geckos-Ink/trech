"""Validation runner — loads run outputs and dispatches cases."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .cases import ALL_CASES, CaseResult, ValidationCase


@dataclass
class RunOutputs:
    """Bag of parsed outputs for a single TRECH run directory."""

    directory: Path
    scores: Optional[dict] = None
    provenance: List[dict] = field(default_factory=list)
    viz_scene: Optional[dict] = None
    viz_trajectories: List[dict] = field(default_factory=list)
    hook_emits: List[dict] = field(default_factory=list)

    @classmethod
    def load(cls, directory: Path) -> "RunOutputs":
        directory = directory.expanduser().resolve()
        out = cls(directory=directory)
        scores_path = directory / "trech_scores.jsonl"
        if scores_path.exists():
            with open(scores_path, "r", encoding="utf-8") as fh:
                lines = [l.strip() for l in fh if l.strip()]
            if lines:
                # The run-end record is the last in the file by convention.
                try:
                    out.scores = json.loads(lines[-1])
                except json.JSONDecodeError:
                    out.scores = None
        prov_path = directory / "trech_provenance.jsonl"
        if prov_path.exists():
            with open(prov_path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.provenance.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        scene_path = directory / "trech_viz_scene.json"
        if scene_path.exists():
            try:
                out.viz_scene = json.loads(scene_path.read_text())
            except json.JSONDecodeError:
                pass
        traj_path = directory / "trech_viz_trajectories.jsonl"
        if traj_path.exists():
            with open(traj_path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.viz_trajectories.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        emits_path = directory / "trech_hook_emits.jsonl"
        if emits_path.exists():
            with open(emits_path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.hook_emits.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return out


@dataclass
class RunContext:
    """Loaded outputs for every named run dir referenced by cases."""

    runs: Dict[str, RunOutputs] = field(default_factory=dict)

    def get(self, name: str) -> Optional[RunOutputs]:
        return self.runs.get(name)


def load_runs(runs_dir: Path, names: List[str]) -> RunContext:
    ctx = RunContext()
    for name in names:
        path = runs_dir / name
        if path.exists():
            ctx.runs[name] = RunOutputs.load(path)
    return ctx


def required_run_names() -> List[str]:
    names = set()
    for case in ALL_CASES:
        for ref in case.required_runs():
            names.add(ref)
    return sorted(names)


def run_all(runs_dir: Path) -> List[CaseResult]:
    ctx = load_runs(runs_dir, required_run_names())
    results: List[CaseResult] = []
    for case in ALL_CASES:
        try:
            result = case.evaluate(ctx)
        except Exception as exc:  # pragma: no cover - guard for case bugs
            result = CaseResult(
                name=case.name,
                description=case.description,
                category=case.category,
                status="error",
                summary=f"case raised {type(exc).__name__}: {exc}",
            )
        results.append(result)
    # Stable alphabetical order keeps the Markdown diff clean.
    results.sort(key=lambda r: (r.category, r.name))
    return results
