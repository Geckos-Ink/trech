"""Per-stage execution status of a recorded solution/process recipe.

Reads only the engine-recorded ``process_recipe_state`` hook emits and, when
present, the recipe plan recorded in ``hooks.inputs.recipe.steps``. Nothing is
re-run, interpolated or inferred: a stage that never reported is shown as
``not reached``, a blocked stage keeps the engine's error code/reason, and
inference/draw counts are summed from each report's ``engine`` accounting.
A count of executed inferences says nothing about physical accuracy.
Commits the operator contract declared as no-ops (for example a spatial
binding whose ``empty_neighbourhood`` is ``complete``, or a scalar evolve/react binding
whose ``empty_population`` is ``complete``) are counted separately:
they advanced the process clock without running any operator.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

RECIPE_TAG = "process_recipe_state"
STATUSES = ("advanced", "complete", "blocked", "rejected", "strict_disabled")


@dataclass
class StageReport:
    process: str
    role: str = ""
    planned: bool = False
    attempts: int = 0
    counts: Dict[str, int] = field(default_factory=dict)
    last_status: str = "not reached"
    last_error_code: str = ""
    last_reason: str = ""
    contract_id: str = ""
    selection_status: str = ""
    inferences: int = 0
    out_of_domain: int = 0
    draws: int = 0
    no_ops: Dict[str, int] = field(default_factory=dict)
    first_event: Optional[int] = None
    last_event: Optional[int] = None

    @property
    def committed(self) -> int:
        return self.counts.get("advanced", 0) + self.counts.get("complete", 0)


@dataclass
class RecipeStatus:
    stages: List[StageReport]
    emits: int
    final_status: str
    completed: bool
    elapsed_s: Optional[float]
    calls: Optional[int]
    strict_disabled: int
    unplanned: List[str]

    @property
    def available(self) -> bool:
        return self.emits > 0


def _int(value: Any) -> int:
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


def _plan_steps(config: Optional[dict]) -> List[dict]:
    recipe = (((config or {}).get("hooks") or {}).get("inputs") or {}).get("recipe")
    steps = recipe.get("steps") if isinstance(recipe, dict) else None
    return [s for s in steps if isinstance(s, dict) and s.get("id")] if isinstance(steps, list) else []


def build_recipe_status(emits: Iterable[Any], config: Optional[dict] = None) -> RecipeStatus:
    """Summarise recorded recipe emits stage by stage, in plan order."""
    stages: Dict[str, StageReport] = {}
    for step in _plan_steps(config):
        stages[str(step["id"])] = StageReport(process=str(step["id"]), role=str(step.get("role") or ""), planned=True)
    count = strict = 0
    last: Optional[dict] = None
    for emit in emits:
        if getattr(emit, "tag", None) != RECIPE_TAG or not isinstance(getattr(emit, "payload", None), dict):
            continue
        payload = emit.payload
        count += 1
        last = payload
        status = str(payload.get("status") or "")
        if status == "strict_disabled":
            strict += 1
        process = payload.get("process")
        if not process:
            # complete/strict reports carry no active process; they do not touch a stage.
            continue
        stage = stages.setdefault(str(process), StageReport(process=str(process)))
        stage.attempts += 1
        stage.counts[status] = stage.counts.get(status, 0) + 1
        stage.last_status = status or "unknown"
        no_op = payload.get("no_op")
        if isinstance(no_op, str) and no_op and status in ("advanced", "complete"):
            stage.no_ops[no_op] = stage.no_ops.get(no_op, 0) + 1
        event = getattr(emit, "event_id", None)
        if isinstance(event, int) and event >= 0:
            stage.first_event = event if stage.first_event is None else stage.first_event
            stage.last_event = event
        report = payload.get("report") if isinstance(payload.get("report"), dict) else {}
        error = report.get("error") if isinstance(report.get("error"), dict) else {}
        stage.last_error_code = str(error.get("code") or "") if status in ("blocked", "rejected") else ""
        stage.last_reason = str(payload.get("reason") or "") if status in ("blocked", "rejected") else ""
        stage.contract_id = str(report.get("contract_id") or stage.contract_id)
        engine = report.get("engine") if isinstance(report.get("engine"), dict) else {}
        selection = engine.get("selection") if isinstance(engine.get("selection"), dict) else {}
        stage.selection_status = str(selection.get("status") or stage.selection_status)
        stage.inferences += _int(engine.get("inferenceCount"))
        stage.out_of_domain += _int(engine.get("outOfDomainInferences"))
        stage.draws += _int(engine.get("drawCount"))
    elapsed = last.get("elapsed_s") if last else None
    calls = last.get("calls") if last else None
    return RecipeStatus(
        stages=list(stages.values()), emits=count,
        final_status=str(last.get("status") or "") if last else "",
        completed=bool(last.get("completed")) if last else False,
        elapsed_s=float(elapsed) if isinstance(elapsed, (int, float)) and not isinstance(elapsed, bool) else None,
        calls=int(calls) if isinstance(calls, (int, float)) and not isinstance(calls, bool) else None,
        strict_disabled=strict,
        unplanned=[s.process for s in stages.values() if not s.planned and _plan_steps(config)])


def stage_summary(stage: StageReport) -> str:
    if not stage.attempts:
        return "not reached — no recorded report"
    parts = [f"{stage.last_status}", f"{stage.attempts} call(s)", f"{stage.committed} committed"]
    no_ops = sum(stage.no_ops.values())
    if no_ops:
        parts.append(f"{no_ops} no-op")
    for status in ("blocked", "rejected"):
        if stage.counts.get(status):
            parts.append(f"{stage.counts[status]} {status}")
    return " · ".join(parts)


def stage_details(stage: StageReport) -> List[str]:
    lines = []
    if stage.role:
        lines.append(f"operator role: {stage.role}")
    if stage.contract_id:
        lines.append(f"contract: {stage.contract_id}")
    if stage.selection_status:
        lines.append(f"model selection: {stage.selection_status}")
    if stage.last_error_code or stage.last_reason:
        lines.append(f"last error: {stage.last_error_code or 'none'} — {stage.last_reason}".rstrip(" —"))
    for reason, n in sorted(stage.no_ops.items()):
        lines.append(f"declared no-op commits: {n} × {reason.replace('_', ' ')} (no operator ran; clock advanced)")
    if stage.attempts:
        lines.append(f"inferences {stage.inferences} · out-of-domain {stage.out_of_domain} · draws {stage.draws}")
    if stage.first_event is not None:
        lines.append(f"events {stage.first_event}–{stage.last_event}")
    if not stage.planned:
        lines.append("not in the recorded recipe plan")
    return lines


def overall_summary(status: RecipeStatus) -> str:
    if not status.available:
        return "No process_recipe_state emits recorded."
    text = (f"{status.emits} recorded recipe step(s); last status {status.final_status or 'unknown'}; "
            f"{'completed' if status.completed else 'not completed'}")
    if status.elapsed_s is not None:
        text += f"; committed process time {status.elapsed_s:g} s"
    if status.strict_disabled:
        text += f"; {status.strict_disabled} strict-mode step(s) disabled inference by design"
    return text + ". Status reflects recorded operator execution, not physical accuracy."
