"""Console: the streamed log from ``trech run`` (and lab messages).

The run header that used to live here as a second tab is now the dedicated **Run summary** panel
([`run_summary.py`](run_summary.py)), which groups the same provenance/scores with their honesty
labels instead of a flat key/value dump. This widget is the log stream only.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit, QWidget


class Console(QPlainTextEdit):
    """Read-only, colourised log of engine stdout/stderr and Studio notices."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setMaximumBlockCount(5000)
        font = QFont("Menlo, Consolas, monospace")
        font.setStyleHint(QFont.Monospace)
        font.setPointSize(11)
        self.setFont(font)

    # --- log --------------------------------------------------------------------------

    def append_line(self, text: str, color: Optional[str] = None) -> None:
        self.moveCursor(QTextCursor.End)
        if color:
            self.appendHtml(f'<span style="color:{color}">{_escape(text)}</span>')
        else:
            self.appendPlainText(text)
        self.moveCursor(QTextCursor.End)

    def log_stdout(self, line: str) -> None:
        self.append_line(line)

    def log_stderr(self, line: str) -> None:
        self.append_line(line, color="#e07a7a")

    def log_info(self, line: str) -> None:
        self.append_line(line, color="#7fd18b")


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
