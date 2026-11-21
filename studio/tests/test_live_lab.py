"""Live scenario lab: the ``trech lab`` protocol routing and Studio's params/watch controller.

The protocol and controller checks run offline. ``test_live_lab_real_engine`` drives a real
Geant4 ``trech lab <scenario.js> --watch`` session when a built engine is available (``$TRECH_BIN``
or ``build/rel/trech``) and is skipped otherwise.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QCoreApplication, QObject, Signal  # noqa: E402

from trech_studio.engine.lab import LabSession  # noqa: E402
from trech_studio.engine.live_lab import LiveScenarioLab, describe_batch  # noqa: E402
from trech_studio.engine.locator import EngineLocation  # noqa: E402

_APP = QCoreApplication.instance() or QCoreApplication([])
REPO = Path(__file__).resolve().parents[2]
EXAMPLE = REPO / "examples" / "lab" / "live_hook_tuning.js"


def _collect(signal):
    seen = []
    signal.connect(seen.append)
    return seen


def test_protocol_routing_strips_prompts_and_splits_outputs():
    session = LabSession(EngineLocation(None, "missing"))
    plans, scripts, refusals, snapshots, messages = (
        _collect(session.round_plan), _collect(session.script_status), _collect(session.refused),
        _collect(session.snapshot), _collect(session.message))
    status = {"phase": "lab_script", "generation": 2, "trigger": "params",
              "sources": [{"path": "exp.js", "sha256": "ab"}]}
    session.handle_line("trech-lab> " + json.dumps(status))
    session.handle_line('trech-lab> trech-lab> {"phase":"lab_round_plan","planned_rounds":20}\r')
    session.handle_line("lab error: re-evaluation refused: restart the lab session")
    session.handle_line('{"phase":"lab_snapshot","config":{}}')
    session.handle_line("trech-lab> Scenario re-evaluated (script generation 2, params).")
    session.handle_line("trech-lab> ")
    assert scripts == [status] and session.generation == 2 and session.script == status
    assert plans == [{"phase": "lab_round_plan", "planned_rounds": 20}]
    assert refusals == ["re-evaluation refused: restart the lab session"]
    assert snapshots == [{"phase": "lab_snapshot", "config": {}}]
    assert messages == ["Scenario re-evaluated (script generation 2, params)."]


class _FakeSession(QObject):
    """Records commands; emits what a lab would print."""

    script_status = Signal(dict)
    round_plan = Signal(dict)
    refused = Signal(str)
    failed = Signal(str)
    stopped = Signal(int)

    def __init__(self):
        super().__init__()
        self.commands = []
        self.started_with = None
        self.scenario = None
        self.script = {}
        self.active = False

    @property
    def generation(self):
        return int(self.script.get("generation", 0))

    def is_active(self):
        return self.active

    def start(self, scenario, params, output_dir, watch):
        self.started_with = {"scenario": scenario, "params": list(params), "watch": watch}
        self.scenario = Path(scenario).resolve()
        self.active = True
        return True

    def simulate(self, events=None):
        self.commands.append(("simulate", events))
        return True

    def set_params(self, values):
        self.commands.append(("params", dict(values)))
        return True

    def quit(self):
        self.active = False


def test_controller_sends_only_changed_values_and_reports_batches(tmp_path):
    scenario = tmp_path / "exp.js"
    scenario.write_text("// scenario\n", encoding="utf-8")
    (tmp_path / "helper.js").write_text("// include\n", encoding="utf-8")
    fake = _FakeSession()
    lab = LiveScenarioLab(EngineLocation(None, "missing"), session=fake, debounce_ms=0)
    batches = _collect(lab.batch_finished)
    out = tmp_path / "out"
    out.mkdir()
    assert lab.start(scenario, {"threshold": 0.5, "mode": "fast"}, out)
    assert fake.started_with["watch"] is True
    assert fake.started_with["params"] == ["--param", "threshold=0.5", "--param", 'mode="fast"']
    assert fake.commands == [("simulate", None)]

    fake.script = {"phase": "lab_script", "generation": 1,
                   "sources": [{"path": "exp.js"}, {"path": "helper.js"}],
                   "data": [{"path": "table.json"}]}
    fake.script_status.emit(fake.script)

    # Unchanged values send nothing; a slider drag sends one params command with the last value.
    lab.values_changed({"threshold": 0.5, "mode": "fast"})
    lab.values_changed({"threshold": 0.2, "mode": "fast"})
    lab.values_changed({"threshold": 0.1, "mode": "fast"})
    lab._flush_params()
    assert fake.commands[1:] == [("params", {"threshold": 0.1}), ("simulate", None)]
    lab.values_changed({"threshold": 0.1, "mode": "fast"})
    lab._flush_params()
    assert len(fake.commands) == 3

    # Only files the active generation read run a batch on save.
    assert lab.source_saved(tmp_path / "helper.js")
    assert lab.source_saved(tmp_path / "table.json")
    assert not lab.source_saved(tmp_path / "unrelated.js")
    assert fake.commands[3:] == [("simulate", None), ("simulate", None)]

    # Each batch reports the onRunEnd emits appended since the previous one.
    emits = out / "trech_hook_emits.jsonl"
    first = {"hook": "onRunEnd", "tag": "tally", "payload": {"above": 3}}
    emits.write_text(json.dumps(first) + "\n" + json.dumps({"hook": "onEventEnd", "tag": "x"}) + "\n",
                     encoding="utf-8")
    fake.round_plan.emit({"phase": "lab_round_plan", "planned_rounds": 20, "achieved_hz": 4.0})
    with emits.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"hook": "onRunEnd", "tag": "tally", "payload": {"above": 5}}) + "\n")
        handle.write('{"hook": "onRunEnd", "tag": "partial"')  # not yet terminated
    fake.round_plan.emit({"phase": "lab_round_plan", "planned_rounds": 20, "achieved_hz": 4.0})
    assert [b["emits"][0]["payload"]["above"] for b in batches] == [3, 5]
    assert all(len(b["emits"]) == 1 and b["generation"] == 1 for b in batches)
    line = describe_batch(batches[0])
    assert "generation 1" in line and "20 events" in line and 'tally: {"above":3}' in line

    lab.stop()
    assert not lab.is_active()
    lab.values_changed({"threshold": 0.3})
    assert not lab._pending


def _engine() -> Path | None:
    for candidate in (os.environ.get("TRECH_BIN"), REPO / "build" / "rel" / "trech"):
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return Path(candidate)
    return None


def _wait(condition, timeout=180.0):
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("timed out waiting for the live lab")
        QCoreApplication.processEvents()
        time.sleep(0.01)


@pytest.mark.skipif(_engine() is None, reason="needs a built trech engine with Geant4")
def test_live_lab_real_engine(tmp_path):
    scenario = tmp_path / "live_hook_tuning.js"
    shutil.copyfile(EXAMPLE, scenario)
    lab = LiveScenarioLab(EngineLocation(_engine(), "test"), debounce_ms=0)
    batches, errors = _collect(lab.batch_finished), _collect(lab.error)
    try:
        assert lab.start(scenario, {"edep_threshold_mev": 0.5, "beam_energy_mev": 1.25},
                         tmp_path / "out", events=20)
        _wait(lambda: len(batches) == 1)

        lab.values_changed({"edep_threshold_mev": 0.1, "beam_energy_mev": 1.25})
        lab._flush_params()
        _wait(lambda: len(batches) == 2)

        lab.values_changed({"edep_threshold_mev": 0.1, "beam_energy_mev": 2.0})
        lab._flush_params()
        _wait(lambda: len(batches) == 3)

        text = scenario.read_text(encoding="utf-8")
        scenario.write_text(text.replace("batch_in_generation: batches,",
                                         "batch_in_generation: batches, edited: true,"),
                            encoding="utf-8")
        assert lab.source_saved(scenario)
        _wait(lambda: len(batches) == 4)
    finally:
        lab.stop()

    payloads = [b["emits"][0]["payload"] for b in batches]
    assert [p["threshold_mev"] for p in payloads] == [0.5, 0.1, 0.1, 0.1]
    assert [b["generation"] for b in batches] == [1, 2, 2, 3]
    assert payloads[3].get("edited") is True and "edited" not in payloads[2]
    assert len(errors) == 1 and "restart the lab session" in errors[0]
    # Identical Geant4 transport across generations: the same seed gives the same deposits.
    assert len({round(p["mean_edep_mev"], 12) for p in payloads}) == 1
