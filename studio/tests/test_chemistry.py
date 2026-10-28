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



def test_orbital_details_selection_inventory_and_clock_updates():
    from trech_studio.render.probability import build_probability_playback
    from trech_studio.engine.quantum import geometry_request
    from trech_studio.ui.probability_details import ProbabilityDetails
    root = Path(__file__).resolve().parents[2]
    scene = json.loads((root/'data/chemistry_probability/water_deuterium.json').read_text())
    emits = [SimpleNamespace(tag='quantum_frame', payload=dict(f, cursor=float(i), time_kind='parameter_scan',
        structure={'atoms': [], 'bonds': []}, particle_inventory={'protons': 12, 'neutrons': 10, 'electrons': 12}))
        for i, f in enumerate(scene['frames'])]
    playback = build_probability_playback(emits, 'density:mo_6')
    details = ProbabilityDetails()
    details.set_playback(playback)
    assert '12 electrons' in details.summary.text() and 'Selected MO 6' in details.summary.text()
    assert details.table.rowCount() == len(scene['frames'][0]['electronic_structure']['orbitals'])
    assert 'HOMO' in details.table.item(5, 0).text()
    selected = []
    details.view_requested.connect(selected.append)
    details._select_state(5, 0)
    assert selected == ['density:mo_6']
    last = details.table.item(5, 1).text()
    details.set_cursor(0)
    assert details.table.item(5, 1).text() != last
    request = geometry_request(scene)
    assert 'fields' not in request['frames'][0] and 'electronic_structure' not in request['frames'][0]
    assert len(scene['frames'][0]['fields']) == 10
    panel = ChemistryPanel()
    state = {'structure': {'atoms': [], 'bonds': []}, 'scene_restore_source': 'provenance.config_json.hooks.inputs.scene'}
    run = SimpleNamespace(emits=[SimpleNamespace(tag='chemistry_state', payload=state)],
        provenance=[{'config_json': json.dumps({'hooks': {'inputs': {'scene': scene}}})}])
    panel.show_run(run)
    assert panel._last_state['scene'] == scene
    details.set_playback(None)
    assert details.table.rowCount() == 0 and 'No chemistry probability' in details.summary.text()


def test_quantum_action_uses_engine_bridge_and_preserves_changed_drafts():
    from PySide6.QtWidgets import QWidget
    from trech_studio.ui import main_window as module
    from trech_studio.settings import StudioSettings
    root = Path(__file__).resolve().parents[2]
    binary = root/'build/rel/trech'
    if not binary.is_file(): return
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
        requests = []
        window._quantum_job.start = lambda *a: requests.append(a)
        window._calculate_quantum_reference()
        assert len(requests) == 1 and len(requests[0][0]['molecules']) == 1
        assert not window.chemistry.quantum_button.isEnabled()
        window.chemistry.add_atom()
        window._quantum_reference_ready(root/'data/chemistry_probability/water_deuterium.json')
        assert 'draft changed' in window.chemistry.status.text()
        assert window.chemistry.atoms.rowCount() == 10
    finally:
        if window: window.close()
        module.create_viewport = original


def test_optional_quantum_job_preserves_virtualenv_and_completes():
    from PySide6.QtCore import QEventLoop, QTimer
    from trech_studio.engine.quantum import QuantumReferenceJob, quantum_python
    from trech_studio.engine.chemistry import read_scene
    from trech_studio.engine.parameters import inspect_scenario
    from trech_studio.engine.locator import EngineLocation
    import tempfile
    root = Path(__file__).resolve().parents[2]
    interpreter = root/'build/render-venv/bin/python'
    if not interpreter.is_file() or not (root/'build/rel/trech').is_file():
        print('SKIP optional PySCF job: runtime unavailable')
        return
    if not os.environ.get('TRECH_QUANTUM_PYTHON'):
        assert Path(quantum_python(root)) == interpreter
    # The ordinary default scaffold must work through the actual QProcess path.
    inspection = inspect_scenario(EngineLocation(root/'build/rel/trech', 'test'), root/'examples/experiments/chemistry_mode.js')
    structure = inspection.config['hooks']['inputs']['structure']
    scene = {'schema': 'trech_chemistry_scene_v1', 'molecules': [{'id': 'edited', 'structure': structure}]}
    with tempfile.TemporaryDirectory() as directory:
        loop = QEventLoop()
        job = QuantumReferenceJob(root)
        completed, errors = [], []
        job.finished.connect(lambda path: (completed.append(path), loop.quit()))
        job.failed.connect(lambda message: (errors.append(message), loop.quit()))
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        timer.start(60000)
        job.start(scene, directory)
        loop.exec()
        timer.stop()
        job.stop()
        assert completed and not errors, errors
        result = read_scene(completed[0])
        assert result['frames'][0]['electronic_structure']['electron_count'] == 26
        assert len(result['frames'][0]['fields']) == 8
        checked = inspect_scenario(EngineLocation(root/'build/rel/trech', 'test'), root/'examples/experiments/chemistry_mode.js',
                                  ['--param', 'scene_file='+json.dumps(str(completed[0]))])
        assert checked.config['hooks']['inputs']['scene']['frames'][0]['electronic_structure']['electron_count'] == 26


