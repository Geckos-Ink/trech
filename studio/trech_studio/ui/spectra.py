"""Spectra dock: the Studio extension of the spectrum-prediction subproject.

Active only when the scenario declares the extension (its ``studio_mode`` switch). It plots the
engine-emitted measured reference against the learned prediction, lists engine trust badges per
inference stage, shows the trainer's architecture leaderboard as emitted by the run, and can launch
the optional JavaScript training pipeline. No model evaluation or metric is computed here.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QCheckBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPlainTextEdit,
                               QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget, QTextEdit,
                               QVBoxLayout, QWidget)

from ..spectra import SpectrumRecord, SpectrumWorkspace, build_spectrum_workspace, format_stage, plot_bounds

_MEASURED = QColor.fromRgbF(0.20, 0.55, 0.95, 1.0)
_PREDICTED = QColor.fromRgbF(0.95, 0.45, 0.15, 1.0)


def _color(values, fallback: QColor) -> QColor:
    try:
        return QColor.fromRgbF(*[float(v) for v in values][:4])
    except (TypeError, ValueError):
        return fallback


class SpectrumPlot(QWidget):
    """Measured vs predicted curves on the record's own grid (bin centres, emitted units)."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.record: Optional[SpectrumRecord] = None
        self.setMinimumHeight(240)

    def set_record(self, record: Optional[SpectrumRecord]) -> None:
        self.record = record
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt naming)
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#0c1322"))
        r = self.record
        if r is None:
            p.setPen(QColor("#dbe6f4"))
            p.drawText(12, 24, "Run the spectrum_prediction scenario to plot recorded predictions.")
            p.end()
            return
        x0, x1, y0, y1 = plot_bounds(r)
        rect = QRectF(54, 30, max(1, self.width() - 70), max(1, self.height() - 76))
        sx = lambda x: rect.left() + (x - x0) / max(x1 - x0, 1e-9) * rect.width()
        sy = lambda y: rect.bottom() - (y - y0) / max(y1 - y0, 1e-9) * rect.height()
        p.setRenderHint(QPainter.Antialiasing, True)
        for j in range(5):
            y = rect.bottom() - rect.height() * j / 4
            p.setPen(QColor("#2b3a50"))
            p.drawLine(int(rect.left()), int(y), int(rect.right()), int(y))
            p.setPen(QColor("#c9d8e9"))
            p.drawText(4, int(y + 4), f"{y0 + (y1 - y0) * j / 4:.2f}")
        for j in range(5):
            x = x0 + (x1 - x0) * j / 4
            p.drawText(int(sx(x) - 16), int(rect.bottom() + 16), f"{x:.0f}")
        # Measured maxima as ticks (molecules): the recorded source bands, not a fitted shape.
        p.setPen(QPen(_color(r.display.get("measured_color"), _MEASURED), 1, Qt.DotLine))
        for band in r.measured_bands:
            wl = band.get("wavelength_nm")
            if isinstance(wl, (int, float)) and x0 <= wl <= x1:
                p.drawLine(int(sx(wl)), int(rect.top()), int(sx(wl)), int(rect.bottom()))
        # Calibrated interval band (engine-reported half-widths) under the curves.
        if r.interval is not None:
            band = QPainterPath()
            for i, (cx, cy) in enumerate(zip(r.centers, r.interval.upper)):
                (band.moveTo if i == 0 else band.lineTo)(sx(cx), sy(cy))
            for cx, cy in reversed(list(zip(r.centers, r.interval.lower))):
                band.lineTo(sx(cx), sy(cy))
            band.closeSubpath()
            fill = QColor(_color(r.display.get("predicted_color"), _PREDICTED))
            fill.setAlphaF(0.22)
            p.fillPath(band, fill)
        for values, color, width in ((r.measured, _color(r.display.get("measured_color"), _MEASURED), 2),
                                     (r.predicted, _color(r.display.get("predicted_color"), _PREDICTED), 2)):
            if values is None:
                continue
            path = QPainterPath()
            for i, (cx, cy) in enumerate(zip(r.centers, values)):
                (path.moveTo if i == 0 else path.lineTo)(sx(cx), sy(cy))
            p.setPen(QPen(color, width))
            p.drawPath(path)
        p.setPen(QColor("#e2ecf8"))
        p.drawText(12, 18, r.display.get("title") or r.label)
        p.setPen(_color(r.display.get("measured_color"), _MEASURED))
        p.drawText(int(rect.right() - 230), 18, "measured reference")
        p.setPen(_color(r.display.get("predicted_color"), _PREDICTED))
        p.drawText(int(rect.right() - 100), 18, "learned" if r.predicted is not None else "no prediction")
        p.setPen(QColor("#9baec5"))
        p.drawText(int(rect.left()), self.height() - 8,
                   f"{r.display.get('x_label', 'wavelength (' + r.unit + ')')} · y: {r.display.get('y_label', 'target units')}")
        p.end()


