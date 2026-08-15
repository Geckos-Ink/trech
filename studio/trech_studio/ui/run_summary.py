"""Run summary panel: the honest run header, grouped and labelled.

A view over :func:`trech_studio.run_summary.build_run_summary` — determinism/seed/physics list,
Geant4's primary tallies, the analytic cross-check gaps, the learned-inference counters (including
how many predictions ran outside their trained domain) and the hook sideband. Glue only: this
module formats rows someone else derived, and every caution shown here comes from the report.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..run_summary import RunSummary


class RunSummaryPanel(QScrollArea):
    """Scrollable, sectioned view of one run's provenance/scores."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self._body = QWidget(self)
        self._layout = QVBoxLayout(self._body)
        self._layout.setContentsMargins(12, 10, 12, 12)
        self._layout.setSpacing(6)
        self.setWidget(self._body)
        self._summary: Optional[RunSummary] = None
        self.show_message("No run loaded yet.")

    # --- public API ---------------------------------------------------------------------

    def summary(self) -> Optional[RunSummary]:
        """The report currently displayed (headless tests assert on this)."""
        return self._summary

    def show_message(self, message: str) -> None:
        self._summary = None
        self._clear()
        label = QLabel(message, self._body)
        label.setWordWrap(True)
        label.setProperty("role", "warn")
        self._layout.addWidget(label)
        self._layout.addStretch(1)

    def show_summary(self, summary: RunSummary) -> None:
        self._summary = summary
        self._clear()
        if summary.is_empty:
            self.show_message(f"No provenance or scores in {summary.output_dir}.")
            return

        head = QLabel(f"<b>{summary.headline()}</b><br/>{summary.output_dir}", self._body)
        head.setWordWrap(True)
        head.setTextFormat(Qt.RichText)
        self._layout.addWidget(head)

        for section in summary.sections:
            self._layout.addWidget(self._rule())
            title = QLabel(f"<b>{section.title}</b>", self._body)
            title.setTextFormat(Qt.RichText)
            self._layout.addWidget(title)
            if section.note:
                self._layout.addWidget(self._note(section.note))
            for row in section.rows:
                text = f"{row.label}: <b>{_escape(row.value)}</b>"
                widget = QLabel(text, self._body)
                widget.setTextFormat(Qt.RichText)
                widget.setWordWrap(True)
                if row.warn:
                    widget.setProperty("role", "warn")
                self._layout.addWidget(widget)
                if row.note:
                    self._layout.addWidget(self._note(row.note, indent=True))

        for caveat in summary.caveats:
            self._layout.addWidget(self._note(caveat))
        self._layout.addStretch(1)

    # --- internals ----------------------------------------------------------------------

    def _clear(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _note(self, text: str, indent: bool = False) -> QLabel:
        label = QLabel(("    " if indent else "") + text, self._body)
        label.setWordWrap(True)
        label.setProperty("role", "warn")
        return label

    def _rule(self) -> QFrame:
        line = QFrame(self._body)
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        return line


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
