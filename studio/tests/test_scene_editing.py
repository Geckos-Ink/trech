"""Inspector drafts are validated, exportable, and never inherit recorded playback."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication, QPushButton, QWidget
from trech_studio.engine.outputs import RunResult
from trech_studio.scene.writer import scene_to_config
from trech_studio.settings import StudioSettings
from trech_studio.ui import main_window as module
from test_scene_writer import recorded_scene

_APP = QApplication.instance() or QApplication([])


class DraftViewport(QWidget):
    def __init__(self):
        super().__init__()
        self.scene = None
        self.playback = None

    def set_scene(self, value): self.scene = value
    def set_playback(self, value): self.playback = value
    def set_playback_time(self, value): pass
    def set_render_budget(self, value): pass


@pytest.fixture
def window(tmp_path):
    scene, config = recorded_scene()
    scene.source_path = str(tmp_path / "trech_viz_scene.json")
    repo = Path(__file__).resolve().parents[2]
    with patch.object(module, "create_viewport", lambda **kwargs: DraftViewport()):
        window = module.StudioWindow(StudioSettings(repo_root=repo, engine_bin=repo / "build/rel/trech"))
    window._loaded_run = RunResult(tmp_path, provenance=[{"config_json": json.dumps(config)}],
                                   viz_scene_path=Path(scene.source_path))
    window._apply_scene(scene)
    window._configure_scene_editing()
    source = tmp_path / "source.js"
    source.write_text("// original source")
    window.code_editor.load_file(source)
    window.code_editor.editor.setPlainText("// independent source draft")
    window.test_original_config = deepcopy(config)
    yield window
    # Tests leave their intentionally unsaved drafts intact, so avoid the close guard at teardown.
    window.deleteLater()
    _APP.processEvents()


def apply(panel):
    panel.findChild(QPushButton, "apply_scene_draft").click()


def test_inspector_edits_world_volume_shape_pose_and_beam_without_mutating_recorded_config(window):
    panel = window.inspector
    panel.show_node("world", "")
    panel._fields["world_size"].setText("150")
    apply(panel)
    assert window._scene.world_size_mm == 150

    panel.show_node("volume", "sample")
    panel._fields["shape"].setCurrentText("tube")
    assert not panel._fields["size"].isEnabled() and panel._fields["length"].isEnabled()
    panel._fields["outer_radius"].setText("12")
    panel._fields["inner_radius"].setText("8")
    panel._fields["length"].setText("30")
    panel._fields["position"].setText("2, 3, 4")
    panel._fields["rotation"].setText("10, 20, 30")
    panel._fields["material"].setCurrentText("G4_AIR")
    apply(panel)
    vol = window._scene.volumes[0]
    assert vol.shape.type == "tube" and vol.shape.size_mm == (0., 0., 0.)
    assert vol.position_mm == (2., 3., 4.) and vol.rotation_deg == (10., 20., 30.)
    assert vol.material == "G4_AIR"
    assert window.outliner.selectedItems()[0].text(1) == "tube"
    assert window.viewport.scene is window._scene

    panel.show_node("beam", "gamma")
    panel._fields["particle"].setText("proton")
    panel._fields["energy"].setText("2e7")
    apply(panel)
    assert window._scene.beams[0].particle == "proton"
    assert window._scene.beams[0].energy_ev == 2e7
    assert window.outliner.selectedItems()[0].text(0) == "proton"
    original = window._loaded_run.recorded_config()
    assert original == window.test_original_config
    edited = scene_to_config(window._scene, original)
    assert edited["beam"]["originMm"] == original["beam"]["originMm"]
    assert edited["beam"]["energyMeV"] == 20.
    assert edited["materials"] == original["materials"]
    assert window._scene.raw["world"]["size_mm"] == 100.
    assert window.code_editor.text() == "// independent source draft"
    assert window.code_editor.current_path().read_text() == "// original source"


@pytest.mark.parametrize("key,value", [("outer_radius", "-1"), ("inner_radius", "12"),
                                       ("position", "1,2"), ("rotation", "0,nan,0")])
def test_invalid_edits_are_atomic_and_keep_the_current_scene(window, key, value):
    panel = window.inspector
    panel.show_node("volume", "sample")
    panel._fields["shape"].setCurrentText("tube")
    panel._fields["outer_radius"].setText("12")
    panel._fields["inner_radius"].setText("8")
    panel._fields["length"].setText("30")
    panel._fields[key].setText(value)
    original = deepcopy(window._scene)
    apply(panel)
    assert window._scene == original and not window._scene_dirty
    assert panel._edit_status.text()


def test_apply_hides_recorded_playback_and_does_not_touch_sources_or_active_jobs(window):
    stopped = []
    window._runner.stop = lambda: stopped.append("runner")
    window._preview_export.stop = lambda: stopped.append("preview")
    window._quantum_job.stop = lambda: stopped.append("reference")
    window.viewport.playback = object()
    window.inspector.show_node("world", "")
    window.inspector._fields["world_size"].setText("200")
    apply(window.inspector)
    assert window.viewport.playback is None and window.timeline._playback is None
    assert window._scene_is_draft and window._scene_dirty and window._loaded_run is not None
    assert not stopped and window.code_editor.text() == "// independent source draft"
    with patch.object(module.QFileDialog, "getExistingDirectory") as dialog:
        window._export_preview(False)
        dialog.assert_not_called()
    # Changing the stream selector cannot put old trajectories back over the new geometry.
    window._select_recorded_stream(0)
    assert window.viewport.playback is None


def test_scene_guard_cancel_and_failed_export_preserve_scene_and_jobs(window, tmp_path):
    from PySide6.QtGui import QCloseEvent
    from PySide6.QtWidgets import QMessageBox
    window.inspector.show_node("world", "")
    window.inspector._fields["world_size"].setText("200")
    apply(window.inspector)
    scene = window._scene
    with patch.object(QMessageBox, "exec", return_value=QMessageBox.Cancel):
        window.open_output_dir(tmp_path / "other")
        assert not window.open_scenario(tmp_path / "other.js")
        event = QCloseEvent()
        window.closeEvent(event)
        assert not event.isAccepted()
    with patch.object(QMessageBox, "exec", return_value=QMessageBox.Save), \
            patch.object(module.QFileDialog, "getSaveFileName", return_value=("", "")):
        assert not window._resolve_scene_draft()
    assert window._scene is scene and window._scene_dirty
    target = tmp_path / "scene.js"
    with patch.object(module.QFileDialog, "getSaveFileName", return_value=(str(target), "")):
        assert window._export_scene_scenario()
    assert not window._scene_dirty and window._scene_is_draft and target.is_file()
    assert window.code_editor.text() == "// independent source draft"


def test_callback_runs_keep_the_inspector_read_only(window):
    config = window._loaded_run.recorded_config()
    config["hooks"] = {"registered": ["onRun"]}
    window._loaded_run.provenance = [{"config_json": json.dumps(config)}]
    window._configure_scene_editing()
    window.inspector.show_node("world", "")
    assert not window.inspector._fields
    assert "callbacks" in window.inspector._editing_reason


def test_noop_apply_and_explicit_discard_do_not_leave_an_unsaved_scene(window):
    from PySide6.QtWidgets import QMessageBox
    window.inspector.show_node("world", "")
    apply(window.inspector)
    assert not window._scene_dirty and "No scene fields changed" in window.inspector._edit_status.text()
    window.inspector._fields["world_size"].setText("200")
    apply(window.inspector)
    with patch.object(QMessageBox, "exec", return_value=QMessageBox.Discard):
        assert window._resolve_scene_draft()
    assert window._scene.world_size_mm == 100. and not window._scene_dirty and not window._scene_is_draft
    assert window.viewport.scene is window._scene and window._resolve_scene_draft()
    assert window.code_editor.text() == "// independent source draft"


@pytest.mark.parametrize("draft", [False, True])
def test_sceneless_output_cannot_mix_new_results_with_previous_scene(window, tmp_path, draft):
    if draft:
        window.inspector.show_node("world", "")
        window.inspector._fields["world_size"].setText("200")
        apply(window.inspector)
        with patch.object(module.QFileDialog, "getSaveFileName", return_value=(str(tmp_path / "scene.js"), "")):
            assert window._export_scene_scenario()
        assert not window._scene_dirty and window._scene_is_draft
    scene, result = window._scene, window._loaded_run
    old_playback = window.viewport.playback
    missing = tmp_path / "no_scene"
    missing.mkdir()
    (missing / "trech_scores.jsonl").write_text('{"n_events": 999}\n')
    window.open_output_dir(missing)
    assert window._scene is scene and window._loaded_run is result
    assert window.viewport.playback is old_playback and window._scene_is_draft == draft
