"""Chemistry authoring round-trip and engine-output playback; offscreen Qt, no GPU."""
from __future__ import annotations
import json
import numpy as np
import os
from pathlib import Path
import sys
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from trech_studio.ui.chemistry import ChemistryPanel
from trech_studio.render.playback import build_material_frame_playback

_APP = QApplication.instance() or QApplication([])


def test_authoring_round_trip_and_remove_reindexes_bonds():
    panel = ChemistryPanel()
    s = {"atoms": [{"element": "H", "massNumber": 2, "position": [0, 0, 0]},
                   {"element": "O", "position": [1, 0, 0]},
                   {"element": "H", "position": [2, 0, 0]}],
         "bonds": [[0, 1, 1], [1, 2, 1]], "charge": -1}
    panel.set_structure(s)
    panel.set_active(True)
    args = panel.command_args()
    assert json.loads(json.loads(args[1].split("=", 1)[1])) == s
    panel.atoms.setCurrentCell(0, 0)
    panel.remove_atom()
    assert panel.structure()["bonds"] == [[0, 1, 1]]
    assert panel.structure()["atoms"][0]["element"] == "O"
    panel.set_active(False)
    assert panel.command_args() == []


def test_invalid_authoring_is_reported_without_inventing_structure():
    panel = ChemistryPanel()
    panel.set_active(True)
    panel.add_atom()
    panel.atoms.item(0, 1).setText("2.3")
    try:
        panel.command_args()
        raise AssertionError("fractional mass number accepted")
    except ValueError:
        pass
    panel.atoms.item(0, 1).setText("")
    panel.bonds.setPlainText("broken JSON")
    panel.atoms.setCurrentCell(0, 0)
    panel.remove_atom()
    assert panel.atoms.rowCount() == 1
    assert "Fix bond JSON" in panel.status.text()


def test_engine_results_are_separate_from_authored_edits():
    panel = ChemistryPanel()
    s = {"atoms": [{"element": "H", "position": [1, 2, 3]}], "bonds": [], "charge": 0}
    panel.set_structure(s)
    state = {"structure": s, "mode": "strict", "geometry_source": "authored", "capabilities": {
        "stability": {"available": False, "reason": "no trained model"}},
        "atoms": [{"z": 1, "isotopes": [{"a": 2, "neutrons": 1}]}]}
    run = SimpleNamespace(emits=[SimpleNamespace(tag="chemistry_state", payload=state)])
    panel.show_run(run)
    assert panel.structure() == s
    report = json.loads(panel.results.toPlainText())
    assert report["capabilities"]["stability"]["available"] is False
    assert report["atoms"][0]["isotopes"][0]["neutrons"] == 1
    assert "authored coordinates" in panel.status.text()
    panel.add_atom()
    panel.restore_run()
    assert panel.structure() == s


def test_chemistry_frame_keeps_native_coordinates_and_declared_bonds():
    payload = {"stream": "chemistry_structure", "length_unit": "angstrom", "up_axis": "y",
               "time_s": 0, "physical_time_s": 0, "positions": [[0, 0, 0], [1, 2, 3]],
               "colors_rgba": [[1, 1, 1, 1], [1, 0, 0, 1]], "radii": [0.16, 0.25],
               "bonds": [[0, 1]], "motion_scope": "authored structure"}
    pb = build_material_frame_playback([SimpleNamespace(tag="material_frame", payload=payload)])
    assert len(pb.frames) == 1 and pb.t_min == pb.t_max == 0
    assert pb.length_unit == "angstrom"
    assert pb.frames[0].positions.tolist() == payload["positions"]
    assert pb.frames[0].bonds.tolist() == payload["bonds"]


