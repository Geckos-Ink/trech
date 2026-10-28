"""Optional offline quantum reference job. UI never imports PySCF or computes physics."""
from __future__ import annotations
import copy
import os
from pathlib import Path
import sys
import uuid
from PySide6.QtCore import QObject, QProcess, Signal
from .chemistry import write_scene


def geometry_request(scene):
    request = copy.deepcopy(scene)
    for frame in request.get('frames', []):
        frame.pop('fields', None)
        frame.pop('electronic_structure', None)
    return request


def quantum_python(root):
    configured = os.environ.get('TRECH_QUANTUM_PYTHON')
    if configured:
        # Preserve the venv executable path; resolving its final symlink loses
        # pyvenv.cfg and silently launches the system Python without PySCF.
        return str(Path(configured).expanduser().absolute())
    local = Path(root)/'build/render-venv/bin/python'
    return str(local.absolute()) if local.is_file() else sys.executable


class QuantumReferenceJob(QObject):
    finished = Signal(object)  # completed scene path
    message = Signal(str)
    failed = Signal(str)

    def __init__(self, root, parent=None):
        super().__init__(parent)
        self.root = Path(root).resolve()
        self.process = None
        self.output = None
        self._diagnostic = ''

    def is_running(self):
        return self.process is not None and self.process.state() != QProcess.NotRunning

    def start(self, scene, directory):
        if self.is_running():
            self.failed.emit('A quantum reference calculation is already running.')
            return
        work = Path(directory).resolve()/('qm_'+uuid.uuid4().hex)
        work.mkdir(parents=True)
        request = work/'request.json'
        write_scene(request, geometry_request(scene))
        self.output = work/'reference.json'
        proc = QProcess(self)
        self.process = proc
        self._diagnostic = ''
        proc.setWorkingDirectory(str(self.root))
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(self._read)
        proc.finished.connect(self._done)
        proc.errorOccurred.connect(lambda _: self.failed.emit(proc.errorString()))
        proc.start(quantum_python(self.root), [str(self.root/'tools/quantum/build_density_scene.py'),
                   '--scene', str(request), '--out', str(self.output)])
        self.message.emit('Calculating independent RHF/6-31g electronic reference; geometry is clamped, no reaction dynamics.')

    def _read(self):
        if self.process:
            message = bytes(self.process.readAllStandardOutput()).decode('utf-8', 'replace')
            self._diagnostic = (self._diagnostic+message)[-6000:]
            self.message.emit(message.strip())

    def _done(self, code, _status):
        self._read()
        self.process = None
        if code == 0 and self.output.is_file():
            self.finished.emit(self.output)
        else:
            self.failed.emit('Quantum reference failed. Install optional PySCF in TRECH_QUANTUM_PYTHON. '+self._diagnostic)

    def stop(self):
        if self.is_running():
            self.process.terminate()
            if not self.process.waitForFinished(1500):
                self.process.kill()
