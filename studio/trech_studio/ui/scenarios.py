"""Scenario browser: a tree of scenario folders in the left sidebar.

By default it shows the repo's ``examples/`` folder — the shipped experiment scenarios, lab
configs, and macros. That set doubles as Studio's own test suite: every scenario there is a
complex, real run Studio should be able to open, render, and (once run) play back on the
timeline, so browsing + activating them is how we exercise the viewer against hard cases.

Users can add their own scenario folders ("scenarios created") via the toolbar; each root is a
top-level node. A filter box narrows the tree: every whitespace-separated token must appear in
a scenario's file name, its folder path under the root, or its leading comment block (the
scenario's own description). Enter in the filter opens the scenario when exactly one matches.
Two selectors narrow by validation family and recorded validation status, read from the
committed purity index (``docs/validation/TRECH_current_scenarios_purity.json``, regenerated with the
purity report); the same facts are searchable as ``family:<f>``, ``validation:<s>``,
``grade:<g>`` and ``physics:<status>`` tokens. They describe the committed validation report's
checkout, not the file on disk now. Activating a scenario (double-click / Enter) emits ``scenario_activated`` with
its path — the main window opens it in the code editor and, if a matching run output already
exists, loads that run so the tree acts as a one-click launcher for the suite.

This is a pure Qt view over the filesystem — no engine calls, no physics.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
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

_FAMILY_ROLE = 0x0103  # validation families (tuple) from the purity index
_STATUS_ROLE = 0x0104  # recorded validation status from the purity index

# The leading comment is streamed line by line and stops at the first code line,
# so a long description is read whole (it used to be cut at 8 KiB / 120 lines);
# these bounds only guard against a pathological comment-only file.
_HEADER_BYTES = 1 << 20
_HEADER_LINES = 4000

PURITY_INDEX = Path("docs") / "validation" / "TRECH_current_scenarios_purity.json"
PURITY_INDEX_SCHEMA = "trech_scenario_purity_index_v1"
ALL_FAMILIES = "All families"
ANY_VALIDATION = "Any validation"


def _comment_lines(path: Path):
    read = 0
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        for count, raw in enumerate(handle):
            read += len(raw)
            if count >= _HEADER_LINES or read > _HEADER_BYTES:
                return
            yield raw


def scenario_description(path: Path) -> str:
    """The leading comment block of a scenario file (``//``, ``#`` or ``/* */`` lines).

    Reads until the first code line (bounded by ``_HEADER_BYTES``/``_HEADER_LINES``);
    unreadable files and JSON configs give ``""``.
    """
    lines: List[str] = []
    in_block = False
    try:
        raws = list(_iter_until_code(path))
    except OSError:
        return ""
    for raw in raws:
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


def _iter_until_code(path: Path):
    """Raw lines up to and including the first code line (comment state tracked)."""
    in_block = False
    for raw in _comment_lines(path):
        yield raw
        line = raw.strip()
        if in_block:
            in_block = "*/" not in line
            continue
        if line.startswith("/*"):
            in_block = "*/" not in line[2:]
        elif line and not line.startswith(("//", "#")):
            return


def load_purity_index(root: Path) -> Tuple[Optional[Path], Dict[str, dict], str]:
    """(repository root, entry path -> index record, recorded git sha) for ``root``.

    Walks up from ``root`` to the first folder holding the committed purity index.
    A missing or malformed index gives an empty mapping (no family/status facts).
    """
    for folder in [Path(root).resolve(), *Path(root).resolve().parents]:
        candidate = folder / PURITY_INDEX
        if not candidate.is_file():
            continue
        try:
            doc = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None, {}, ""
        if not isinstance(doc, dict) or doc.get("schema") != PURITY_INDEX_SCHEMA:
            return None, {}, ""
        records: Dict[str, dict] = {}
        for record in (doc.get("scenarios") or {}).values():
            if isinstance(record, dict) and isinstance(record.get("entry"), str):
                records[record["entry"]] = record
        return folder, records, str(doc.get("validation_git_sha", ""))
    return None, {}, ""


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
        facet_row = QHBoxLayout()
        facet_row.setContentsMargins(6, 0, 6, 4)
        self.family_combo = QComboBox(self)
        self.family_combo.setToolTip(
            "Validation family (category of the suite cases attributed to the scenario)")
        self.status_combo = QComboBox(self)
        self.status_combo.setToolTip(
            "Validation status recorded by the committed validation report")
        self.family_combo.currentTextChanged.connect(lambda _text: self._apply_filter())
        self.status_combo.currentTextChanged.connect(lambda _text: self._apply_filter())
        facet_row.addWidget(self.family_combo, 1)
        facet_row.addWidget(self.status_combo, 1)
        layout.addLayout(facet_row)
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
            self._index = load_purity_index(root)
            self._populate_dir(node, root)
            node.setExpanded(True)
        self._refresh_facets()
        self._apply_filter()

    def _refresh_facets(self) -> None:
        families = sorted({f for item in self._file_items() for f in (item.data(0, _FAMILY_ROLE) or ())})
        statuses = sorted({item.data(0, _STATUS_ROLE) for item in self._file_items()
                           if item.data(0, _STATUS_ROLE)})
        for combo, first, values in ((self.family_combo, ALL_FAMILIES, families),
                                     (self.status_combo, ANY_VALIDATION, statuses)):
            previous = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems([first, *values])
            combo.setCurrentIndex(max(0, combo.findText(previous)))
            combo.setEnabled(bool(values))
            combo.blockSignals(False)

    def set_facets(self, family: str = ALL_FAMILIES, validation: str = ANY_VALIDATION) -> None:
        """Select a family and validation status (unknown values fall back to all)."""
        self.family_combo.setCurrentIndex(max(0, self.family_combo.findText(family)))
        self.status_combo.setCurrentIndex(max(0, self.status_combo.findText(validation)))
        self._apply_filter()

    def _index_record(self, child: Path) -> Tuple[Optional[dict], str]:
        repo, records, sha = getattr(self, "_index", (None, {}, ""))
        if repo is None:
            return None, sha
        try:
            entry = child.resolve().relative_to(repo).as_posix()
        except ValueError:
            return None, sha
        return records.get(entry), sha

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
                record, sha = self._index_record(child)
                facts = ""
                tip = str(child)
                if record is not None:
                    families = tuple(f for f in record.get("families", ()) if isinstance(f, str))
                    status = str(record.get("validation", ""))
                    item.setData(0, _FAMILY_ROLE, families)
                    item.setData(0, _STATUS_ROLE, status)
                    facts = " ".join([*(f"family:{f}" for f in families), f"validation:{status}",
                                      f"grade:{record.get('grade', '')}",
                                      f"physics:{record.get('physics_status', '')}"])
                    tip += (f"\nPurity grade {record.get('grade', '?')} · validation {status}"
                            + (f" ({', '.join(families)})" if families else "")
                            + (f" · recorded at {sha[:7]}" if sha else ""))
                item.setData(0, _SEARCH_ROLE,
                             " ".join((child.name, folder, description, facts)).lower())
                summary = description.split("\n", 1)[0] if description else ""
                item.setToolTip(0, f"{tip}\n{summary}" if summary else tip)
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
        family = self.family_combo.currentText()
        status = self.status_combo.currentText()
        family = "" if family in ("", ALL_FAMILIES) else family
        status = "" if status in ("", ANY_VALIDATION) else status
        narrowing = bool(tokens or family or status)
        total = 0
        shown = 0

        def visit(item: QTreeWidgetItem) -> bool:
            nonlocal total, shown
            if item.data(0, _ISFILE_ROLE):
                total += 1
                haystack = item.data(0, _SEARCH_ROLE) or item.text(0).lower()
                visible = (all(token in haystack for token in tokens)
                           and (not family or family in (item.data(0, _FAMILY_ROLE) or ()))
                           and (not status or item.data(0, _STATUS_ROLE) == status))
                shown += visible
                item.setHidden(not visible)
                return visible
            any_visible = False
            for i in range(item.childCount()):
                any_visible = visit(item.child(i)) or any_visible
            item.setHidden(narrowing and not any_visible)
            if narrowing and any_visible:
                item.setExpanded(True)
            return any_visible

        for i in range(self.tree.topLevelItemCount()):
            visit(self.tree.topLevelItem(i))
        self.count_label.setText(f"{shown} of {total}" if narrowing else f"{total} scenarios")

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
