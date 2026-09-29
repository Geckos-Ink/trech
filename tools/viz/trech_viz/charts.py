"""2D side-panel charts composited next to a 3D GIF frame.

Charts only *plot* data the run produced — a scenario's emitted per-frame ``samples`` / ``curves``
(``material_frame`` contract) or statistics of the recorded Geant4 trajectories (first-interaction
depths, energy deposited along the beam, boundary outcomes, …) — plus, where the run itself
reports one, the engine's formula prediction as a labelled comparison line. Every series point
carries the playback time at which it becomes known, so the panel fills in as the 3D replay
advances instead of showing the answer in advance.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

PANEL_BG = "#0d1019"
AXES_BG = "#121726"
TEXT = "#f4d6af"
GRID = "#2a3145"


@dataclass
class Series:
    label: str
    color: str
    x: np.ndarray
    y: np.ndarray
    # Playback time at which each point becomes known (same clock as ``now``); None = static.
    t: Optional[np.ndarray] = None
    style: str = "line"          # line | points | step | hist | bars | hline
    dashed: bool = False
    bins: Optional[np.ndarray] = None   # hist: bin edges over x
    normalize: Optional[float] = None   # hist: divide counts by this (fractions)
    width: float = 1.8
    alpha: float = 1.0
    weights: Optional[np.ndarray] = None  # hist: per-sample weights (e.g. MeV deposited)
    offset: float = 0.0                   # bars: x offset (side-by-side measured vs formula)
    bar_width: float = 0.6
    hatch: bool = False                   # bars: hollow hatched (formula) vs filled (measured)
    # Recomputed from the data revealed by ``now`` (a survival curve of the primaries seen so far).
    dynamic: Optional[Callable[[float], Tuple[np.ndarray, np.ndarray]]] = None
    reference: bool = False  # a comparison line: never widens a time-series chart's x range

    def visible(self, now: float) -> Tuple[np.ndarray, np.ndarray]:
        if self.dynamic is not None:
            x, y = self.dynamic(now)
            return np.asarray(x, dtype=float), np.asarray(y, dtype=float)
        if self.t is None:
            return self.x, self.y
        keep = self.t <= now
        return self.x[keep], self.y[keep]

    def visible_weights(self, now: float) -> Optional[np.ndarray]:
        if self.weights is None:
            return None
        if self.t is None:
            return self.weights
        return self.weights[self.t <= now]


@dataclass
class Chart:
    title: str
    x_label: str = ""
    y_label: str = ""
    series: List[Series] = field(default_factory=list)
    log_x: bool = False
    log_y: bool = False
    xlim: Optional[Tuple[float, float]] = None
    ylim: Optional[Tuple[float, float]] = None
    vlines: List[Tuple[float, str, str]] = field(default_factory=list)  # (x, label, color)
    categories: Optional[List[str]] = None   # bars: x are category indices
    cursor: bool = False                     # draw a vertical 'now' line at x = now * cursor_scale
    cursor_scale: float = 1.0
    note: str = ""

    def auto_limits(self) -> None:
        """Fix axes to the whole run's extent so they never jump while revealing."""
        xs = [s.x for s in self.series if s.x.size and s.style not in ("hline",)]
        data_xs = [s.x for s in self.series
                   if s.x.size and not s.reference and s.style not in ("hline",)]
        if data_xs and len(data_xs) < len(xs):
            xs = data_xs
        ys = [s.y for s in self.series if s.y.size and s.style not in ("hist",)]
        if self.xlim is None and xs:
            lo = float(min(np.nanmin(x) for x in xs))
            hi = float(max(np.nanmax(x) for x in xs))
            for s in self.series:
                if s.bins is not None:
                    lo, hi = min(lo, float(s.bins[0])), max(hi, float(s.bins[-1]))
            if hi <= lo:
                hi = lo + 1.0
            pad = 0.0 if self.log_x else 0.02 * (hi - lo)
            self.xlim = (lo - pad, hi + pad)
        if self.ylim is None and ys and not self.log_y:
            lo = float(min(np.nanmin(y) for y in ys))
            hi = float(max(np.nanmax(y) for y in ys))
            for s in self.series:
                if s.style == "hist" and s.x.size and s.bins is not None:
                    counts, _ = np.histogram(s.x, bins=s.bins, weights=s.weights)
                    top = float(counts.max()) / (s.normalize or 1.0)
                    hi = max(hi, top)
                    lo = min(lo, 0.0)
                if s.style == "bars":
                    lo = min(lo, 0.0)
            if hi <= lo:
                hi = lo + 1.0
            pad = 0.06 * (hi - lo)
            self.ylim = (lo - (pad if lo != 0.0 else 0.0), hi + pad)


