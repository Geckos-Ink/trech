"""Models dock: registry/inspection parsing and the offscreen panel against the real trech-ml CLI.

    QT_QPA_PLATFORM=offscreen python -m pytest tests/test_models.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication  # noqa: E402

from trech_studio.engine import models as bridge  # noqa: E402
from trech_studio.models import (  # noqa: E402
    discover_definition_files, human_bytes, ml_include_line, model_entry_snippet, new_definition_source, parse_inspection, parse_prune,
    parse_registry, relative_time,
)
from trech_studio.ui.code_editor import CodeEditor  # noqa: E402
from trech_studio.ui.models import ModelsPanel, PruneDialog  # noqa: E402

_APP = QApplication.instance() or QApplication([])
REPO = Path(__file__).resolve().parents[2]
NODE = bridge.node_executable()
needs_node = pytest.mark.skipif(NODE is None, reason="Node.js is required for the trech-ml CLI")

VALID = """TRECH_ML.defineModel({name: "demo", inputs: ["a", "b"], outputs: ["y"], scale: "meso",
  structure: {family: "mlp", width: 4, depth: 1}, training: {runs: ["runs/train"]}});
"""


def _model_json(path: Path, width: int = 4, bias: float = 0.0) -> Path:
    layers = [{"weights": [[0.1, 0.2]] * width, "bias": [bias] * width, "activation": "silu"},
              {"weights": [[0.3] * width], "bias": [0.0], "activation": "none"}]
    path.write_text(json.dumps({"model": "generic_surrogate_v1", "input_features": ["a", "b"], "output_features": ["y"],
                                "input_mean": [0, 0], "input_std": [1, 1], "output_mean": [0], "output_std": [1], "layers": layers,
                                "holdout": {"r2_min": 0.91, "n": 12}}))
    return path


def _cli(store: Path, *args: str):
    proc = subprocess.run([NODE, str(REPO / bridge.CLI), *args, "--store", str(store), "--json"], capture_output=True, text=True, cwd=REPO)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


@pytest.fixture
def workspace(tmp_path):
    ml_root = tmp_path / "ml"
    (ml_root / "definitions").mkdir(parents=True)
    (ml_root / "definitions" / "demo.model.js").write_text(VALID)
    store = tmp_path / "store"
    return ml_root, store


def test_registry_parsing_sorting_and_honest_absence():
    assert parse_registry(None).is_empty
    assert parse_registry({"schema": "other"}).error
    raw = {"schema": "trech_model_registry_v1", "models": {
        "a": {"active": "a@v2", "checkpoints": [
            {"id": "a@v1", "name": "a", "version": 1, "role": "final", "structure_id": "s1", "structure_label": "linear", "size_bytes": 100,
             "use_count": 1, "last_used_at": "2026-01-01T00:00:00Z", "files": [{"format": "generic_surrogate"}], "metrics": None},
            {"id": "a@v2", "name": "a", "version": 2, "role": "best", "structure_id": "s2", "structure_label": "mlp", "size_bytes": 50,
             "use_count": 0, "files": [], "metrics": {"y": {"r2": 0.8}, "z": {"r2": 0.6}}, "holdout_source": "selection_runs",
             "validation": {"status": "warn", "failed": [], "warned": ["beats_linear_baseline"], "report": "validations/a/x.json"}}]},
        "b": {"active": None, "checkpoints": [
            {"id": "b@v1", "name": "b", "version": 1, "role": "final", "structure_id": "s3", "structure_label": "mlp", "size_bytes": 900,
             "use_count": 5, "last_used_at": "2025-06-01T00:00:00Z", "files": []}]}}}
    registry = parse_registry(raw)
    assert [m.name for m in registry.sorted_models("uses")] == ["b", "a"]
    assert [m.name for m in registry.sorted_models("recent")] == ["a", "b"]
    assert [m.name for m in registry.sorted_models("size")] == ["b", "a"]
    a = registry.models[0]
    assert [c.id for c in a.checkpoints] == ["a@v2", "a@v1"] and a.checkpoints[0].active
    assert a.checkpoints[1].metric_summary() == "no carried accuracy"
    assert a.checkpoints[0].metric_summary() == "R²min 0.600"
    assert "optimistic" in a.checkpoints[0].holdout_note()
    assert a.checkpoints[0].validation_summary() == "warn · warn beats_linear_baseline"
    assert a.checkpoints[1].validation_summary() == "not validated"
    assert registry.total_bytes == 1050 and a.structures == 2
    now = datetime(2026, 1, 1, 2, 0, tzinfo=timezone.utc)
    assert relative_time(None) == "never"
    assert relative_time("2026-01-01T00:00:00Z", now) == "2 h ago"
    assert human_bytes(1536) == "1.5 KiB" and human_bytes(None) == "–"


def test_inspection_and_prune_parsing():
    bad = parse_inspection({"schema": "trech_ml_inspection_v1", "ok": False, "errors": [{"message": "boom", "line": 3}]})
    assert not bad.ok and bad.errors[0].describe() == "line 3: boom"
    assert not parse_inspection(None).ok
    assert parse_inspection({"event": "error", "message": "no node"}).errors[0].message == "no node"
    plan = parse_prune({"delete": [{"id": "x@v1"}], "total_bytes": 2048, "bytes_freed": 1024, "dry_run": True, "fits": False})
    assert "Would delete 1 checkpoint(s), freeing 1.0 KiB of 2.0 KiB" in plan.describe() and "cannot be met" in plan.describe()
    with pytest.raises(ValueError):
        parse_prune({})
    assert "defineSearch" in new_definition_source("search", "s") and "defineModel" in new_definition_source("model", "m")


def test_definition_discovery(workspace):
    ml_root, _ = workspace
    (ml_root / "shared").mkdir()
    (ml_root / "shared" / "columns.js").write_text("globalThis.X = 1;")
    (ml_root / "searches").mkdir()
    (ml_root / "searches" / "s.search.js").write_text("")
    assert [p.relative_to(ml_root).as_posix() for p in discover_definition_files(ml_root)] == ["definitions/demo.model.js", "searches/s.search.js"]


@needs_node
def test_live_inspection_follows_the_unsaved_draft(workspace):
    ml_root, store = workspace
    panel = ModelsPanel(REPO, store, confirm=lambda *_: True, ml_root=ml_root)
    assert panel.files.count() == 1
    panel.load_definition(ml_root / "definitions" / "demo.model.js")
    panel.inspector.wait()
    assert panel.inspection.ok and panel.inspection.definitions[0]["parameter_count"] == 2 * 4 + 4 + 4 + 1
    assert panel.run_button.isEnabled() and panel.run_button.text() == "Train ▶"
    panel.editor.setPlainText(VALID.replace("width: 4", "width: 0"))
    assert panel.is_dirty() and panel.save_button.isEnabled()
    inspection = panel.inspect_now()
    assert not inspection.ok and inspection.errors[0].line == 1 and "structure.width" in inspection.errors[0].message
    assert "line 1" in panel.validation.text() and not panel.run_button.isEnabled()
    # Debounced async path: wait for the timer and the inspector process.
    panel.editor.setPlainText(VALID.replace("width: 4", "width: 8"))
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and (panel.inspection is None or not panel.inspection.ok):
        _APP.processEvents()
        panel.inspector.wait(200)
    assert panel.inspection.ok and panel.inspection.definitions[0]["structure"]["width"] == 8
    assert (ml_root / "definitions" / "demo.model.js").read_text() == VALID, "inspection never writes the file"
    panel.save()
    assert (ml_root / "definitions" / "demo.model.js").read_text().count("width: 8") == 1 and not panel.is_dirty()
    created = panel.create_definition("search", "fresh")
    assert created == ml_root / "searches" / "fresh.search.js" and panel.run_button.text() == "Search ▶"
    panel.shutdown()


@needs_node
def test_checkpoint_management_through_the_cli(workspace, tmp_path):
    ml_root, store = workspace
    first = _cli(store, "register", str(_model_json(tmp_path / "m1.json")), "--name", "demo")
    second = _cli(store, "register", str(_model_json(tmp_path / "m2.json", bias=1.0)), "--name", "demo", "--role", "candidate")
    asked = []
    panel = ModelsPanel(REPO, store, confirm=lambda title, text: asked.append((title, text)) or True, ml_root=ml_root)
    rows = panel.checkpoint_rows()
    assert rows[0][0] == "demo" and rows[1][0] == second["id"] and rows[2][0] == first["id"]
    assert rows[2][8] == "R²min 0.910" and rows[2][5] == "never"
    assert panel.select(first["id"])
    panel.toggle_pin()
    assert panel.registry.checkpoint(first["id"]).pinned and "PINNED" in panel.checkpoint_rows()[2][7]
    panel.select(first["id"])
    panel.activate_selected()
    assert panel.registry.models[0].active == first["id"]
    # Prune: preview first; pinned/active/candidate rules come from the CLI.
    dialog = PruneDialog(panel.prune_preview)
    dialog.keep_last.setValue(0)
    dialog.run_preview()
    assert [d["id"] for d in dialog.plan.delete] == [second["id"]] and dialog.delete_button.isEnabled()
    dialog.keep_last.setValue(1)
    assert not dialog.delete_button.isEnabled(), "changing the policy invalidates the preview"
    plan = panel.prune(["--keep-last", "0"])
    assert plan.removed and panel.registry.checkpoint(second["id"]) is None
    # Usage is recorded from run provenance hashes, once per run.
    run = tmp_path / "run"
    run.mkdir()
    sha = panel.registry.checkpoint(first["id"]).files[0]["sha256"]
    (run / "trech_provenance.jsonl").write_text(json.dumps({"phase": "run_start", "config_hash": "c",
                                                            "model_artifacts": {"models": [{"loaded": True, "sha256": sha}]}}) + "\n")
    assert first["id"] in panel.record_run_usage(run)
    assert panel.record_run_usage(run) is None
    assert panel.registry.checkpoint(first["id"]).use_count == 1
    # Delete asks about the protected (pinned + active) checkpoint, then for final confirmation.
    panel.select("demo")
    assert panel.delete_selected()
    assert any("protected" in text for _, text in asked) and any("cannot be undone" in text for _, text in asked)
    assert panel.registry.is_empty and not (store / "checkpoints" / "demo").exists()
    panel.shutdown()


def _evaluate_entry(snippet: str, source: Path) -> dict:
    """Evaluate a modelEntry snippet with the real js/trech_ml.js, reading JSON relative to ``source``."""
    script = """
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const [lib, dir, snippet] = process.argv.slice(1);
const context = vm.createContext({TRECH_READ_JSON: (p) => JSON.parse(fs.readFileSync(path.resolve(dir, p), 'utf8'))});
vm.runInContext(fs.readFileSync(lib, 'utf8'), context);
process.stdout.write(JSON.stringify(vm.runInContext(snippet, context)));
"""
    proc = subprocess.run([NODE, "-e", script, str(REPO / "js" / "trech_ml.js"), str(source.parent), snippet],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


@needs_node
def test_model_entry_snippet_pins_the_selected_checkpoint(workspace, tmp_path):
    ml_root, store = workspace
    first = _cli(store, "register", str(_model_json(tmp_path / "m1.json")), "--name", "demo")
    second = _cli(store, "register", str(_model_json(tmp_path / "m2.json", width=6)), "--name", "demo")
    source = tmp_path / "scenarios" / "probe" / "probe.js"
    source.parent.mkdir(parents=True)
    source.write_text('TRECH_INCLUDE("../../js/trech_helpers.js");\n// config\nconst cfg = {models: []};\n')
    panel = ModelsPanel(REPO, store, confirm=lambda *_: True, ml_root=ml_root)
    assert not panel.insert_entry_button.isEnabled()
    with pytest.raises(ValueError, match="select a checkpoint"):
        panel.model_entry_for(source)
    # The older checkpoint stays loadable by name even though resolve() would pick the newest.
    assert panel.select(first["id"]) and panel.insert_entry_button.isEnabled()
    snippet, include = panel.model_entry_for(source, source.read_text())
    assert '"index": ' not in snippet and 'index: "../../store/index.json"' in snippet and "version: 1" in snippet
    assert "not a Geant4 result" in snippet and "scale" not in snippet, "an imported checkpoint records no scale"
    entry = _evaluate_entry(snippet, source)
    checkpoint = panel.registry.checkpoint(first["id"])
    assert entry["registry"]["checkpoint"] == first["id"] and entry["registry"]["resolved_by"] == "version"
    assert entry["registry"]["structure_id"] == checkpoint.structure_id and "scale" not in entry
    assert (source.parent / entry["path"]).resolve().is_file(), "the checkpoint path resolves from the scenario file"
    assert entry["registry"]["sha256"] == checkpoint.files[0]["sha256"]
    assert include == ml_include_line(source, REPO) and include.endswith('js/trech_ml.js");')
    assert (source.parent / include[len('TRECH_INCLUDE("'):-len('");')]).resolve() == (REPO / "js" / "trech_ml.js").resolve()
    assert panel.model_entry_for(source, 'TRECH_INCLUDE("x/trech_ml.js");')[1] == "", "an existing include is kept"
    # The newer checkpoint pins its own version and structure.
    panel.select(second["id"])
    other = _evaluate_entry(panel.model_entry_for(source)[0], source)
    assert other["registry"]["checkpoint"] == second["id"] and "scale" not in other
    # Through the signal: no open scenario is refused; an open one receives snippet + include.
    received = []
    panel.insert_snippet_requested.connect(lambda text, inc: received.append((text, inc)))
    assert not panel.request_model_entry() and received == []
    panel.scenario_source = lambda: (source, source.read_text())
    assert panel.request_model_entry() and received[0][1].endswith('trech_ml.js");')
    panel.shutdown()


def test_model_entry_snippet_scale_and_unloadable_checkpoints(tmp_path):
    registry = parse_registry({"schema": "trech_model_registry_v1", "models": {"m": {"checkpoints": [
        {"id": "m@v1", "name": "m", "version": 1, "role": "final", "structure_id": "s1", "structure_label": "linear",
         "files": [{"format": "torchscript", "path": "x.pt", "sha256": "0"}]},
        {"id": "m@v2", "name": "m", "version": 2, "role": "final", "structure_id": "s1", "structure_label": "linear",
         "scale": "meso", "files": [{"format": "generic_surrogate", "path": "m.json", "sha256": "1"}]}]}}}, tmp_path)
    with pytest.raises(ValueError, match="no generic_surrogate file"):
        model_entry_snippet(registry.checkpoint("m@v1"), tmp_path, tmp_path / "s.js")
    snippet = model_entry_snippet(registry.checkpoint("m@v2"), tmp_path / "store", tmp_path / "a" / "s.js")
    assert 'index: "../store/index.json"' in snippet and 'scale: "meso"' in snippet and "version: 2" in snippet
    assert ml_include_line(Path("/elsewhere/s.js"), REPO) == f'TRECH_INCLUDE("{(REPO / "js" / "trech_ml.js").resolve().as_posix()}");', \
        "a file sharing only the root gets an absolute include"


def test_editor_inserts_a_snippet_and_its_include_as_one_undoable_edit(tmp_path):
    source = tmp_path / "s.js"
    original = '// header\nTRECH_INCLUDE("a.js");\nTRECH_INCLUDE("b.js");\nconst cfg = {models: []};\n'
    source.write_text(original)
    editor = CodeEditor()
    assert not editor.insert_snippet("X")
    editor.load_file(source)
    cursor = editor.editor.textCursor()
    cursor.setPosition(original.index("[]") + 1)
    editor.editor.setTextCursor(cursor)
    assert editor.insert_snippet('TRECH_ML.modelEntry("m", {})', 'TRECH_INCLUDE("ml.js");')
    text = editor.text()
    assert text.splitlines()[3] == 'TRECH_INCLUDE("ml.js");', "after the last top-of-file include"
    assert 'models: [TRECH_ML.modelEntry("m", {})]' in text
    assert text[:editor.editor.textCursor().position()].endswith('modelEntry("m", {})'), "cursor ends after the snippet"
    assert editor.dirty_paths() == (source.resolve(),) and source.read_text() == original, "inserted, not saved"
    editor.insert_snippet("Y", 'TRECH_INCLUDE("ml.js");')
    assert editor.text().count("ml.js") == 1, "an include already present is not repeated"
    editor.editor.undo()
    editor.editor.undo()
    assert editor.text() == original


@needs_node
def test_delete_is_cancelled_without_confirmation(workspace, tmp_path):
    ml_root, store = workspace
    record = _cli(store, "register", str(_model_json(tmp_path / "m.json")), "--name", "keep")
    panel = ModelsPanel(REPO, store, confirm=lambda *_: False, ml_root=ml_root)
    panel.select(record["id"])
    assert not panel.delete_selected()
    assert panel.registry.checkpoint(record["id"]) is not None
    panel.shutdown()


def test_read_only_without_node(workspace, monkeypatch):
    ml_root, store = workspace
    monkeypatch.setattr(bridge, "node_executable", lambda: None)
    with pytest.raises(bridge.CliError, match="read-only"):
        bridge.run_cli(REPO, "list")
    panel = ModelsPanel(REPO, store, confirm=lambda *_: True, ml_root=ml_root)
    panel.load_definition(ml_root / "definitions" / "demo.model.js")
    assert "read-only" in panel.validation.text()
    panel.shutdown()
