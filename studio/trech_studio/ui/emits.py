"""Emit inspector: browse ``trech_hook_emits.jsonl`` by tag and jump a frame onto the timeline.

Scenario emits are the engine's sideband — hook-layer data ("physics for comparison"), not Geant4
tallies — so this panel shows them as recorded and says what they are. It does three things:

* filter the run's emits by tag (with per-tag counts) and by a free-text match;
* pretty-print one emit's payload, truncating long arrays with an explicit, labelled note (a
  display choice — the file is untouched);
* jump an emit that the timeline is actually playing onto the timeline cursor, so a
  ``material_frame``/``fluid_frame`` record and the frame on screen are the same record.

Glue only: no parsing (``engine.outputs`` did that), no physics, no re-derivation.
"""

from __future__ import annotations

import json
from typing import Any, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..engine.outputs import HookEmit, RunResult
from ..render.playback import Playback

_ALL_TAGS = "all tags"
_MAX_ITEMS = 24          # array entries shown before the labelled truncation note
_MAX_CHARS = 20000       # hard cap on the rendered payload text


class EmitInspector(QWidget):
    """Tag-filtered list of hook emits + payload view + timeline jump."""

    cursor_requested = Signal(float)   # playback-native cursor for the selected emit's frame

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._emits: List[HookEmit] = []
        self._visible: List[HookEmit] = []
        self._playback: Optional[Playback] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        controls = QHBoxLayout()
        controls.setSpacing(6)
        self._tag_combo = QComboBox(self)
        self._tag_combo.setMinimumWidth(180)
        self._tag_combo.currentIndexChanged.connect(lambda _idx: self._refresh_list())
        controls.addWidget(self._tag_combo, 1)

        self._search = QLineEdit(self)
        self._search.setPlaceholderText("filter payload text…")
        self._search.textChanged.connect(lambda _t: self._refresh_list())
        controls.addWidget(self._search, 1)

        self._jump_button = QPushButton("Show on timeline", self)
        self._jump_button.setEnabled(False)
        self._jump_button.clicked.connect(self._jump_to_selected)
        controls.addWidget(self._jump_button)
        layout.addLayout(controls)

        splitter = QSplitter(Qt.Vertical, self)
        self._list = QListWidget(splitter)
        self._list.currentRowChanged.connect(self._on_selected)
        splitter.addWidget(self._list)

        self._payload = QPlainTextEdit(splitter)
        self._payload.setReadOnly(True)
        font = QFont("Menlo, Consolas, monospace")
        font.setStyleHint(QFont.Monospace)
        font.setPointSize(11)
        self._payload.setFont(font)
        splitter.addWidget(self._payload)
        splitter.setSizes([220, 320])
        layout.addWidget(splitter, 1)

        self._status = QLabel("No run loaded yet.", self)
        self._status.setWordWrap(True)
        self._status.setProperty("role", "warn")
        layout.addWidget(self._status)

        self.set_run(None)

    # --- public API ---------------------------------------------------------------------

    def set_run(self, result: Optional[RunResult]) -> None:
        """Bind a parsed run (or ``None`` to clear)."""
        self._emits = list(result.emits) if result is not None else []
        counts: dict[str, int] = {}
        for emit in self._emits:
            counts[emit.tag] = counts.get(emit.tag, 0) + 1

        self._tag_combo.blockSignals(True)
        self._tag_combo.clear()
        self._tag_combo.addItem(f"{_ALL_TAGS} ({len(self._emits)})", None)
        for tag in sorted(counts):
            self._tag_combo.addItem(f"{tag} ({counts[tag]})", tag)
        self._tag_combo.blockSignals(False)
        self._refresh_list()

    def set_playback(self, playback: Optional[Playback]) -> None:
        """Tell the panel which tag the timeline is playing, so jumps are honest."""
        self._playback = playback
        self._on_selected(self._list.currentRow())

    def visible_emits(self) -> List[HookEmit]:
        """The emits currently listed (headless tests assert on this)."""
        return list(self._visible)

    def selected_emit(self) -> Optional[HookEmit]:
        row = self._list.currentRow()
        if 0 <= row < len(self._visible):
            return self._visible[row]
        return None

    def select_row(self, row: int) -> None:
        self._list.setCurrentRow(row)

    # --- filtering ----------------------------------------------------------------------

    def _selected_tag(self) -> Optional[str]:
        return self._tag_combo.currentData()

    def _refresh_list(self) -> None:
        tag = self._selected_tag()
        needle = self._search.text().strip().lower()
        self._visible = []
        for emit in self._emits:
            if tag is not None and emit.tag != tag:
                continue
            if needle and needle not in _payload_text(emit.payload).lower() and needle not in emit.tag.lower():
                continue
            self._visible.append(emit)

        self._list.blockSignals(True)
        self._list.clear()
        for emit in self._visible:
            self._list.addItem(QListWidgetItem(_label_for(emit)))
        self._list.blockSignals(False)

        if not self._emits:
            self._status.setText("This run recorded no hook emits.")
            self._payload.setPlainText("")
        elif not self._visible:
            self._status.setText("No emit matches the current filter.")
            self._payload.setPlainText("")
        else:
            self._list.setCurrentRow(0)
            self._status.setText(
                f"{len(self._visible)} of {len(self._emits)} emits · scenario sideband "
                "(hook-layer data, not a Geant4 tally)"
            )

    # --- selection ----------------------------------------------------------------------

    def _on_selected(self, row: int) -> None:
        if not (0 <= row < len(self._visible)):
            self._jump_button.setEnabled(False)
            return
        emit = self._visible[row]
        self._payload.setPlainText(_render_payload(emit.payload))
        target = self._timeline_time(emit)
        self._jump_button.setEnabled(target is not None)
        self._jump_button.setToolTip(
            "Move the timeline cursor to this emitted frame"
            if target is not None
            else "The timeline is not playing this tag, so there is no frame to jump to"
        )

    def _timeline_time(self, emit: HookEmit) -> Optional[float]:
        """Playback cursor for ``emit``, or ``None`` when the timeline isn't playing its tag.

        The frames the timeline plays were built from the emits of one tag in file order, so the
        n-th emit of that tag is the n-th frame. No time is invented: the cursor is the frame's
        own engine-emitted time.
        """
        pb = self._playback
        if pb is None or pb.is_empty or pb.kind != "particles" or not pb.frames:
            return None
        if pb.source_tag and emit.tag != pb.source_tag:
            return None
        index = 0
        for candidate in self._emits:
            if candidate is emit:
                break
            if candidate.tag == emit.tag:
                index += 1
        else:
            return None
        if index >= len(pb.frames):
            return None
        return float(pb.frames[index].time)

    def _jump_to_selected(self) -> None:
        emit = self.selected_emit()
        if emit is None:
            return
        target = self._timeline_time(emit)
        if target is not None:
            self.cursor_requested.emit(target)