def _mpl():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    return plt


class ChartPanel:
    """Renders a vertical stack of charts to an RGB array of a fixed pixel size."""

    def __init__(self, charts: Sequence[Chart], width: int, height: int):
        self.charts = [chart for chart in charts if chart.series]
        for chart in self.charts:
            chart.auto_limits()
        self.width, self.height = int(width), int(height)

    def __bool__(self) -> bool:
        return bool(self.charts)

    def render(self, now: float, cursor_now: Optional[float] = None) -> np.ndarray:
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return self._render(now, now if cursor_now is None else cursor_now)

    def _render(self, now: float, cursor_now: float) -> np.ndarray:
        plt = _mpl()
        dpi = 100.0
        fig = plt.figure(figsize=(self.width / dpi, self.height / dpi), dpi=dpi,
                         facecolor=PANEL_BG)
        n = len(self.charts)
        font = max(7.0, min(11.0, self.height / 62.0))
        top, bottom, gap = 0.035, 0.07, 0.11 * (3.0 / max(n, 3))
        avail = 1.0 - top - bottom - gap * (n - 1)
        each = avail / n
        for index, chart in enumerate(self.charts):
            y0 = 1.0 - top - (index + 1) * each - index * gap
            ax = fig.add_axes([0.17, y0, 0.78, each * 0.86])
            self._draw(ax, chart, now, font, cursor_now)
        fig.canvas.draw()
        image = np.asarray(fig.canvas.buffer_rgba())[:, :, :3].copy()
        plt.close(fig)
        if image.shape[0] != self.height or image.shape[1] != self.width:
            from PIL import Image

            image = np.asarray(Image.fromarray(image).resize((self.width, self.height)))
        return image

    @staticmethod
    def _draw(ax, chart: Chart, now: float, font: float, cursor_now: float) -> None:
        ax.set_facecolor(AXES_BG)
        for spine in ax.spines.values():
            spine.set_color(GRID)
        ax.tick_params(colors=TEXT, labelsize=font * 0.82, length=3)
        ax.grid(True, color=GRID, linewidth=0.6, alpha=0.8)
        ax.set_title(chart.title, color=TEXT, fontsize=font, loc="left", pad=3)
        if chart.x_label:
            ax.set_xlabel(chart.x_label, color=TEXT, fontsize=font * 0.85, labelpad=1)
        if chart.y_label:
            ax.set_ylabel(chart.y_label, color=TEXT, fontsize=font * 0.85, labelpad=2)
        if chart.log_x:
            ax.set_xscale("log")
        if chart.log_y:
            ax.set_yscale("log")
        handles = []
        for s in chart.series:
            x, y = s.visible(now)
            ls = "--" if s.dashed else "-"
            if s.style == "hist":
                if s.bins is None:
                    continue
                counts, edges = np.histogram(x, bins=s.bins, weights=s.visible_weights(now))
                values = counts / (s.normalize or 1.0)
                h = ax.stairs(values, edges, color=s.color, fill=True, alpha=0.45 * s.alpha,
                              label=s.label)
                ax.stairs(values, edges, color=s.color, linewidth=1.2)
                handles.append(h)
            elif s.style == "bars":
                if s.hatch:
                    h = ax.bar(x + s.offset, y, width=s.bar_width, facecolor="none",
                               edgecolor=s.color, hatch="///", linewidth=1.2, label=s.label)
                else:
                    h = ax.bar(x + s.offset, y, width=s.bar_width, color=s.color,
                               alpha=0.85 * s.alpha, label=s.label)
                handles.append(h)
            elif s.style == "points":
                h = ax.scatter(x, y, s=18, color=s.color, alpha=s.alpha, label=s.label,
                               zorder=3, edgecolors="none")
                handles.append(h)
            elif s.style == "hline":
                if y.size:
                    h = ax.axhline(float(y[0]), color=s.color, linestyle=ls, linewidth=s.width,
                                   alpha=s.alpha, label=s.label)
                    handles.append(h)
            elif s.style == "step":
                if x.size:
                    (h,) = ax.step(x, y, where="post", color=s.color, linestyle=ls,
                                   linewidth=s.width, alpha=s.alpha, label=s.label)
                    handles.append(h)
            else:
                if x.size:
                    (h,) = ax.plot(x, y, color=s.color, linestyle=ls, linewidth=s.width,
                                   alpha=s.alpha, label=s.label)
                    handles.append(h)
                    if s.t is not None and x.size:
                        ax.plot([x[-1]], [y[-1]], "o", color=s.color, markersize=3.5)
        for rank, (x_value, label, color) in enumerate(chart.vlines):
            ax.axvline(x_value, color=color, linestyle=":", linewidth=1.3)
            if label:
                lo, hi = ax.get_xlim()
                right = (x_value - lo) > 0.6 * (hi - lo) if hi > lo else False
                ax.annotate(label, (x_value, 1.0), xycoords=("data", "axes fraction"),
                            xytext=(-3 if right else 3, -10 - 12 * rank),
                            textcoords="offset points",
                            color=color, fontsize=font * 0.72, ha="right" if right else "left")
        if chart.cursor:
            ax.axvline(cursor_now * chart.cursor_scale, color="#ffffff", linewidth=0.8, alpha=0.5)
        if chart.categories is not None:
            ax.set_xticks(range(len(chart.categories)))
            ax.set_xticklabels(chart.categories, fontsize=font * 0.78, color=TEXT)
        if chart.xlim is not None:
            lo, hi = chart.xlim
            if chart.log_x:
                lo = max(lo, 1e-30)
            if hi > lo:
                ax.set_xlim(lo, hi)
        if chart.ylim is not None:
            ax.set_ylim(*chart.ylim)
        labelled = [h for h in handles if not str(h.get_label()).startswith("_")]
        if labelled:
            legend = ax.legend(handles=labelled, fontsize=font * 0.72,
                               loc="upper right" if chart.note else "best",
                               facecolor=AXES_BG, edgecolor=GRID, framealpha=0.85,
                               labelcolor=TEXT, handlelength=1.4, borderpad=0.3)
            legend.get_frame().set_linewidth(0.6)
        if chart.note:
            ax.text(0.01, 0.97, chart.note, transform=ax.transAxes, ha="left", va="top",
                    color=TEXT, fontsize=font * 0.7, alpha=0.9)


