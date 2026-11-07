"""Optional spectrum-prediction training job (the JavaScript subproject, run on Node.js).

Studio never trains or evaluates a model itself: this launches
``projects/spectrum_prediction/bin/spectra.cjs <command> --studio`` via QProcess, relays its
JSON-lines progress, and hands back the run directory. The trained models only reach the UI
through an ordinary TRECH run of the ``spectrum_prediction`` scenario with ``data_dir`` set.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
from typing import List, Optional

from PySide6.QtCore import QObject, QProcess, Signal

SCENARIO = Path("examples/scenarios/spectrum_prediction/spectrum_prediction.js")
CLI = Path("projects/spectrum_prediction/bin/spectra.cjs")


def node_executable() -> Optional[str]:
    configured = os.environ.get("TRECH_NODE")
    if configured:
        return str(Path(configured).expanduser())
    return shutil.which("node") or shutil.which("nodejs")


def training_arguments(root: Path, out_dir: Path, *, offline: bool, command: str = "all",
                       family_cv: bool = True, architectures: Optional[List[str]] = None) -> List[str]:
    if command not in ("all", "build", "train", "collect"):
        raise ValueError(f"unsupported spectrum pipeline command {command!r}")
    args = [str(Path(root) / CLI), command, "--studio", "--out", str(out_dir)]
    if offline:
        args.append("--offline")
    if not family_cv:
        args.append("--no-family-cv")
    if architectures:
        args.extend(["--arch", ",".join(architectures)])
    return args


def parse_progress(line: str) -> Optional[dict]:
    """One JSON-lines event from --studio mode, or None for ordinary log text."""
    line = line.strip()
    if not line.startswith("{"):
        return None
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return None
    return event if isinstance(event, dict) and "event" in event else None


def describe_event(event: dict) -> str:
    kind = event.get("event")
    if kind == "stage":
        return f"[{event.get('stage')}] {event.get('message', '')}"
    if kind == "architecture":
        return (f"{event.get('task')}: {event.get('name')} — CV RMSE {event.get('cv_rmse', float('nan')):.4f}, "
                f"test RMSE {event.get('test_rmse', float('nan')):.4f}")
    if kind in ("atom", "molecule"):
        return f"collect {kind} {event.get('symbol') or event.get('name')}: {event.get('status')}"
    if kind == "done":
        return f"done: {event.get('manifest')}"
    return json.dumps(event)


class SpectrumTrainingJob(QObject):
    finished = Signal(object)  # run directory (Path)
    message = Signal(str)
    failed = Signal(str)

    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.root = Path(root).resolve()
        self.process: Optional[QProcess] = None
        self.out_dir: Optional[Path] = None
        self._buffer = ""
        self._tail = ""
        self._done = False

    def is_running(self) -> bool:
        return self.process is not None and self.process.state() != QProcess.NotRunning

    def start(self, out_dir: Path, *, offline: bool = True, command: str = "all", family_cv: bool = True) -> bool:
        if self.is_running():
            self.failed.emit("A spectrum training job is already running.")
            return False
        node = node_executable()
        if node is None:
            self.failed.emit("Node.js >= 18 was not found (set TRECH_NODE). The committed fixture stays usable.")
            return False
        self.out_dir = Path(out_dir).resolve()
        self.out_dir.mkdir(parents=True, exist_ok=True)
        proc = QProcess(self)
        self.process = proc
        self._buffer, self._tail, self._done = "", "", False
        proc.setWorkingDirectory(str(self.root))
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(self._read)
        proc.finished.connect(self._finished)
        proc.errorOccurred.connect(lambda _: self.failed.emit(proc.errorString()))
        proc.start(node, training_arguments(self.root, self.out_dir, offline=offline, command=command, family_cv=family_cv))
        self.message.emit(("Offline: rebuilding from the local cache. " if offline else "Collecting from PubChem/NIST. ") +
                          "Training runs in Node.js; results reach Studio only through a TRECH run.")
        return True

    def _read(self) -> None:
        if not self.process:
            return
        self._buffer += bytes(self.process.readAllStandardOutput()).decode("utf-8", "replace")
        *lines, self._buffer = self._buffer.split("\n")
        for line in lines:
            event = parse_progress(line)
            if event and event.get("event") == "done":
                self._done = True
            if line.strip():
                self._tail = (self._tail + line + "\n")[-4000:]
                self.message.emit(describe_event(event) if event else line.strip())

    def _finished(self, code, _status) -> None:
        self._read()
        self.process = None
        if code == 0 and self._done and self.out_dir and (self.out_dir / "report.json").is_file():
            self.finished.emit(self.out_dir)
        else:
            self.failed.emit("Spectrum training failed (exit %s). %s" % (code, self._tail[-800:]))

    def stop(self) -> None:
        if self.is_running():
            self.process.terminate()
            if not self.process.waitForFinished(1500):
                self.process.kill()
