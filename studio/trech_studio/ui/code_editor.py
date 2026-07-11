"""Scenario code editor: a JS text editor with syntax highlighting + a Run button.

Studio authors scenarios as ``.js`` today (a ``SceneModel -> .js`` writer is ROADMAP M2), so
this panel is where a run is actually launched from. The Run button is wired by the main
window to :class:`engine.runner.EngineRunner`.

Highlighting is a lightweight ``QSyntaxHighlighter`` — no LSP, no external editor dependency;
the goal is legibility, not full IntelliSense (that is a ROADMAP item).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import QRegularExpression, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QSyntaxHighlighter,
    QTextCharFormat,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

_KEYWORDS = [
    "const", "let", "var", "function", "return", "if", "else", "for", "while",
    "new", "throw", "typeof", "true", "false", "null", "undefined", "this",
    "import", "export", "class", "extends", "of", "in", "break", "continue",
]

# TRECH scenario-surface identifiers worth highlighting so the authoring API stands out.
_TRECH_IDENTS = [
    "TRECH_INCLUDE", "TRECH_HELPERS", "TRECH_PUBCHEM", "ctx", "globalThis",
]


class _JsHighlighter(QSyntaxHighlighter):
    def __init__(self, document) -> None:
        super().__init__(document)
        self._rules = []

        def fmt(color: str, bold: bool = False, italic: bool = False) -> QTextCharFormat:
            f = QTextCharFormat()
            f.setForeground(QColor(color))
            if bold:
                f.setFontWeight(QFont.Bold)
            f.setFontItalic(italic)
            return f

        kw_fmt = fmt("#5aa9e0", bold=True)
        for kw in _KEYWORDS:
            self._rules.append((QRegularExpression(rf"\b{kw}\b"), kw_fmt))

        trech_fmt = fmt("#c98af0", bold=True)
        for ident in _TRECH_IDENTS:
            self._rules.append((QRegularExpression(rf"\b{ident}\b"), trech_fmt))

        self._rules.append((QRegularExpression(r"\b[0-9]+\.?[0-9]*([eE][-+]?[0-9]+)?\b"), fmt("#e0b25a")))
        self._rules.append((QRegularExpression(r"\"[^\"]*\"|'[^']*'|`[^`]*`"), fmt("#7fd18b")))
        # Comments last so they win over tokens inside them.
        self._comment_fmt = fmt("#6b7078", italic=True)
        self._rules.append((QRegularExpression(r"//[^\n]*"), self._comment_fmt))

    def highlightBlock(self, text: str) -> None:  # noqa: N802 (Qt naming)
        for pattern, char_fmt in self._rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                match = it.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), char_fmt)


class CodeEditor(QWidget):
    """Scenario editor + Run/Save controls."""

    run_requested = Signal()
    save_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._path: Optional[Path] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        toolbar = QHBoxLayout()
        self._path_label = QLabel("no scenario open", self)
        self._path_label.setProperty("role", "warn")
        self.run_button = QPushButton("Run ▶", self)
        self.run_button.clicked.connect(self.run_requested.emit)
        self.save_button = QPushButton("Save", self)
        self.save_button.clicked.connect(self.save_requested.emit)
        toolbar.addWidget(self._path_label, 1)
        toolbar.addWidget(self.save_button)
        toolbar.addWidget(self.run_button)
        layout.addLayout(toolbar)

        self.editor = QPlainTextEdit(self)
        self.editor.setTabStopDistance(28)
        font = QFont("Menlo, Consolas, monospace")
        font.setStyleHint(QFont.Monospace)
        font.setPointSize(12)
        self.editor.setFont(font)
        self.editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._highlighter = _JsHighlighter(self.editor.document())
        layout.addWidget(self.editor, 1)

    # --- document API -------------------------------------------------------------------

    def load_file(self, path: Path) -> None:
        path = Path(path)
        try:
            self.editor.setPlainText(path.read_text(encoding="utf-8"))
        except OSError as exc:
            self.editor.setPlainText(f"// could not read {path}: {exc}")
        self._path = path
        self._path_label.setText(str(path))
        self._path_label.setProperty("role", "run")
        self._path_label.style().unpolish(self._path_label)
        self._path_label.style().polish(self._path_label)

    def save(self) -> Optional[Path]:
        if self._path is None:
            return None
        self._path.write_text(self.editor.toPlainText(), encoding="utf-8")
        return self._path

    def current_path(self) -> Optional[Path]:
        return self._path

    def text(self) -> str:
        return self.editor.toPlainText()
