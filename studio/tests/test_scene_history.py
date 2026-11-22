"""Scene draft history: linear undo/redo of copied snapshots, without Qt."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trech_studio.scene.history import SceneHistory
from trech_studio.scene.model import SceneModel, VolumeNode


def scene(size):
    return SceneModel(world_size_mm=size, volumes=[VolumeNode(name="a", material="G4_WATER")])


def test_undo_redo_walks_the_recorded_states_with_their_selections():
    history = SceneHistory()
    assert not history.can_undo and not history.can_redo and history.undo() is None
    s100, s150, s200 = scene(100.), scene(150.), scene(200.)
    history.record(s100, ("world", ""), s150, ("world", ""), "world")
    history.record(s150, ("volume", "a"), s200, ("volume", "a"), "volume a")
    assert history.undo_label == "volume a" and not history.can_redo

    state = history.undo()
    assert state.scene == s150 and state.selection == ("volume", "a")
    assert history.redo_label == "volume a"
    assert history.undo().scene == s100 and not history.can_undo
    assert history.redo().scene == s150
    assert history.redo().scene == s200 and history.redo() is None


def test_snapshots_are_isolated_from_later_mutation():
    history = SceneHistory()
    before, after = scene(100.), scene(150.)
    history.record(before, ("world", ""), after, ("world", ""), "world")
    before.world_size_mm = after.world_size_mm = 1.
    restored = history.undo()
    assert restored.scene.world_size_mm == 100.
    restored.scene.volumes[0].material = "G4_AIR"
    assert history.redo().scene.volumes[0].material == "G4_WATER"
    assert history.undo().scene.volumes[0].material == "G4_WATER"


def test_new_edit_after_undo_drops_the_redo_branch_and_limit_drops_the_oldest():
    history = SceneHistory(limit=2)
    history.record(scene(1.), ("world", ""), scene(2.), ("world", ""), "one")
    history.record(scene(2.), ("world", ""), scene(3.), ("world", ""), "two")
    history.undo()
    history.record(scene(2.), ("world", ""), scene(4.), ("world", ""), "three")
    assert not history.can_redo and len(history) == 2
    history.record(scene(4.), ("world", ""), scene(5.), ("world", ""), "four")
    assert len(history) == 2
    assert history.undo().scene.world_size_mm == 4.
    assert history.undo().scene.world_size_mm == 2. and not history.can_undo
    history.clear()
    assert len(history) == 0 and not history.can_redo
    with pytest.raises(ValueError):
        SceneHistory(limit=0)
