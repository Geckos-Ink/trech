"""Scenario browser: a tree of scenario folders in the left sidebar.

By default it shows the repo's ``examples/`` folder — the shipped experiment scenarios, lab
configs, and macros. That set doubles as Studio's own test suite: every scenario there is a
complex, real run Studio should be able to open, render, and (once run) play back on the
timeline, so browsing + activating them is how we exercise the viewer against hard cases.

Users can add their own scenario folders ("scenarios created") via the toolbar; each root is a
top-level node. Activating a scenario (double-click / Enter) emits ``scenario_activated`` with
its path — the main window opens it in the code editor and, if a matching run output already
exists, loads that run so the tree acts as a one-click launcher for the suite.

This is a pure Qt view over the filesystem — no engine calls, no physics.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

# Files worth surfacing as "scenarios" (and the label shown in the type column).
_SCENARIO_SUFFIXES = {".js": "scenario", ".json": "config", ".mac": "macro"}
_SKIP_DIRS = {"__pycache__", ".git", ".venv", "node_modules"}

_PATH_ROLE = 0x0100   # absolute path stashed on file items
_ISFILE_ROLE = 0x0101


class ScenarioBrowser(QWidget):
    """Filesystem tree of scenario roots. Emits the activated scenario's path."""

    scenario_activated = Signal(str)  # absolute path to the activated scenario file

    def __init__(self, roots: Sequence[Path], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._roots: List[Path] = [Path(r) for r in roots]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(6, 6, 6, 4)
        self._add_button = QPushButton("Add folder…", self)
        self._add_button.setToolTip("Add another folder of scenarios to the tree")
        self._add_button.clicked.connect(self._pick_folder)
        self._refresh_button = QPushButton("Refresh", self)
        self._refresh_button.clicked.connect(self.reload)
        toolbar.addWidget(self._add_button)
        toolbar.addWidget(self._refresh_button)
        toolbar.addStretch(1)
        layout.addLayout(toolbar)

        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels(["Scenario", "Type"])
        self.tree.setColumnWidth(0, 220)
        self.tree.setRootIsDecorated(True)
        self.tree.itemActivated.connect(self._on_activated)
        self.tree.itemDoubleClicked.connect(self._on_activated)
        layout.addWidget(self.tree, 1)

        self.reload()

    # --- roots --------------------------------------------------------------------------

    def add_root(self, path: Path) -> None:
        path = Path(path)
        if path.is_dir() and path not in self._roots:
            self._roots.append(path)
            self.reload()

    def _pick_folder(self) -> None:
        start = str(self._roots[0]) if self._roots else str(Path.home())
        chosen = QFileDialog.getExistingDirectory(self, "Add scenario folder", start)
        if chosen:
            self.add_root(Path(chosen))

    # --- population ---------------------------------------------------------------------

    def reload(self) -> None:
        self.tree.clear()
        for root in self._roots:
            if not root.exists():
                continue
            node = QTreeWidgetItem(self.tree, [root.name or str(root), "folder"])
            node.setData(0, _ISFILE_ROLE, False)
            node.setToolTip(0, str(root))
            self._populate_dir(node, root)
            node.setExpanded(True)

    def _populate_dir(self, parent_item: QTreeWidgetItem, directory: Path) -> int:
        """Recurse into ``directory``; returns how many scenario files it (transitively) holds."""
        try:
            children = sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except OSError:
            return 0

        count = 0
        for child in children:
            if child.name.startswith(".") or child.name in _SKIP_DIRS:
                continue
            if child.is_dir():
                node = QTreeWidgetItem(parent_item, [child.name, "folder"])
                node.setData(0, _ISFILE_ROLE, False)
                found = self._populate_dir(node, child)
                if found == 0:
                    # Prune empty branches so the tree only shows scenario-bearing folders.
                    parent_item.removeChild(node)
                else:
                    node.setExpanded(directory in self._roots)
                    count += found
            else:
                label = _SCENARIO_SUFFIXES.get(child.suffix.lower())
                if label is None:
                    continue
                item = QTreeWidgetItem(parent_item, [child.name, label])
                item.setData(0, _PATH_ROLE, str(child.resolve()))
                item.setData(0, _ISFILE_ROLE, True)
                item.setToolTip(0, str(child))
                count += 1
        return count

    # --- activation ---------------------------------------------------------------------

    def _on_activated(self, item: QTreeWidgetItem, _column: int = 0) -> None:
        if not item.data(0, _ISFILE_ROLE):
            item.setExpanded(not item.isExpanded())
            return
        path = item.data(0, _PATH_ROLE)
        if path:
            self.scenario_activated.emit(str(path))
