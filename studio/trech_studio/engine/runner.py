"""Launch ``trech run <experiment.js> --output <dir>`` and stream its output.

Uses Qt's ``QProcess`` (not a raw thread) so the run integrates with the app event loop:
stdout/stderr arrive as signals the console panel can render live, and the UI never blocks
on the engine. This is the *batch* path; the real-time editing path is ``engine/lab.py``.

Qt is imported here (not in ``engine/__init__``) so the non-Qt parts of the engine layer
(locator, outputs) stay importable without PySide6.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QObject, QProcess, Signal

from .locator import EngineLocation


class EngineRunner(QObject):
    """Runs one scenario to completion, streaming stdout/stderr and reporting the exit code."""

    started = Signal()
    stdout_line = Signal(str)
    stderr_line = Signal(str)
    finished = Signal(int, Path)   # (exit_code, output_dir)
    failed = Signal(str)           # could-not-start / no-binary message

    def __init__(self, engine: EngineLocation, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._engine = engine
        self._proc: Optional[QProcess] = None
        self._output_dir: Optional[Path] = None
        self._stdout_buf = ""
        self._stderr_buf = ""

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.state() != QProcess.NotRunning

    def run(
        self,
        experiment: Path,
        output_dir: Path,
        seed: Optional[int] = None,
        events: Optional[int] = None,
        extra_args: Optional[List[str]] = None,
    ) -> bool:
        """Start a run. Returns False (emitting ``failed``) if it cannot be started."""
        if not self._engine.available:
            self.failed.emit(self._engine.describe())
            return False
        if self.is_running():
            self.failed.emit("a run is already in progress")
            return False

        experiment = Path(experiment).resolve()
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        self._output_dir = output_dir

        args = ["run", str(experiment), "--output", str(output_dir)]
        if seed is not None:
            args += ["--seed", str(int(seed))]
        if events is not None:
            args += ["--events", str(int(events))]
        if extra_args:
            args += list(extra_args)

        proc = QProcess(self)
        # Keep stdout and stderr separate so the console can style them differently.
        proc.setProcessChannelMode(QProcess.SeparateChannels)
        proc.setWorkingDirectory(str(experiment.parent if experiment.parent.exists() else Path.cwd()))
        proc.readyReadStandardOutput.connect(self._drain_stdout)
        proc.readyReadStandardError.connect(self._drain_stderr)
        proc.finished.connect(self._on_finished)
        proc.errorOccurred.connect(self._on_error)
        self._proc = proc
        self._stdout_buf = ""
        self._stderr_buf = ""

        proc.start(str(self._engine.path), args)
        if not proc.waitForStarted(3000):
            self.failed.emit(f"failed to start engine: {self._engine.describe()}")
            self._proc = None
            return False
        self.started.emit()
        return True

    def stop(self) -> None:
        if self.is_running() and self._proc is not None:
            self._proc.terminate()
            if not self._proc.waitForFinished(1500):
                self._proc.kill()

    # --- internals ----------------------------------------------------------------------

    def _emit_lines(self, buf: str, signal: Signal) -> str:
        *lines, rest = buf.split("\n")
        for line in lines:
            signal.emit(line.rstrip("\r"))
        return rest

    def _drain_stdout(self) -> None:
        if self._proc is None:
            return
        self._stdout_buf += bytes(self._proc.readAllStandardOutput()).decode("utf-8", "replace")
        self._stdout_buf = self._emit_lines(self._stdout_buf, self.stdout_line)

    def _drain_stderr(self) -> None:
        if self._proc is None:
            return
        self._stderr_buf += bytes(self._proc.readAllStandardError()).decode("utf-8", "replace")
        self._stderr_buf = self._emit_lines(self._stderr_buf, self.stderr_line)

    def _on_finished(self, exit_code: int, _status: object) -> None:
        # Flush any trailing partial lines.
        if self._stdout_buf:
            self.stdout_line.emit(self._stdout_buf)
            self._stdout_buf = ""
        if self._stderr_buf:
            self.stderr_line.emit(self._stderr_buf)
            self._stderr_buf = ""
        out = self._output_dir or Path(".")
        self._proc = None
        self.finished.emit(int(exit_code), out)

    def _on_error(self, _error: object) -> None:
        if self._proc is not None:
            self.failed.emit(self._proc.errorString())
