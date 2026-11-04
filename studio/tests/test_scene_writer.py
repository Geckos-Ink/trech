"""Transport-scene export preserves canonical physics, and refuses lossy process export."""

from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trech_studio.engine.outputs import RunResult
from trech_studio.scene.loader import scene_from_viz_data
from trech_studio.scene.model import Beam, MaterialDef, RunParams, SceneModel, Shape, VolumeNode
from trech_studio.scene.writer import scene_to_config, scene_to_js


def recorded_scene():
    beam = {"particle": "gamma", "energyMeV": 0.019999999999999997,
            "direction": [0., 0., 1.], "originMm": [1., 2., -30.],
            "spotRadiusMm": 2., "divergenceDeg": 3., "energySpreadFractional": .05,
            "spectrum": [{"energyMeV": .018, "weight": 1.}, {"energyMeV": .022, "weight": 2.}],
            "polarization": "linear", "polarizationAngleDeg": 37.}
    material = {"name": "heavy_water", "densityGcm3": 1.1,
                "components": [{"element": "H", "massNumber": 2, "atoms": 2}, {"element": "O", "atoms": 1}]}
    volume = {"name": "sample", "material": "heavy_water", "scoreEdep": True,
              "shape": {"type": "box", "sizeMm": [10., 20., 30.]},
              "placement": {"positionMm": [0., 0., 0.], "rotationDeg": [0., 10., 0.]},
              "tags": ["viz_opacity=0.2"]}
    config = {"detector": {"worldSizeMm": 100., "worldMaterial": "G4_AIR", "mediumBoxMm": 0.,
                            "mediumMaterial": "G4_WATER", "temperatureK": 315., "pressureAtm": 2.},
              "beam": beam, "materials": [material], "geometry": {"volumes": [volume]},
              "run": {"nEvents": 4, "seed": 123, "threads": 1},
              "determinism": {"mode": "strict"}, "physics": {"optical": False},
              "viz": {"enable": True}, "scoring": {"eventEnergyMoments": True}}
    raw = {"world": {"size_mm": 100., "material": "G4_AIR"}, "seed": 123,
           "n_events": 4, "determinism_mode": "strict",
           "volumes": [{"name": "sample", "material": "heavy_water", "score_edep": True,
                        "shape": {"type": "box", "size_mm": [10., 20., 30.]},
                        "position_mm": [0., 0., 0.], "rotation_deg": [0., 10., 0.],
                        "tags": ["viz_opacity=0.2"]}],
           # Current viz output loses element/atoms/isotope details. The writer
           # must keep them from config instead of reverse-engineering this list.
           "materials": [{"name": "heavy_water", "density_gcm3": 1.1,
                          "components": [{"material": "", "fraction": 0.}, {"material": "", "fraction": 0.}]}],
           "derived_optics": [{"material_name": "G4_AIR", "available": True,
                               "mean_refractive_index": 1.0003}],
           "beams": [{"particle": "gamma", "energy_ev": beam["energyMeV"] * 1e6,
                      "direction": [0., 0., 1.], "active": False}]}
    return scene_from_viz_data(raw), config


def test_unchanged_loaded_scene_keeps_exact_config_and_ignores_derived_appearance():
    scene, config = recorded_scene()
    original = deepcopy(config)
    exported = scene_to_config(scene, config)
    assert exported == original
    exported["beam"]["originMm"][0] = 99
    assert config == original
    assert scene_to_js(scene, config) == scene_to_js(scene, config)
    assert "derived_optics" not in scene_to_js(scene, config)
    assert all(m["name"] != "G4_AIR" for m in scene_to_config(scene, config)["materials"])


def test_scene_edits_preserve_unrepresented_conditions_sources_and_isotopes():
    scene, config = recorded_scene()
    scene.world_size_mm = 150.
    scene.volumes[0].position_mm = (2., 3., 4.)
    scene.volumes[0].shape = Shape(type="tube", outer_radius_mm=12., inner_radius_mm=8., length_mm=30.)
    scene.materials[0].density_gcm3 = 1.2
    scene.beams[0].energy_ev = 40000.
    scene.run.seed = 456
    result = scene_to_config(scene, config)
    assert result["detector"]["worldSizeMm"] == 150.
    assert result["detector"]["temperatureK"] == 315.
    assert result["beam"]["energyMeV"] == .04
    assert result["beam"]["originMm"] == [1., 2., -30.]
    assert result["beam"]["spotRadiusMm"] == 2.
    assert result["materials"][0]["densityGcm3"] == 1.2
    assert result["materials"][0]["components"] == config["materials"][0]["components"]
    assert result["geometry"]["volumes"][0]["placement"]["positionMm"] == [2., 3., 4.]
    assert result["geometry"]["volumes"][0]["shape"]["innerRadiusMm"] == 8.
    assert result["run"] == {"nEvents": 4, "seed": 456, "threads": 1}
    assert config["run"]["seed"] == 123


