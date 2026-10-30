"""Behavioural checks for engine-owned JS descriptions and multi-source editing."""
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication, QWidget
from trech_studio.engine.parameters import inspection_from_json
from trech_studio.render.playback import build_material_frame_playback
from trech_studio.ui.code_editor import CodeEditor

_APP = QApplication.instance() or QApplication([])


def test_editor_preserves_module_drafts_and_root_run_target():
    with tempfile.TemporaryDirectory() as tmp:
        root, module = Path(tmp).resolve() / "scenario.js", Path(tmp).resolve() / "model.js"
        root.write_text("// root")
        module.write_text("// module")
        editor = CodeEditor()
        editor.load_file(root)
        editor.set_sources((root, module))
        assert editor.dirty_paths() == ()
        editor.editor.setPlainText("// root edited")
        assert editor.dirty_paths() == (root,)
        assert editor.sources.itemText(0).endswith(" *")
        editor.sources.setCurrentIndex(1)
        editor.editor.setPlainText("// module edited")
        assert editor.dirty_paths() == (root, module)
        editor.sources.setCurrentIndex(0)
        assert editor.text() == "// root edited"
        editor.sources.setCurrentIndex(1)
        assert editor.text() == "// module edited"
        assert editor.current_path() == module and editor.scenario_path() == root
        assert editor.save() == root
        assert root.read_text() == "// root edited" and module.read_text() == "// module edited"
        assert editor.dirty_paths() == () and not editor.sources.currentText().endswith(" *")
        module.write_text("// changed externally")
        editor.editor.setPlainText("// another edit")
        try:
            editor.save()
        except OSError:
            pass
        else:
            raise AssertionError("External module edit was overwritten")
        assert module.read_text() == "// changed externally"


def test_unsaved_sources_guard_switch_close_and_failed_save():
    from PySide6.QtGui import QCloseEvent
    from PySide6.QtWidgets import QMessageBox
    from trech_studio.ui import main_window as module
    from trech_studio.settings import StudioSettings

    class Viewport(QWidget):
        def set_scene(self, value): pass
        def set_playback(self, value): pass
        def set_playback_time(self, value): pass
        def set_render_budget(self, value): pass

    repo = Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory() as tmp, patch.object(module, "create_viewport", lambda **kwargs: Viewport()):
        root, include, next_scenario = [Path(tmp).resolve() / name for name in ("root.js", "include.js", "next.js")]
        original = "TRECH_INCLUDE('include.js'); globalThis.TRECH_CONFIG={};"
        root.write_text(original)
        include.write_text("// include")
        next_scenario.write_text("globalThis.TRECH_CONFIG={};")
        window = module.StudioWindow(StudioSettings(repo_root=repo, engine_bin=repo / "build/rel/trech"))
        assert window.open_scenario(root)
        editor = window.code_editor
        editor.editor.setPlainText(original + "\n// root draft")
        editor.sources.setCurrentIndex(1)
        editor.editor.setPlainText("// include draft")
        changes = editor.dirty_paths()
        clear_calls, stopped, warnings = [], [], []
        window._clear_playback = lambda: clear_calls.append(True)
        window._runner.stop = lambda: stopped.append("runner")
        window._preview_export.stop = lambda: stopped.append("preview")
        window._quantum_job.stop = lambda: stopped.append("quantum")

        def cancel(prompt):
            assert all(str(path) in prompt.detailedText() for path in changes)
            assert prompt.defaultButton() == prompt.button(QMessageBox.Cancel)
            return QMessageBox.Cancel

        with patch.object(QMessageBox, "exec", cancel):
            window._open_scenario_from_browser(str(next_scenario))
            assert editor.scenario_path() == root and editor.current_path() == include
            assert editor.text() == "// include draft" and editor.dirty_paths() == changes
            assert not clear_calls and root.read_text() == original
            assert not window._open_chemistry() and not clear_calls
            event = QCloseEvent()
            window.closeEvent(event)
            assert not event.isAccepted() and not stopped

        # All changed sources are checked before any write. A conflicting
        # include must keep both drafts and the original workspace intact.
        include.write_text("// external update")
        with patch.object(QMessageBox, "exec", lambda self: QMessageBox.Save), patch.object(
                QMessageBox, "warning", lambda *args: warnings.append(args)):
            assert not window.open_scenario(next_scenario)
            assert warnings and editor.scenario_path() == root and editor.dirty_paths() == changes
            assert root.read_text() == original and include.read_text() == "// external update"
            event = QCloseEvent()
            window.closeEvent(event)
            assert not event.isAccepted() and not stopped
            include.write_text("// include")
            assert window.open_scenario(next_scenario)
            assert root.read_text().endswith("// root draft") and include.read_text() == "// include draft"
            assert editor.scenario_path() == next_scenario and editor.dirty_paths() == ()

        editor.editor.setPlainText("// discarded draft")
        with patch.object(QMessageBox, "exec", lambda self: QMessageBox.Discard):
            assert not window.open_scenario(Path(tmp) / "missing.js")
            assert editor.scenario_path() == next_scenario and editor.text() == "// discarded draft"
            assert window.open_scenario(root)
            assert next_scenario.read_text() == "globalThis.TRECH_CONFIG={};"
            assert editor.dirty_paths() == ()
            editor.editor.setPlainText(editor.text() + "\n// close draft")
            event = QCloseEvent()
            window.closeEvent(event)
            assert event.isAccepted() and set(stopped) == {"runner", "preview", "quantum"}
            assert not root.read_text().endswith("// close draft")
        # Dispose the test window without asking about the deliberately
        # discarded in-memory draft a second time.
        editor.load_file(root)
        window.close()


