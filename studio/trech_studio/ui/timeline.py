"""Timeline: a playback bar that scrubs a run's animation in the 3D viewport.

The timeline drives one scalar cursor (in the engine's own units — ``time_ns`` for sampled
trajectories, ``time_s`` for particle frames) and emits it as ``cursor_changed``. The main
window forwards that to the viewport, which either grows the trajectory polylines up to the
cursor or shows the particle frame at it. Nothing here is computed physics — it replays what
the engine emitted, on the engine's clock (studio/AGENTS.md honesty rule).

Playback traverses the whole timeline over a fixed *wall-clock* window (``_play_seconds`` at
1×), independent of whether the physical span is nanoseconds or seconds, so a preview always
reads at a watchable speed. On load the cursor sits at the end (the complete, pre-elaborated
result is shown); pressing Play rewinds to the start and animates.
"""

from __future__ import annotations

import time
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QWidget,
)

from ..render.playback import Playback

_SLIDER_MAX = 1000
_PLAY_SECONDS = 6.0            # wall-clock seconds to traverse the whole timeline at 1×
_SPEEDS = (0.25, 0.5, 1.0, 2.0, 4.0)


class Timeline(QWidget):
    """Play / pause / scrub control over a :class:`Playback`."""

    cursor_changed = Signal(float)  # cursor in native units (ns for trajectories, s for frames)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._playback: Optional[Playback] = None
        self._frac = 1.0               # normalised cursor in [0, 1]
        self._playing = False
        self._speed = 1.0
        self._last_monotonic: Optional[float] = None

        self._timer = QTimer(self)
        self._timer.setInterval(33)    # ~30 fps preview
        self._timer.timeout.connect(self._on_tick)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        self._play_button = QPushButton("▶ Play", self)
        self._play_button.setFixedWidth(88)
        self._play_button.clicked.connect(self._toggle_play)
        layout.addWidget(self._play_button)

        self._reset_button = QPushButton("⟲", self)
        self._reset_button.setFixedWidth(34)
        self._reset_button.setToolTip("Rewind to start")
        self._reset_button.clicked.connect(self._rewind)
        layout.addWidget(self._reset_button)

        self._slider = QSlider(Qt.Horizontal, self)
        self._slider.setRange(0, _SLIDER_MAX)
        self._slider.setValue(_SLIDER_MAX)
        self._slider.sliderPressed.connect(self._pause)
        self._slider.valueChanged.connect(self._on_slider)
        layout.addWidget(self._slider, 1)

        self._time_label = QLabel("—", self)
        self._time_label.setMinimumWidth(220)
        self._time_label.setAlignment(Qt.AlignVCenter | Qt.AlignRight)
        layout.addWidget(self._time_label)

        self._loop_check = QCheckBox("Loop", self)
        self._loop_check.setChecked(True)
        layout.addWidget(self._loop_check)

        self._speed_combo = QComboBox(self)
        for s in _SPEEDS:
            self._speed_combo.addItem(f"{s:g}×", s)
        self._speed_combo.setCurrentIndex(_SPEEDS.index(1.0))
        self._speed_combo.currentIndexChanged.connect(self._on_speed)
        layout.addWidget(self._speed_combo)

        self.set_playback(None)

    # --- public API ---------------------------------------------------------------------

    def set_playback(self, playback: Optional[Playback]) -> None:
        """Bind a new run's playback (or ``None``). Resets the cursor to the end and pauses."""
        self._pause()
        self._playback = playback
        active = bool(playback is not None and not playback.is_empty)
        # bool(...) guards against numpy scalars in t_min/t_max (Qt setEnabled wants a real bool).
        scrubbable = bool(active and playback.t_max > playback.t_min)

        self._play_button.setEnabled(scrubbable)
        self._reset_button.setEnabled(scrubbable)
        self._slider.setEnabled(scrubbable)
        self._loop_check.setEnabled(scrubbable)
        self._speed_combo.setEnabled(scrubbable)

        self._frac = 1.0
        self._set_slider_frac(1.0)
        if active:
            self._emit_cursor()
        else:
            self._time_label.setText("no playback for this run")

    def set_cursor(self, t: float) -> bool:
        """Move the cursor to an engine-native time (used by the emit inspector's jump).

        Returns False when there is no scrubbable playback or the time is outside its span —
        the caller is asking for a moment this run never emitted, and the cursor stays put.
        """
        pb = self._playback
        if pb is None or pb.is_empty or pb.t_max <= pb.t_min:
            return False
        if t < pb.t_min or t > pb.t_max:
            return False
        self._pause()
        self._frac = (t - pb.t_min) / (pb.t_max - pb.t_min)
        self._set_slider_frac(self._frac)
        self._emit_cursor()
        return True

    def cursor_time(self) -> float:
        """The cursor's current engine-native time."""
        return self._cursor_time()

    # --- playback loop ------------------------------------------------------------------

    def _toggle_play(self) -> None:
        if self._playing:
            self._pause()
        else:
            self._play()

    def _play(self) -> None:
        if self._playback is None or self._playback.is_empty:
            return
        if self._frac >= 1.0:
            self._frac = 0.0          # rewind before playing from the end
        self._playing = True
        self._play_button.setText("⏸ Pause")
        self._last_monotonic = time.monotonic()
        self._timer.start()

    def _pause(self) -> None:
        self._playing = False
        self._timer.stop()
        self._last_monotonic = None
        self._play_button.setText("▶ Play")

    def _rewind(self) -> None:
        self._pause()
        self._frac = 0.0
        self._set_slider_frac(0.0)
        self._emit_cursor()

    def _on_tick(self) -> None:
        now = time.monotonic()
        dt = 0.0 if self._last_monotonic is None else (now - self._last_monotonic)
        self._last_monotonic = now
        self._frac += (dt / _PLAY_SECONDS) * self._speed
        if self._frac >= 1.0:
            if self._loop_check.isChecked():
                self._frac = 0.0
            else:
                self._frac = 1.0
                self._pause()
        self._set_slider_frac(self._frac)
        self._emit_cursor()

    # --- controls -----------------------------------------------------------------------

    def _on_slider(self, value: int) -> None:
        # Only react to user drags — programmatic updates block signals via _set_slider_frac.
        self._frac = value / float(_SLIDER_MAX)
        self._emit_cursor()

    def _on_speed(self, index: int) -> None:
        self._speed = float(self._speed_combo.itemData(index))

    def _set_slider_frac(self, frac: float) -> None:
        self._slider.blockSignals(True)
        self._slider.setValue(int(round(max(0.0, min(1.0, frac)) * _SLIDER_MAX)))
        self._slider.blockSignals(False)

    # --- cursor -------------------------------------------------------------------------

    def _cursor_time(self) -> float:
        pb = self._playback
        if pb is None:
            return 0.0
        return pb.t_min + self._frac * (pb.t_max - pb.t_min)

    def _emit_cursor(self) -> None:
        pb = self._playback
        if pb is None or pb.is_empty:
            return
        t = self._cursor_time()
        self._update_label(t)
        self.cursor_changed.emit(t)

    def _update_label(self, t: float) -> None:
        pb = self._playback
        if pb is None or pb.is_empty:
            self._time_label.setText("—")
            return
        if pb.kind == "particles":
            idx = pb.frame_index_at(t)
            frame = pb.frames[idx] if pb.frames else None
            phase = f" · {frame.phase}" if frame and frame.phase else ""
            physical = ""
            if frame and frame.physical_time_s is not None and pb.time_accelerated:
                if frame.physical_time_s >= 60.0:
                    physical_value = f"{frame.physical_time_s / 60.0:.3g} min"
                else:
                    physical_value = f"{frame.physical_time_s:.3g} s"
                scale = f" · {frame.time_scale:.0f}× clock" if frame.time_scale > 1.0 else ""
                physical = f" · physical {physical_value}{scale}"
            self._time_label.setText(
                f"frame {idx + 1}/{pb.frame_count} · t = {t:.4g} {pb.unit}{physical}{phase}"
            )
        else:
            self._time_label.setText(
                f"t = {t:.4g} / {pb.t_max:.4g} {pb.unit} · {pb.count_at(t)}/{pb.segment_count} segs"
            )