def test_unrepresented_materials_and_independent_primary_source_survive():
    scene, config = recorded_scene()
    config["materials"].append({"name": "unused", "smiles": "O", "densityGcm3": 1.})
    display_beam = deepcopy(config["beam"])
    config["beams"] = [display_beam]
    config["beam"] = {**config["beam"], "originMm": [9., 8., 7.]}
    scene.beams[0].energy_ev = 50000.
    result = scene_to_config(scene, config)
    assert result["materials"] == config["materials"]
    assert result["beam"] == config["beam"]
    assert result["beams"][0]["energyMeV"] == .05


def test_named_source_edits_follow_identity_after_reordering_and_leave_independent_primary():
    scene, config = recorded_scene()
    a = {**config["beam"], "name": "A", "originMm": [10., 0., 0.]}
    b = {**config["beam"], "name": "B", "originMm": [20., 0., 0.]}
    config["beams"] = [a, b]
    raw = deepcopy(scene.raw)
    raw["beams"] = [{**raw["beams"][0], "name": name} for name in ("A", "B")]
    scene = scene_from_viz_data(raw)
    scene.beams.reverse()
    scene.beams[0].origin_mm = (21., 2., 3.)
    scene.beams[0].divergence_deg = 0.
    scene.beams[0].energy_spread_fractional = .2
    expected = deepcopy(config)
    expected["beams"] = [{**b, "originMm": [21., 2., 3.], "divergenceDeg": 0.,
                           "energySpreadFractional": .2}, a]
    assert scene_to_config(scene, config) == expected


def test_omitted_source_defaults_remain_omitted_until_edited():
    scene, config = recorded_scene()
    for key in ("originMm", "spotRadiusMm", "divergenceDeg", "energySpreadFractional"):
        config["beam"].pop(key)
    assert scene_to_config(scene, config) == config
    scene.beams[0].direction = (1., 0., 1.)
    result = scene_to_config(scene, config)
    assert result == {**config, "beam": {**config["beam"], "direction": [1., 0., 1.]}}
    scene.beams[0].origin_mm = (4., 5., 6.)
    scene.beams[0].spot_radius_mm = 1.
    result = scene_to_config(scene, config)
    assert result["beam"]["originMm"] == [4., 5., 6.]
    assert result["beam"]["spotRadiusMm"] == 1.
    assert "divergenceDeg" not in result["beam"]


def test_named_beam_reordering_and_nonprimary_deletion_keep_source_identity():
    scene, config = recorded_scene()
    a = {**config["beam"], "name": "A", "originMm": [10., 0., 0.]}
    b = {**config["beam"], "name": "B", "originMm": [20., 0., 0.]}
    config.update(beam=deepcopy(a), beams=[a, b])
    raw = deepcopy(scene.raw)
    raw["beams"] = [{**raw["beams"][0], "name": name} for name in ("A", "B")]
    scene = scene_from_viz_data(raw)
    scene.beams.reverse()
    result = scene_to_config(scene, config)
    assert [(beam["name"], beam["originMm"]) for beam in result["beams"]] == [
        ("B", [20., 0., 0.]), ("A", [10., 0., 0.])]
    assert result["beam"] == a
    scene.beams = [next(beam for beam in scene.beams if beam.name == "A")]
    result = scene_to_config(scene, config)
    assert result["beams"] == [a] and result["beam"] == a
    scene.beams[0].name = "B"
    with pytest.raises(ValueError, match="new primary beam"):
        scene_to_config(scene, config)
    scene.beams[0].name = "renamed"
    with pytest.raises(ValueError, match="beam identities"):
        scene_to_config(scene, config)


def test_ambiguous_unnamed_source_reordering_is_rejected():
    scene, config = recorded_scene()
    config["beams"] = [deepcopy(config["beam"]), {**config["beam"], "energyMeV": .05}]
    raw = deepcopy(scene.raw)
    raw["beams"].append({**raw["beams"][0], "energy_ev": .05 * 1e6})
    scene = scene_from_viz_data(raw)
    scene.beams.reverse()
    with pytest.raises(ValueError, match="Name every beam"):
        scene_to_config(scene, config)


