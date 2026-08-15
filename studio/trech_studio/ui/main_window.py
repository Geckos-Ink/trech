"""The Studio main window: a dockable editor shell wiring the panels to the engine.

Layout (industry-standard editor shape):
    ┌──────────────┬───────────────────────────┬──────────────┐
    │  Outliner    │                           │  Inspector   │
    ├──────────────┤        3D Viewport        ├──────────────┤
    │ Code editor  │        (wgpu)             │              │
    └──────────────┴───────────────────────────┴──────────────┘
    │              Timeline                                    │
    │   Console · Run summary · Emits (tabbed)                 │
    └──────────────────────────────────────────────────────────┘

The window owns the engine bridge objects (locator + runner + lab session) and the current
``SceneModel``; panels are pure views/controllers over those.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDockWidget,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QWidget,
)

from ..engine.locator import EngineLocation, locate_engine
from ..engine.outputs import RunResult, load_run_result
from ..engine.parameters import inspect_scenario
from ..engine.runner import EngineRunner
from ..render.playback import build_playback
from ..render.viewport import WGPU_AVAILABLE, create_viewport
from ..scene.loader import placeholder_scene, scene_from_output_dir, scene_from_viz_json
from ..scene.model import SceneModel
from ..precision import build_precision_report
from ..settings import StudioSettings
from ..run_summary import build_run_summary
from ..cascade import build_scale_ladder
from .cascade import ScaleLadderPanel
from .console import Console
from .emits import EmitInspector
from .inspector import Inspector
from .outliner import Outliner
from .run_summary import RunSummaryPanel
from .code_editor import CodeEditor
from .scenarios import ScenarioBrowser
from .scenario_options import ScenarioOptions
from .timeline import Timeline


class StudioWindow(QMainWindow):
    def __init__(self, settings: StudioSettings) -> None:
        super().__init__()
        self.settings = settings
        self.setWindowTitle("TRECH Studio")
        self.resize(1500, 950)

        self._engine: EngineLocation = locate_engine(settings.repo_root, settings.engine_bin)
        self._runner = EngineRunner(self._engine, self)
        self._scene: SceneModel = placeholder_scene()

        # --- central viewport --------------------------------------------------------
        self.viewport = create_viewport(background=settings.background, parent=self)
        self.setCentralWidget(self.viewport)

        # --- docks -------------------------------------------------------------------
        self.scenarios = ScenarioBrowser([settings.examples_root()], self)
        self.outliner = Outliner(self)
        self.inspector = Inspector(self)
        self.scenario_options = ScenarioOptions(self)
        self.console = Console(self)
        self.run_summary = RunSummaryPanel(self)
        self.emit_inspector = EmitInspector(self)
        self.scale_ladder = ScaleLadderPanel(self)
        self.code_editor = CodeEditor(self)
        self.timeline = Timeline(self)
        self.timeline.setMaximumHeight(74)

        scen_dock = self._add_dock("Scenarios", self.scenarios, Qt.LeftDockWidgetArea)
        out_dock = self._add_dock("Outliner", self.outliner, Qt.LeftDockWidgetArea)
        self.tabifyDockWidget(scen_dock, out_dock)
        scen_dock.raise_()
        self._add_dock("Scenario", self.code_editor, Qt.LeftDockWidgetArea)
        options_dock = self._add_dock("Options", self.scenario_options, Qt.RightDockWidgetArea)
        inspector_dock = self._add_dock("Inspector", self.inspector, Qt.RightDockWidgetArea)
        self.splitDockWidget(options_dock, inspector_dock, Qt.Vertical)
        timeline_dock = self._add_dock("Timeline", self.timeline, Qt.BottomDockWidgetArea)
        console_dock = self._add_dock("Console", self.console, Qt.BottomDockWidgetArea)
        self.splitDockWidget(timeline_dock, console_dock, Qt.Vertical)
        summary_dock = self._add_dock("Run summary", self.run_summary, Qt.BottomDockWidgetArea)
        emits_dock = self._add_dock("Emits", self.emit_inspector, Qt.BottomDockWidgetArea)
        ladder_dock = self._add_dock("Scale ladder", self.scale_ladder, Qt.BottomDockWidgetArea)
        self.tabifyDockWidget(console_dock, summary_dock)
        self.tabifyDockWidget(summary_dock, emits_dock)
        self.tabifyDockWidget(emits_dock, ladder_dock)
        console_dock.raise_()
        self._summary_dock = summary_dock

        self._build_menu()
        self._wire_signals()
        self._apply_scene(self._scene)
        self._announce_engine()

    # --- assembly ----------------------------------------------------------------------

    def _add_dock(self, title: str, widget: QWidget, area: Qt.DockWidgetArea) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(f"dock_{title.lower()}")
        dock.setWidget(widget)
        dock.setAllowedAreas(Qt.AllDockWidgetAreas)
        self.addDockWidget(area, dock)
        return dock

    def _build_menu(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu("&File")
        file_menu.addAction("Open scenario…", self._pick_scenario)
        file_menu.addAction("Open run output…", self._pick_output_dir)
        file_menu.addSeparator()
        file_menu.addAction("Save scenario", self._save_scenario)
        file_menu.addSeparator()
        file_menu.addAction("Quit", self.close)

        run_menu = bar.addMenu("&Run")
        run_menu.addAction("Run scenario ▶", self._run_scenario)
        run_menu.addAction("Stop", self._runner.stop)

    def _wire_signals(self) -> None:
        self.outliner.node_selected.connect(self.inspector.show_node)
        self.code_editor.run_requested.connect(self._run_scenario)
        self.code_editor.save_requested.connect(self._save_scenario)
        self.scenarios.scenario_activated.connect(self._open_scenario_from_browser)
        self.timeline.cursor_changed.connect(self.viewport.set_playback_time)
        # The emit inspector jumps the shared cursor; the timeline stays the only clock.
        self.emit_inspector.cursor_requested.connect(self._jump_to_emit_time)

        self._runner.started.connect(lambda: self.console.log_info("run started"))
        self._runner.stdout_line.connect(self.console.log_stdout)
        self._runner.stderr_line.connect(self.console.log_stderr)
        self._runner.finished.connect(self._on_run_finished)
        self._runner.failed.connect(lambda msg: self.console.log_stderr(f"run failed: {msg}"))

    def _announce_engine(self) -> None:
        if self._engine.available:
            self.console.log_info(f"engine: {self._engine.describe()}")
        else:
            self.console.log_stderr(f"engine: {self._engine.describe()}")
        if not WGPU_AVAILABLE:
            self.console.log_stderr("wgpu unavailable — 3D viewport running in fallback mode.")
        self.statusBar().showMessage(
            f"engine {'ready' if self._engine.available else 'missing'} · "
            f"viewport {'wgpu' if WGPU_AVAILABLE else 'fallback'}"
        )

    # --- scene / run flow --------------------------------------------------------------

    def _apply_scene(self, scene: SceneModel) -> None:
        self._scene = scene
        self.outliner.set_scene(scene)
        self.inspector.set_scene(scene)
        self.inspector.set_precision(None)
        if hasattr(self.viewport, "set_scene"):
            self.viewport.set_scene(scene)

    def _clear_playback(self) -> None:
        self.viewport.set_playback(None)
        self.timeline.set_playback(None)
        self.emit_inspector.set_playback(None)

    def _jump_to_emit_time(self, t: float) -> None:
        if not self.timeline.set_cursor(t):
            self.console.log_stderr(
                f"timeline: {t:g} is outside this run's playable span — cursor unchanged"
            )

    def open_output_dir(self, output_dir: Path) -> None:
        output_dir = Path(output_dir)
        scene = scene_from_output_dir(output_dir)
        if scene is not None:
            self._apply_scene(scene)
        else:
            self.console.log_stderr(f"no trech_viz_scene.json in {output_dir}")
        result = load_run_result(output_dir)
        self.run_summary.show_summary(build_run_summary(result))
        self.emit_inspector.set_run(result)
        self.scale_ladder.show_ladder(build_scale_ladder(result, str(output_dir)))

        # Build the animation preview (trajectories, or a particle family like fluid_frame) and
        # hand it to the viewport + timeline. Everything here is engine output on the engine clock.
        trajectories = result.load_trajectories(limit=4000)
        playback = build_playback(trajectories, result.emits)
        self.viewport.set_playback(playback)
        self.timeline.set_playback(playback)
        self.emit_inspector.set_playback(playback)
        precision = build_precision_report(
            result, playback, scene=self._scene,
            output_px=(max(1, self.viewport.width()), max(1, self.viewport.height())),
            supersample=1, purpose="preview",
        )
        self.inspector.set_precision(precision)
        self.console.log_info(precision.preview_summary())
        self.statusBar().showMessage(precision.preview_summary())
        if not playback.is_empty:
            self.console.log_info(f"timeline: {playback.label} ({playback.kind})")
        else:
            self.console.log_info("timeline: no trajectories or playable frames in this run")

    def open_scenario(self, path: Path) -> None:
        path = Path(path)
        self.code_editor.load_file(path)
        self._refresh_scenario_parameters(path)

    def _refresh_scenario_parameters(self, path: Path, preserve_values: bool = True) -> bool:
        """Evaluate declarations through TRECH itself; never parse JavaScript in Studio."""
        if not self._engine.available:
            self.scenario_options.show_error(
                "The TRECH engine is unavailable, so custom scenario options cannot be inspected."
            )
            return False
        try:
            inspection = inspect_scenario(self._engine, path)
        except (OSError, RuntimeError, ValueError) as exc:
            self.scenario_options.show_error(f"Could not inspect scenario options:\n{exc}")
            self.console.log_stderr(f"scenario inspection failed: {exc}")
            return False
        self.scenario_options.set_parameters(
            inspection.parameters, preserve_values=preserve_values
        )
        if inspection.parameters:
            self.console.log_info(
                f"scenario options: {len(inspection.parameters)} typed value(s)"
            )
        return True

    def _open_scenario_from_browser(self, path: str) -> None:
        """Open a scenario picked in the browser; auto-load its last run if one exists."""
        p = Path(path)
        self.open_scenario(p)
        if p.suffix.lower() == ".js":
            out_dir = self.settings.output_root / f"studio_{p.stem}"
            if (out_dir / "trech_viz_scene.json").is_file():
                self.console.log_info(f"loading existing run for {p.name}")
                self.open_output_dir(out_dir)
                return
        self._clear_playback()

    def _pick_scenario(self) -> None:
        start = str(self.settings.examples_dir())
        path, _ = QFileDialog.getOpenFileName(self, "Open scenario", start, "Scenario (*.js)")
        if path:
            self.open_scenario(Path(path))

    def _pick_output_dir(self) -> None:
        start = str(self.settings.output_root.parent)
        path = QFileDialog.getExistingDirectory(self, "Open run output directory", start)
        if path:
            self.open_output_dir(Path(path))

    def _save_scenario(self) -> None:
        saved = self.code_editor.save()
        if saved is not None:
            self.console.log_info(f"saved {saved}")

    def _run_scenario(self) -> None:
        if not self._engine.available:
            QMessageBox.warning(self, "Engine missing", self._engine.describe())
            return
        experiment = self.code_editor.current_path()
        if experiment is None:
            QMessageBox.information(self, "No scenario", "Open a scenario .js first.")
            return
        # Save edits before running so what runs matches what is shown.
        self.code_editor.save()
        if not self._refresh_scenario_parameters(experiment, preserve_values=True):
            return

        out_dir = self.settings.output_root / f"studio_{experiment.stem}"
        self.console.log_info(f"running {experiment.name} -> {out_dir}")
        self._runner.run(
            experiment, out_dir, extra_args=self.scenario_options.command_args()
        )

    def _on_run_finished(self, exit_code: int, output_dir: Path) -> None:
        if exit_code == 0:
            self.console.log_info(f"run finished OK -> {output_dir}")
            self.open_output_dir(output_dir)
        else:
            self.console.log_stderr(f"run exited with code {exit_code}")

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        self._runner.stop()
        super().closeEvent(event)
