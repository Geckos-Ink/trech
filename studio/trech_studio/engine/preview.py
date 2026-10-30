"""Nonblocking preview export through Studio's ordinary capture entry point."""
from pathlib import Path
import os
import sys

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Signal


class PreviewExport(QObject):
    message = Signal(str)
    finished = Signal(Path)
    failed = Signal(str)

    def __init__(self, repo_root, parent=None):
        super().__init__(parent)
        self.root = Path(repo_root)
        self.process = None
        self.prefix = None
        self._video = False

    def start(self, run_dir, prefix, *, video=False, stream=None):
        if self.process is not None:
            self.failed.emit("A preview export is already running.")
            return False
        self.prefix = Path(prefix)
        self._video = video
        args = ["-m", "trech_studio.capture", "--run", str(run_dir), "--out", str(prefix),
                "--annotations", "--label", Path(run_dir).name, "--width", "960", "--height", "640",
                "--seconds", "6", "--fps", "12", "--orbit", "0", "--supersample", "1"]
        if not video:
            args.append("--still")
        if stream is not None:
            args.extend(("--stream", stream))
        proc = QProcess(self)
        self.process = proc
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONPATH", str(self.root / "studio") + (os.pathsep + env.value("PYTHONPATH") if env.value("PYTHONPATH") else ""))
        env.insert("QT_QPA_PLATFORM", "offscreen")
        proc.setProcessEnvironment(env)
        proc.setWorkingDirectory(str(self.root))
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(lambda: self.message.emit(bytes(proc.readAllStandardOutput()).decode("utf-8", "replace").strip()))
        proc.finished.connect(lambda code, status: self._done(proc, code))
        proc.errorOccurred.connect(lambda error: self._error(proc) if error == QProcess.FailedToStart else None)
        proc.start(sys.executable, args)
        self.message.emit("Rendering recorded frames with Studio's standard camera; no simulation is rerun.")
        return True

    def _error(self, proc):
        if self.process is proc:
            self.process = None
            self.failed.emit(proc.errorString())
            proc.deleteLater()

    def _done(self, proc, code):
        if self.process is not proc:
            return
        self.process = None
        if code == 0 and (not self._video or self.prefix.with_suffix(".gif").is_file()):
            self.finished.emit(self.prefix)
        else:
            self.failed.emit("Preview export incomplete; check Console and the JSON sidecar. GIF export needs a healthy ffmpeg installation.")
        proc.deleteLater()

    def stop(self):
        if self.process is not None:
            proc = self.process
            self.process = None
            proc.terminate()
            if not proc.waitForFinished(1500):
                proc.kill()
                proc.waitForFinished(1500)
            proc.deleteLater()
            self.message.emit("Preview export cancelled; partial files may remain.")
