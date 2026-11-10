"""Bridge to the ``trech-ml`` Node CLI (model definitions, structure searches, checkpoint store).

Studio never trains, scores or deletes a model itself. Quick operations (inspect a draft, pin,
activate, plan/execute a prune or delete, record run usage) run the CLI synchronously with a
timeout; training and searches run as a QProcess job that relays the CLI's JSON-lines events.
Reading the registry index is plain file parsing (``models.parse_registry``); every mutation
goes through the CLI, which is the store's only writer. Without Node.js the panel stays
read-only and says so.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from typing import Any, List, Optional, Sequence

from PySide6.QtCore import QObject, QProcess, Signal

from ..models import Registry, parse_registry
from .spectra import node_executable

CLI = Path("tools/ml/bin/trech-ml.cjs")
NODE_MISSING = "Node.js >= 18 was not found (set TRECH_NODE): model definitions and checkpoints are read-only."


def default_store(repo_root: Path) -> Path:
    configured = os.environ.get("TRECH_MODEL_STORE")
    return Path(configured).expanduser() if configured else Path(repo_root) / "build" / "model_store"


def cli_arguments(root: Path, command: str, *args: str, store: Optional[Path] = None) -> List[str]:
    out = [str(Path(root) / CLI), command, *args, "--json", "--root", str(root)]
    if store is not None:
        out += ["--store", str(store)]
    return out


def read_registry(store: Path) -> Registry:
    index = Path(store) / "index.json"
    if not index.is_file():
        return parse_registry(None, Path(store))
    try:
        return parse_registry(json.loads(index.read_text(encoding="utf-8")), Path(store))
    except (OSError, json.JSONDecodeError) as error:
        return Registry(store=Path(store), error=f"cannot read {index}: {error}")


class CliError(RuntimeError):
    pass


def run_cli(root: Path, command: str, *args: str, store: Optional[Path] = None, stdin: Optional[str] = None,
            timeout: float = 30.0, ok_codes: Sequence[int] = (0,)) -> Any:
    """Run one CLI command and return its last JSON line. Raises CliError with the CLI's message."""
    node = node_executable()
    if node is None:
        raise CliError(NODE_MISSING)
    try:
        proc = subprocess.run([node, *cli_arguments(root, command, *args, store=store)], input=stdin, capture_output=True,
                              text=True, timeout=timeout, cwd=str(root))
    except subprocess.TimeoutExpired as error:
        raise CliError(f"trech-ml {command} timed out after {timeout:.0f} s") from error
    except OSError as error:
        raise CliError(f"cannot start Node.js: {error}") from error
    payload = None
    for line in reversed(proc.stdout.splitlines()):
        line = line.strip()
        if line.startswith("{") or line.startswith("["):
            try:
                payload = json.loads(line)
                break
            except json.JSONDecodeError:
                continue
    if isinstance(payload, dict) and payload.get("event") == "error":
        raise CliError(str(payload.get("message")))
    if proc.returncode not in ok_codes and command != "inspect":
        raise CliError((proc.stderr or proc.stdout or f"exit {proc.returncode}").strip()[-1200:])
    if payload is None:
        raise CliError((proc.stderr or "trech-ml produced no JSON output").strip()[-1200:])
    return payload


def inspect_source(root: Path, path: Path, source: Optional[str] = None, timeout: float = 10.0) -> Any:
    """Inspect a definition file — or an unsaved draft of it, passed on stdin."""
    args = [str(path)] + (["--stdin"] if source is not None else [])
    return run_cli(root, "inspect", *args, stdin=source, timeout=timeout, ok_codes=(0, 1))


def describe_event(event: dict) -> str:
    kind = event.get("event")
    if kind == "trainer":
        return "    " + str(event.get("line", ""))
    if kind == "candidate":
        loss = event.get("loss")
        score = "unrankable" if loss is None else f"selection loss {loss:.5g}"
        tail = f" — ERROR {str(event.get('error')).splitlines()[0]}" if event.get("error") else ""
        return f"[{event.get('index')}/{event.get('total')}] {event.get('structure_label')} ({event.get('parameter_count')} params): {score}{tail}"
    if kind == "registered":
        return f"registered {event.get('checkpoint')}" + (" (identical bytes already stored)" if event.get("duplicate") else "")
    if kind == "search_done":
        best = event.get("best") or {}
        return f"search done: best {best.get('checkpoint')} {best.get('structure_label')} (holdout: {best.get('holdout_source')})"
    if kind == "error":
        return "ERROR " + str(event.get("message"))
    if kind == "done":
        return "done"
    return str(event.get("message") or json.dumps(event))