def test_field_explorer_changes_slice_and_probability_without_resetting_cursor():
    from trech_studio.ui.density_explorer import DensityExplorer
    from trech_studio.render.playback import ParticleFrame, Playback
    from trech_studio.render.probability import ScalarDensity
    d=ScalarDensity(np.arange(27,dtype=np.float32).reshape(3,3,3),np.array([-1,-1,-1]),1,.5,'electrons/angstrom^3','test')
    d.statistics={'mass_levels':[{'threshold':2,'enclosed_fraction':.9}]*99}
    frames=[ParticleFrame(time=0,positions=np.zeros((1,3)),density=d),ParticleFrame(time=1,positions=np.zeros((1,3)),density=d)]
    pb=Playback(kind='particles',unit='parameter',frames=frames,frame_times=np.array([0,1]),t_min=0,t_max=1)
    panel=DensityExplorer()
    panel.set_playback(pb)
    panel.set_cursor(0)
    updates=[]
    panel.display_changed.connect(updates.append)
    panel.mass.setValue(50)
    panel.axis.setCurrentIndex(1)
    panel.section.setValue(900)
    assert updates[-1].mass_percent==50 and updates[-1].axis==1 and updates[-1].slice_fraction==.9
    assert panel._playback is pb and panel._density is d
    assert 'Threshold 2' in panel.mass_note.text()
    panel.set_playback(None)
    assert panel.slice.density is None and not panel.mass.isEnabled()


def test_occupied_energy_profiles_have_distinct_core_and_valence_not_linear_fade():
    from trech_studio.ui.electron_levels import ElectronLevels
    from trech_studio.render.probability import build_probability_playback
    root=Path(__file__).resolve().parents[2]
    frame=json.loads((root/'data/chemistry_probability/neon_atom.json').read_text())['frames'][0]
    atoms=frame['molecules'][0]['structure']['atoms']
    raw=dict(frame,time_kind='snapshot',cursor=0,structure={'atoms':atoms,'bonds':[],'molecule_ids':['neon']})
    pb=build_probability_playback([SimpleNamespace(tag='quantum_frame',payload=raw)],'density:energy_density')
    panel=ElectronLevels();panel.set_playback(pb)
    assert '10 electrons in 3' in panel.title.text()
    assert panel.plot.logarithmic and not panel.plot.radial
    profile=panel.plot.profile
    radius=np.asarray(profile['radii_angstrom'])
    peaks=[radius[np.argmax(g['radial_probability_per_angstrom'])] for g in profile['levels']]
    assert peaks[0]<min(peaks[1:])/3
    assert [g['occupation'] for g in profile['levels']]==[2,2,6]
    panel.kind.setCurrentIndex(1)
    assert panel.plot.radial and not panel.plot.logarithmic
    panel.span.setValue(6)
    assert panel.plot.span==.6
    # Exercise the actual painter and recorded curves, not a placeholder image.
    panel.resize(600,700);panel.show();_APP.processEvents()
    assert not panel.grab().isNull()
    panel.close()


if __name__ == "__main__":
    tests = [v for k, v in globals().copy().items() if k.startswith("test_")]
    for test in tests:
        test()
        print("PASS", test.__name__)
    print(f"{len(tests)}/{len(tests)} passed")
