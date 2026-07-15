"""Real-time bridge to a persistent ``trech lab`` session.

The engine's lab mode reads a JSONL command stream on stdin and writes snapshot JSON on
stdout at ``lab.targetHz`` (see repo ``examples/lab/realtime_lab_commands.jsonl`` and
``src/core/LabSession``). This class owns that protocol so the inspector can turn a live
property edit into a ``patch`` command and get an updated snapshot back — the 60 Hz editing
loop of Milestone 2.

Command actions (from the lab command schema):
  {"action": "patch",    "patch": {...config subtree...}}
  {"action": "simulate"}                 # adaptive learned round count
  {"action": "simulate", "events": N}   # explicit one-command override
  {"action": "snapshot"}
  {"action": "help"}
  {"action": "quit"}

Status: the protocol is fully wired here; the inspector is not yet emitting patches
(ROADMAP M2). Verified in isolation against the bootstrap config.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from PySide6.QtCore import QObject, QProcess, Signal

from .locator import EngineLocation


class LabSession(QObject):
    """A long-lived ``trech lab`` process driven by JSONL commands."""

    started = Signal()
    message = Signal(str)                 # plain textual lines from the engine
    snapshot = Signal(dict)               # parsed snapshot JSON objects
    round_plan = Signal(dict)             # lab_round_plan throughput/precision telemetry
    stopped = Signal(int)                 # exit code
    failed = Signal(str)

    def __init__(self, engine: EngineLocation, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._engine = engine
        self._proc: Optional[QProcess] = None
        self._buf = ""

    def is_active(self) -> bool:
        return self._proc is not None and self._proc.state() != QProcess.NotRunning

    def start(
        self,
        bootstrap: Optional[Path] = None,
        output_dir: Optional[Path] = None,
    ) -> bool:
        if not self._engine.available:
            self.failed.emit(self._engine.describe())
            return False
        if self.is_active():
            return True

        args = ["lab"]
        if bootstrap is not None:
            args += ["--config", str(bootstrap)]
        if output_dir is not None:
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            args += ["--output", str(output_dir)]

        proc = QProcess(self)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(self._drain)
        proc.finished.connect(self._on_finished)
        proc.errorOccurred.connect(self._on_error)
        self._proc = proc
        self._buf = ""

        proc.start(str(self._engine.path), args)
        if not proc.waitForStarted(3000):
            self.failed.emit(f"failed to start lab: {self._engine.describe()}")
            self._proc = None
            return False
        self.started.emit()
        return True

    # --- commands -----------------------------------------------------------------------

    def send(self, command: Dict[str, Any]) -> bool:
        """Send one JSONL command; returns False if the session is not active."""
        if not self.is_active() or self._proc is None:
            return False
        line = json.dumps(command, separators=(",", ":")) + "\n"
        self._proc.write(line.encode("utf-8"))
        return True

    def patch(self, subtree: Dict[str, Any]) -> bool:
        return self.send({"action": "patch", "patch": subtree})

    def simulate(self, events: Optional[int] = None) -> bool:
        cmd: Dict[str, Any] = {"action": "simulate"}
        if events is not None:
            cmd["events"] = int(events)
        return self.send(cmd)

    def request_snapshot(self) -> bool:
        return self.send({"action": "snapshot"})

    def quit(self) -> None:
        if self.is_active():
            self.send({"action": "quit"})
            if self._proc is not None and not self._proc.waitForFinished(1500):
                self._proc.terminate()

    # --- internals ----------------------------------------------------------------------

    def _drain(self) -> None:
        if self._proc is None:
            return
        self._buf += bytes(self._proc.readAllStandardOutput()).decode("utf-8", "replace")
        *lines, self._buf = self._buf.split("\n")
        for raw in lines:
            raw = raw.rstrip("\r")
            if not raw:
                continue
            stripped = raw.lstrip()
            if stripped.startswith("{") or stripped.startswith("["):
                try:
                    obj = json.loads(stripped)
                except json.JSONDecodeError:
                    self.message.emit(raw)
                    continue
                if isinstance(obj, dict):
                    if obj.get("phase") == "lab_round_plan":
                        self.round_plan.emit(obj)
                    else:
                        self.snapshot.emit(obj)
                else:
                    self.message.emit(raw)
            else:
                self.message.emit(raw)

    def _on_finished(self, exit_code: int, _status: object) -> None:
        self._proc = None
        self.stopped.emit(int(exit_code))

    def _on_error(self, _error: object) -> None:
        if self._proc is not None:
            self.failed.emit(self._proc.errorString())
