"""Console + run-summary panel.

Two tabs:
  - Log: streamed stdout/stderr from ``trech run`` (and lab messages).
  - Run: the honest run header (seed / determinism / physics list / tallies) from provenance +
    scores, plus a list of the emit tags the scenario produced. Nothing here is computed by
    Studio — it is a straight read of the engine's outputs.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtGui import QColor, QFont, QTextCursor
from PySide6.QtWidgets import (
    QFormLayout,
    QLabel,
    QPlainTextEdit,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..engine.outputs import RunResult


class _Log(QPlainTextEdit):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(5000)
        font = QFont("Menlo, Consolas, monospace")
        font.setStyleHint(QFont.Monospace)
        font.setPointSize(11)
        self.setFont(font)

    def append_line(self, text: str, color: Optional[str] = None) -> None:
        self.moveCursor(QTextCursor.End)
        if color:
            self.appendHtml(f'<span style="color:{color}">{_escape(text)}</span>')
        else:
            self.appendPlainText(text)
        self.moveCursor(QTextCursor.End)


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


class Console(QTabWidget):
    """Log stream + run summary."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.log = _Log(self)
        self.addTab(self.log, "Log")

        self._summary_body = QWidget(self)
        self._summary_layout = QVBoxLayout(self._summary_body)
        self._summary_layout.setContentsMargins(10, 10, 10, 10)
        self.addTab(self._summary_body, "Run")
        self._reset_summary("No run loaded yet.")

    # --- log --------------------------------------------------------------------------

    def log_stdout(self, line: str) -> None:
        self.log.append_line(line)

    def log_stderr(self, line: str) -> None:
        self.log.append_line(line, color="#e07a7a")

    def log_info(self, line: str) -> None:
        self.log.append_line(line, color="#7fd18b")

    # --- summary ----------------------------------------------------------------------

    def _reset_summary(self, message: str) -> None:
        while self._summary_layout.count():
            item = self._summary_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        label = QLabel(message, self._summary_body)
        label.setProperty("role", "warn")
        self._summary_layout.addWidget(label)
        self._summary_layout.addStretch(1)

    def show_run(self, result: RunResult) -> None:
        while self._summary_layout.count():
            item = self._summary_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        summary = result.summary()
        header = QLabel(f"output: {result.output_dir}", self._summary_body)
        header.setWordWrap(True)
        self._summary_layout.addWidget(header)

        form_host = QWidget(self._summary_body)
        form = QFormLayout(form_host)
        for key in (
            "seed", "n_events", "determinism_mode", "predictive_mode", "physics_list",
            "geant4_version", "total_edep_mev", "primaries_transmitted_fraction",
            "primaries_uncollided_fraction", "analytic_checks_within_tolerance",
            "hook_emit_count",
        ):
            val = summary.get(key)
            if val is not None:
                form.addRow(key, QLabel(str(val)))
        self._summary_layout.addWidget(form_host)

        tags = result.emit_tags()
        if tags:
            self._summary_layout.addWidget(QLabel("emit tags: " + ", ".join(tags), self._summary_body))

        note = QLabel(
            "All values above are read straight from the engine's provenance/scores — "
            "Studio computes none of them.",
            self._summary_body,
        )
        note.setWordWrap(True)
        note.setProperty("role", "warn")
        self._summary_layout.addWidget(note)
        self._summary_layout.addStretch(1)
        self.setCurrentIndex(1)