# --- payload rendering (display only) ---------------------------------------------------


def _label_for(emit: HookEmit) -> str:
    parts = [emit.tag or "(untagged)"]
    if emit.hook:
        parts.append(emit.hook)
    if emit.event_id >= 0:
        parts.append(f"event {emit.event_id}")
    if emit.step_index >= 0:
        parts.append(f"step {emit.step_index}")
    return " · ".join(parts)


def _payload_text(payload: Any) -> str:
    try:
        return json.dumps(payload, sort_keys=True)
    except (TypeError, ValueError):
        return str(payload)


def _truncate(value: Any) -> Any:
    """Shorten long arrays for display, leaving an explicit note in place of the dropped rows."""
    if isinstance(value, list):
        if len(value) > _MAX_ITEMS:
            head = [_truncate(v) for v in value[:_MAX_ITEMS]]
            head.append(f"… display-truncated: {len(value) - _MAX_ITEMS} more entries in the file")
            return head
        return [_truncate(v) for v in value]
    if isinstance(value, dict):
        return {k: _truncate(v) for k, v in value.items()}
    return value


def _render_payload(payload: Any) -> str:
    try:
        text = json.dumps(_truncate(payload), indent=2, sort_keys=True)
    except (TypeError, ValueError):
        text = str(payload)
    if len(text) > _MAX_CHARS:
        text = text[:_MAX_CHARS] + "\n… display-truncated (the emitted record itself is complete)"
    return text
