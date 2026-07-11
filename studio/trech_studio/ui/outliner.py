"""Scene outliner: the tree of world / volumes / beams / materials for the loaded scene.

Selecting a node emits ``node_selected`` so the inspector can show its properties. Editing is
ROADMAP M2 — today the tree is a faithful read-only view of the ``SceneModel``.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QWidget

from ..scene.model import SceneModel

# Roles stashed on tree items so selection can be routed back to a model object.
_KIND_ROLE = 0x0100


class Outliner(QTreeWidget):
    """Read-only scene tree (M0). Emits (kind, name) on selection."""

    node_selected = Signal(str, str)  # (kind, name): kind in {world, volume, beam, material}

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setHeaderLabels(["Scene", "Type"])
        self.setColumnWidth(0, 220)
        self.setRootIsDecorated(True)
        self.itemSelectionChanged.connect(self._on_selection)
        self._scene: Optional[SceneModel] = None

    def set_scene(self, scene: SceneModel) -> None:
        self._scene = scene
        self.clear()

        src = scene.source_path or "authored / placeholder"
        world = QTreeWidgetItem(self, [f"world  ({scene.world_material})", "world"])
        world.setData(0, _KIND_ROLE, ("world", ""))
        world.setToolTip(0, f"source: {src}\nsize: {scene.world_size_mm:.1f} mm")

        if scene.volumes:
            vol_root = QTreeWidgetItem(self, [f"volumes ({len(scene.volumes)})", ""])
            for v in scene.volumes:
                label = v.name or "(unnamed)"
                tag_hint = "  ·  " + ", ".join(v.tags) if v.tags else ""
                item = QTreeWidgetItem(vol_root, [f"{label}{tag_hint}", v.shape.type])
                item.setData(0, _KIND_ROLE, ("volume", v.name))
                item.setToolTip(0, f"material: {v.material}\ntags: {v.tags}")
            vol_root.setExpanded(True)

        if scene.beams:
            beam_root = QTreeWidgetItem(self, [f"beams ({len(scene.beams)})", ""])
            for b in scene.beams:
                item = QTreeWidgetItem(beam_root, [b.name or b.particle, "beam"])
                item.setData(0, _KIND_ROLE, ("beam", b.name or b.particle))
            beam_root.setExpanded(True)

        if scene.materials:
            mat_root = QTreeWidgetItem(self, [f"materials ({len(scene.materials)})", ""])
            for m in scene.materials:
                optics = " · optics" if m.optics_available else ""
                item = QTreeWidgetItem(mat_root, [f"{m.name}{optics}", "material"])
                item.setData(0, _KIND_ROLE, ("material", m.name))

        world.setExpanded(True)

    def _on_selection(self) -> None:
        items = self.selectedItems()
        if not items:
            return
        data = items[0].data(0, _KIND_ROLE)
        if isinstance(data, tuple):
            kind, name = data
            self.node_selected.emit(kind, name)
