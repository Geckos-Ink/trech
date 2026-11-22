"""Engine trace: the bottom panel that shows the engine's verbose log live, at the level asked.

The panel does two jobs:

* **Request.** Its *Level* and *Categories* fields decide the ``--trace`` arguments Studio adds to
  the next ``trech run`` or live lab (see ``docs/engine/engine_trace.md``). *Off* adds nothing,
  but a run started with ``TRECH_TRACE`` in Studio's environment is still shown.
* **Show.** While the run writes ``trech_trace.jsonl``, the panel tails the file
  (:class:`~trech_studio.engine.trace_feed.TraceTail`) and appends each record as it arrives.
  Lowering the level or narrowing the categories filters what is shown at once. Raising them
  applies from the next run, because a running engine cannot record more than it was asked for.
  The run attribution summary, which says how much of the run the engine answered, appears in
  the banner when the run ends.

Studio stays a viewer: the panel never changes what the engine computes, and the trace itself
is observation-only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSettings, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QPlainTextEdit, QPushButton, QSplitter, QTableView, QVBoxLayout,
                               QWidget)

from ..engine.trace_feed import (LEVELS, TRACE_FILE, TraceFilter, TraceTail, compact, parse_categories,
                                 trace_args, where)

MAX_RECORDS = 50000
COLUMNS = ("#", "Level", "Category", "Where", "Message", "Data")
_COLORS = {"warn": "#e0b45a", "error": "#e07a7a", "summary": "#7fd18b", "debug": "#9aa4b2", "trace": "#7d8796"}


class TraceRecordModel(QAbstractTableModel):
    """All received records, and the filtered rows the table shows."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._all: List[Dict[str, Any]] = []
        self._rows: List[Dict[str, Any]] = []
        self.filter = TraceFilter()

    # --- data -------------------------------------------------------------------------

    def clear(self) -> None:
        self.beginResetModel()
        self._all, self._rows = [], []
        self.endResetModel()

    def append(self, records: List[Dict[str, Any]]) -> int:
        """Store records; returns how many became visible."""
        if not records:
            return 0
        self._all.extend(records)
        if len(self._all) > MAX_RECORDS:
            self._all = self._all[-MAX_RECORDS:]
            self.refilter()
            return len(records)
        shown = [r for r in records if self.filter.accepts(r)]
        if shown:
            first = len(self._rows)
            self.beginInsertRows(QModelIndex(), first, first + len(shown) - 1)
            self._rows.extend(shown)
            self.endInsertRows()
        return len(shown)

    def refilter(self) -> None:
        self.beginResetModel()
        self._rows = [r for r in self._all if self.filter.accepts(r)]
        self.endResetModel()

    def record(self, row: int) -> Optional[Dict[str, Any]]:
        return self._rows[row] if 0 <= row < len(self._rows) else None

    def total(self) -> int:
        return len(self._all)

    # --- Qt model ---------------------------------------------------------------------

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(COLUMNS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole) -> Any:  # noqa: N802
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return COLUMNS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        record = self.record(index.row())
        if record is None:
            return None
        if role == Qt.DisplayRole:
            column = index.column()
            if column == 0:
                return str(record.get("seq", ""))
            if column == 1:
                severity = record.get("severity")
                return f"{record.get('level', '')} {severity}" if severity else str(record.get("level", ""))
            if column == 2:
                return str(record.get("cat", ""))
            if column == 3:
                return where(record)
            if column == 4:
                return str(record.get("msg", ""))
            return compact(record.get("data"))
        if role == Qt.ForegroundRole:
            key = record.get("severity") or ("summary" if record.get("cat") == "summary" else record.get("level"))
            color = _COLORS.get(str(key))
            return QBrush(QColor(color)) if color else None
        if role == Qt.ToolTipRole and index.column() == 5:
            return compact(record.get("data"), 2000)
        return None


