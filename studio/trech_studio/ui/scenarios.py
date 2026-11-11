"""Scenario browser: a tree of scenario folders in the left sidebar.

By default it shows the repo's ``examples/`` folder — the shipped experiment scenarios, lab
configs, and macros. That set doubles as Studio's own test suite: every scenario there is a
complex, real run Studio should be able to open, render, and (once run) play back on the
timeline, so browsing + activating them is how we exercise the viewer against hard cases.

Users can add their own scenario folders ("scenarios created") via the toolbar; each root is a
top-level node. A filter box narrows the tree: every whitespace-separated token must appear in
a scenario's file name, its folder path under the root, or its leading comment block (the
scenario's own description). Enter in the filter opens the scenario when exactly one matches. Activating a scenario (double-click / Enter) emits ``scenario_activated`` with
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
    QLabel,
    QLineEdit,
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
_SEARCH_ROLE = 0x0102  # lower-cased name + relative folder + leading comment, for the filter

_HEADER_BYTES = 8192   # only the head of a file is read for its description
_HEADER_LINES = 120


def scenario_description(path: Path) -> str:
    """The leading comment block of a scenario file (``//``, ``#`` or ``/* */`` lines).

    Reads at most the first few KiB; unreadable files and JSON configs give ``""``.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            head = handle.read(_HEADER_BYTES)
    except OSError:
        return ""
    lines: List[str] = []
    in_block = False
    for raw in head.splitlines()[:_HEADER_LINES]:
        line = raw.strip()
        if in_block:
            end = line.find("*/")
            lines.append((line[:end] if end >= 0 else line).lstrip("*").strip())
            in_block = end < 0
            continue
        if line.startswith("//") or line.startswith("#"):
            lines.append(line.lstrip("/#").strip())
        elif line.startswith("/*"):
            body = line[2:]
            end = body.find("*/")
            lines.append((body[:end] if end >= 0 else body).lstrip("*").strip())
            in_block = end < 0
        elif not line and lines:
            lines.append("")
        elif line:
            break
    return "\n".join(lines).strip()


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

        filter_row = QHBoxLayout()
        filter_row.setContentsMargins(6, 0, 6, 4)
        self.filter_edit = QLineEdit(self)
        self.filter_edit.setPlaceholderText("Filter: name, folder or description words")
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.setToolTip(
            "Every word must match the file name, its folder or the scenario's leading comment.\n"
            "Enter opens the scenario when exactly one matches.")
        self.filter_edit.textChanged.connect(self.set_filter)
        self.filter_edit.returnPressed.connect(self._activate_single_match)
        self.count_label = QLabel(self)
        filter_row.addWidget(self.filter_edit, 1)
        filter_row.addWidget(self.count_label)
        layout.addLayout(filter_row)
        self._filter_tokens: List[str] = []

        self.tree = QTreeWidget(self)
        self.tree.setHeaderLabels(["Scenario", "Type"])
        self.tree.setColumnWidth(0, 220)
        self.tree.setRootIsDecorated(True)
        self.tree.itemActivated.connect(self._on_activated)
        # Qt activation already covers double-click/Enter. Connecting both
        # would open twice and repeat an unsaved-draft prompt after Cancel.
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
        self._apply_filter()

    def _populate_dir(self, parent_item: QTreeWidgetItem, directory: Path,
                      root: Optional[Path] = None) -> int:
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
                found = self._populate_dir(node, child, root or directory)
                if found == 0:
                    # Prune empty branches so the tree only shows scenario-bearing folders.
                    parent_item.removeChild(node)
                else:
                    node.setExpanded(directory in self._roots)
                    count += found
            else:
                label = _SCENARIO_SUFFIXES.get(child.suffix.lower())
                if label is None or child.name.endswith((".view.js", ".ui.js", ".validation.js")) or child.name.startswith("trech_"):
                    continue
                item = QTreeWidgetItem(parent_item, [child.name, label])
                item.setData(0, _PATH_ROLE, str(child.resolve()))
                item.setData(0, _ISFILE_ROLE, True)
                description = scenario_description(child)
                try:
                    folder = str(child.parent.relative_to(root or directory))
                except ValueError:
                    folder = ""
                item.setData(0, _SEARCH_ROLE,
                             " ".join((child.name, folder, description)).lower())
                summary = description.split("\n", 1)[0] if description else ""
                item.setToolTip(0, f"{child}\n{summary}" if summary else str(child))
                count += 1
        return count

    # --- filtering ----------------------------------------------------------------------

    def set_filter(self, text: str) -> None:
        """Show only scenarios matching every whitespace-separated token of ``text``."""
        self._filter_tokens = text.lower().split()
        if self.filter_edit.text() != text:
            self.filter_edit.setText(text)   # re-enters through textChanged; harmless
        self._apply_filter()

    def visible_scenarios(self) -> List[str]:
        """Absolute paths of the scenario files the current filter leaves visible."""
        return [item.data(0, _PATH_ROLE) for item in self._file_items() if not item.isHidden()]

    def _file_items(self) -> List[QTreeWidgetItem]:
        found: List[QTreeWidgetItem] = []
        stack = [self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount())]
        while stack:
            item = stack.pop()
            if item.data(0, _ISFILE_ROLE):
                found.append(item)
            stack.extend(item.child(i) for i in range(item.childCount()))
        found.sort(key=lambda it: str(it.data(0, _PATH_ROLE)))
        return found

    def _apply_filter(self) -> None:
        tokens = self._filter_tokens
        total = 0
        shown = 0

        def visit(item: QTreeWidgetItem) -> bool:
            nonlocal total, shown
            if item.data(0, _ISFILE_ROLE):
                total += 1
                haystack = item.data(0, _SEARCH_ROLE) or item.text(0).lower()
                visible = all(token in haystack for token in tokens)
                shown += visible
                item.setHidden(not visible)
                return visible
            any_visible = False
            for i in range(item.childCount()):
                any_visible = visit(item.child(i)) or any_visible
            item.setHidden(bool(tokens) and not any_visible)
            if tokens and any_visible:
                item.setExpanded(True)
            return any_visible

        for i in range(self.tree.topLevelItemCount()):
            visit(self.tree.topLevelItem(i))
        self.count_label.setText(f"{shown} of {total}" if tokens else f"{total} scenarios")

    def _activate_single_match(self) -> None:
        matches = self.visible_scenarios()
        if self._filter_tokens and len(matches) == 1:
            self.scenario_activated.emit(str(matches[0]))

    # --- activation ---------------------------------------------------------------------

    def _on_activated(self, item: QTreeWidgetItem, _column: int = 0) -> None:
        if not item.data(0, _ISFILE_ROLE):
            item.setExpanded(not item.isExpanded())
            return
        path = item.data(0, _PATH_ROLE)
        if path:
            self.scenario_activated.emit(str(path))