def compose(left: np.ndarray, right: Optional[np.ndarray]) -> np.ndarray:
    """Place the chart panel to the right of the 3D frame (same height)."""
    if right is None:
        return left
    if right.shape[0] != left.shape[0]:
        from PIL import Image

        right = np.asarray(Image.fromarray(right).resize((right.shape[1], left.shape[0])))
    return np.ascontiguousarray(np.hstack([left, right]))


# --------------------------------------------------------------------------- material frames


def _time_value(frame, key: str) -> Optional[float]:
    if key in ("time", "physical_time_s"):
        return float(frame.physical_time_s)
    value = (frame.samples or {}).get(key)
    return float(value) if isinstance(value, (int, float)) and math.isfinite(value) else None


def charts_from_frames(frames: Sequence) -> List[Chart]:
    """Build charts from the frames' emitted ``charts`` spec, ``samples`` and ``curves``.

    Time-series points become known at their frame's physical time; per-frame ``curves`` (a
    g(r) that sharpens, an MSD, a spectrum) are drawn as the latest snapshot at or before now.
    """
    spec: List[Dict] = []
    for frame in frames:
        if frame.charts:
            spec = list(frame.charts)
    charts: List[Chart] = []
    for entry in spec:
        chart_id = str(entry.get("id") or entry.get("title") or len(charts))
        x_key = str(entry.get("x") or "time")
        x_scale = float(entry.get("x_scale") or 1.0)
        chart = Chart(title=str(entry.get("title") or chart_id),
                      x_label=str(entry.get("x_label") or ""),
                      y_label=str(entry.get("y_label") or ""),
                      log_x=bool(entry.get("log_x")), log_y=bool(entry.get("log_y")))
        if isinstance(entry.get("x_range"), list) and len(entry["x_range"]) == 2:
            chart.xlim = (float(entry["x_range"][0]), float(entry["x_range"][1]))
        if isinstance(entry.get("y_range"), list) and len(entry["y_range"]) == 2:
            chart.ylim = (float(entry["y_range"][0]), float(entry["y_range"][1]))
        chart.note = str(entry.get("note") or "")
        if isinstance(entry.get("categories"), list):
            chart.categories = [str(c) for c in entry["categories"]]
        for series in entry.get("series") or []:
            key = str(series.get("key") or "")
            xs, ys, ts = [], [], []
            for frame in frames:
                x = _time_value(frame, x_key)
                y = _time_value(frame, key) if key else None
                if x is None or y is None:
                    continue
                xs.append(x * x_scale)
                ys.append(y * float(series.get("scale") or 1.0))
                # Revealed in playback order (frames sharing a physical time stay ordered).
                ts.append(float(frame.playback_time_s))
            if xs:
                chart.series.append(Series(
                    label=str(series.get("label") or key), color=str(series.get("color") or TEXT),
                    x=np.asarray(xs), y=np.asarray(ys), t=np.asarray(ts),
                    style=str(series.get("style") or "line"), dashed=bool(series.get("dashed"))))
        for ref in entry.get("reference") or []:
            chart.series.append(Series(
                label=str(ref.get("label") or "reference"), color=str(ref.get("color") or "#9aa4b8"),
                x=np.asarray(ref.get("x") or [], dtype=float),
                y=np.asarray(ref.get("y") or [], dtype=float),
                style=str(ref.get("style") or "line"), dashed=ref.get("dashed", True) is not False,
                alpha=0.9, reference=bool(entry.get("series"))))
        for vline in entry.get("vlines") or []:
            chart.vlines.append((float(vline.get("x", 0.0)), str(vline.get("label") or ""),
                                 str(vline.get("color") or "#9aa4b8")))
        if entry.get("cursor") and x_key == "time":
            chart.cursor = True
            chart.cursor_scale = x_scale
        chart._curve_id = chart_id  # type: ignore[attr-defined]
        charts.append(chart)
    return charts