class SpectraPanel(QWidget):
    open_requested = Signal()
    run_requested = Signal()
    train_requested = Signal(bool, bool)  # offline, family_cv
    use_run_requested = Signal(str)       # data_dir for the scenario

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.workspace = SpectrumWorkspace((), None, (), (), None, None)
        self._trained_dir: Optional[str] = None
        layout = QVBoxLayout(self)
        self.status = QLabel("Spectrum prediction workspace: open it from the Spectra menu.", self)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QHBoxLayout()
        self.open_button = QPushButton("Open workspace", self)
        self.run_button = QPushButton("Run prediction ▶", self)
        self.open_button.clicked.connect(self.open_requested)
        self.run_button.clicked.connect(self.run_requested)
        buttons.addWidget(self.open_button)
        buttons.addWidget(self.run_button)
        layout.addLayout(buttons)

        self.tabs = QTabWidget(self)
        layout.addWidget(self.tabs, 1)
        # Predictions tab ------------------------------------------------------------------
        predictions = QSplitter(Qt.Vertical, self)
        self.targets = QListWidget(predictions)
        self.targets.currentRowChanged.connect(self._select)
        self.plot = SpectrumPlot(predictions)
        self.details = QTextEdit(predictions)
        self.details.setReadOnly(True)
        predictions.addWidget(self.targets)
        predictions.addWidget(self.plot)
        predictions.addWidget(self.details)
        predictions.setSizes([120, 260, 160])
        self.tabs.addTab(predictions, "Predictions")
        # Leaderboard tab ------------------------------------------------------------------
        board = QWidget(self)
        board_layout = QVBoxLayout(board)
        self.leaderboard = QTableWidget(0, 9, board)
        self.leaderboard.setHorizontalHeaderLabels(["Task", "Architecture", "Family", "CV RMSE", "Family-CV RMSE",
                                                    "Test RMSE", "Test R²", "Test cosine", "Export"])
        self.leaderboard.setEditTriggers(QTableWidget.NoEditTriggers)
        self.ablation = QLabel("", board)
        self.ablation.setWordWrap(True)
        board_layout.addWidget(self.leaderboard, 1)
        board_layout.addWidget(self.ablation)
        self.tabs.addTab(board, "Architectures")
        # Training tab ---------------------------------------------------------------------
        training = QWidget(self)
        t_layout = QVBoxLayout(training)
        note = QLabel("Runs projects/spectrum_prediction (Node.js) to collect PubChem/NIST spectra and train every "
                      "catalogued architecture. Studio shows the result only after a TRECH run with the new data_dir.", training)
        note.setWordWrap(True)
        self.offline = QCheckBox("Offline (reuse the local cache, no network)", training)
        self.offline.setChecked(True)
        self.family_cv = QCheckBox("Leave-one-family-out validation (slower)", training)
        self.family_cv.setChecked(True)
        row = QHBoxLayout()
        self.train_button = QPushButton("Train models", training)
        self.use_button = QPushButton("Use trained run", training)
        self.use_button.setEnabled(False)
        self.train_button.clicked.connect(lambda: self.train_requested.emit(self.offline.isChecked(), self.family_cv.isChecked()))
        self.use_button.clicked.connect(lambda: self._trained_dir and self.use_run_requested.emit(self._trained_dir))
        row.addWidget(self.train_button)
        row.addWidget(self.use_button)
        self.training_log = QPlainTextEdit(training)
        self.training_log.setReadOnly(True)
        self.training_log.setMaximumBlockCount(2000)
        for w in (note, self.offline, self.family_cv):
            t_layout.addWidget(w)
        t_layout.addLayout(row)
        t_layout.addWidget(self.training_log, 1)
        self.tabs.addTab(training, "Training")
        self.set_active(False)

    # --- mode / data -------------------------------------------------------------------
    def set_active(self, active: bool) -> None:
        self.run_button.setEnabled(active)
        if not active and self.workspace.is_empty:
            self.status.setText("Spectrum prediction workspace is inactive. Spectra → Open spectrum prediction workspace.")

    def show_run(self, result) -> SpectrumWorkspace:
        try:
            self.workspace = build_spectrum_workspace(result.emits)
        except ValueError as exc:
            self.workspace = SpectrumWorkspace((), None, (), (), None, None)
            self.status.setText(f"Spectrum records rejected: {exc}")
        else:
            self.status.setText(self.workspace.header())
        self.targets.blockSignals(True)
        self.targets.clear()
        for record in self.workspace.records:
            item = QListWidgetItem(record.summary_line())
            item.setData(Qt.UserRole, record.id)
            self.targets.addItem(item)
        self.targets.blockSignals(False)
        self._fill_leaderboard()
        if self.workspace.records:
            self.targets.setCurrentRow(0)
        else:
            self.plot.set_record(None)
            self.details.clear()
        return self.workspace

    def _fill_leaderboard(self) -> None:
        rows = self.workspace.leaderboard
        self.leaderboard.setRowCount(len(rows))
        fmt = lambda v, d=3: "—" if v is None else f"{v:.{d}f}"
        for i, r in enumerate(rows):
            cv = "—" if r.cv_rmse is None else f"{r.cv_rmse:.3f} ± {fmt(r.cv_rmse_std)}"
            for j, text in enumerate((r.task, r.name, r.family, cv, fmt(r.family_cv_rmse), fmt(r.test_rmse),
                                      fmt(r.test_r2), fmt(r.test_cosine), r.exported or "")):
                item = QTableWidgetItem(text)
                item.setToolTip(r.note)
                self.leaderboard.setItem(i, j, item)
        self.leaderboard.resizeColumnsToContents()
        if self.workspace.ablation:
            parts = [f"{a['with']} vs {a['without']}: ΔCV RMSE {a['cv_rmse_delta']:+.4f}, ΔTest RMSE {a['test_rmse_delta']:+.4f}"
                     for a in self.workspace.ablation]
            self.ablation.setText("Atomic → molecular cascade ablation (negative = pooled atomic predictions helped):\n" + "\n".join(parts))
        elif self.workspace.records:
            self.ablation.setText("Leaderboard is emitted only in Studio mode (studio_mode=true).")
        else:
            self.ablation.setText("")

    def _select(self, row: int) -> None:
        if not 0 <= row < len(self.workspace.records):
            return
        record = self.workspace.records[row]
        self.plot.set_record(record)
        lines = [record.honesty, ""]
        m = record.metrics
        if record.predicted is None:
            lines.append(f"No prediction: {record.inference}. The measured reference is still shown.")
        elif m:
            lines.append(f"Engine-emitted comparison: RMSE {m.get('rmse'):.4f}, cosine {m.get('cosine'):.3f}, "
                         f"peak {m.get('measured_peak_nm')} nm measured vs {m.get('predicted_peak_nm')} nm predicted.")
        if record.interval is not None:
            lines.append(record.interval.describe() + ".")
        lines.append("Split: " + {"test": "held out from training (generalisation evidence)",
                                  "train": "training member (fit quality only, not generalisation)"}.get(record.split, record.split))
        lines.append("")
        lines.extend("• " + format_stage(s) for s in record.stages)
        src = record.sources
        if src.get("uv_text"):
            lines += ["", "PubChem statement: " + str(src["uv_text"]), "Source: " + str(src.get("uv_url", ""))]
        elif src.get("nist_lines"):
            lines += ["", "NIST ASD lines: " + str(src["nist_lines"].get("url", ""))]
        ctx = self.workspace.geant4_context
        if ctx and ctx.get("available"):
            lines += ["", f"Geant4 context (same composition, declared density {ctx.get('density_g_per_cm3')} g/cm³): "
                          f"mean excitation energy {ctx.get('mean_excitation_energy_ev'):.2f} eV — not a model input."]
        self.details.setPlainText("\n".join(lines))

    # --- training job -----------------------------------------------------------------
    def training_started(self) -> None:
        self.train_button.setEnabled(False)
        self.use_button.setEnabled(False)
        self.training_log.clear()

    def training_message(self, text: str) -> None:
        self.training_log.appendPlainText(text)

    def training_finished(self, out_dir) -> None:
        self.train_button.setEnabled(True)
        self._trained_dir = str(out_dir)
        self.use_button.setEnabled(True)
        self.training_log.appendPlainText(f"Trained run ready: {out_dir}. 'Use trained run' sets data_dir; then run.")

    def training_failed(self, message: str) -> None:
        self.train_button.setEnabled(True)
        self.training_log.appendPlainText(message)
