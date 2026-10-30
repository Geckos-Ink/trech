"""Behavioural checks for engine-owned JS descriptions and multi-source editing."""
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

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
        editor.editor.setPlainText("// root edited")
        editor.sources.setCurrentIndex(1)
        editor.editor.setPlainText("// module edited")
        editor.sources.setCurrentIndex(0)
        assert editor.text() == "// root edited"
        editor.sources.setCurrentIndex(1)
        assert editor.text() == "// module edited"
        assert editor.current_path() == module and editor.scenario_path() == root
        assert editor.save() == root
        assert root.read_text() == "// root edited" and module.read_text() == "// module edited"
        module.write_text("// changed externally")
        editor.editor.setPlainText("// another edit")
        try:
            editor.save()
        except OSError:
            pass
        else:
            raise AssertionError("External module edit was overwritten")
        assert module.read_text() == "// changed externally"


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
