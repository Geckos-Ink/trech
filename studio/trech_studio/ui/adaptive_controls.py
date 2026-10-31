"""Independent simulation and representation controls; physics stays in TRECH."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QDoubleSpinBox, QFormLayout, QLabel, QSpinBox, QWidget

from ..render.adaptive import RenderBudget, suggested_memory_mib


class AdaptiveControls(QWidget):
    render_changed = Signal()

    def __init__(self, target_fps: int = 60, parent=None):
        super().__init__(parent)
        form = QFormLayout(self)
        self.refine = QCheckBox("Override scenario profile", self)
        self.refinement = QDoubleSpinBox(self)
        self.refinement.setRange(0.01, 1024.0)
        self.refinement.setDecimals(3)
        self.refinement.setValue(1.0)
        self.refinement.setSingleStep(0.125)
        self.refinement.setToolTip("Continuous factor relative to balanced. Scenario axis bounds and explicit overrides still apply.")
        self.refinement.setEnabled(False)
        self.refine.toggled.connect(self.refinement.setEnabled)
        self.seconds = QDoubleSpinBox(self)
        self.seconds.setRange(0, 86400 * 30)
        self.seconds.setSuffix(" s")
        self.seconds.setSpecialValueText("Fixed work")
        self.seconds.setToolTip("Predictive runs only. Soft simulation budget checked after full events; initialization is excluded.")
        self.auto = QCheckBox("Adapt rendering to frame cost", self)
        self.auto.setChecked(True)
        self.detail = QDoubleSpinBox(self)
        self.detail.setRange(0.125, 8.0)
        self.detail.setSingleStep(0.125)
        self.detail.setValue(1.0)
        self.detail.setSuffix(" ×")
        self.detail.setToolTip("Higher values sample merged material boundaries more finely and add mesh detail. Does not add simulated particles. Working budget may limit the effective detail.")
        self.merge_radius = QDoubleSpinBox(self)
        self.merge_radius.setRange(.5, 2.0)
        self.merge_radius.setDecimals(2)
        self.merge_radius.setSingleStep(.1)
        self.merge_radius.setValue(1.0)
        self.merge_radius.setSuffix(" ×")
        self.merge_radius.setToolTip("Gaussian parcel surfaces only: larger values fuse nearby representatives more strongly. Can change apparent connections, never recorded material membership or physical coalescence. Class-grid boundaries stay fixed.")
        self.fps = QSpinBox(self)
        self.fps.setRange(1, 240)
        self.fps.setValue(target_fps)
        self.memory = QSpinBox(self)
        self.memory.setRange(16, 16384)
        self.memory.setSuffix(" MiB")
        self.memory.setValue(suggested_memory_mib())
        self.memory.setToolTip("Estimated preview loading/cache allowance; applied when opening output. This is not a hard process memory limit.")
        self.status = QLabel("Rendering choices preserve emitted positions and time.", self)
        self.status.setWordWrap(True)
        self.axes_info = QLabel("Particle/cell counts are set in Scenario options, then Run again.", self)
        self.axes_info.setWordWrap(True)
        form.addRow(self.axes_info)
        form.addRow("Run precision profile", self.refine)
        form.addRow("Refinement factor", self.refinement)
        form.addRow("Simulation time", self.seconds)
        form.addRow("Preview", self.auto)
        form.addRow("Surface / mesh detail", self.detail)
        form.addRow("Parcel merge radius", self.merge_radius)
        form.addRow("Target frame rate", self.fps)
        form.addRow("Preview working budget", self.memory)
        form.addRow(self.status)
        for control in (self.auto, self.detail, self.merge_radius, self.fps, self.memory):
            signal = control.toggled if isinstance(control, QCheckBox) else control.valueChanged
            signal.connect(lambda *_: self.render_changed.emit())

    def set_config(self, config: dict) -> None:
        supported = bool((config.get("precision") or {}).get("axes"))
        self.refine.setEnabled(supported)
        if not supported:
            self.refine.setChecked(False)
        axes = (config.get('precision') or {}).get('axes', [])
        summary = '; '.join(f"{a.get('name', '')}: {a.get('value', '?')} {a.get('unit', '')} ({a.get('role', '')})"
                            for a in axes if a.get('role') in ('spatial', 'representation'))
        self.axes_info.setText("Particle/cell counts: Scenario options → Run again." +
                               ("\nResolved sampling: " + summary if summary else ''))
        predictive = (config.get("determinism") or {}).get("mode") == "predictive"
        self.seconds.setEnabled(predictive)
        if not predictive:
            self.seconds.setValue(0)

    def command_args(self) -> list[str]:
        args = []
        if self.refine.isChecked():
            args += ["--refinement", str(self.refinement.value())]
        if self.seconds.value() > 0:
            args += ["--time-budget", str(self.seconds.value())]
        return args

    def render_budget(self) -> RenderBudget:
        return RenderBudget(self.auto.isChecked(), self.fps.value(), self.detail.value(), self.memory.value(),
                            merge_radius_scale=self.merge_radius.value())

    def show_precision(self, info: dict) -> None:
        self.merge_radius.setEnabled(info.get('gaussian_merge_available', True))
        merge_note = (f"merge radius {info.get('merge_radius_scale', 1):.2g}×" if info.get('gaussian_merge_available', True)
                      else 'class/recorded boundaries unchanged')
        self.status.setText(
            f"Representation only · detail {info.get('render_detail_factor', 1):.3g} · "
            f"{info.get('recorded_particle_count', 0)} recorded particles · "
            f"{merge_note} · "
            f"{info.get('sphere_sectors', 16)} sphere sectors · "
            f"CPU frame {info.get('cpu_frame_seconds_ewma', 0) * 1000:.1f} ms "
            "(GPU time unmeasured). Positions and clock unchanged."
        )
