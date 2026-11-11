"""Models dock: edit JS model definitions / structure searches live, manage checkpoints.

Left: the ``ml/`` definition files in a JS editor. Every edit is re-inspected (debounced) by the
``trech-ml`` CLI from the unsaved draft, so structure IDs, parameter counts, search candidates and
errors (with line numbers) update while typing; files changed on disk reload when the draft is
clean. Right: the checkpoint store — versions, typed roles, structure IDs, recorded uses / last
use, sizes, pin / activate, delete and the disk-space prune policy. Glue only: parsing lives in
``trech_studio.models`` and every store change goes through ``engine.models`` (the CLI).
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, List, Optional

from PySide6.QtCore import QFileSystemWatcher, Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QInputDialog,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QSplitter,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ..engine import models as bridge
from ..models import (
    Checkpoint, Inspection, PrunePlan, Registry, SORT_KEYS, definition_kind, discover_definition_files, human_bytes,
    new_definition_source, parse_inspection, parse_prune, relative_time,
)
from .code_editor import _JsEditor, _JsHighlighter

INSPECT_DELAY_MS = 400
CHECKPOINT_COLUMNS = ("checkpoint", "role", "structure", "structure id", "uses", "last used", "size", "state", "accuracy")


def _ask(parent, title: str, text: str) -> bool:
    return QMessageBox.question(parent, title, text, QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes


class PruneDialog(QDialog):
    """Policy form → dry-run preview → explicit delete. Nothing is deleted before the preview."""

    def __init__(self, preview: Callable[[List[str]], PrunePlan], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Free disk space — prune checkpoints")
        self._preview = preview
        self.plan: Optional[PrunePlan] = None
        form = QFormLayout()
        self.keep_last = QSpinBox(); self.keep_last.setRange(0, 1000); self.keep_last.setValue(3)
        self.keep_last.setToolTip("Always keep the newest N final/best versions of every model.")
        self.use_idle = QCheckBox("only if unused for"); self.idle_days = QSpinBox(); self.idle_days.setRange(0, 3650); self.idle_days.setValue(30)
        idle = QHBoxLayout(); idle.addWidget(self.use_idle); idle.addWidget(self.idle_days); idle.addWidget(QLabel("days"))
        self.roles = {role: QCheckBox(role) for role in ("candidate", "intermediate", "final", "best")}
        for role in ("candidate", "intermediate"):
            self.roles[role].setChecked(True)
        roles = QHBoxLayout()
        for box in self.roles.values():
            roles.addWidget(box)
        self.max_size = QLineEdit(); self.max_size.setPlaceholderText("e.g. 500M or 2G (empty = no size target)")
        self.model = QLineEdit(); self.model.setPlaceholderText("all models")
        form.addRow("Keep newest", self.keep_last)
        form.addRow("Idle", idle)
        form.addRow("Roles", roles)
        form.addRow("Shrink store to", self.max_size)
        form.addRow("Model", self.model)
        self.result = QPlainTextEdit(); self.result.setReadOnly(True)
        self.result.setPlaceholderText("Pinned and active checkpoints are never pruned. Preview first.")
        buttons = QDialogButtonBox()
        self.preview_button = buttons.addButton("Preview", QDialogButtonBox.ActionRole)
        self.delete_button = buttons.addButton("Delete", QDialogButtonBox.DestructiveRole)
        self.delete_button.setEnabled(False)
        buttons.addButton(QDialogButtonBox.Cancel)
        buttons.rejected.connect(self.reject)
        self.preview_button.clicked.connect(self.run_preview)
        self.delete_button.clicked.connect(self.accept)
        for widget in (self.keep_last, self.idle_days):
            widget.valueChanged.connect(self._invalidate)
        for widget in (self.max_size, self.model):
            widget.textChanged.connect(self._invalidate)
        for box in list(self.roles.values()) + [self.use_idle]:
            box.toggled.connect(self._invalidate)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.result, 1)
        layout.addWidget(buttons)
        self.resize(560, 420)

    def arguments(self) -> List[str]:
        args = ["--keep-last", str(self.keep_last.value())]
        if self.use_idle.isChecked():
            args += ["--unused-days", str(self.idle_days.value())]
        roles = [r for r, box in self.roles.items() if box.isChecked()]
        if roles and len(roles) < len(self.roles):
            args += ["--roles", ",".join(roles)]
        if self.max_size.text().strip():
            args += ["--max-bytes", self.max_size.text().strip()]
        if self.model.text().strip():
            args += ["--name", self.model.text().strip()]
        return args

    def _invalidate(self, *_):
        self.plan = None
        self.delete_button.setEnabled(False)

    def run_preview(self) -> None:
        try:
            self.plan = self._preview(self.arguments())
        except (bridge.CliError, ValueError) as error:
            self.plan = None
            self.result.setPlainText(str(error))
            self.delete_button.setEnabled(False)
            return
        lines = [self.plan.describe(), ""]
        lines += [f"delete {d['id']}  ({d.get('role')}, {d.get('use_count', 0)} uses, idle {d.get('idle_days')} d, "
                  f"{human_bytes(d.get('size_bytes'))})" for d in self.plan.delete]
        kept = [k for k in self.plan.keep if k.get("reason") != "other model"]
        lines += [f"keep   {k['id']}  ({k['reason']})" for k in kept]
        self.result.setPlainText("\n".join(lines))
        self.delete_button.setText(f"Delete {len(self.plan.delete)} checkpoint(s)")
        self.delete_button.setEnabled(bool(self.plan.delete))


class ModelsPanel(QWidget):
    """The Models dock. ``confirm(title, text) -> bool`` is injectable for headless tests."""

    status_message = Signal(str)

    def __init__(self, repo_root: Path, store: Optional[Path] = None, parent: Optional[QWidget] = None,
                 confirm: Optional[Callable[[str, str], bool]] = None, ml_root: Optional[Path] = None) -> None:
        super().__init__(parent)
        self.repo_root = Path(repo_root).resolve()
        self.ml_root = Path(ml_root).resolve() if ml_root else self.repo_root / "ml"
        self.store = Path(store) if store else bridge.default_store(self.repo_root)
        self.confirm = confirm or (lambda title, text: _ask(self, title, text))
        self.registry = Registry(store=self.store)
        self.inspection: Optional[Inspection] = None
        self._path: Optional[Path] = None
        self._saved_text = ""
        self._inspected_at = 0.0
        self._loading = False

        self.job = bridge.ModelJob(self.repo_root, self)
        self.inspector = bridge.DraftInspector(self.repo_root, self)
        self.inspector.inspected.connect(self._on_inspected)
        self.inspector.failed.connect(self._on_inspect_failed)
        self.job.message.connect(self._append)
        self.job.finished.connect(self._job_finished)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(INSPECT_DELAY_MS)
        self._timer.timeout.connect(self._inspect_draft)
        self.watcher = QFileSystemWatcher(self)
        self.watcher.fileChanged.connect(self._on_file_changed)
        self.watcher.directoryChanged.connect(self._on_directory_changed)

        # --- definitions (left) ------------------------------------------------------------
        self.files = QListWidget()
        self.files.currentItemChanged.connect(self._select_file)
        new_model = QPushButton("New model…"); new_model.clicked.connect(lambda: self.create_definition("model"))
        new_search = QPushButton("New search…"); new_search.clicked.connect(lambda: self.create_definition("search"))
        file_bar = QHBoxLayout(); file_bar.addWidget(QLabel("Definitions (ml/)")); file_bar.addStretch(1)
        file_bar.addWidget(new_model); file_bar.addWidget(new_search)
        self.editor = _JsEditor()
        self.editor.setFont(QFont("Menlo", 11))
        self.editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._highlighter = _JsHighlighter(self.editor.document())
        self.editor.textChanged.connect(self._on_text_changed)
        self.save_button = QPushButton("Save"); self.save_button.clicked.connect(self.save)
        self.revert_button = QPushButton("Revert"); self.revert_button.clicked.connect(self.revert)
        self.run_button = QPushButton("Train ▶"); self.run_button.clicked.connect(lambda: self.start_job(dry_run=False))
        self.dry_button = QPushButton("Dry run"); self.dry_button.clicked.connect(lambda: self.start_job(dry_run=True))
        self.stop_button = QPushButton("Stop"); self.stop_button.clicked.connect(self.job.stop)
        edit_bar = QHBoxLayout()
        for button in (self.save_button, self.revert_button):
            edit_bar.addWidget(button)
        edit_bar.addStretch(1)
        for button in (self.dry_button, self.run_button, self.stop_button):
            edit_bar.addWidget(button)
        self.validation = QLabel("Select or create a definition file.")
        self.validation.setWordWrap(True)
        self.outline = QTreeWidget()
        self.outline.setHeaderLabels(["declaration", "structure", "structure id", "params"])
        self.outline.setRootIsDecorated(True)
        left = QWidget(); left_layout = QVBoxLayout(left); left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addLayout(file_bar)
        left_split = QSplitter(Qt.Vertical)
        left_split.addWidget(self.files)
        left_split.addWidget(self.editor)
        left_split.addWidget(self.outline)
        left_split.setSizes([90, 320, 140])
        left_layout.addWidget(left_split, 1)
        left_layout.addWidget(self.validation)
        left_layout.addLayout(edit_bar)

        # --- checkpoints (right) -----------------------------------------------------------
        self.store_label = QLabel()
        self.store_label.setWordWrap(True)
        self.sort = QComboBox()
        self.sort.addItems(["most used", "recently used", "name", "size"])
        self.sort.currentIndexChanged.connect(lambda _i: self.show_registry(self.registry))
        refresh = QPushButton("Refresh"); refresh.clicked.connect(self.refresh_registry)
        store_bar = QHBoxLayout(); store_bar.addWidget(self.store_label, 1); store_bar.addWidget(QLabel("Sort")); store_bar.addWidget(self.sort)
        store_bar.addWidget(refresh)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(list(CHECKPOINT_COLUMNS))
        self.tree.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tree.currentItemChanged.connect(self._show_details)
        self.pin_button = QPushButton("Pin"); self.pin_button.clicked.connect(self.toggle_pin)
        self.activate_button = QPushButton("Activate"); self.activate_button.clicked.connect(self.activate_selected)
        self.delete_button = QPushButton("Delete…"); self.delete_button.clicked.connect(self.delete_selected)
        self.prune_button = QPushButton("Free space…"); self.prune_button.clicked.connect(self.open_prune)
        self.verify_button = QPushButton("Verify"); self.verify_button.clicked.connect(self.verify)
        self.open_def_button = QPushButton("Open definition"); self.open_def_button.clicked.connect(self.open_selected_definition)
        actions = QHBoxLayout()
        for button in (self.pin_button, self.activate_button, self.delete_button, self.prune_button, self.verify_button, self.open_def_button):
            actions.addWidget(button)
        actions.addStretch(1)
        self.details = QPlainTextEdit(); self.details.setReadOnly(True)
        self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.log.setMaximumBlockCount(2000)
        self.log.setPlaceholderText("Training / search progress and store operations.")
        right = QWidget(); right_layout = QVBoxLayout(right); right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addLayout(store_bar)
        right_split = QSplitter(Qt.Vertical)
        right_split.addWidget(self.tree)
        right_split.addWidget(self.details)
        right_split.addWidget(self.log)
        right_split.setSizes([300, 120, 120])
        right_layout.addWidget(right_split, 1)
        right_layout.addLayout(actions)

        split = QSplitter(Qt.Horizontal)
        split.addWidget(left)
        split.addWidget(right)
        split.setSizes([480, 560])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addWidget(split)
        self._update_buttons()
        self.reload_files()
        self.refresh_registry()

    # ---- definition files -------------------------------------------------------------------

    def reload_files(self) -> None:
        current = self._path
        self.files.blockSignals(True)
        self.files.clear()
        for path in discover_definition_files(self.ml_root):
            item = QListWidgetItem(path.relative_to(self.ml_root).as_posix())
            item.setData(Qt.UserRole, str(path))
            item.setToolTip(f"{definition_kind(path)} definition — {path}")
            self.files.addItem(item)
            if current and path == current:
                self.files.setCurrentItem(item)
        self.files.blockSignals(False)
        if self.ml_root.is_dir() and str(self.ml_root) not in self.watcher.directories():
            self.watcher.addPath(str(self.ml_root))
            for sub in self.ml_root.iterdir():
                if sub.is_dir():
                    self.watcher.addPath(str(sub))

    def is_dirty(self) -> bool:
        return self._path is not None and self.editor.toPlainText() != self._saved_text

    def _select_file(self, item, previous) -> None:
        if item is None:
            return
        path = Path(item.data(Qt.UserRole))
        if path == self._path:
            return
        if self.is_dirty() and not self.confirm("Unsaved definition", f"Discard unsaved changes to {self._path.name}?"):
            self.files.blockSignals(True)
            self.files.setCurrentItem(previous)
            self.files.blockSignals(False)
            return
        self.load_definition(path)

    def load_definition(self, path: Path) -> None:
        path = Path(path).resolve()
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        if self._path is not None and str(self._path) in self.watcher.files():
            self.watcher.removePath(str(self._path))
        self._path = path
        self._saved_text = text
        self._loading = True
        self.editor.setPlainText(text)
        self._loading = False
        if path.exists():
            self.watcher.addPath(str(path))
        for i in range(self.files.count()):
            if Path(self.files.item(i).data(Qt.UserRole)) == path:
                self.files.blockSignals(True)
                self.files.setCurrentRow(i)
                self.files.blockSignals(False)
        self.run_button.setText("Search ▶" if definition_kind(path) == "search" else "Train ▶")
        self._update_buttons()
        self._schedule_inspect(immediate=True)

    def create_definition(self, kind: str, name: Optional[str] = None) -> Optional[Path]:
        if name is None:
            name, ok = QInputDialog.getText(self, f"New {kind} definition", "Model name (letters, digits, _ . -):")
            if not ok or not name.strip():
                return None
        name = name.strip()
        folder = self.ml_root / ("searches" if kind == "search" else "definitions")
        path = folder / f"{name}.{kind}.js"
        if path.exists():
            self.validation.setText(f"{path.relative_to(self.repo_root)} already exists.")
            return None
        folder.mkdir(parents=True, exist_ok=True)
        path.write_text(new_definition_source(kind, name), encoding="utf-8")
        self.reload_files()
        self.load_definition(path)
        return path

    def save(self) -> Optional[Path]:
        if self._path is None:
            return None
        text = self.editor.toPlainText()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self.watcher.removePath(str(self._path))
        self._path.write_text(text, encoding="utf-8")
        self.watcher.addPath(str(self._path))
        self._saved_text = text
        self._update_buttons()
        self._log(f"saved {self._path.relative_to(self.repo_root) if self._path.is_relative_to(self.repo_root) else self._path}")
        return self._path

    def revert(self) -> None:
        if self._path is not None:
            self.load_definition(self._path)

    def _on_file_changed(self, path: str) -> None:
        if self._path is None or Path(path) != self._path:
            return
        if not self._path.exists():
            self.validation.setText(f"{self._path.name} was removed on disk; Save recreates it.")
            return
        text = self._path.read_text(encoding="utf-8")
        if text == self._saved_text:
            return
        if self.is_dirty():
            self.validation.setText(f"{self._path.name} changed on disk; your unsaved draft is kept (Revert to load the file).")
            self._saved_text = text
            self._update_buttons()
            return
        self.load_definition(self._path)
        self._log(f"reloaded {self._path.name} (changed on disk)")

    def _on_directory_changed(self, path: str) -> None:
        if Path(path) == self.store:
            self.refresh_registry()
        else:
            self.reload_files()

    # ---- live inspection ----------------------------------------------------------------------

    def _on_text_changed(self) -> None:
        if self._loading:
            return
        self._update_buttons()
        self._schedule_inspect()

    def _schedule_inspect(self, immediate: bool = False) -> None:
        if self._path is None:
            return
        self.validation.setText("checking…")
        if immediate:
            self._timer.stop()
            self._inspect_draft()
        else:
            self._timer.start()

    def _inspect_draft(self) -> None:
        if self._path is not None:
            self.inspector.request(self._path, self.editor.toPlainText())

    def inspect_now(self) -> Inspection:
        """Synchronous inspection of the current draft (Check button, tests)."""
        self.inspector.wait()
        try:
            payload = bridge.inspect_source(self.repo_root, self._path, self.editor.toPlainText())
        except bridge.CliError as error:
            payload = {"event": "error", "message": str(error)}
        self._on_inspected(payload, self.editor.toPlainText())
        return self.inspection

    def _on_inspect_failed(self, message: str) -> None:
        self.validation.setText(message)

    def _on_inspected(self, payload, source: str) -> None:
        if source != self.editor.toPlainText():
            return  # a newer draft is queued; never show stale results as current
        self.inspection = parse_inspection(payload)
        self._inspected_at = time.monotonic()
        self.show_inspection(self.inspection)

    def show_inspection(self, inspection: Inspection) -> None:
        self.outline.clear()
        for d in inspection.definitions:
            item = QTreeWidgetItem([f"model {d.get('name')}", str(d.get("structure_label")), str(d.get("structure_id")), str(d.get("parameter_count"))])
            item.setToolTip(0, f"[{', '.join(d.get('inputs', []))}] → [{', '.join(d.get('outputs', []))}]"
                               + (f" @ {d['scale']}" if d.get("scale") else ""))
            stored = [c for m in self.registry.models if m.name == d.get("name") for c in m.checkpoints]
            matching = [c for c in stored if c.structure_id == d.get("structure_id")]
            QTreeWidgetItem(item, ["checkpoints", f"{len(matching)} with this structure", f"{len(stored) - len(matching)} with other structures", ""])
            self.outline.addTopLevelItem(item)
            item.setExpanded(True)
        for s in inspection.searches:
            item = QTreeWidgetItem([f"search {s.get('name')}", f"{s.get('strategy')} · objective {s.get('objective')}", "",
                                    f"{len(s.get('candidates') or [])} candidates"])
            for c in s.get("candidates") or []:
                QTreeWidgetItem(item, ["candidate", str(c.get("structure_label")), str(c.get("structure_id")), str(c.get("parameter_count"))])
            for k in s.get("skipped") or []:
                QTreeWidgetItem(item, ["skipped", str(k.get("structure")), str(k.get("reason")), ""])
            self.outline.addTopLevelItem(item)
            item.setExpanded(True)
        if inspection.errors:
            self.validation.setText("\n".join(e.describe() for e in inspection.errors))
            self.validation.setStyleSheet("color: #e07a5f;" if not inspection.ok else "color: #e0b25a;")
        else:
            self.validation.setText("✓ " + " · ".join(inspection.summary_lines()[:2]) if inspection.summary_lines() else "✓ valid")
            self.validation.setStyleSheet("color: #7fd18b;")
        self._update_buttons()

    # ---- jobs ---------------------------------------------------------------------------------

    def start_job(self, dry_run: bool = False) -> bool:
        if self._path is None:
            return False
        if self.is_dirty():
            if not self.confirm("Save definition", f"Save {self._path.name} before running it?"):
                return False
            self.save()
        command = "search" if definition_kind(self._path) == "search" else "train"
        if dry_run:
            try:
                plan = bridge.run_cli(self.repo_root, command, str(self._path), "--dry-run", store=self.store)
            except bridge.CliError as error:
                self._log("dry run failed: " + str(error))
                return False
            self._log(self._describe_dry_run(command, plan))
            return True
        started = self.job.start(command, self._path, store=self.store)
        self._update_buttons()
        return started

    @staticmethod
    def _describe_dry_run(command: str, plan) -> str:
        if command == "train":
            return "\n".join(f"would train {p['name']} ({p['structure_id']}):\n  " + " ".join(p["command"]) for p in plan)
        lines = []
        for s in plan:
            lines.append(f"search {s['name']}: {len(s['candidates'])} candidates")
            lines += [f"  {c['structure_label']}  {c['structure_id']}  {c['parameter_count']} params" for c in s["candidates"]]
        return "\n".join(lines)

    def _job_finished(self, ok: bool, summary: str) -> None:
        self._log(("✓ " if ok else "✗ ") + summary)
        self.refresh_registry()
        self._update_buttons()

    # ---- registry -----------------------------------------------------------------------------

    def refresh_registry(self) -> None:
        self.show_registry(bridge.read_registry(self.store))
        index = self.store / "index.json"
        if index.exists() and str(index) not in self.watcher.files():
            self.watcher.addPath(str(index))
        if self.store.is_dir() and str(self.store) not in self.watcher.directories():
            self.watcher.addPath(str(self.store))

    def _sort_key(self) -> str:
        return SORT_KEYS[self.sort.currentIndex()]

    def show_registry(self, registry: Registry) -> None:
        self.registry = registry
        selected = self.selected_checkpoint()
        self.tree.clear()
        state = f"{human_bytes(registry.total_bytes)} in {len(registry.models)} model(s)"
        if registry.error:
            state = registry.error
        elif registry.is_empty:
            state = "empty — train a definition or run a search"
        self.store_label.setText(f"Store {registry.store}: {state}")
        for model in registry.sorted_models(self._sort_key()):
            top = QTreeWidgetItem([model.name, f"{len(model.checkpoints)} version(s)", f"{model.structures} structure(s)", "",
                                   str(model.use_count), relative_time(model.last_used_at), human_bytes(model.size_bytes),
                                   f"active {model.active}" if model.active else "", ""])
            top.setData(0, Qt.UserRole, ("model", model.name))
            for c in model.checkpoints:
                flags = [f for f, on in (("ACTIVE", c.active), ("PINNED", c.pinned)) if on]
                child = QTreeWidgetItem([c.id, c.role, c.structure_label, c.structure_id, str(c.use_count),
                                         relative_time(c.last_used_at), human_bytes(c.size_bytes), " ".join(flags), c.metric_summary()])
                child.setData(0, Qt.UserRole, ("checkpoint", c.id))
                child.setToolTip(8, c.holdout_note())
                top.addChild(child)
                if selected and selected.id == c.id:
                    self.tree.setCurrentItem(child)
            self.tree.addTopLevelItem(top)
            top.setExpanded(True)
        for column in range(len(CHECKPOINT_COLUMNS)):
            self.tree.resizeColumnToContents(column)
        if self.inspection is not None:
            self.show_inspection(self.inspection)
        self._update_buttons()

    def checkpoint_rows(self) -> List[List[str]]:
        """Flat (model, checkpoint...) rows as displayed — for tests and accessibility."""
        rows = []
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            rows.append([top.text(c) for c in range(len(CHECKPOINT_COLUMNS))])
            for j in range(top.childCount()):
                rows.append([top.child(j).text(c) for c in range(len(CHECKPOINT_COLUMNS))])
        return rows

    def _selected_data(self):
        item = self.tree.currentItem()
        return item.data(0, Qt.UserRole) if item is not None else None

    def selected_checkpoint(self) -> Optional[Checkpoint]:
        data = self._selected_data()
        return self.registry.checkpoint(data[1]) if data and data[0] == "checkpoint" else None

    def select(self, ref: str) -> bool:
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            if top.data(0, Qt.UserRole)[1] == ref:
                self.tree.setCurrentItem(top)
                return True
            for j in range(top.childCount()):
                if top.child(j).data(0, Qt.UserRole)[1] == ref:
                    self.tree.setCurrentItem(top.child(j))
                    return True
        return False

    def _show_details(self, *_):
        c = self.selected_checkpoint()
        if c is None:
            data = self._selected_data()
            model = next((m for m in self.registry.models if data and m.name == data[1]), None)
            self.details.setPlainText("" if model is None else
                                      f"{model.name}: {len(model.checkpoints)} checkpoint(s), latest v{model.latest_version}, "
                                      f"{model.use_count} recorded use(s), last used {relative_time(model.last_used_at)}, "
                                      f"{human_bytes(model.size_bytes)}.\nActive: {model.active or 'none (newest final/best resolves)'}")
        else:
            lines = [f"{c.id} — {c.role} · {c.structure_label} · {c.structure_id}" + (f" · {c.parameter_count} params" if c.parameter_count else ""),
                     f"IO: [{', '.join(c.inputs)}] → [{', '.join(c.outputs)}]" + (f" @ {c.scale}" if c.scale else ""),
                     "Files: " + ", ".join(str(f.get("format")) + " " + human_bytes(f.get("size_bytes")) for f in c.files),
                     f"Created {c.created_at}; {c.use_count} recorded use(s); last used {c.last_used_at or 'never'}",
                     f"Accuracy: {c.metric_summary()} on {c.holdout_note()}",
                     f"Validation: {c.validation_summary()}" + (f" (report {c.validation.get('report')})" if c.validation else ""),
                     f"Definition: {c.definition_file or 'imported (no definition file)'}"]
            if c.search:
                lines.append("Search: " + ", ".join(f"{k}={v}" for k, v in c.search.items()))
            if c.note:
                lines.append("Note: " + c.note)
            lines.append("A learned comparison model — its predictions are not Geant4 results.")
            self.details.setPlainText("\n".join(lines))
        self._update_buttons()

    def _cli(self, command: str, *args: str, ok_codes=(0,)):
        try:
            result = bridge.run_cli(self.repo_root, command, *args, store=self.store, ok_codes=ok_codes)
        except bridge.CliError as error:
            self._log(f"{command} failed: {error}")
            return None
        return result

    def toggle_pin(self) -> None:
        c = self.selected_checkpoint()
        if c is not None and self._cli("unpin" if c.pinned else "pin", c.id) is not None:
            self._log(("unpinned " if c.pinned else "pinned ") + c.id)
            self.refresh_registry()

    def activate_selected(self) -> None:
        c = self.selected_checkpoint()
        if c is None:
            return
        result = self._cli("deactivate", c.name) if c.active else self._cli("activate", c.id)
        if result is not None:
            self._log(f"{c.name}: " + ("no active checkpoint (newest final/best resolves)" if c.active else f"active = {c.id}"))
            self.refresh_registry()

    def delete_selected(self) -> bool:
        data = self._selected_data()
        if not data:
            return False
        kind, ref = data
        extra = ["--all"] if kind == "model" else []
        plan = self._cli("delete", ref, *extra, ok_codes=(0, 2))
        if plan is None:
            return False
        force = []
        if plan.get("blocked"):
            blocked = ", ".join(f"{b['id']} ({b['reason']})" for b in plan["blocked"])
            if self.confirm("Protected checkpoints", f"{blocked} are protected. Delete them too?"):
                force = ["--force"]
                plan = self._cli("delete", ref, *extra, "--force", ok_codes=(0, 2)) or plan
        if not plan.get("delete"):
            self._log(f"nothing deleted for {ref}")
            return False
        names = ", ".join(d["id"] for d in plan["delete"])
        if not self.confirm("Delete checkpoints", f"Permanently delete {names} ({human_bytes(plan.get('bytes'))})? This cannot be undone."):
            return False
        result = self._cli("delete", ref, *extra, *force, "--yes")
        if result is None:
            return False
        self._log(f"deleted {', '.join(r['id'] for r in result['removed'])} — freed {human_bytes(result['bytes_freed'])}")
        self.refresh_registry()
        return True

    def prune_preview(self, args: List[str]) -> PrunePlan:
        return parse_prune(bridge.run_cli(self.repo_root, "prune", *args, store=self.store))

    def prune(self, args: List[str]) -> Optional[PrunePlan]:
        result = self._cli("prune", *args, "--yes")
        if result is None:
            return None
        plan = parse_prune(result)
        self._log(plan.describe())
        self.refresh_registry()
        return plan

    def open_prune(self) -> None:
        dialog = PruneDialog(self.prune_preview, self)
        if dialog.exec() == QDialog.Accepted and dialog.plan and dialog.plan.delete:
            self.prune(dialog.arguments())

    def verify(self) -> None:
        result = self._cli("verify", ok_codes=(0, 1))
        if result is None:
            return
        bad = [f for f in result.get("files", []) if f.get("status") != "ok"]
        self._log("all checkpoint files intact" if not bad else
                  "PROBLEMS: " + "; ".join(f"{f['id']} {f['path']} {f['status']}" for f in bad))

    def open_selected_definition(self) -> None:
        c = self.selected_checkpoint()
        if c is None or not c.definition_file:
            return
        path = (self.repo_root / c.definition_file).resolve()
        if path.exists() and definition_kind(path):
            self.load_definition(path)

    def record_run_usage(self, output_dir: Path) -> Optional[str]:
        """After a TRECH run: count registered checkpoints the engine actually loaded (by SHA-256)."""
        if not (Path(output_dir) / "trech_provenance.jsonl").exists() or not (self.store / "index.json").exists():
            return None
        try:
            results = bridge.run_cli(self.repo_root, "touch", "--run", str(output_dir), store=self.store)
        except bridge.CliError as error:
            return f"model usage not recorded: {error}"
        touched = [t for r in results for t in r.get("touched", [])]
        if touched:
            self.refresh_registry()
            return "model checkpoints used: " + ", ".join(touched)
        return None

    # ---- misc -----------------------------------------------------------------------------------

    def _update_buttons(self) -> None:
        has_file = self._path is not None
        running = self.job.is_running()
        valid = self.inspection is not None and self.inspection.ok and (self.inspection.definitions or self.inspection.searches)
        self.save_button.setEnabled(has_file and self.is_dirty())
        self.revert_button.setEnabled(has_file and self.is_dirty())
        self.run_button.setEnabled(has_file and bool(valid) and not running)
        self.dry_button.setEnabled(has_file and bool(valid) and not running)
        self.stop_button.setEnabled(running)
        c = self.selected_checkpoint()
        self.pin_button.setEnabled(c is not None)
        self.pin_button.setText("Unpin" if c is not None and c.pinned else "Pin")
        self.activate_button.setEnabled(c is not None and c.role in ("final", "best"))
        self.activate_button.setText("Deactivate" if c is not None and c.active else "Activate")
        self.delete_button.setEnabled(self._selected_data() is not None)
        self.open_def_button.setEnabled(c is not None and bool(c.definition_file))
        self.prune_button.setEnabled(not self.registry.is_empty)

    def _append(self, text: str) -> None:
        self.log.appendPlainText(text)

    def _log(self, text: str) -> None:
        self.log.appendPlainText(text)
        self.status_message.emit(text)

    def shutdown(self) -> None:
        self.job.stop()
        self.inspector.stop()
