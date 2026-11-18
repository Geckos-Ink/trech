"""Models → Browse all models: every learned model Studio can find, with architecture and context.

Lists the repository's models, the ``trech-ml`` checkpoint store, ``trech arch`` output
(``build/arch`` by default) and any folder the user adds, grouped by origin, input context
(unnamed: models that read the same named inputs), scale band or folder. The details pane shows
what the file records (architecture, inputs/outputs, scale, measured domain, holdout, generator
provenance, the ``trech arch`` decision) and, for models a loaded run used (same SHA-256 as its
recorded snapshot), the context the scenario registered them with. Studio ranks nothing.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional, Sequence

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSplitter,
    QTextBrowser, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
)

from ..engine.model_catalog import CatalogScan, scan_models
from ..model_catalog import (
    GROUP_KEYS, GROUP_LABELS, ModelEntry, attach_run, entry_html, group_entries, matches_filter, parameters_text,
)

FOLDERS_KEY = "model_browser/extra_folders"
ENTRY_ROLE = Qt.UserRole + 1


class ModelBrowser(QDialog):
    """Non-modal browser. ``settings`` (a QSettings) keeps added folders; tests pass their own."""

    def __init__(self, repo_root: Path, store: Optional[Path], parent=None,
                 settings: Optional[QSettings] = None,
                 pick_folder: Optional[Callable[[], Optional[Path]]] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Models")
        self.resize(1100, 680)
        self.repo_root = Path(repo_root)
        self.store = Path(store) if store is not None else None
        self._settings = settings if settings is not None else QSettings("TRECH", "Studio")
        self._pick_folder = pick_folder or self._ask_folder
        self._manifest = None
        self.scan = CatalogScan()
        self.extra_folders: List[Path] = [Path(p) for p in self._stored_folders()]

        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter by name, input, output, scale, format…")
        self.group_by = QComboBox()
        for key in GROUP_KEYS:
            self.group_by.addItem(GROUP_LABELS[key], key)
        self.add_folder_button = QPushButton("Add folder…")
        self.remove_folders_button = QPushButton("Forget added folders")
        self.refresh_button = QPushButton("Refresh")
        top = QHBoxLayout()
        top.addWidget(self.filter, 1)
        top.addWidget(QLabel("Group by"))
        top.addWidget(self.group_by)
        top.addWidget(self.add_folder_button)
        top.addWidget(self.remove_folders_button)
        top.addWidget(self.refresh_button)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Model", "Format", "Parameters", "Scale", "Inputs → outputs"])
        self.tree.setUniformRowHeights(True)
        self.details = QTextBrowser()
        self.details.setOpenLinks(False)
        splitter = QSplitter()
        splitter.addWidget(self.tree)
        splitter.addWidget(self.details)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        self.status = QLabel()
        self.status.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(splitter, 1)
        layout.addWidget(self.status)

        self.filter.textChanged.connect(self._populate)
        self.group_by.currentIndexChanged.connect(self._populate)
        self.add_folder_button.clicked.connect(self.add_folder)
        self.remove_folders_button.clicked.connect(self.forget_folders)
        self.refresh_button.clicked.connect(self.refresh)
        self.tree.currentItemChanged.connect(self._show_current)
        self.refresh()

    # --- folders ---------------------------------------------------------------------------
    def _stored_folders(self) -> List[str]:
        value = self._settings.value(FOLDERS_KEY, [])
        if isinstance(value, str):
            return [value] if value else []
        return [str(v) for v in value or []]

    def _ask_folder(self) -> Optional[Path]:
        chosen = QFileDialog.getExistingDirectory(self, "Add a model folder", str(self.repo_root))
        return Path(chosen) if chosen else None

    def add_folder(self) -> None:
        folder = self._pick_folder()
        if folder is None or folder in self.extra_folders:
            return
        self.extra_folders.append(Path(folder))
        self._settings.setValue(FOLDERS_KEY, [str(p) for p in self.extra_folders])
        self.refresh()

    def forget_folders(self) -> None:
        self.extra_folders = []
        self._settings.setValue(FOLDERS_KEY, [])
        self.refresh()

    # --- data ------------------------------------------------------------------------------
    def set_run_manifest(self, manifest) -> None:
        """The loaded run's ``model_artifacts`` (or None): marks the models it used."""
        self._manifest = manifest
        attach_run(self.scan.entries, manifest)
        self._populate()

    def refresh(self) -> None:
        app = QApplication.instance()
        if app is not None:
            QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.scan = scan_models(self.repo_root, self.store, self.extra_folders)
        finally:
            if app is not None:
                QApplication.restoreOverrideCursor()
        attach_run(self.scan.entries, self._manifest)
        self._populate()

    def entries(self) -> List[ModelEntry]:
        return list(self.scan.entries)

    # --- view ------------------------------------------------------------------------------
    def _populate(self) -> None:
        current = self.tree.currentItem()
        keep = current.data(0, ENTRY_ROLE) if current is not None else None
        self.tree.clear()
        key = self.group_by.currentData() or "origin"
        shown = [e for e in self.scan.entries if matches_filter(e, self.filter.text())]
        select = None
        for label, members in group_entries(shown, key, self.repo_root):
            group = QTreeWidgetItem([f"{label}  ({len(members)})"])
            group.setFirstColumnSpanned(True)
            self.tree.addTopLevelItem(group)
            for entry in members:
                name = entry.name + ("  ● used by loaded run" if entry.run_context is not None else "")
                io = f"{len(entry.inputs)} → {len(entry.outputs)}"
                item = QTreeWidgetItem([name, entry.format, parameters_text(entry),
                                        ", ".join(entry.bands) or "–", io])
                item.setToolTip(0, str(entry.path))
                item.setToolTip(4, ", ".join(entry.inputs) + "  →  " + ", ".join(entry.outputs))
                item.setData(0, ENTRY_ROLE, str(entry.path))
                item.setTextAlignment(2, Qt.AlignRight | Qt.AlignVCenter)
                group.addChild(item)
                if keep is not None and str(entry.path) == keep:
                    select = item
            group.setExpanded(True)
        for column in range(1, 5):
            self.tree.resizeColumnToContents(column)
        self.tree.setColumnWidth(0, max(self.tree.columnWidth(0), 320))
        used = sum(1 for e in self.scan.entries if e.run_context is not None)
        parts = [f"{len(shown)} of {len(self.scan.entries)} models",
                 f"{self.scan.outcomes} trech arch outcome record(s)",
                 "searched: " + ", ".join(self._short(r) for r in self.scan.roots)]
        if self._manifest is not None:
            parts.append(f"{used} used by the loaded run")
        if self.scan.skipped:
            parts.append(f"{len(self.scan.skipped)} unreadable file(s) skipped")
        if self.scan.truncated:
            parts.append("file limit reached: narrow the added folders")
        self.status.setText(" · ".join(parts))
        if select is not None:
            self.tree.setCurrentItem(select)
        else:
            self.details.setHtml("<p><i>Select a model to see its architecture and context.</i></p>")

    def _short(self, root: Path) -> str:
        try:
            return str(root.relative_to(self.repo_root))
        except ValueError:
            return str(root)

    def entry_for(self, path: str) -> Optional[ModelEntry]:
        for entry in self.scan.entries:
            if str(entry.path) == path:
                return entry
        return None

    def select(self, path: Path) -> bool:
        for i in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(i)
            for j in range(group.childCount()):
                if group.child(j).data(0, ENTRY_ROLE) == str(path):
                    self.tree.setCurrentItem(group.child(j))
                    return True
        return False

    def _show_current(self, current: Optional[QTreeWidgetItem], _previous=None) -> None:
        path = current.data(0, ENTRY_ROLE) if current is not None else None
        entry = self.entry_for(path) if path else None
        if entry is None:
            self.details.setHtml("<p><i>Select a model to see its architecture and context.</i></p>")
            return
        self.details.setHtml(entry_html(entry, self.repo_root))
