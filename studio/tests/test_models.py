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
    discover_definition_files, human_bytes, new_definition_source, parse_inspection, parse_prune, parse_registry, relative_time,
)
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
             "use_count": 0, "files": [], "metrics": {"y": {"r2": 0.8}, "z": {"r2": 0.6}}, "holdout_source": "selection_runs"}]},
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