@pytest.mark.parametrize("field", [{"run": {"seed": 2 ** 53 + 1}}, {"opaque": {"__proto__": {"x": 1}}}])
def test_js_export_rejects_values_that_object_literals_cannot_preserve(field):
    scene, config = recorded_scene()
    config.update(field)
    with pytest.raises(ValueError):
        scene_to_js(scene, config)


@pytest.mark.parametrize("dependency", [
    {"hooks": {"registered": ["onEvent"]}},
    {"models": [{"name": "stage", "path": "data/model.json"}]},
    {"stratify": {"modelPath": "classifier.json"}},
    {"optics": {"derive": {"surrogateModelPath": "optics.json"}}},
])
def test_export_refuses_lost_callbacks_and_external_dependencies(dependency):
    scene, config = recorded_scene()
    config.update(dependency)
    with pytest.raises(ValueError, match="original scenario"):
        scene_to_js(scene, config)


def test_loaded_scene_needs_matching_full_config():
    scene, config = recorded_scene()
    with pytest.raises(ValueError, match="full recorded config"):
        scene_to_js(scene)
    config["beam"]["originMm"][0] = 88  # invisible in viz, retained as recorded
    assert scene_to_config(scene, config)["beam"]["originMm"][0] == 88
    config["geometry"]["volumes"][0]["shape"]["sizeMm"][0] = 11
    with pytest.raises(ValueError, match="do not match"):
        scene_to_js(scene, config)


@pytest.mark.parametrize("patch", [{"run": {"seed": 124, "nEvents": 4}},
                                   {"run": {"seed": 123, "nEvents": 5}},
                                   {"determinism": {"mode": "predictive"}}])
def test_same_geometry_from_another_run_cannot_supply_export_config(patch):
    scene, config = recorded_scene()
    config.update(patch)
    with pytest.raises(ValueError, match="run identity do not match"):
        scene_to_js(scene, config)


def test_authored_scene_is_data_only_and_rejects_invalid_geometry():
    scene = SceneModel(volumes=[VolumeNode("sample\"\\\n", "G4_WATER",
                       shape=Shape(type="sphere", outer_radius_mm=4.))],
                       beams=[Beam("source", "gamma", energy_ev=30000.)],
                       run=RunParams(n_events=2, seed=7))
    source = scene_to_js(scene)
    assert json.loads(source.split("globalThis.TRECH_CONFIG = ")[1][:-2])["run"]["seed"] == 7
    scene.volumes[0].shape = Shape(type="mesh")
    with pytest.raises(ValueError, match="Unsupported scene shape"):
        scene_to_js(scene)
    scene.volumes[0].shape = Shape(size_mm=(10., float("nan"), 10.))
    with pytest.raises(ValueError, match="finite"):
        scene_to_js(scene)


def test_latest_recorded_config_is_detached_and_invalid_latest_never_falls_back(tmp_path):
    result = RunResult(tmp_path, provenance=[{"config_json": '{"run":{"seed":1}}'},
                                              {"config_json": '{"run":{"seed":2}}'}])
    config = result.recorded_config()
    config["run"]["seed"] = 3
    assert result.recorded_config()["run"]["seed"] == 2
    for invalid in ("bad", "[]", None):
        result.provenance[-1]["config_json"] = invalid
        assert result.recorded_config() is None
    result.provenance = [{"phase": "run_start", "config_json": '{"beam":{"originMm":[10,0,0]}}'},
                         {"phase": "run_start"}, {"phase": "run_end"}]
    assert result.recorded_config() is None
    result.provenance[-2]["config_json"] = '{"beam":{"originMm":[20,0,0]}}'
    assert result.recorded_config()["beam"]["originMm"] == [20, 0, 0]