class FrameCharts:
    """Chart panel for held material frames: time series + per-frame curve snapshots."""

    def __init__(self, frames: Sequence, width: int, height: int):
        self.frames = list(frames)
        self.charts = charts_from_frames(self.frames)
        self.width, self.height = width, height
        # Per chart id: sorted (time, curves) snapshots.
        self.snapshots: Dict[str, List[Tuple[float, List[Dict]]]] = {}
        for frame in self.frames:
            per_chart: Dict[str, List[Dict]] = {}
            for curve in frame.curves or []:
                per_chart.setdefault(str(curve.get("chart") or ""), []).append(curve)
            for chart_id, curves in per_chart.items():
                bucket = self.snapshots.setdefault(chart_id, [])
                snapshot = (float(frame.playback_time_s), curves)
                # A later frame at the same physical time supersedes the earlier snapshot.
                if bucket and bucket[-1][0] == snapshot[0]:
                    bucket[-1] = snapshot
                else:
                    bucket.append(snapshot)
        # Fix axis limits over every snapshot of each chart.
        for chart in self.charts:
            snaps = self.snapshots.get(getattr(chart, "_curve_id", ""), [])
            static = [self._curve_series(c) for _, curves in snaps for c in curves]
            probe = Chart(chart.title, series=list(chart.series) + static,
                          log_x=chart.log_x, log_y=chart.log_y, xlim=chart.xlim, ylim=chart.ylim)
            probe.auto_limits()
            chart.xlim, chart.ylim = probe.xlim, probe.ylim

    def __bool__(self) -> bool:
        return bool(self.charts)

    @staticmethod
    def _curve_series(curve: Dict) -> Series:
        return Series(label=str(curve.get("label") or ""), color=str(curve.get("color") or TEXT),
                      x=np.asarray(curve.get("x") or [], dtype=float),
                      y=np.asarray(curve.get("y") or [], dtype=float),
                      style=str(curve.get("style") or "line"), dashed=bool(curve.get("dashed")))

    def render(self, now: float, cursor_now: Optional[float] = None) -> np.ndarray:
        """``now`` is the frame's playback time (reveal order); ``cursor_now`` its physical time."""
        charts = []
        for chart in self.charts:
            current = [s for s in chart.series]
            snaps = self.snapshots.get(getattr(chart, "_curve_id", ""), [])
            latest = None
            for time_s, curves in snaps:
                if time_s <= now + 1e-30:
                    latest = curves
            if latest:
                current += [self._curve_series(c) for c in latest]
            charts.append(Chart(chart.title, chart.x_label, chart.y_label, current,
                                chart.log_x, chart.log_y, chart.xlim, chart.ylim,
                                chart.vlines, chart.categories, chart.cursor,
                                chart.cursor_scale, chart.note))
        panel = ChartPanel([], self.width, self.height)
        panel.charts = [c for c in charts if c.series or c.vlines]
        if not panel.charts:
            panel.charts = charts
        return panel.render(now, cursor_now)
