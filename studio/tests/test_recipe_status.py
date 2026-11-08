"""Recorded recipe stage reports: pure summary plus the offscreen Processes panel view."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication  # noqa: E402

from trech_studio.engine.outputs import HookEmit  # noqa: E402
from trech_studio.recipe_status import build_recipe_status, overall_summary, stage_details  # noqa: E402
from trech_studio.ui.processes import ProcessesPanel  # noqa: E402

_APP = QApplication.instance() or QApplication([])

CONFIG = {"hooks": {"inputs": {"recipe": {"steps": [
    {"id": "mix", "role": "solution_dissolution"},
    {"id": "heat", "role": "solution_thermal"},
    {"id": "evaporate", "role": "solution_evaporation"},
]}}}}


def _emit(event, payload, tag="process_recipe_state"):
    return HookEmit(hook="onEventEnd", tag=tag, event_id=event, step_index=-1, payload=payload)


def _report(ran, accepted, inferences=0, draws=0, ood=0, code=None, selection="selected"):
    report = {"ran": ran, "accepted": accepted, "contract_id": "c",
              "engine": {"inferenceCount": inferences, "drawCount": draws, "outOfDomainInferences": ood,
                         "selection": {"status": selection}}}
    if code:
        report["error"] = {"code": code, "message": code}
    return report


def _emits():
    return [
        _emit(0, {"status": "advanced", "process": "mix", "elapsed_s": 0.1, "calls": 1, "completed": False,
                  "report": _report(True, True, inferences=4, draws=4)}),
        _emit(1, {"status": "rejected", "process": "mix", "elapsed_s": 0.1, "calls": 2, "completed": False,
                  "reason": "conservation violated", "report": _report(True, False, inferences=4, draws=4, ood=1)}),
        _emit(2, {"status": "advanced", "process": "mix", "elapsed_s": 0.2, "calls": 3, "completed": False,
                  "report": _report(True, True, inferences=4, draws=4)}),
        _emit(3, {"status": "blocked", "process": "heat", "elapsed_s": 0.2, "calls": 4, "completed": False,
                  "reason": "Required operator unavailable",
                  "report": _report(False, False, code="operator_unavailable", selection="no_compatible")}),
        _emit(3, {"ignored": True}, tag="material_frame"),
    ]


def test_stages_follow_plan_and_keep_engine_accounting() -> None:
    status = build_recipe_status(_emits(), CONFIG)
    assert [s.process for s in status.stages] == ["mix", "heat", "evaporate"]
    mix, heat, evaporate = status.stages
    assert (mix.attempts, mix.committed, mix.counts.get("rejected")) == (3, 2, 1)
    # Rejected proposals still ran inference: their accounting is kept.
    assert (mix.inferences, mix.draws, mix.out_of_domain) == (12, 12, 1)
    assert mix.last_status == "advanced" and mix.last_error_code == ""
    assert (mix.first_event, mix.last_event) == (0, 2)
    assert heat.last_status == "blocked" and heat.last_error_code == "operator_unavailable"
    assert heat.selection_status == "no_compatible" and heat.committed == 0
    assert evaporate.attempts == 0 and evaporate.last_status == "not reached"
    assert status.emits == 4 and status.final_status == "blocked" and not status.completed
    assert status.elapsed_s == 0.2 and status.calls == 4 and status.unplanned == []
    assert "not physical accuracy" in overall_summary(status)
    assert any("operator_unavailable" in line for line in stage_details(heat))


def test_strict_and_unplanned_and_empty_runs() -> None:
    strict = [_emit(i, {"status": "strict_disabled", "report": None, "elapsed_s": 0, "calls": 0,
                        "completed": False}) for i in range(3)]
    status = build_recipe_status(strict, CONFIG)
    assert status.strict_disabled == 3 and all(s.attempts == 0 for s in status.stages)
    assert "disabled inference by design" in overall_summary(status)
    extra = build_recipe_status([_emit(0, {"status": "advanced", "process": "dry", "report": {}})], CONFIG)
    assert extra.unplanned == ["dry"]
    assert "not in the recorded recipe plan" in stage_details(extra.stages[-1])
    # Without a recorded plan, stages appear in report order and nothing is called unplanned.
    unplanned = build_recipe_status(_emits())
    assert [s.process for s in unplanned.stages] == ["mix", "heat"] and unplanned.unplanned == []
    empty = build_recipe_status([], None)
    assert not empty.available and empty.stages == []
    assert overall_summary(empty) == "No process_recipe_state emits recorded."


def test_processes_panel_shows_recipe_stages() -> None:
    panel = ProcessesPanel()
    panel.set_recipe_reports(_emits(), CONFIG)
    assert panel.recipe.topLevelItemCount() == 3
    heat = panel.recipe.topLevelItem(1)
    assert heat.text(0) == "heat" and heat.text(1).startswith("blocked")
    details = [heat.child(i).text(1) for i in range(heat.childCount())]
    assert any("operator_unavailable" in line for line in details)
    assert panel.recipe.topLevelItem(2).text(1).startswith("not reached")
    panel.set_recipe_reports([])
    assert panel.recipe.topLevelItemCount() == 0
    assert panel.recipe_summary.text() == "No process_recipe_state emits recorded."
