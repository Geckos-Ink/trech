"""Per-field engine diagnostics in the Inspector.

The engine records what it built differently from the declared scene (``geometry_resolution``)
and which config keys it never read (``config_unknown_keys``). Studio attaches each one to the
Inspector field it concerns, verbatim, and adds nothing of its own.
"""
import json

from PySide6.QtWidgets import QLabel

from trech_studio.engine.outputs import RunResult
from trech_studio.run_summary import engine_field_diagnostics, geometry_resolution_marks
from trech_studio.scene.model import SceneModel, Shape, VolumeNode
from trech_studio.ui.inspector import Inspector

BLOCK = {"schema": "trech_geometry_resolution_v1", "issues": [
    {"kind": "material_fallback", "role": "volume", "volume": "sample", "requested": "unobtanium",
     "resolved": "G4_AIR", "reason": "unknown_material"},
    {"kind": "parent_fallback", "role": "volume", "volume": "sample", "requested": "ghost",
     "resolved": "world", "reason": "unknown_parent"},
    {"kind": "overlap", "role": "volume", "volume": "sample", "requested": "shield", "resolved": "",
     "reason": "overlaps_sibling", "depth_mm": 1.5},
    {"kind": "material_fallback", "role": "world", "volume": "", "requested": "air",
     "resolved": "G4_AIR", "reason": "unknown_material"},
    {"kind": "material_fallback", "role": "medium", "volume": "", "requested": "brine",
     "resolved": "G4_WATER", "reason": "unknown_material"}]}
CONFIG = {"geometry": {"volumes": [{"name": "shield"}, {"name": "sample", "colour": "red"}]},
          "beam": {"particle": "gamma"}}
UNKNOWN = ["beam.positionMm", "environment.humidity", "geometry.volumes[1].colour", "run.typo"]


def _result(tmp_path, **end):
    return RunResult(tmp_path, provenance=[
        {"phase": "run_start", "config_json": json.dumps(CONFIG), "config_unknown_keys": UNKNOWN},
        {"phase": "run_end", "geometry_resolution": BLOCK, "config_unknown_keys": UNKNOWN, **end}])


def test_issues_land_on_the_field_they_concern(tmp_path):
    diagnostics = engine_field_diagnostics(_result(tmp_path))
    sample = diagnostics[("volume", "sample")]
    assert sample["material"] == ["material 'unobtanium' → G4_AIR (unknown_material)"]
    assert sample["parent"] == ["placed in the world, not in 'ghost' (unknown_parent)"]
    assert sample["position"] == ["overlaps 'shield' by ≥ 1.5 mm (overlap)"]
    assert sample["unknown:colour"] == ["ignored by the engine (unknown key)"]
    # A sibling overlap marks both volumes, as in the Outliner.
    assert diagnostics[("volume", "shield")]["position"] == ["overlaps 'sample' by ≥ 1.5 mm (overlap)"]
    assert diagnostics[("world", "")]["world_material"] == ["material 'air' → G4_AIR (unknown_material)"]
    assert diagnostics[("world", "")]["unknown:humidity"] == ["ignored by the engine (unknown key)"]
    assert diagnostics[("medium", "")]["medium"] == ["material 'brine' → G4_WATER (unknown_material)"]
    assert diagnostics[("beam", "gamma")]["unknown:positionMm"] == ["ignored by the engine (unknown key)"]
    # A key with no Inspector node (run.*) is left to the run summary's ignored-keys section.
    assert not any("unknown:typo" in fields for fields in diagnostics.values())
    # The Outliner marks are the same lines per node.
    marks = geometry_resolution_marks(_result(tmp_path))
    assert sorted(marks[("volume", "sample")]) == sorted(
        sample["material"] + sample["parent"] + sample["position"])


def test_older_or_clean_runs_have_no_diagnostics(tmp_path):
    assert engine_field_diagnostics(RunResult(tmp_path, provenance=[{"phase": "run_start"}])) == {}
    clean = RunResult(tmp_path, provenance=[{"phase": "run_start", "config_json": "not json",
                                             "config_unknown_keys": ["geometry.volumes[0].x"]}])
    assert engine_field_diagnostics(clean) == {}  # no recorded config, so no volume to name


def _scene():
    scene = SceneModel(world_size_mm=200.0, world_material="G4_AIR")
    scene.volumes = [VolumeNode("sample", "G4_AIR", parent="ghost", shape=Shape(type="box", size_mm=(4., 4., 4.)))]
    return scene


def _rows(inspector, prefix="engine_diagnostic_"):
    return {label.objectName(): label.text() for label in inspector.findChildren(QLabel)
            if label.objectName().startswith(prefix)}


def test_inspector_shows_each_diagnostic_under_its_field(tmp_path):
    inspector = Inspector()
    inspector.set_scene(_scene())
    inspector.set_field_diagnostics(engine_field_diagnostics(_result(tmp_path)))
    inspector.show_node("volume", "sample")
    rows = _rows(inspector)
    assert rows["engine_diagnostic_material"] == "material 'unobtanium' → G4_AIR (unknown_material)"
    assert rows["engine_diagnostic_parent"].startswith("placed in the world")
    assert rows["engine_diagnostic_unknown:colour"] == "ignored by the engine (unknown key)"
    inspector.show_node("world", "")
    rows = _rows(inspector)
    assert rows["engine_diagnostic_world_material"].startswith("material 'air'")
    assert rows["engine_diagnostic_medium"].startswith("material 'brine'")  # medium box shows on world
    inspector.set_field_diagnostics(None)
    inspector.show_node("volume", "sample")
    assert _rows(inspector) == {}


def test_editable_field_carries_the_diagnostic_as_tooltip(tmp_path):
    inspector = Inspector()
    inspector.set_scene(_scene())
    inspector.set_editing(True, config={"geometry": {"volumes": []}})
    inspector.set_field_diagnostics(engine_field_diagnostics(_result(tmp_path)))
    inspector.show_node("volume", "sample")
    material = inspector._fields["material"]
    assert material.toolTip() == "Engine, recorded run: material 'unobtanium' → G4_AIR (unknown_material)"
    assert material.property("engine_diagnostic") is True
    assert inspector._fields["position"].toolTip().startswith("Engine, recorded run: overlaps 'shield'")
    assert not inspector._fields["shape"].toolTip()  # no issue, no tooltip
