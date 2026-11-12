"""JS source drafts, syntax highlighting and local TRECH API completion.

The completion catalog describes executable bindings, not dynamic JS types or physics.
Run stays bound to the root scenario while included sources retain independent drafts.
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Optional

from PySide6.QtCore import QRegularExpression, QStringListModel, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QComboBox,
    QCompleter,
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
    "TRECH_INCLUDE", "TRECH_HELPERS", "TRECH_PUBCHEM", "TRECH_VALUE", "TRECH_CONFIG",
    "TRECH_HOOKS", "TRECH_STUDIO", "TRECH_FLOW", "TRECH_PARAMETERS", "TRECH_PARAMETER",
    "TRECH_VIEWS", "TRECH_VALIDATIONS", "TRECH_READ_JSON", "TRECH_ML", "TRECH_GEOMETRY",
    "ctx", "globalThis",
]

# Small, intentionally explicit catalog: keep in step with JsRuntime::dispatchHook,
# kTrechValueBootstrap and Config.cpp. Unknown/dynamic objects get no invented members.
_GLOBALS = tuple(name for name in _TRECH_IDENTS if name not in {"ctx", "globalThis"})
_MEMBERS = {
    # Library global installed by TRECH_INCLUDE("js/trech_ml.js") (model definitions/searches).
    "TRECH_ML": ("defineModel", "defineSearch", "modelEntry", "resolve", "candidates", "layerPlan",
                 "parameterCount", "describeStructure"),
    # Library global installed by TRECH_INCLUDE("js/trech_geometry.js") (procedural generators).
    "TRECH_GEOMETRY": ("volume", "sphereVolume", "grid", "ring", "layerStack", "concentricShells",
                       "audit", "assertClean"),
    "ctx": ("config", "runtime", "event", "step", "state", "rng", "materials", "optics",
            "emit", "predict", "cascade", "evolve", "react", "interact", "operatorCatalog"),
    "ctx.rng": ("uniform", "int", "normal"),
    "ctx.runtime": ("seed", "nEvents", "mode", "runId"),
    "ctx.event": ("id", "edepMeV", "totalTrackLengthMm", "totalStepCount", "totalTrackCount",
                  "opticalPhotonSteps", "opticalPhotonTracks", "opticalPhotonTrackLengthMm"),
    "ctx.step": ("index", "edepMeV", "stepLengthMm", "trackId", "parentTrackId", "particle",
                 "volume", "process", "prePositionMm", "postPositionMm", "preTimeNs",
                 "postTimeNs", "preKineticEnergyMeV", "postKineticEnergyMeV"),
    "TRECH_VALUE": ("number", "integer", "boolean", "string", "choice"),
    "TRECH_HOOKS": ("onInit", "onRunStart", "onEventStart", "onStep", "onEventEnd", "onRunEnd"),
    "globalThis": _GLOBALS,
}
_CONFIG_MEMBERS = {
    "": ("environment", "medium", "detector", "beam", "beams", "run", "physics", "determinism", "system", "optics",
         "chemistry", "nuclear", "multiscale", "analytic", "precision", "materialProbe",
         "geometry", "materials", "models", "hooks", "stratify", "lab"),
    "detector": ("worldSizeMm", "worldMaterial", "mediumBoxMm", "mediumMaterial",
                 "temperatureK", "pressureAtm"),
    "run": ("nEvents", "seed", "threads", "timeBudgetSeconds"),
    "beam": ("name", "particle", "energyMeV", "direction", "originMm", "spotRadiusMm",
             "divergenceDeg", "energySpreadFractional", "polarization", "polarizationAngleDeg",
             "spectrum", "active"),
    "physics": ("list", "radioactiveDecayThresholdYears"),
    "determinism": ("mode",),
    "system": ("enable", "mode", "frame", "ensemble", "volumeMm3"),
    "optics": ("enable", "refractiveIndex", "absorptionLengthMm", "scatterLengthMm", "spectrum", "derive"),
    "chemistry": ("enable", "model", "solver"),
    "geometry": ("volumes", "overlapCheck", "refuseOn"),
    "models": ("name", "path", "scale", "operator_role", "element_kind", "required_context_keys"),
    "hooks": ("registered", "inputs", "maxStepCallbacks", "maxEmitsPerCallback", "maxEmitPayloadBytes"),
    "lab": ("enable", "mode", "commandSchema", "commandChannel", "targetHz", "roundsPerTick",
            "minRoundsPerTick", "maxRoundsPerTick", "roundLearningRate"),
}
_CONFIG_MEMBERS["beams"] = _CONFIG_MEMBERS["beam"]
# environment / medium / detector are aliases of one engine block (merged in that order).
_CONFIG_MEMBERS["environment"] = _CONFIG_MEMBERS["medium"] = _CONFIG_MEMBERS["detector"]
_JS_NON_CODE = re.compile(
    r'//[^\n]*|/\*[\s\S]*?(?:\*/|\Z)|'
    r'"(?:\\(?:[\s\S]|\Z)|[^"\\])*(?:"|\Z)|'
    r"'(?:\\(?:[\s\S]|\Z)|[^'\\])*(?:'|\Z)|"
    r'`(?:\\(?:[\s\S]|\Z)|[^`\\])*(?:`|\Z)'
)


def _code_mask(text: str) -> tuple[str, bool]:
    """Blank strings/comments while preserving offsets; suppress template literals too.

    This is a lexical helper, not a JS parser: aliases, computed keys and template
    interpolation are deliberately outside the completion surface.
    """
    parts, end, in_code = [], 0, True
    for match in _JS_NON_CODE.finditer(text):
        token = match.group()
        parts.append(text[end:match.start()])
        parts.append(re.sub(r"[^\n]+", lambda part: " " * len(part.group()), token))
        end = match.end()
        if end == len(text):
            if token.startswith("//"):
                in_code = False
            elif token.startswith("/*"):
                in_code = token.endswith("*/")
            else:
                # An escaped final quote belongs to the unfinished literal.
                slashes = len(token[:-1]) - len(token[:-1].rstrip("\\"))
                in_code = len(token) > 1 and token.endswith(token[0]) and slashes % 2 == 0
    parts.append(text[end:])
    return "".join(parts), in_code


def _config_key_members(code: str) -> tuple[str, ...]:
    """Recognize direct TRECH_CONFIG object keys, including nested arrays of objects."""
    # Frames hold delimiter, config path (None for unrelated JS), key-boundary offset.
    stack: list[tuple[str, Optional[str], int]] = []
    for match in re.finditer(r"[{}\[\](),]", code):
        char, index = match.group(), match.start()
        if char in "{[":
            path = None
            if char == "{" and re.search(r"\bTRECH_CONFIG\s*=\s*$", code[max(0, index - 128):index]):
                path = ""
            elif stack and stack[-1][1] is not None:
                parent_delimiter, parent_path, boundary = stack[-1]
                key = re.fullmatch(r"\s*([A-Za-z_$][\w$]*)\s*:\s*", code[boundary:index])
                if parent_delimiter == "{" and key:
                    path = ".".join(part for part in (parent_path, key.group(1)) if part)
                elif parent_delimiter == "[" and not code[boundary:index].strip():
                    path = parent_path
            stack.append((char, path, index + 1))
        elif char == "(":
            stack.append((char, None, index + 1))
        elif char in "}])":
            if stack:
                stack.pop()
        elif char == "," and stack:
            delimiter, path, _ = stack[-1]
            stack[-1] = (delimiter, path, index + 1)
    if stack:
        delimiter, path, boundary = stack[-1]
        if delimiter == "{" and path is not None and not code[boundary:].strip():
            return _CONFIG_MEMBERS.get(path, ())
    return ()


def completion_candidates(before_cursor: str) -> tuple[str, tuple[str, ...]]:
    """Return the current identifier prefix and its context-filtered candidates."""
    code, in_code = _code_mask(before_cursor)
    if not in_code:
        return "", ()
    # Known receiver paths are short. Bound regex backtracking independently of
    # document length, then retain the absolute prefix offset for config keys.
    offset = max(0, len(code) - 256)
    match = re.search(r"(?<![\w$.])((?:[A-Za-z_$][\w$]*\s*\.\s*)*)([A-Za-z_$][\w$]*)?$", code[offset:])
    if not match:
        return "", ()
    chain, prefix = match.group(1), match.group(2) or ""
    if chain:
        receiver = re.sub(r"\s+", "", chain)[:-1]
        receiver = receiver.removeprefix("globalThis.")
        members = _MEMBERS.get(receiver, ())
        for root in ("TRECH_CONFIG", "ctx.config"):
            if receiver == root or receiver.startswith(root + "."):
                members = _CONFIG_MEMBERS.get(receiver[len(root):].lstrip("."), ())
                break
    else:
        members = _config_key_members(code[:offset + match.start(2)] if match.group(2) else code)
        if not members and prefix:
            members = _GLOBALS
    return prefix, tuple(sorted(member for member in members if member.startswith(prefix)))


class _JsEditor(QPlainTextEdit):
    """Completion on a known receiver, or explicitly with Ctrl+Space."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.completer = QCompleter(self)
        self.completer.setWidget(self)
        self.completer.setCompletionMode(QCompleter.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseSensitive)
        self._completion_model = QStringListModel(self)
        self.completer.setModel(self._completion_model)
        self.completer.activated[str].connect(self._accept_completion)
        self.cursorPositionChanged.connect(self.completer.popup().hide)
        self.textChanged.connect(self.completer.popup().hide)
        self.setToolTip("TRECH API suggestions: Ctrl+Space; Enter/Tab accepts, Escape dismisses")

    def _before_cursor(self) -> str:
        # QTextCursor uses UTF-16 offsets; selecting text avoids treating those as
        # Python character indices when comments contain emoji or other astral text.
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.Start, QTextCursor.KeepAnchor)
        return cursor.selectedText().replace("\u2029", "\n")

    def show_completions(self, explicit: bool = False) -> None:
        if self.textCursor().hasSelection() or self.isReadOnly():
            self.completer.popup().hide()
            return
        before = self._before_cursor()
        prefix, candidates = completion_candidates(before)
        member_prefix = re.search(r"\.\s*[A-Za-z_$][\w$]*$", before[-256:])
        if not candidates or (not explicit and len(prefix) < 2 and not before.endswith(".") and not member_prefix):
            self.completer.popup().hide()
            return
        if not explicit and candidates == (prefix,):
            self.completer.popup().hide()
            return
        self._completion_model.setStringList(list(candidates))
        self.completer.setCompletionPrefix(prefix)
        self.completer.popup().setCurrentIndex(self.completer.completionModel().index(0, 0))
        rect = self.cursorRect()
        rect.setWidth(max(220, self.completer.popup().sizeHintForColumn(0) + 24))
        self.completer.complete(rect)

    def _accept_completion(self, completion: str) -> None:
        prefix, candidates = completion_candidates(self._before_cursor())
        if self.isReadOnly() or self.textCursor().hasSelection() or completion not in candidates:
            return
        cursor = self.textCursor()
        after = self.toPlainText()[len(self._before_cursor()):]
        suffix = re.match(r"[A-Za-z0-9_$]*", after).group()
        cursor.beginEditBlock()
        for _ in prefix:
            cursor.movePosition(QTextCursor.PreviousCharacter)
        for _ in prefix + suffix:
            cursor.movePosition(QTextCursor.NextCharacter, QTextCursor.KeepAnchor)
        cursor.insertText(completion)
        cursor.endEditBlock()
        self.setTextCursor(cursor)
        self.completer.popup().hide()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if self.completer.popup().isVisible() and event.key() in {
            Qt.Key_Enter, Qt.Key_Return, Qt.Key_Escape, Qt.Key_Tab, Qt.Key_Backtab,
        }:
            event.ignore()  # QCompleter owns navigation/acceptance while its popup is open.
            return
        explicit = event.key() == Qt.Key_Space and event.modifiers() == Qt.ControlModifier
        if explicit:
            self.show_completions(explicit=True)
            return
        super().keyPressEvent(event)
        if ((event.key() in {Qt.Key_Backspace, Qt.Key_Delete}
             or event.text() and re.fullmatch(r"[A-Za-z0-9_$.]", event.text()))
                and not event.modifiers() & (Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)):
            self.show_completions()
        else:
            self.completer.popup().hide()


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
        self._scenario: Optional[Path] = None
        self._drafts: dict[Path, str] = {}
        self._originals: dict[Path, str] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        toolbar = QHBoxLayout()
        self._path_label = QLabel("no scenario open", self)
        self._path_label.setProperty("role", "warn")
        self.run_button = QPushButton("Run ▶", self)
        self.run_button.clicked.connect(self.run_requested.emit)
        self.save_button = QPushButton("Save + apply UI", self)
        self.save_button.clicked.connect(self.save_requested.emit)
        toolbar.addWidget(self._path_label, 1)
        toolbar.addWidget(self.save_button)
        toolbar.addWidget(self.run_button)
        layout.addLayout(toolbar)
        self.sources = QComboBox(self)
        self.sources.setToolTip("Scenario and included JavaScript modules; Run always runs the scenario")
        self.sources.currentIndexChanged.connect(self._select_source)
        layout.addWidget(self.sources)

        self.editor = _JsEditor(self)
        self.editor.setTabStopDistance(28)
        font = QFont("Menlo, Consolas, monospace")
        font.setStyleHint(QFont.Monospace)
        font.setPointSize(12)
        self.editor.setFont(font)
        self.editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._highlighter = _JsHighlighter(self.editor.document())
        self.editor.textChanged.connect(self._update_dirty_indicator)
        layout.addWidget(self.editor, 1)

    # --- document API -------------------------------------------------------------------

    def load_file(self, path: Path) -> None:
        path = Path(path).resolve()
        content = path.read_text(encoding="utf-8")
        self._scenario = path
        self._drafts = {path: content}
        self._originals = {path: content}
        self._show_source(path, content)
        self.set_sources((path,))

    def _show_source(self, path: Path, content: str) -> None:
        self._path = path
        self.editor.setPlainText(content)
        self._update_dirty_indicator()
        self._path_label.setToolTip(str(path))
        self._path_label.setProperty("role", "run")
        self._path_label.style().unpolish(self._path_label)
        self._path_label.style().polish(self._path_label)

    def set_sources(self, paths) -> None:
        self.sources.blockSignals(True)
        self.sources.clear()
        for path in dict.fromkeys(Path(p).resolve() for p in [self._scenario, *paths] if p is not None):
            self.sources.addItem(path.name, str(path))
            self.sources.setItemData(self.sources.count() - 1, str(path), Qt.ToolTipRole)
        index = self.sources.findData(str(self._path))
        self.sources.setCurrentIndex(max(0, index))
        self.sources.blockSignals(False)
        self._update_dirty_indicator()

    def dirty_paths(self) -> tuple[Path, ...]:
        """Changed root/include drafts, including the currently visible text."""
        return tuple(path for path, original in self._originals.items()
                     if (self.text() if path == self._path else self._drafts[path]) != original)

    def source_paths(self) -> tuple[Path, ...]:
        """Inventoried sources and retained drafts, including dormant includes."""
        return tuple(dict.fromkeys([
            *(Path(self.sources.itemData(i)) for i in range(self.sources.count())),
            *self._drafts,
        ]))

    def _update_dirty_indicator(self) -> None:
        dirty = set(self.dirty_paths())
        if self._path is not None:
            self._path_label.setText(self._path.name + (" *" if self._path in dirty else ""))
        for index in range(self.sources.count()):
            path = Path(self.sources.itemData(index))
            self.sources.setItemText(index, path.name + (" *" if path in dirty else ""))

    def _select_source(self, index: int) -> None:
        raw = self.sources.itemData(index)
        if raw is None:
            return
        path = Path(raw)
        if path == self._path:
            return
        if self._path is not None:
            self._drafts[self._path] = self.text()
        try:
            content = self._drafts[path] if path in self._drafts else path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            self._path_label.setText(f"Could not open {path.name}: {exc}")
            self.sources.blockSignals(True)
            self.sources.setCurrentIndex(self.sources.findData(str(self._path)))
            self.sources.blockSignals(False)
            return
        self._originals.setdefault(path, content)
        self._show_source(path, content)

    def save(self) -> Optional[Path]:
        if self._path is None:
            return None
        self._drafts[self._path] = self.text()
        changed = {path: content for path, content in self._drafts.items()
                   if content != self._originals[path]}
        for path in changed:
            if path.read_text(encoding="utf-8") != self._originals[path]:
                raise OSError(f"{path} changed outside Studio; reopen it before saving")
        for path, content in changed.items():
            path.write_text(content, encoding="utf-8")
            self._originals[path] = content
        self._update_dirty_indicator()
        return self._scenario

    def scenario_path(self) -> Optional[Path]:
        return self._scenario

    def current_path(self) -> Optional[Path]:
        return self._path

    def text(self) -> str:
        return self.editor.toPlainText()
