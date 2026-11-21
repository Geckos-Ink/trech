"""Real-time bridge to a persistent ``trech lab`` session.

The engine's lab mode reads a JSONL command stream on stdin and writes snapshot JSON on
stdout at ``lab.targetHz`` (see repo ``examples/lab/realtime_lab_commands.jsonl`` and
``src/core/LabSession``). This class owns that protocol so the inspector can turn a live
property edit into a ``patch`` command and get an updated snapshot back — the 60 Hz editing
loop of Milestone 2.

Two ways to start a session:
  ``start(bootstrap=config.json)``  -> ``trech lab --config config.json`` (no JavaScript)
  ``start(scenario=exp.js, params=[...])`` -> ``trech lab exp.js --param n=<json> ...``: the
      scenario's hooks run in every batch, and ``set_params`` / ``reload`` re-evaluate it
      between batches on the same Geant4 kernel (docs/engine/cli.md).

Command actions (from the lab command schema):
  {"action": "patch",    "patch": {...config subtree...}}
  {"action": "simulate"}                 # adaptive learned round count
  {"action": "simulate", "events": N}   # explicit one-command override
  {"action": "snapshot"}
  {"action": "params", "values": {...}}  # scenario lab: change TRECH_VALUEs (null = default)
  {"action": "reload"}                   # scenario lab: re-read the scenario from disk
  {"action": "help"}
  {"action": "quit"}

Output routing: ``lab_round_plan`` telemetry -> ``round_plan``; the scenario lab's
``lab_script`` status (generation, trigger, source digests, TRECH_VALUEs) -> ``script_status``;
``lab error:`` lines (a refused re-evaluation or batch) -> ``refused``; other JSON objects ->
``snapshot``; everything else -> ``message``. The interactive ``trech-lab>`` prompt that
prefixes the first line of every reply is stripped first.

Status: the protocol is fully wired here; Studio's live scenario lab
(``engine/live_lab.py``) drives ``params``/``reload``; the inspector is not yet emitting
patches (ROADMAP M2).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from PySide6.QtCore import QObject, QProcess, Signal

from .locator import EngineLocation

PROMPT = "trech-lab> "


class LabSession(QObject):
    """A long-lived ``trech lab`` process driven by JSONL commands."""

    started = Signal()
    message = Signal(str)                 # plain textual lines from the engine
    snapshot = Signal(dict)               # parsed snapshot JSON objects
    round_plan = Signal(dict)             # lab_round_plan throughput/precision telemetry
    script_status = Signal(dict)          # scenario lab: lab_script generation and identity
    refused = Signal(str)                 # "lab error: ..." (refused re-evaluation or batch)
    stopped = Signal(int)                 # exit code
    failed = Signal(str)

    def __init__(self, engine: EngineLocation, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._engine = engine
        self._proc: Optional[QProcess] = None
        self._buf = ""
        self.scenario: Optional[Path] = None
        self.script: Dict[str, Any] = {}  # last lab_script status (scenario lab)

    def is_active(self) -> bool:
        return self._proc is not None and self._proc.state() != QProcess.NotRunning

    def start(
        self,
        bootstrap: Optional[Path] = None,
        output_dir: Optional[Path] = None,
        scenario: Optional[Path] = None,
        params: Sequence[str] = (),
        watch: bool = False,
    ) -> bool:
        """Start ``trech lab``. ``scenario`` hosts that experiment's hooks live (``params`` are
        ``--param`` arguments, ``watch`` adds ``--watch``); ``bootstrap`` is a config-only lab."""
        if not self._engine.available:
            self.failed.emit(self._engine.describe())
            return False
        if self.is_active():
            return True
        if scenario is not None and bootstrap is not None:
            self.failed.emit("a lab takes a scenario or a bootstrap config, not both")
            return False

        args = ["lab"]
        self.scenario = None
        self.script = {}
        if scenario is not None:
            self.scenario = Path(scenario).resolve()
            args.append(str(self.scenario))
            args += list(params)
            if watch:
                args.append("--watch")
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

        if self.scenario is not None:
            # Same working directory as a Studio batch run and `inspect` of this scenario.
            proc.setWorkingDirectory(str(self.scenario.parent))
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

    def set_params(self, values: Dict[str, Any]) -> bool:
        """Scenario lab: re-evaluate with these TRECH_VALUE changes (``None`` = default)."""
        return self.send({"action": "params", "values": dict(values)})

    def reload(self) -> bool:
        """Scenario lab: re-read the scenario (and its includes) from disk."""
        return self.send({"action": "reload"})

    @property
    def generation(self) -> int:
        return int(self.script.get("generation", 0))

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
            self.handle_line(raw)

    def handle_line(self, raw: str) -> None:
        """Route one engine output line (public so the protocol is testable offline)."""
        raw = raw.rstrip("\r")
        while raw.startswith(PROMPT):
            raw = raw[len(PROMPT):]
        if not raw.strip():
            return
        stripped = raw.lstrip()
        if stripped.startswith("lab error:"):
            self.refused.emit(stripped[len("lab error:"):].strip())
            return
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError:
                self.message.emit(raw)
                return
            if isinstance(obj, dict):
                phase = obj.get("phase")
                if phase == "lab_round_plan":
                    self.round_plan.emit(obj)
                elif phase == "lab_script":
                    self.script = obj
                    self.script_status.emit(obj)
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
