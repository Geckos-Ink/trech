"""Engine trace panel: the live tail of ``trech_trace.jsonl``, the level/category request for the
next run, display filtering and the attribution banner.

    QT_QPA_PLATFORM=offscreen python -m pytest studio/tests/test_trace_log.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from trech_studio.engine.locator import locate_engine  # noqa: E402
from trech_studio.engine.trace_feed import (TraceFilter, TraceTail, describe, parse_categories,  # noqa: E402
                                            trace_args, trace_spec)
from trech_studio.ui.trace_log import TraceLogPanel  # noqa: E402

_APP = QApplication.instance() or QApplication([])
REPO = Path(__file__).resolve().parents[2]


def _record(seq, level="info", cat="hook", msg="m", **extra):
    return dict({"schema": "trech_trace_v1", "seq": seq, "level": level, "cat": cat, "msg": msg}, **extra)


def _settings(tmp_path):
    return QSettings(str(tmp_path / "studio.ini"), QSettings.IniFormat)


def test_tail_returns_complete_lines_and_restarts_on_truncation(tmp_path):
    path = tmp_path / "trech_trace.jsonl"
    tail = TraceTail(path)
    assert tail.poll() == []  # no file yet
    with open(path, "w") as out:
        out.write(json.dumps(_record(1)) + "\n" + json.dumps(_record(2))[:10])
    assert [r["seq"] for r in tail.poll()] == [1]
    with open(path, "a") as out:
        out.write(json.dumps(_record(2))[10:] + "\nnot json\n")
    assert [r["seq"] for r in tail.poll()] == [2]
    assert tail.bad_lines == 1
    path.write_text(json.dumps(_record(9)) + "\n")  # a new run rewrote the file
    assert [r["seq"] for r in tail.poll()] == [9]
    assert tail.resets == 1


def test_spec_args_and_filter():
    assert trace_spec("debug", ["hook", " predict "]) == "debug:hook,predict"
    assert trace_args("off", [], Path("x")) == []
    assert trace_args("trace", ["evolve"], Path("o/t.jsonl")) == ["--trace", "trace:evolve", "--trace-file", "o/t.jsonl"]
    assert parse_categories("hook; predict,, ") == ["hook", "predict"]
    with pytest.raises(ValueError):
        trace_spec("loud")
    f = TraceFilter(level="info", categories=["hook"])
    assert f.accepts(_record(1, "info", "hook"))
    assert not f.accepts(_record(2, "debug", "hook"))
    assert not f.accepts(_record(3, "info", "predict"))
    assert f.accepts(_record(4, "info", "script", severity="warn")), "warnings always pass"
    assert f.accepts(_record(5, "summary", "summary")), "the summary always passes"
    assert "onEventEnd#3" in describe(_record(6, hook="onEventEnd", event=3))


def test_panel_requests_level_filters_live_and_shows_the_verdict(tmp_path):
    panel = TraceLogPanel(settings=_settings(tmp_path), poll_ms=10)
    panel.level.setCurrentText("debug")
    panel.categories.setText("hook,predict")
    panel.categories.editingFinished.emit()
    out = tmp_path / "run"
    assert panel.command_args(out) == ["--trace", "debug:hook,predict", "--trace-file", str(out / "trech_trace.jsonl")]
    out.mkdir()
    panel.begin(out, "demo.js")
    assert panel.is_following()
    trace = out / "trech_trace.jsonl"
    with open(trace, "w") as stream:
        stream.write(json.dumps(_record(1, "debug", "hook", "onEventEnd", hook="onEventEnd", event=0,
                                        data={"emits": 1})) + "\n")
        stream.write(json.dumps(_record(2, "trace", "predict", "ctx.predict")) + "\n")
        stream.write(json.dumps(_record(3, "info", "scenario", "note")) + "\n")
    assert panel.poll() == 3
    assert panel.record_count() == 1, "trace-level and other-category records are filtered out"
    panel.level.setCurrentText("trace")
    assert panel.record_count() == 2, "raising the shown level reveals stored records"
    panel.categories.setText("")
    panel.categories.editingFinished.emit()
    assert panel.record_count() == 3
    panel.search.setText("note")
    assert panel.record_count() == 1
    panel.search.setText("")
    with open(trace, "a") as stream:
        stream.write(json.dumps(_record(4, "summary", "summary", "run attribution summary",
                                        data={"verdict": "1 of 2 ctx inference calls returned an engine result.",
                                              "models_missing": ["viscosity"]})) + "\n")
    panel.finish()
    assert not panel.is_following()
    assert "1 of 2 ctx inference calls" in panel.banner.text() and "viscosity" in panel.banner.text()
    assert panel.summary()["models_missing"] == ["viscosity"]
    # The level is remembered for the next session.
    again = TraceLogPanel(settings=_settings(tmp_path))
    assert again.requested_level() == "trace"


def test_panel_off_adds_no_arguments_but_still_shows_an_inherited_trace(tmp_path):
    panel = TraceLogPanel(settings=_settings(tmp_path))
    panel.level.setCurrentText("off")
    assert panel.command_args(tmp_path) == []
    (tmp_path / "trech_trace.jsonl").write_text(json.dumps(_record(1, "trace", "predict")) + "\n")
    assert panel.load_file(tmp_path / "trech_trace.jsonl") == 1
    assert panel.record_count() == 1


def test_panel_follows_a_real_engine_run(tmp_path):
    engine = locate_engine(repo_root=REPO)
    if not engine.available:
        pytest.skip("no trech binary built")
    usage = subprocess.run([str(engine.path), "--help"], capture_output=True, text=True).stderr
    if "--trace" not in usage:
        pytest.skip(f"{engine.path} predates the engine trace; rebuild it")
    scenario = tmp_path / "logged.js"
    scenario.write_text("""
TRECH_TRACE.channel("demo").info("evaluating");
globalThis.TRECH_CONFIG = { run: { nEvents: 2, seed: 5 }, determinism: { mode: "strict" },
  hooks: { registered: ["onEventEnd"] } };
globalThis.TRECH_HOOKS = {
  onEventEnd(ctx) {
    const p = ctx.predict("absent", {});
    if (p === null) ctx.authored("fallback");
    console.log("event", ctx.event.id);
    ctx.emit("e", { id: ctx.event.id });
  },
};
""")
    panel = TraceLogPanel(settings=_settings(tmp_path))
    panel.level.setCurrentText("debug")
    out = tmp_path / "out"
    out.mkdir()
    panel.begin(out, "logged.js")
    run = subprocess.run([str(engine.path), "run", str(scenario), "--output", str(out)] + panel.command_args(out),
                         capture_output=True, text=True, timeout=300)
    assert run.returncode == 0, run.stderr[-2000:]
    panel.finish()
    cats = {panel.model.record(i)["cat"] for i in range(panel.record_count())}
    assert {"run", "demo", "console", "hook", "authored", "summary"} <= cats, cats
    assert panel.summary()["calls"]["predict"]["null_strict"] == 2
    assert "TRECH trace summary" in run.stderr
