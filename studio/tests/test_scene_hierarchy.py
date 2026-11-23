"""Nested volumes: the Inspector's parent control and world placement through parents.

A volume's position and rotation are relative to its parent, as Geant4 places a daughter in its
mother's frame. Studio composes parents when it draws and frames the scene, and the Inspector
creates nested volumes and reparents existing ones.
"""
import math

import pytest
from PySide6.QtWidgets import QPushButton

from test_scene_editing import apply, window  # noqa: F401  (fixture)
from trech_studio.scene.model import SceneModel, Shape, VolumeNode
from trech_studio.scene.writer import scene_to_config


def _scene(*volumes):
    scene = SceneModel(world_size_mm=200.0, world_material="G4_AIR")
    scene.volumes = list(volumes)
    return scene


def test_world_placement_composes_a_rotated_parent():
    holder = VolumeNode("holder", "G4_WATER", parent="world", position_mm=(10., 0., 0.),
                        rotation_deg=(0., 0., 90.), shape=Shape(type="box", size_mm=(4., 4., 4.)))
    core = VolumeNode("core", "G4_WATER", parent="Holder", position_mm=(5., 0., 0.),
                      shape=Shape(type="box", size_mm=(2., 2., 2.)))
    placed = _scene(holder, core).world_placements()
    rotation, position = placed["core"]
    # Geant4 turns a volume by (Rz Ry Rx)^T, so an authored +90 deg about z maps +x to -y.
    assert position == pytest.approx((10., -5., 0.), abs=1e-12)
    assert rotation[0][1] == pytest.approx(1.) and rotation[1][0] == pytest.approx(-1.)
    lo, hi = _scene(holder, core).bounds_mm()
    assert lo[1] == pytest.approx(-6.) and hi[1] == pytest.approx(2.)  # holder and core both fit


def test_rotation_sense_matches_the_geant4_pencil_beam_probes():
    """Anchors from Geant4 runs (2026-11-23): 100 MeV protons along +z deposited energy only
    where Studio now draws the volume (docs/studio/studio_authoring.md, rotation sense)."""
    slab = VolumeNode("slab", "G4_WATER", parent="world", rotation_deg=(25., -35., 40.),
                      shape=Shape(type="box", size_mm=(100., 4., 4.)))
    rotation, _ = _scene(slab).world_placements()["slab"]
    tip = tuple(40. * rotation[i][0] for i in range(3))   # 40 mm along the slab's local +x
    assert tip == pytest.approx((25.10, -30.73, -5.06), abs=0.01)  # beam here: 112 MeV, elsewhere ~0
    frame = VolumeNode("frame", "G4_AIR", parent="world", rotation_deg=(0., 0., 30.),
                       shape=Shape(type="box", size_mm=(120., 120., 20.)))
    pad = VolumeNode("pad", "G4_WATER", parent="frame", position_mm=(40., 0., 0.),
                     shape=Shape(type="box", size_mm=(10., 10., 10.)))
    _, position = _scene(frame, pad).world_placements()["pad"]
    assert position == pytest.approx((34.64, -20.0, 0.), abs=0.01)  # beam here: 157 MeV; at +20: 0.27


def test_unknown_later_and_builtin_parents_place_in_the_world_like_the_engine():
    later = VolumeNode("child", "G4_WATER", parent="box", position_mm=(1., 2., 3.))
    box = VolumeNode("box", "G4_WATER", parent="medium", position_mm=(50., 0., 0.))
    placed = _scene(later, box).world_placements()
    assert placed["child"][1] == (1., 2., 3.)   # parent declared later: the engine's world fallback
    assert placed["box"][1] == (50., 0., 0.)    # the medium box sits on the origin, unrotated
    stray = VolumeNode("stray", "G4_WATER", parent="missing", position_mm=(4., 0., 0.))
    assert _scene(stray).world_placements()["stray"][1] == (4., 0., 0.)


def test_inspector_creates_a_nested_volume_and_exports_its_parent(window):  # noqa: F811
    panel = window.inspector
    panel.show_node("world", "")
    panel.findChild(QPushButton, "add_scene_volume").click()
    parents = [panel._fields["parent"].itemData(i) for i in range(panel._fields["parent"].count())]
    assert parents == ["", "world", "sample"]   # no medium box in this scene
    assert panel._fields["parent"].currentData() == "world"
    panel._fields["name"].setText("core")
    panel._fields["parent"].setCurrentIndex(parents.index("sample"))
    panel._fields["position"].setText("0, 0, 5")
    apply(panel)
    core = window._scene.volume_by_name("core")
    assert core.parent == "sample"
    volumes = scene_to_config(window._scene, window._loaded_run.recorded_config())["geometry"]["volumes"]
    assert [v["name"] for v in volumes] == ["sample", "core"]
    assert volumes[1]["placement"]["parent"] == "sample"
    assert "parent" not in volumes[0]["placement"]   # an untouched recorded volume keeps its bytes
    # The sample is rotated 10 deg about y (by R^T, as Geant4 places it), so the child sits on
    # the sample's tilted axis.
    position = window._scene.world_placements()["core"][1]
    assert position == pytest.approx((-5 * math.sin(math.radians(10.)), 0., 5 * math.cos(math.radians(10.))))


def test_reparenting_offers_neither_the_volume_nor_its_descendants(window):  # noqa: F811
    panel = window.inspector
    for name, parent in (("core", "sample"), ("tip", "core"), ("probe", "world")):
        panel.show_node("world", "")
        panel.findChild(QPushButton, "add_scene_volume").click()
        panel._fields["name"].setText(name)
        field = panel._fields["parent"]
        field.setCurrentIndex(field.findData(parent))
        apply(panel)
    panel.show_node("volume", "sample")
    field = panel._fields["parent"]
    choices = [field.itemData(i) for i in range(field.count())]
    assert choices == ["", "world", "probe"]          # not sample, core or tip
    assert field.currentData() == ""                   # the recorded default is kept
    field.setCurrentIndex(choices.index("probe"))      # nest sample in the later probe
    apply(panel)
    assert window._scene.volume_by_name("sample").parent == "probe"
    volumes = scene_to_config(window._scene, window._loaded_run.recorded_config())["geometry"]["volumes"]
    order = [v["name"] for v in volumes]
    assert order.index("probe") < order.index("sample") < order.index("core") < order.index("tip")