def test_exported_scene_is_accepted_by_real_engine(tmp_path):
    repo = Path(__file__).resolve().parents[2]
    candidates = ([Path(os.environ["TRECH_BIN"])] if os.environ.get("TRECH_BIN") else [])
    candidates += [repo / p for p in ("build/dev/trech", "build/rel/trech", "build/torch-check/trech")]
    engine = next((p.resolve() for p in candidates if p.is_file()), None)
    if engine is None:
        pytest.skip("No built TRECH binary for inspection round-trip")
    scene, config = recorded_scene()
    original = tmp_path / "original_scene.js"
    original.write_text("globalThis.TRECH_CONFIG = " + json.dumps(config) + ";", encoding="utf-8")
    canonical = json.loads(subprocess.run([str(engine), "inspect", str(original)], cwd=repo,
                           text=True, capture_output=True, timeout=20, check=True).stdout)["config"]
    target = tmp_path / "exported_scene.js"
    target.write_text(scene_to_js(scene, canonical), encoding="utf-8")
    unchanged = json.loads(subprocess.run([str(engine), "inspect", str(target)], cwd=repo,
                           text=True, capture_output=True, timeout=20, check=True).stdout)["config"]
    assert unchanged == canonical
    scene.volumes[0].position_mm = (1., 2., 3.)
    scene.beams[0].energy_ev = 35000.
    target.write_text(scene_to_js(scene, canonical), encoding="utf-8")
    completed = subprocess.run([str(engine), "inspect", str(target)], cwd=repo,
                               text=True, capture_output=True, timeout=20, check=True)
    inspected = json.loads(completed.stdout)["config"]
    assert inspected["beam"]["energyMeV"] == .035
    assert inspected["beam"]["originMm"] == [1., 2., -30.]
    assert inspected["materials"][0]["components"][0]["massNumber"] == 2
    assert inspected["geometry"]["volumes"][0]["placement"]["positionMm"] == [1., 2., 3.]
    expected = deepcopy(canonical)
    expected["beam"]["energyMeV"] = .035
    expected["geometry"]["volumes"][0]["placement"]["positionMm"] = [1., 2., 3.]
    assert inspected == expected
    # Source-only authoring must not re-round energy or erase spectral/polarization fields.
    scene.beams[0].origin_mm = (4., 5., -20.)
    scene.beams[0].direction = (1., 0., 2.)
    scene.beams[0].spot_radius_mm = 1.5
    scene.beams[0].divergence_deg = 12.
    scene.beams[0].energy_spread_fractional = .1
    target.write_text(scene_to_js(scene, canonical), encoding="utf-8")
    inspected = json.loads(subprocess.run([str(engine), "inspect", str(target)], cwd=repo,
                           text=True, capture_output=True, timeout=20, check=True).stdout)["config"]
    expected["beam"].update(originMm=[4., 5., -20.], direction=[1., 0., 2.], spotRadiusMm=1.5,
                            divergenceDeg=12., energySpreadFractional=.1)
    assert inspected == expected


def test_file_export_writes_draft_without_touching_editor_or_loading_it(tmp_path):
    from trech_studio.ui import main_window as module

    scene, config = recorded_scene()
    scene.source_path = str(tmp_path / "trech_viz_scene.json")
    result = RunResult(tmp_path, provenance=[{"config_json": json.dumps(config)}],
                       viz_scene_path=Path(scene.source_path))
    target = tmp_path / "new_scene.js"
    editor_source = tmp_path / "original.js"
    editor_source.write_text("// unsaved workspace remains open")
    messages, warnings = [], []
    window = SimpleNamespace(_loaded_run=result, _scene=scene,
                             settings=SimpleNamespace(output_root=tmp_path),
                             code_editor=SimpleNamespace(source_paths=lambda: (editor_source,)),
                             console=SimpleNamespace(log_info=messages.append))
    with patch.object(module.QFileDialog, "getSaveFileName", return_value=(str(target), "")), \
            patch.object(module.QMessageBox, "warning", lambda *args: warnings.append(args)):
        module.StudioWindow._export_scene_scenario(window)
    assert target.read_text() == scene_to_js(scene, config) and messages and not warnings
    assert editor_source.read_text() == "// unsaved workspace remains open"
    with patch.object(module.QFileDialog, "getSaveFileName", return_value=(str(editor_source), "")), \
            patch.object(module.QMessageBox, "warning", lambda *args: warnings.append(args)):
        module.StudioWindow._export_scene_scenario(window)
    assert warnings and editor_source.read_text() == "// unsaved workspace remains open"
    config["hooks"] = {"registered": ["onEvent"]}
    result.provenance = [{"config_json": json.dumps(config)}]
    with patch.object(module.QFileDialog, "getSaveFileName") as dialog, \
            patch.object(module.QMessageBox, "warning", lambda *args: warnings.append(args)):
        module.StudioWindow._export_scene_scenario(window)
        dialog.assert_not_called()