def test_descriptor_validation_and_legacy_inspection():
    assert inspection_from_json('{"config":{}}').studio == {}
    descriptor = {"schema": "trech_studio_v1", "title": "A", "panels": {"processes": True},
                  "processes": [{"id": "training", "kind": "offline", "description": "Not executed by the UI"}]}
    base = {"config": {}, "authoring": {"sources": ["/tmp/model.js"], "studio": descriptor}}
    assert inspection_from_json(json.dumps(base)).sources == (Path("/tmp/model.js"),)
    for bad in (None, [], {"schema": "unknown"}, {**descriptor, "panels": {"options": "yes"}},
                {**descriptor, "processes": ["execute this"]}):
        base["authoring"]["studio"] = bad
        try:
            inspection_from_json(json.dumps(base))
        except ValueError:
            continue
        raise AssertionError("Malformed UI descriptor accepted")


def test_stream_selection_and_nonphysical_clock():
    emits = [SimpleNamespace(tag="material_frame", payload={"positions_mm": [[1, 2, 3]],
        "colors_rgba": [[1, 0, 0, 1]], "stream": stream, "time": step, "time_unit": "step",
        "show_geant4_scene": False}) for stream, step in (("first", 0), ("second", 7), ("second", 9))]
    assert len(build_material_frame_playback(emits).frames) == 1
    selected = build_material_frame_playback(emits, stream_name="second")
    assert [f.time for f in selected.frames] == [7, 9]
    assert selected.unit == "step" and selected.physical_t_max is None and not selected.show_geant4_scene
    assert build_material_frame_playback(emits, stream_name="missing").is_empty


def test_save_applies_js_ui_and_run_uses_scenario_from_module():
    from trech_studio.ui import main_window as module
    from trech_studio.settings import StudioSettings

    class Viewport(QWidget):
        def set_scene(self, value): pass
        def set_playback(self, value): pass
        def set_playback_time(self, value): pass
        def set_render_budget(self, value): pass

    repo = Path(__file__).resolve().parents[2]
    original = module.create_viewport
    module.create_viewport = lambda **kwargs: Viewport()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            scenario, process = Path(tmp).resolve() / "scenario.js", Path(tmp).resolve() / "process.js"
            process.write_text("globalThis.UI_TITLE = 'Initial';")
            scenario.write_text("TRECH_INCLUDE('process.js'); globalThis.TRECH_CONFIG={}; "
                "TRECH_VALUE.integer('retired_control',{default:1,min:1,max:9});"
                "globalThis.TRECH_STUDIO={schema:'trech_studio_v1',title:UI_TITLE,"
                "processes:[{id:'train',kind:'offline',description:'A declared offline trainer'}]};")
            window = module.StudioWindow(StudioSettings(repo_root=repo, engine_bin=repo / "build/rel/trech"))
            window.open_scenario(scenario)
            assert window.windowTitle() == "Initial"
            editor = window.code_editor
            assert editor.sources.count() == 2
            editor.sources.setCurrentIndex(1)
            editor.editor.setPlainText("globalThis.UI_TITLE = 'Changed without restart';")
            window._save_scenario()
            assert window.windowTitle() == "Changed without restart"
            assert window.processes.tree.topLevelItemCount() == 1
            window.scenario_options._widgets["retired_control"].setValue(7)
            # A source edit removes an overridden control: refreshing must not
            # replay its obsolete --param and strand the workspace in an error.
            editor.sources.setCurrentIndex(0)
            editor.editor.setPlainText(editor.text().replace(
                "TRECH_VALUE.integer('retired_control',{default:1,min:1,max:9});", ""))
            window._save_scenario()
            assert "retired_control" not in window.scenario_options._widgets
            editor.sources.setCurrentIndex(1)
            targets = []
            window._runner.run = lambda experiment, *args, **kwargs: targets.append(experiment)
            window._run_scenario()
            assert targets == [scenario]
            assert editor.current_path() == process
            window.close()
    finally:
        module.create_viewport = original


if __name__ == "__main__":
    for name, test in sorted(list(globals().items())):
        if name.startswith("test_"):
            test()
            print("PASS", name)
