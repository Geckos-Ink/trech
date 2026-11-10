"""Scene outliner: the tree of world / volumes / beams / materials for the loaded scene.

Selecting a node emits ``node_selected`` so the Inspector can show or edit its properties.
The tree reflects the current scene draft; it does not change identities itself.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QWidget

from ..scene.model import SceneModel

# Roles stashed on tree items so selection can be routed back to a model object.
_KIND_ROLE = 0x0100
# Declared-scene tooltip kept so repeated marking replaces, never stacks, engine lines.
_BASE_TOOLTIP_ROLE = 0x0101
# Marker appended to nodes the engine built differently from the declared scene.
RESOLUTION_MARK = "  ⚠ engine substituted"
_WARN_BRUSH = QBrush(QColor(214, 120, 0))


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
        self._marks: Dict[Tuple[str, str], List[str]] = {}

    def set_scene(self, scene: SceneModel) -> None:
        self._scene = scene
        self._marks = {}
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

    def set_resolution_marks(self, marks: Dict[Tuple[str, str], List[str]]) -> int:
        """Mark nodes the engine skipped, re-parented or built with a fallback material.

        ``marks`` comes from ``run_summary.geometry_resolution_marks`` (engine provenance,
        read verbatim). The tree still shows the *declared* scene; a marked node says Geant4
        built something else there. Marks are cleared by the next ``set_scene``. Returns the
        number of nodes marked; substitutions without a node here are left to Run summary.
        """
        self._marks = dict(marks)
        marked = 0

        def visit(item: QTreeWidgetItem) -> None:
            nonlocal marked
            data = item.data(0, _KIND_ROLE)
            lines = self._marks.get(data) if isinstance(data, tuple) else None
            if lines:
                text = item.text(0)
                if not text.endswith(RESOLUTION_MARK):
                    item.setText(0, text + RESOLUTION_MARK)
                item.setForeground(0, _WARN_BRUSH)
                base = item.data(0, _BASE_TOOLTIP_ROLE)
                if base is None:
                    base = item.toolTip(0)
                    item.setData(0, _BASE_TOOLTIP_ROLE, base)
                item.setToolTip(0, (base + "\n" if base else "") + "engine: " + "\nengine: ".join(lines))
                marked += 1
            for i in range(item.childCount()):
                visit(item.child(i))

        for i in range(self.topLevelItemCount()):
            visit(self.topLevelItem(i))
        return marked

    def resolution_marks(self) -> Dict[Tuple[str, str], List[str]]:
        return dict(self._marks)

    def select_node(self, kind: str, name: str) -> None:
        """Restore selection after rebuilding the scene tree for an applied draft."""
        def visit(item):
            if item.data(0, _KIND_ROLE) == (kind, name):
                self.setCurrentItem(item)
                return True
            return any(visit(item.child(i)) for i in range(item.childCount()))
        for i in range(self.topLevelItemCount()):
            if visit(self.topLevelItem(i)):
                break

    def _on_selection(self) -> None:
        items = self.selectedItems()
        if not items:
            return
        data = items[0].data(0, _KIND_ROLE)
        if isinstance(data, tuple):
            kind, name = data
            self.node_selected.emit(kind, name)