def test_window_inspection_run_arguments_and_scaffold_loading():
    # Real engine inspection, stub viewport/launch: verifies the production glue
    # without a GPU or modifying the scenario source.
    from PySide6.QtWidgets import QWidget
    from trech_studio.ui import main_window as module
    from trech_studio.settings import StudioSettings
    root = Path(__file__).resolve().parents[2]
    binary = root / "build/rel/trech"
    if not binary.is_file():
        print("SKIP window integration: built engine unavailable")
        return
    class Viewport(QWidget):
        def set_scene(self, *_): pass
        def set_playback(self, *_): pass
        def set_render_budget(self, *_): pass
        def set_playback_time(self, *_): pass
    original = module.create_viewport
    module.create_viewport = lambda **kwargs: Viewport()
    window = None
    try:
        window = module.StudioWindow(StudioSettings(repo_root=root, engine_bin=binary))
        window._open_chemistry()
        assert window.chemistry.run_button.isEnabled()
        assert window.chemistry.atoms.rowCount() == 9
        window.chemistry.atoms.item(0, 1).setText("13")
        window.scenario_options._widgets["mode"].setCurrentIndex(1)
        launches = []
        window._runner.run = lambda *a, **kw: launches.append((a, kw))
        window.code_editor.save = lambda: window.code_editor.current_path()
        window._run_scenario()
        assert len(launches) == 1
        args = launches[0][1]["extra_args"]
        assert sum(a.startswith("structure_json=") for a in args) == 1
        encoded = next(a.split("=", 1)[1] for a in args if a.startswith("structure_json="))
        assert json.loads(json.loads(encoded))["atoms"][0]["massNumber"] == 13
        assert 'mode="strict"' in args
        window.chemistry.atoms.item(0, 1).setText("13.5")
        window._run_scenario()
        assert len(launches) == 1
        assert "rejected the draft" in window.chemistry.status.text()
        assert window.scenario_options.values()["mode"] == "strict"
        window.chemistry.atoms.item(0, 1).setText("13")
        preset = window.scenario_options._widgets["preset"]
        preset.setCurrentIndex(preset.findData("formamide"))
        window._load_chemistry_scaffold()
        assert window.chemistry.atoms.rowCount() == 6
        assert all("massNumber" not in a for a in window.chemistry.structure()["atoms"])
        window.open_scenario(root / "examples/experiments/chemistry_probability_reference.js")
        assert window.chemistry.scene_enabled.isChecked()
        window._run_chemistry()
        assert len(launches) == 2
        args = launches[-1][1]["extra_args"]
        assert max(map(len, args)) < 32768
        assert 'scene_json=""' in args
        assert sum(a.startswith('scene_file=') for a in args) == 1
        assert window.code_editor.current_path().name == 'chemistry_probability_reference.js'
    finally:
        if window:
            window.close()
        module.create_viewport = original


def test_multi_molecule_json_overrides_unused_single_draft():
    panel = ChemistryPanel()
    panel.set_active(True)
    panel.add_atom()
    panel.append_molecule()
    panel.append_molecule()
    scene = panel.scene_document()
    assert [m['id'] for m in scene['molecules']] == ['molecule_0', 'molecule_1']
    panel.atoms.item(0, 1).setText('invalid unused single draft')
    args = panel.command_args()
    assert not any(arg.startswith('structure_json=') for arg in args)
    encoded = next(arg.split('=', 1)[1] for arg in args if arg.startswith('scene_json='))
    assert json.loads(json.loads(encoded)) == scene


def test_probability_timeline_discloses_nonphysical_clock():
    from trech_studio.ui.timeline import Timeline
    from trech_studio.render.playback import Playback, ParticleFrame
    panel = Timeline()
    frame = ParticleFrame(time=1., positions=np.zeros((1, 3)), phase='independent nuclear state')
    panel.set_playback(Playback(kind='particles', unit='ensemble sample', t_min=0, t_max=1,
                              frames=[frame], frame_times=np.asarray([1.])))
    assert 'no physical clock' in panel._time_label.text()
    assert 't =' not in panel._time_label.text()


if __name__ == "__main__":
    tests = [v for k, v in globals().copy().items() if k.startswith("test_")]
    for test in tests:
        test()
        print("PASS", test.__name__)
    print(f"{len(tests)}/{len(tests)} passed")
