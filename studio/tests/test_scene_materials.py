"""Custom material definitions: text form, engine-rule validation, writer and Inspector flow."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QPushButton
from trech_studio.scene.loader import scene_from_viz_data
from trech_studio.scene.materials import (
    format_components, material_references, parse_components, validate_material)
from trech_studio.scene.model import MaterialDef
from trech_studio.scene.writer import scene_to_config, scene_to_js
from test_scene_editing import window  # noqa: F401  (fixture)
from test_scene_writer import recorded_scene

REPO = Path(__file__).resolve().parents[2]


def test_component_text_round_trips_every_config_form():
    components = [{"element": "H", "atoms": 2, "massNumber": 2}, {"element": "O", "atoms": 1}]
    assert parse_components(format_components(components)) == components
    mixture = [{"material": "G4_WATER", "fraction": 0.9}, {"element": "Na", "fraction": 0.04}]
    assert parse_components(format_components(mixture)) == mixture
    text = "  element H atoms 2 A 2   # deuterium\n\nelement O atoms 1\n"
    assert parse_components(text) == components


@pytest.mark.parametrize("text, message", [
    ("element H", "write 'element"),
    ("atom H atoms 2", "starts with"),
    ("element H atoms two", "positive integer"),
    ("element H atoms 0", "positive integer"),
    ("element H atoms 1.5", "positive integer"),
    ("element H fraction x", "number"),
    ("element H atoms 2 atoms 3", "twice"),
    ("element H mole 2", "unknown key"),
])
def test_component_text_errors_name_the_line(text, message):
    with pytest.raises(ValueError, match=message):
        parse_components(text)


@pytest.mark.parametrize("name, density, components, message", [
    ("G4_MINE", 1., [{"element": "H", "fraction": 1.}], "NIST namespace"),
    ("two words", 1., [{"element": "H", "fraction": 1.}], "no spaces"),
    ("m", 0., [{"element": "H", "fraction": 1.}], "density"),
    ("m", float("nan"), [{"element": "H", "fraction": 1.}], "density"),
    ("m", 1., [], "at least one"),
    ("m", 1., [{"element": "H", "material": "G4_AIR", "fraction": 1.}], "exactly one"),
    ("m", 1., [{"element": "H", "atoms": 2}, {"element": "O", "fraction": .5}], "every component"),
    ("m", 1., [{"element": "H", "atoms": 2}, {"material": "G4_WATER", "atoms": 1}], "must be elements"),
    ("m", 1., [{"element": "H", "fraction": -1.}], "positive finite"),
    ("m", 1., [{"element": "Xx", "fraction": 1.}], "not an element"),
    ("m", 1., [{"element": "C", "fraction": 1., "massNumber": 5}], "below Z=6"),
    ("m", 1., [{"material": "G4_WATER", "fraction": 1., "massNumber": 2}], "isotope of an element"),
    ("m", 1., [{"material": "m", "fraction": 1.}], "contain itself"),
    ("m", 1., [{"material": "later", "fraction": 1.}], "declared before"),
])
def test_validation_refuses_what_the_engine_would_skip_or_reject(name, density, components, message):
    with pytest.raises(ValueError, match=message):
        validate_material(name, density, components, new=True)


def test_validation_accepts_nist_and_earlier_custom_components():
    validate_material("brine", 1.03, [{"material": "G4_WATER", "fraction": .96},
                                      {"material": "salt", "fraction": .04}], earlier=["Salt"], new=True)
    validate_material("heavy", 1.1, [{"element": "H", "atoms": 2, "massNumber": 2},
                                     {"element": "O", "atoms": 1}], new=True)


def test_loader_reads_lossless_viz_components_in_config_form():
    raw = {"world": {"size_mm": 10., "material": "G4_AIR"},
           "materials": [{"name": "heavy", "density_gcm3": 1.1, "components": [
               {"material": "", "fraction": 0., "element": "H", "atoms": 2, "massNumber": 2},
               {"material": "G4_WATER", "fraction": .5}]}],
           "derived_optics": [{"material_name": "G4_AIR", "available": True}]}
    scene = scene_from_viz_data(raw)
    assert scene.material_by_name("heavy").components == [
        {"element": "H", "atoms": 2, "massNumber": 2}, {"material": "G4_WATER", "fraction": .5}]
    assert scene.material_by_name("heavy").authored
    assert not scene.material_by_name("G4_AIR").authored


def test_writer_adds_a_new_material_minimal_and_validated():
    scene, config = recorded_scene()
    scene.materials.append(MaterialDef(name="brine", density_gcm3=1.03, components=[
        {"material": "G4_WATER", "fraction": .96}, {"element": "Na", "fraction": .016},
        {"element": "Cl", "fraction": .024}]))
    scene.volumes[0].material = "brine"
    result = scene_to_config(scene, config)
    assert result["materials"][0] == config["materials"][0]
    assert result["materials"][1] == {"name": "brine", "densityGcm3": 1.03, "components": [
        {"material": "G4_WATER", "fraction": .96}, {"element": "Na", "fraction": .016},
        {"element": "Cl", "fraction": .024}]}
    assert result["geometry"]["volumes"][0]["material"] == "brine"
    scene.materials[-1].components[0]["material"] = "nowhere"
    with pytest.raises(ValueError, match="declared before"):
        scene_to_config(scene, config)


def test_writer_edits_density_without_touching_lossy_recorded_components():
    # The fixture's viz scene records the old lossy components; the recorded config wins.
    scene, config = recorded_scene()
    scene.material_by_name("heavy_water").density_gcm3 = 1.107
    result = scene_to_config(scene, config)
    assert result["materials"][0]["densityGcm3"] == 1.107
    assert result["materials"][0]["components"] == config["materials"][0]["components"]


def test_writer_refuses_removing_a_used_material_and_derived_aliases_stay_read_only():
    scene, config = recorded_scene()
    used = deepcopy(scene)
    used.materials = [m for m in used.materials if m.name != "heavy_water"]
    with pytest.raises(ValueError, match="still used by volume sample"):
        scene_to_config(used, config)
    used.volumes[0].material = "G4_AIR"
    assert scene_to_config(used, config)["materials"] == []
    alias = deepcopy(scene)
    alias.material_by_name("G4_AIR").density_gcm3 = 2.
    with pytest.raises(ValueError, match="derived appearance"):
        scene_to_config(alias, config)
    stray = deepcopy(scene)
    stray.materials.append(MaterialDef(name="ghost", density_gcm3=1., authored=False,
                                       components=[{"element": "H", "fraction": 1.}]))
    with pytest.raises(ValueError, match="derived appearance"):
        scene_to_config(stray, config)


def test_material_references_cover_world_medium_volumes_and_components():
    scene, _ = recorded_scene()
    scene.materials.append(MaterialDef(name="mix", components=[{"material": "heavy_water", "fraction": 1.}]))
    uses = material_references("HEAVY_WATER", world="G4_AIR", medium="heavy_water",
                               volumes=scene.volumes, materials=scene.materials)
    assert uses == ["the medium box", "volume sample", "material mix"]


def apply(panel):
    panel.findChild(QPushButton, "apply_scene_draft").click()


def test_inspector_adds_assigns_edits_and_removes_a_custom_material(window):  # noqa: F811
    panel = window.inspector
    panel.show_node("world", "")
    panel.findChild(QPushButton, "add_scene_material").click()
    panel._fields["name"].setText("G4_BRINE")
    panel._fields["components"].setPlainText("material G4_WATER fraction 0.96\nelement Na fraction 0.04")
    apply(panel)
    assert "NIST namespace" in panel._edit_status.text() and not window._scene_dirty

    panel._fields["name"].setText("brine")
    panel._fields["density"].setText("1.03")
    apply(panel)
    assert window._scene_dirty
    assert window._scene.material_by_name("brine").components == [
        {"material": "G4_WATER", "fraction": .96}, {"element": "Na", "fraction": .04}]

    panel.show_node("volume", "sample")
    assert panel._fields["material"].findText("brine") >= 0
    panel._fields["material"].setCurrentText("brine")
    apply(panel)
    assert window._scene.volumes[0].material == "brine"

    panel.show_node("material", "brine")
    panel.findChild(QPushButton, "remove_scene_material").click()
    assert "still used by volume sample" in panel._edit_status.text()
    panel._fields["components"].setPlainText("element H atoms 2\nelement O atoms 1")
    apply(panel)
    exported = scene_to_config(window._scene, window._loaded_run.recorded_config())
    assert exported["materials"][1] == {"name": "brine", "densityGcm3": 1.03, "components": [
        {"element": "H", "atoms": 2}, {"element": "O", "atoms": 1}]}
    assert window._loaded_run.recorded_config() == window.test_original_config

    window.undo_scene_edit()
    assert window._scene.material_by_name("brine").components[0] == {"material": "G4_WATER", "fraction": .96}


def test_inspector_recorded_material_keeps_exact_isotopes_until_edited(window):  # noqa: F811
    panel = window.inspector
    panel.show_node("material", "heavy_water")
    text = panel._fields["components"].toPlainText()
    assert text == "element H atoms 2 A 2\nelement O atoms 1"
    apply(panel)
    assert "No scene fields changed" in panel._edit_status.text()
    panel._fields["density"].setText("1.107")
    apply(panel)
    exported = scene_to_config(window._scene, window._loaded_run.recorded_config())
    assert exported["materials"][0]["components"] == window.test_original_config["materials"][0]["components"]
    assert exported["materials"][0]["densityGcm3"] == 1.107

    panel.show_node("material", "G4_AIR")
    assert panel.findChild(QPushButton, "apply_scene_draft") is None
    panel.show_node("material", "heavy_water")
    panel._fields["components"].setPlainText("element H atoms 2\nelement O fraction 1")
    apply(panel)
    assert "every component" in panel._edit_status.text()


def _engine():
    for p in (REPO / "build/rel/trech", REPO / "build/dev/trech", REPO / "build/trech"):
        if p.is_file():
            return p.resolve()
    pytest.skip("No built TRECH binary for inspection round-trip")


def test_exported_custom_material_round_trips_through_strict_engine_inspection(tmp_path):
    engine = _engine()
    scene, config = recorded_scene()
    scene.materials.append(MaterialDef(name="brine", density_gcm3=1.03, components=[
        {"material": "G4_WATER", "fraction": .96}, {"element": "Na", "fraction": .016},
        {"element": "Cl", "fraction": .024}]))
    scene.materials.append(MaterialDef(name="salted_heavy", density_gcm3=1.12, components=[
        {"material": "heavy_water", "fraction": .9}, {"material": "brine", "fraction": .1}]))
    scene.volumes[0].material = "salted_heavy"
    target = tmp_path / "custom_material.js"
    target.write_text(scene_to_js(scene, config), encoding="utf-8")
    completed = subprocess.run([str(engine), "inspect", str(target), "--strict-config"], cwd=REPO,
                               text=True, capture_output=True, timeout=30, check=True)
    inspected = json.loads(completed.stdout)["config"]
    names = [m["name"] for m in inspected["materials"]]
    assert names == ["heavy_water", "brine", "salted_heavy"]
    assert inspected["materials"][2]["components"] == [
        {"material": "heavy_water", "fraction": .9}, {"material": "brine", "fraction": .1}]
    assert inspected["geometry"]["volumes"][0]["material"] == "salted_heavy"
