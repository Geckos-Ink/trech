"""Local completion respects executable API contexts and the source-draft contract."""
import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from trech_studio.ui.code_editor import CodeEditor, completion_candidates

_APP = QApplication.instance() or QApplication([])


@pytest.mark.parametrize(("code", "prefix", "expected"), [
    ("ctx.ca", "ca", ("cascade",)),
    ("ctx.rng.", "", ("int", "normal", "uniform")),
    ("ctx.runtime.", "", ("mode", "nEvents", "runId", "seed")),
    ("ctx.step.step", "step", ("stepLengthMm",)),
    ("ctx.step.po", "po", ("postKineticEnergyMeV", "postPositionMm", "postTimeNs")),
    ("ctx.step.pa", "pa", ("parentTrackId", "particle")),
    ("TRECH_GEOMETRY.", "", ("assertClean", "audit", "concentricShells", "grid", "layerStack",
                             "ring", "sphereVolume", "volume")),
    ("TRECH_CONFIG = { environment: { world", "world", ("worldMaterial", "worldSizeMm")),
    ("TRECH_CONFIG = { env", "env", ("environment",)),
    ("ctx.event.opticalPhotonT", "opticalPhotonT", ("opticalPhotonTrackLengthMm", "opticalPhotonTracks")),
    ("ctx.config.run.th", "th", ("threads",)),
    ("globalThis.TRECH_VALUE.in", "in", ("integer",)),
    ("TRECH_CONFIG.beam.en", "en", ("energyMeV", "energySpreadFractional")),
    ("globalThis.TRECH_CONFIG = { det", "det", ("detector", "determinism")),
    ("TRECH_CONFIG = {run: { nE", "nE", ("nEvents",)),
    ("TRECH_CONFIG={run:{nEvents:10},beam:{en", "en", ("energyMeV", "energySpreadFractional")),
    ("TRECH_CONFIG={beams:[{en", "en", ("energyMeV", "energySpreadFractional")),
    ("TRECH_CONFIG={models:[{name:'test'}, {req", "req", ("required_context_keys",)),
    ("TRECH_CONFIG={/* ctx.rng.fake */ run: {th", "th", ("threads",)),
    ("// 💧 observer\nctx.em", "em", ("emit",)),
    ("TRECH_VA", "TRECH_VA", ("TRECH_VALIDATIONS", "TRECH_VALUE")),
])
def test_completion_filters_by_receiver_and_config_object(code, prefix, expected):
    assert completion_candidates(code) == (prefix, expected)


@pytest.mark.parametrize("code", [
    "// ctx.em", "/* ctx.em", "'ctx.em", '"ctx.em', "`ctx.em", "`value ${ctx.em",
    "'escaped \\' ctx.em", "const other = {nEv", "TRECH_CONFIG = {run: unknown(nEv",
    "TRECH_CONFIG = {run: {nEvents: nEv", "other.em", "ctx.state.em", "ctx.rng.poisson",
    "ctx.track.", "ctx.config.unknown.en", "TRECH_CONFIG.run.NOT_A_FIELD",
])
def test_completion_ignores_comments_strings_dynamic_objects_and_values(code):
    assert completion_candidates(code)[1] == ()


def _editor_with_text(text):
    widget = CodeEditor()
    widget.resize(700, 400)
    widget.show()
    widget.editor.setPlainText(text)
    widget.editor.moveCursor(QTextCursor.End)
    widget.editor.setFocus()
    _APP.processEvents()
    return widget


@pytest.mark.parametrize("accept_key", [Qt.Key_Tab, Qt.Key_Return])
def test_completion_popup_accepts_key_and_is_one_undo_step(accept_key):
    widget = _editor_with_text("ctx.")
    try:
        QTest.keyClicks(widget.editor, "e")
        assert widget.editor.completer.popup().isVisible()
        QTest.keyClicks(widget.editor, "m")
        assert widget.editor.completer.popup().isVisible()
        assert widget.editor.completer.currentCompletion() == "emit"
        QTest.keyClick(widget.editor.completer.popup(), accept_key)
        assert widget.text() == "ctx.emit"
        widget.editor.undo()
        assert widget.text() == "ctx.em"
    finally:
        widget.close()


def test_explicit_completion_escape_and_ordinary_tab_do_not_insert_suggestion():
    widget = _editor_with_text("ctx.")
    try:
        QTest.keyClick(widget.editor, Qt.Key_Space, Qt.ControlModifier)
        assert widget.editor.completer.popup().isVisible()
        QTest.keyClick(widget.editor.completer.popup(), Qt.Key_Escape)
        assert not widget.editor.completer.popup().isVisible()
        assert widget.text() == "ctx."
        QTest.keyClick(widget.editor, Qt.Key_Tab)
        assert widget.text() == "ctx.\t"
        widget.editor.setPlainText("// ctx.")
        widget.editor.moveCursor(QTextCursor.End)
        QTest.keyClick(widget.editor, Qt.Key_Space, Qt.ControlModifier)
        assert not widget.editor.completer.popup().isVisible()
    finally:
        widget.close()


def test_completion_replaces_whole_identifier_after_unicode_and_rejects_stale_popup():
    widget = _editor_with_text("// 💧\nctx.emsuffix;")
    try:
        cursor = widget.editor.textCursor()
        cursor.movePosition(QTextCursor.PreviousCharacter, QTextCursor.MoveAnchor, len("suffix;"))
        widget.editor.setTextCursor(cursor)
        widget.editor._accept_completion("emit")
        assert widget.text() == "// 💧\nctx.emit;"
        widget.editor.setPlainText("other.em")
        widget.editor.moveCursor(QTextCursor.End)
        widget.editor._accept_completion("emit")
        assert widget.text() == "other.em"
        widget.editor.setPlainText("ctx.em")
        widget.editor.moveCursor(QTextCursor.End)
        widget.editor.setReadOnly(True)
        widget.editor._accept_completion("emit")
        assert widget.text() == "ctx.em"
    finally:
        widget.close()


def test_completion_keeps_dormant_source_drafts_and_root_run_target(tmp_path):
    root, module = tmp_path / "scenario.js", tmp_path / "module.js"
    root.write_text("// root\nctx.em", encoding="utf-8")
    module.write_text("// module\nctx.ca", encoding="utf-8")
    widget = CodeEditor()
    try:
        widget.load_file(root)
        widget.set_sources((root, module))
        widget.editor.moveCursor(QTextCursor.End)
        widget.editor._accept_completion("emit")
        widget.sources.setCurrentIndex(1)
        widget.editor.moveCursor(QTextCursor.End)
        widget.editor._accept_completion("cascade")
        assert widget.dirty_paths() == (root, module)
        assert widget.scenario_path() == root
        widget.sources.setCurrentIndex(0)
        assert widget.text() == "// root\nctx.emit"
        assert root.read_text() == "// root\nctx.em"
        widget.sources.setCurrentIndex(1)
        assert widget.text() == "// module\nctx.cascade"
        assert widget.save() == root
        assert module.read_text() == "// module\nctx.cascade"
    finally:
        widget.close()