class ModelJob(QObject):
    """One long-running ``trech-ml train`` / ``search`` command."""

    message = Signal(str)
    event = Signal(dict)
    finished = Signal(bool, str)  # ok, summary

    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.root = Path(root).resolve()
        self.process: Optional[QProcess] = None
        self._buffer = ""
        self._error = ""
        self._tail = ""

    def is_running(self) -> bool:
        return self.process is not None and self.process.state() != QProcess.NotRunning

    def start(self, command: str, path: Path, *extra: str, store: Optional[Path] = None) -> bool:
        if command not in ("train", "search"):
            raise ValueError("ModelJob runs train or search")
        if self.is_running():
            self.finished.emit(False, "A model job is already running.")
            return False
        node = node_executable()
        if node is None:
            self.finished.emit(False, NODE_MISSING)
            return False
        proc = QProcess(self)
        self.process = proc
        self._buffer, self._error, self._tail = "", "", ""
        proc.setWorkingDirectory(str(self.root))
        proc.readyReadStandardOutput.connect(self._read)
        proc.readyReadStandardError.connect(self._read_stderr)
        proc.finished.connect(self._finished)
        proc.errorOccurred.connect(lambda _err: self.message.emit(proc.errorString()))
        proc.start(node, cli_arguments(self.root, command, str(path), *extra, store=store))
        self.message.emit(f"trech-ml {command} {path.name}: training runs in the Python trainer; "
                          "checkpoints are learned comparison models, not Geant4 results.")
        return True

    def _read(self) -> None:
        if not self.process:
            return
        self._buffer += bytes(self.process.readAllStandardOutput()).decode("utf-8", "replace")
        *lines, self._buffer = self._buffer.split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                self.message.emit(line)
                continue
            if isinstance(event, dict):
                if event.get("event") == "error":
                    self._error = str(event.get("message"))
                self.event.emit(event)
                self.message.emit(describe_event(event))

    def _read_stderr(self) -> None:
        if self.process:
            text = bytes(self.process.readAllStandardError()).decode("utf-8", "replace")
            self._tail = (self._tail + text)[-2000:]

    def _finished(self, code, _status) -> None:
        self._read()
        self.process = None
        if code == 0:
            self.finished.emit(True, "finished")
        else:
            self.finished.emit(False, self._error or self._tail.strip()[-800:] or f"exit {code}")

    def stop(self) -> None:
        if self.is_running():
            self.process.terminate()
            if not self.process.waitForFinished(1500):
                self.process.kill()


class DraftInspector(QObject):
    """Asynchronous ``trech-ml inspect --stdin`` for live editing.

    Only the newest request matters: a request made while one is running replaces any queued
    one, so fast typing produces at most one queued inspection.
    """

    inspected = Signal(object, str)  # payload (dict or None), source text it describes
    failed = Signal(str)

    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.root = Path(root).resolve()
        self.process: Optional[QProcess] = None
        self._pending: Optional[tuple] = None
        self._current_source = ""

    def request(self, path: Path, source: str) -> bool:
        if self.process is not None:
            self._pending = (Path(path), source)
            return True
        node = node_executable()
        if node is None:
            self.failed.emit(NODE_MISSING)
            return False
        proc = QProcess(self)
        self.process = proc
        self._current_source = source
        proc.setWorkingDirectory(str(self.root))
        proc.finished.connect(self._finished)
        proc.errorOccurred.connect(self._error)
        proc.start(node, cli_arguments(self.root, "inspect", str(path), "--stdin"))
        proc.write(source.encode("utf-8"))
        proc.closeWriteChannel()
        return True

    def _error(self, error) -> None:
        if error == QProcess.FailedToStart:
            self.process = None
            self.failed.emit("cannot start Node.js for live inspection")

    def _finished(self, _code, _status) -> None:
        proc, self.process = self.process, None
        payload = None
        if proc is not None:
            for line in reversed(bytes(proc.readAllStandardOutput()).decode("utf-8", "replace").splitlines()):
                if line.strip().startswith("{"):
                    try:
                        payload = json.loads(line)
                        break
                    except json.JSONDecodeError:
                        continue
            proc.deleteLater()
        self.inspected.emit(payload, self._current_source)
        if self._pending is not None:
            path, source = self._pending
            self._pending = None
            self.request(path, source)

    def wait(self, msecs: int = 10000) -> None:
        """Block until the current (and any queued) inspection finished (tests, shutdown)."""
        while self.process is not None:
            if not self.process.waitForFinished(msecs):
                break

    def stop(self) -> None:
        self._pending = None
        if self.process is not None:
            self.process.kill()
            self.process.waitForFinished(1000)