class TraceLogPanel(QWidget):
    """Live engine-trace viewer with the level/category request for the next run."""

    level_changed = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None, settings: Optional[QSettings] = None,
                 poll_ms: int = 250) -> None:
        super().__init__(parent)
        self._settings = settings if settings is not None else QSettings("TRECH", "Studio")
        self._tail: Optional[TraceTail] = None
        self._summary: Optional[Dict[str, Any]] = None
        self._run_level = "off"

        self.level = QComboBox(self)
        self.level.addItems(list(LEVELS))
        self.level.setToolTip("Level requested from the engine for the next run, and the most detailed level shown.")
        saved = str(self._settings.value("trace/level", "info"))
        self.level.setCurrentText(saved if saved in LEVELS else "info")
        self.categories = QLineEdit(self)
        self.categories.setPlaceholderText("all categories (e.g. hook,predict,evolve,scenario,console)")
        self.categories.setText(str(self._settings.value("trace/categories", "")))
        self.search = QLineEdit(self)
        self.search.setPlaceholderText("Filter shown records")
        self.follow = QCheckBox("Follow", self)
        self.follow.setChecked(True)
        self.clear_button = QPushButton("Clear", self)
        self.banner = QLabel("No trace yet. Choose a level and run a scenario.", self)
        self.banner.setWordWrap(True)
        self.banner.setTextInteractionFlags(Qt.TextSelectableByMouse)

        self.model = TraceRecordModel(self)
        self.table = QTableView(self)
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(18)
        self.table.setWordWrap(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setStretchLastSection(True)
        for column, width in enumerate((48, 80, 96, 110, 260)):
            self.table.setColumnWidth(column, width)
        font = QFont("Menlo, Consolas, monospace")
        font.setStyleHint(QFont.Monospace)
        font.setPointSize(11)
        self.table.setFont(font)
        self.details = QPlainTextEdit(self)
        self.details.setReadOnly(True)
        self.details.setFont(font)
        self.details.setPlaceholderText("Select a record to see it in full.")

        bar = QHBoxLayout()
        bar.addWidget(QLabel("Level", self))
        bar.addWidget(self.level)
        bar.addWidget(QLabel("Categories", self))
        bar.addWidget(self.categories, 2)
        bar.addWidget(self.search, 2)
        bar.addWidget(self.follow)
        bar.addWidget(self.clear_button)
        split = QSplitter(Qt.Horizontal, self)
        split.addWidget(self.table)
        split.addWidget(self.details)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(bar)
        layout.addWidget(self.banner)
        layout.addWidget(split, 1)

        self._timer = QTimer(self)
        self._timer.setInterval(poll_ms)
        self._timer.timeout.connect(self.poll)
        self.level.currentTextChanged.connect(self._on_level)
        self.categories.editingFinished.connect(self._on_categories)
        self.search.textChanged.connect(self._on_search)
        self.clear_button.clicked.connect(self.clear)
        self.table.selectionModel().currentRowChanged.connect(self._on_row)
        self._apply_filter()

    # --- request ----------------------------------------------------------------------

    def requested_level(self) -> str:
        return self.level.currentText()

    def requested_categories(self) -> List[str]:
        return parse_categories(self.categories.text())

    def trace_path(self, output_dir: Path) -> Path:
        return Path(output_dir) / TRACE_FILE

    def command_args(self, output_dir: Path) -> List[str]:
        """``--trace`` arguments for a run writing into ``output_dir`` (none when Off)."""
        return trace_args(self.requested_level(), self.requested_categories(), self.trace_path(output_dir))

    # --- live feed --------------------------------------------------------------------

    def begin(self, output_dir: Path, label: str = "run") -> None:
        """Start following ``<output_dir>/trech_trace.jsonl`` for a run that is starting."""
        self.clear()
        path = self.trace_path(output_dir)
        self._tail = TraceTail(path)
        self._run_level = self.requested_level()
        if self._run_level == "off":
            self.banner.setText(f"{label}: trace off (choose a level to record one). Showing {path.name} "
                                "if the run writes one through TRECH_TRACE.")
        else:
            cats = self.requested_categories()
            self.banner.setText(f"{label}: tracing at {self._run_level}"
                                + (f" for {', '.join(cats)}" if cats else "") + f" → {path}")
        self._timer.start()

    def finish(self) -> None:
        """The run ended: read what is left and stop following."""
        self.poll()
        self._timer.stop()
        if self._summary is None and self._tail is not None:
            if self.model.total() == 0:
                self.banner.setText(self.banner.text() + "  (run ended; no trace records)")
            else:
                self.banner.setText(self.banner.text() + "  (run ended)")

    def is_following(self) -> bool:
        return self._timer.isActive()

    def poll(self) -> int:
        if self._tail is None:
            return 0
        if self._tail.resets:
            self._tail.resets = 0
            self.model.clear()
        records = self._tail.poll()
        for record in records:
            if record.get("cat") == "summary":
                self._show_summary(record.get("data") or {})
        shown = self.model.append(records)
        if shown and self.follow.isChecked():
            self.table.scrollToBottom()
        return len(records)

    def load_file(self, path: Path) -> int:
        """Show a finished run's trace (for example an opened output directory)."""
        self.clear()
        self._tail = TraceTail(Path(path))
        count = self.poll()
        self._timer.stop()
        if self._summary is None:
            self.banner.setText(f"{Path(path)}: {count} records")
        return count

    def clear(self) -> None:
        self.model.clear()
        self.details.clear()
        self._summary = None

    def record_count(self) -> int:
        return self.model.rowCount()

    def summary(self) -> Optional[Dict[str, Any]]:
        return self._summary

    # --- internals --------------------------------------------------------------------

    def _show_summary(self, data: Dict[str, Any]) -> None:
        self._summary = data
        verdict = str(data.get("verdict", "run summary received"))
        missing = data.get("models_missing") or []
        extra = f"  Missing models: {', '.join(map(str, missing))}." if missing else ""
        self.banner.setText(f"Run attribution: {verdict}{extra}")

    def _apply_filter(self) -> None:
        self.model.filter = TraceFilter(level=self.requested_level() if self.requested_level() != "off" else "trace",
                                        categories=self.requested_categories(), search=self.search.text().strip())
        self.model.refilter()

    def _on_level(self, level: str) -> None:
        self._settings.setValue("trace/level", level)
        self._apply_filter()
        self.level_changed.emit(level)

    def _on_categories(self) -> None:
        self._settings.setValue("trace/categories", self.categories.text())
        self._apply_filter()

    def _on_search(self, _text: str) -> None:
        self._apply_filter()

    def _on_row(self, current: QModelIndex, _previous: QModelIndex) -> None:
        record = self.model.record(current.row())
        self.details.setPlainText(json.dumps(record, indent=2, ensure_ascii=False) if record else "")
