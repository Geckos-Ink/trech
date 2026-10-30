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
import json
import uuid
from typing import Optional

from PySide6.QtCore import Qt, QTimer
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
from ..engine.chemistry import read_scene, write_scene, stage_scene_parameters
from ..engine.runner import EngineRunner
from ..engine.quantum import QuantumReferenceJob, geometry_request
from ..engine.preview import PreviewExport
from ..render.playback import build_playback, build_material_frame_playback
from ..render.probability import probability_views, build_probability_playback
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
from .adaptive_controls import AdaptiveControls
from .chemistry import ChemistryPanel
from .processes import ProcessesPanel


class StudioWindow(QMainWindow):
    def __init__(self, settings: StudioSettings) -> None:
        super().__init__()
        self.settings = settings
        self.setWindowTitle("TRECH Studio")
        self.resize(1500, 950)

        self._engine: EngineLocation = locate_engine(settings.repo_root, settings.engine_bin)
        self._runner = EngineRunner(self._engine, self)
        self._preview_export = PreviewExport(settings.repo_root, self)
        self._scene: SceneModel = placeholder_scene()

        # --- central viewport --------------------------------------------------------
        self.viewport = create_viewport(background=settings.background, parent=self)
        self.setCentralWidget(self.viewport)

        # --- docks -------------------------------------------------------------------
        self.scenarios = ScenarioBrowser([settings.examples_root()], self)
        self.outliner = Outliner(self)
        self.inspector = Inspector(self)
        self.scenario_options = ScenarioOptions(self)
        self.adaptive_controls = AdaptiveControls(settings.target_fps, self)
        self.chemistry = ChemistryPanel(self)
        self._quantum_job = QuantumReferenceJob(settings.repo_root, self)
        self.console = Console(self)
        self.run_summary = RunSummaryPanel(self)
        self.emit_inspector = EmitInspector(self)
        self.scale_ladder = ScaleLadderPanel(self)
        self.code_editor = CodeEditor(self)
        self.processes = ProcessesPanel(self)
        self.timeline = Timeline(self)
        self.timeline.setMaximumHeight(74)

        scen_dock = self._add_dock("Scenarios", self.scenarios, Qt.LeftDockWidgetArea)
        out_dock = self._add_dock("Outliner", self.outliner, Qt.LeftDockWidgetArea)
        self.tabifyDockWidget(scen_dock, out_dock)
        scen_dock.raise_()
        self._code_dock = self._add_dock("Scenario", self.code_editor, Qt.LeftDockWidgetArea)
        options_dock = self._add_dock("Options", self.scenario_options, Qt.RightDockWidgetArea)
        adaptive_dock = self._add_dock("Precision and resources", self.adaptive_controls, Qt.RightDockWidgetArea)
        self.tabifyDockWidget(options_dock, adaptive_dock)
        self._chemistry_dock = self._add_dock("Chemistry", self.chemistry, Qt.RightDockWidgetArea)
        self.tabifyDockWidget(options_dock, self._chemistry_dock)
        options_dock.raise_()
        inspector_dock = self._add_dock("Inspector", self.inspector, Qt.RightDockWidgetArea)
        self.splitDockWidget(options_dock, inspector_dock, Qt.Vertical)
        timeline_dock = self._add_dock("Timeline", self.timeline, Qt.BottomDockWidgetArea)
        console_dock = self._add_dock("Console", self.console, Qt.BottomDockWidgetArea)
        self._console_dock = console_dock
        self.splitDockWidget(timeline_dock, console_dock, Qt.Vertical)
        summary_dock = self._add_dock("Run summary", self.run_summary, Qt.BottomDockWidgetArea)
        emits_dock = self._add_dock("Emits", self.emit_inspector, Qt.BottomDockWidgetArea)
        ladder_dock = self._add_dock("Scale ladder", self.scale_ladder, Qt.BottomDockWidgetArea)
        processes_dock = self._add_dock("Processes", self.processes, Qt.BottomDockWidgetArea)
        self._script_docks = {"options": options_dock, "scenario": self._code_dock,
                              "processes": processes_dock, "emits": emits_dock,
                              "scale_ladder": ladder_dock}
        self.tabifyDockWidget(console_dock, summary_dock)
        self.tabifyDockWidget(summary_dock, emits_dock)
        self.tabifyDockWidget(emits_dock, ladder_dock)
        self.tabifyDockWidget(ladder_dock, processes_dock)
        self._processes_dock = processes_dock
        self._options_dock = options_dock
        console_dock.raise_()
        self._summary_dock = summary_dock

        self._build_menu()
        self._wire_signals()
        self._apply_render_budget()
        self._apply_scene(self._scene)
        self._announce_engine()
        QTimer.singleShot(0, self._balance_docks)

    def _balance_docks(self):
        # Leave room for the viewport instead of accepting large hidden-panel hints.
        self.resizeDocks([self._code_dock, self._options_dock], [320, 350], Qt.Horizontal)
        self.resizeDocks([self._console_dock], [180], Qt.Vertical)

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
        preview_menu = bar.addMenu("&Preview")
        preview_menu.addAction("Export image…", lambda: self._export_preview(False))
        preview_menu.addAction("Export animation (GIF + MP4)…", lambda: self._export_preview(True))
        preview_menu.addAction("Cancel export", self._preview_export.stop)
        chemistry_menu = bar.addMenu("&Chemistry")
        chemistry_menu.addAction("Open chemistry workspace", self._open_chemistry)
        chemistry_menu.addAction("Run chemistry experiment ▶", self._run_chemistry)
        chemistry_menu.addAction("Atomic core/valence reference (Ne)", lambda: self.open_scenario(self.settings.examples_dir()/"chemistry_atomic_levels_reference"/"chemistry_atomic_levels_reference.js"))

    def _wire_signals(self) -> None:
        self.chemistry.open_requested.connect(self._open_chemistry)
        self.chemistry.run_requested.connect(self._run_chemistry)
        self.chemistry.scaffold_requested.connect(self._load_chemistry_scaffold)
        self.chemistry.import_requested.connect(self._import_chemistry_scene)
        self.chemistry.export_requested.connect(self._export_chemistry_scene)
        self.chemistry.view_requested.connect(self._set_probability_view)
        self.chemistry.field_explorer.display_changed.connect(self._set_density_display)
        self.chemistry.quantum_requested.connect(self._calculate_quantum_reference)
        self._quantum_job.message.connect(self.console.log_info)
        self._quantum_job.finished.connect(self._quantum_reference_ready)
        self._quantum_job.failed.connect(self._quantum_reference_failed)
        self.adaptive_controls.render_changed.connect(self._apply_render_budget)
        if hasattr(self.viewport, "precision_changed"):
            self.viewport.precision_changed.connect(self.adaptive_controls.show_precision)
        self.outliner.node_selected.connect(self.inspector.show_node)
        self.code_editor.run_requested.connect(self._run_scenario)
        self.code_editor.save_requested.connect(self._save_scenario)
        self.processes.streams.currentIndexChanged.connect(self._select_recorded_stream)
        self.scenarios.scenario_activated.connect(self._open_scenario_from_browser)
        self.timeline.cursor_changed.connect(self.viewport.set_playback_time)
        self.timeline.cursor_changed.connect(self.processes.set_cursor)
        self._preview_export.message.connect(self.console.log_info)
        self._preview_export.failed.connect(self.console.log_stderr)
        self._preview_export.finished.connect(lambda prefix: self.console.log_info(f"Preview saved: {prefix} (.png / .gif / .mp4 / .json as available)"))
        self.timeline.cursor_changed.connect(self.chemistry.probability_details.set_cursor)
        self.timeline.cursor_changed.connect(self.chemistry.field_explorer.set_cursor)
        self.timeline.cursor_changed.connect(self.chemistry.electron_levels.set_cursor)
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
        self._loaded_run = None
        self._loaded_trajectories = []
        self.processes.set_streams([])
        self.processes.set_playback(None)
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
        self._loaded_run = result
        self._loaded_output_dir = output_dir
        self.processes.set_streams(result.emits)
        self.run_summary.show_summary(build_run_summary(result))
        self.emit_inspector.set_run(result)
        self.scale_ladder.show_ladder(build_scale_ladder(result, str(output_dir)))
        self.chemistry.show_run(result)
        if any(e.tag == "chemistry_state" for e in result.emits):
            self._chemistry_dock.raise_()

        # Build the animation preview (trajectories, or a particle family like fluid_frame) and
        # hand it to the viewport + timeline. Everything here is engine output on the engine clock.
        tracks, segments = self.adaptive_controls.render_budget().trajectory_limits()
        trajectories = result.load_trajectories(limit=tracks)
        self._loaded_trajectories = trajectories
        playback = build_playback(trajectories, result.emits, max_segments=segments)
        views = probability_views(result.emits)
        default_view = next((key for key, _ in views if key.startswith("density:")), "structure")
        self.chemistry.set_views(views, default_view)
        self.chemistry.probability_details.set_playback(playback)
        self.chemistry.field_explorer.set_playback(playback)
        self.chemistry.electron_levels.set_playback(playback)
        self.processes.set_playback(playback)
        self.viewport.set_playback(playback)
        self._set_density_display(self.chemistry.field_explorer.display)
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

    def _select_recorded_stream(self, index) -> None:
        result = getattr(self, "_loaded_run", None)
        if result is None:
            return
        stream = self.processes.streams.itemData(index)
        _, segments = self.adaptive_controls.render_budget().trajectory_limits()
        playback = (build_material_frame_playback(result.emits, stream_name=stream) if stream is not None
                    else build_playback(getattr(self, "_loaded_trajectories", []), result.emits, max_segments=segments))
        self.viewport.set_playback(playback)
        self.processes.set_playback(playback)
        self.timeline.set_playback(playback)
        self.emit_inspector.set_playback(playback)
        self.chemistry.probability_details.set_playback(playback)
        self.chemistry.field_explorer.set_playback(playback)
        self.chemistry.electron_levels.set_playback(playback)
        report = build_precision_report(result, playback, scene=self._scene,
            output_px=(max(1, self.viewport.width()), max(1, self.viewport.height())), supersample=1, purpose="preview")
        self.inspector.set_precision(report)
        self.statusBar().showMessage(report.preview_summary())

    def _export_preview(self, video) -> None:
        if getattr(self, "_loaded_run", None) is None:
            self.console.log_stderr("Open or run an experiment before exporting a preview.")
            return
        directory = QFileDialog.getExistingDirectory(self, "Export Studio preview", str(self.settings.output_root))
        if directory:
            prefix = Path(directory) / ("preview_" + uuid.uuid4().hex[:8])
            self._preview_export.start(self._loaded_output_dir, prefix, video=video,
                                       stream=self.processes.streams.currentData())

    def _resolve_unsaved_sources(self) -> bool:
        paths = self.code_editor.dirty_paths()
        if not paths:
            return True
        prompt = QMessageBox(self)
        prompt.setWindowTitle("Unsaved source changes")
        prompt.setText("Save source changes before leaving this scenario?")
        prompt.setInformativeText(f"{len(paths)} changed source file(s). Discard leaves their files unchanged.")
        prompt.setDetailedText("\n".join(str(path) for path in paths))
        prompt.setStandardButtons(QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        prompt.setDefaultButton(QMessageBox.Cancel)
        choice = prompt.exec()
        if choice == QMessageBox.Save:
            try:
                self.code_editor.save()
            except (OSError, UnicodeError) as exc:
                self.console.log_stderr(f"Could not save source: {exc}")
                QMessageBox.warning(self, "Source changes were not saved", str(exc))
                return False
            return True
        return choice == QMessageBox.Discard

    def open_scenario(self, path: Path) -> bool:
        path = Path(path)
        if path.suffix.lower() == ".json":
            try:
                scene = read_scene(path)
            except (OSError, ValueError):
                pass
            else:
                if not self._open_chemistry():
                    return False
                self.chemistry.set_scene_document(scene)
                return True
        if not self._resolve_unsaved_sources():
            return False
        try:
            self.code_editor.load_file(path)
        except (OSError, UnicodeError) as exc:
            self.console.log_stderr(f"Could not open scenario: {exc}")
            return False
        self.chemistry.set_active(False)
        self._refresh_scenario_parameters(path, preserve_values=False)
        return True

    def _open_chemistry(self) -> bool:
        if not self.open_scenario(self.settings.examples_dir() / "chemistry_mode" / "chemistry_mode.js"):
            return False
        self._clear_playback()
        self._chemistry_dock.raise_()

        self.resizeDocks([self._code_dock, self._chemistry_dock], [320, 430], Qt.Horizontal)
        self.resizeDocks([self._console_dock], [140], Qt.Vertical)
        return True

    def _set_density_display(self, display):
        if hasattr(self.viewport, "set_density_display"):
            self.viewport.set_density_display(display)

    def _set_probability_view(self, view: str) -> None:
        result = getattr(self, "_loaded_run", None)
        if result is None:
            return
        previous = self.timeline._playback
        previous_cursor = self.timeline.cursor_time()
        playback = build_probability_playback(result.emits, view)
        if playback.is_empty and view == "structure":
            playback = build_playback([], result.emits)
        if playback.is_empty:
            self.chemistry.status.setText("No recorded frames for this view.")
            return
        self.processes.set_playback(playback)
        self.viewport.set_playback(playback)
        self.chemistry.probability_details.set_playback(playback)
        self.chemistry.field_explorer.set_playback(playback)
        self.chemistry.electron_levels.set_playback(playback)
        self.timeline.set_playback(playback)
        if previous is not None and previous.unit == playback.unit:
            self.timeline.set_cursor(previous_cursor)
        self.emit_inspector.set_playback(playback)
        self._set_density_display(self.chemistry.field_explorer.display)
        self.chemistry.tabs.setCurrentWidget(self.chemistry.probability_details if view.startswith("nuclear:") else self.chemistry.field_explorer)
        self.chemistry.status.setText(playback.label + "; held recorded frames, no invented particle paths.")

    def _calculate_quantum_reference(self):
        if self._runner.is_running() or self._quantum_job.is_running():
            self.chemistry.status.setText("Wait for the current engine/reference job to finish.")
            return
        try:
            scene = geometry_request(self.chemistry.reference_scene())
            # Validate through TRECH before the optional solver. Remove stale fields
            # intentionally: this action recalculates them for the edited geometry.
            args = stage_scene_parameters(["--param", "scene_json="+json.dumps(json.dumps(scene)),
                                           "--param", 'scene_file=""'], self.settings.output_root/"chemistry_drafts")
            inspect_scenario(self._engine, self.settings.examples_dir()/"chemistry_mode"/"chemistry_mode.js", parameter_args=args)
            self._quantum_request = scene
            self._quantum_job.start(scene, self.settings.output_root/"quantum_reference")
            self.chemistry.quantum_button.setEnabled(False)
            self.chemistry.status.setText("Calculating independent electronic reference. The result will be validated and replayed by TRECH.")
        except (ValueError, RuntimeError, OSError) as error:
            self._quantum_reference_failed(str(error))

    def _quantum_reference_failed(self, message):
        self.chemistry.quantum_button.setEnabled(self.chemistry.run_button.isEnabled())
        self.chemistry.status.setText(message)
        self.console.log_stderr(message)

    def _quantum_reference_ready(self, path):
        self.chemistry.quantum_button.setEnabled(self.chemistry.run_button.isEnabled())
        try:
            if not self.chemistry.run_button.isEnabled() or geometry_request(self.chemistry.reference_scene()) != self._quantum_request:
                self.chemistry.status.setText(f"Reference saved to {path}. The draft changed during calculation; import the result to inspect it.")
                return
            self.chemistry.set_scene_document(read_scene(path))
        except (ValueError, OSError) as error:
            self._quantum_reference_failed(str(error))
            return
        self._run_chemistry()
        self.chemistry.tabs.setCurrentWidget(self.chemistry.field_explorer)

    def _import_chemistry_scene(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import chemistry scene", str(self.settings.repo_root), "Scene (*.json)")
        if not path:
            return
        try:
            scene = read_scene(Path(path))
            if not self.chemistry.run_button.isEnabled():
                if not self._open_chemistry():
                    return
            self.chemistry.set_scene_document(scene)
        except (OSError, ValueError) as exc:
            self.chemistry.status.setText(f"Could not import scene: {exc}")

    def _export_chemistry_scene(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export chemistry scene", str(self.settings.repo_root / "build" / "chemistry_scene.json"), "Scene (*.json)")
        if not path:
            return
        try:
            write_scene(Path(path), self.chemistry.scene_document())
            self.chemistry.status.setText(f"Saved authored scene to {path}; TRECH validates it before running.")
        except (OSError, ValueError) as exc:
            self.chemistry.status.setText(f"Could not export scene: {exc}")

    def _run_chemistry(self) -> None:
        if not self.chemistry.run_button.isEnabled():
            if not self._open_chemistry():
                return
        self._run_scenario()

    def _chemistry_command_args(self) -> list[str]:
        return stage_scene_parameters(self.chemistry.command_args(), self.settings.output_root / "chemistry_drafts")

    def _load_chemistry_scaffold(self) -> None:
        if not self._engine.available:
            self.chemistry.status.setText(self._engine.describe())
            return
        try:
            inspection = inspect_scenario(self._engine, self.settings.examples_dir() / "chemistry_mode" / "chemistry_mode.js",
                                          self.scenario_options.command_args())
            self.chemistry.set_structure(inspection.config["hooks"]["inputs"]["structure"])
        except (OSError, RuntimeError, ValueError, KeyError) as exc:
            self.chemistry.status.setText(f"Could not load scaffold: {exc}")

    def _apply_render_budget(self) -> None:
        self.viewport.set_render_budget(self.adaptive_controls.render_budget())

    def _refresh_scenario_parameters(self, path: Path, preserve_values: bool = True) -> bool:
        """Evaluate declarations through TRECH itself; never parse JavaScript in Studio."""
        if not self._engine.available:
            self.scenario_options.show_error(
                "The TRECH engine is unavailable, so custom scenario options cannot be inspected."
            )
            return False
        try:
            # Refresh declarations first: a saved module may remove/rename a
            # control. Only replay overrides that still belong to this source.
            inspection = inspect_scenario(self._engine, path)
            if preserve_values:
                allowed = {p.id for p in inspection.parameters}
                old_args = self.scenario_options.command_args() + self._chemistry_command_args()
                args = []
                for flag, value in zip(old_args[::2], old_args[1::2]):
                    if value.split("=", 1)[0] in allowed:
                        args.extend((flag, value))
                if args:
                    inspection = inspect_scenario(self._engine, path, args)
        except (OSError, RuntimeError, ValueError) as exc:
            if self.chemistry.run_button.isEnabled():
                self.chemistry.status.setText(f"TRECH rejected the draft: {exc}")
            else:
                self.scenario_options.show_error(f"Could not inspect scenario options:\n{exc}")
            self.console.log_stderr(f"scenario inspection failed: {exc}")
            return False
        chemistry_inputs = inspection.config.get("hooks", {}).get("inputs", {})
        is_chemistry = chemistry_inputs.get("schema") == "trech_chemistry_inputs_v1"
        self.chemistry.set_active(is_chemistry)
        self._chemistry_dock.setVisible(is_chemistry)
        if is_chemistry and not preserve_values:
            self.chemistry.set_structure(chemistry_inputs["structure"])
            self.chemistry.reaction.clear()
            self.chemistry.scene_enabled.setChecked(False)
            self.chemistry.scene_json.clear()
            scene = chemistry_inputs.get("scene")
            if scene and (len(scene["molecules"]) > 1 or scene["frames"]):
                self.chemistry.set_scene_document(scene)
        self.scenario_options.set_parameters(
            (p for p in inspection.parameters if not is_chemistry or p.id not in ("structure_json", "reaction_json", "scene_json", "scene_file")),
            preserve_values=preserve_values)
        self.adaptive_controls.set_config(inspection.config)
        self.code_editor.set_sources(inspection.sources)
        self.processes.set_description(inspection.studio, inspection.config.get("models", []))
        self.setWindowTitle(inspection.studio.get("title") or "TRECH Studio")
        # Reset script-owned visibility before applying the new description.
        for key, dock in self._script_docks.items():
            dock.setVisible(inspection.studio.get("panels", {}).get(key, True))
        if inspection.studio.get("processes") and inspection.studio.get("panels", {}).get("processes", True):
            self._processes_dock.raise_()
        if inspection.parameters:
            self.console.log_info(
                f"scenario options: {len(inspection.parameters)} typed value(s)"
            )
        return True

    def _open_scenario_from_browser(self, path: str) -> None:
        """Open a scenario picked in the browser; auto-load its last run if one exists."""
        p = Path(path)
        if not self.open_scenario(p):
            return
        if p.suffix.lower() == ".js":
            out_dir = self.settings.output_root / f"studio_{p.stem}"
            if (out_dir / "trech_viz_scene.json").is_file():
                self.console.log_info(f"loading existing run for {p.name}")
                self.open_output_dir(out_dir)
                return
        self._clear_playback()

    def _pick_scenario(self) -> None:
        start = str(self.settings.examples_dir())
        path, _ = QFileDialog.getOpenFileName(self, "Open scenario", start, "Scenario (*.js *.json)")
        if path:
            self.open_scenario(Path(path))

    def _pick_output_dir(self) -> None:
        start = str(self.settings.output_root.parent)
        path = QFileDialog.getExistingDirectory(self, "Open run output directory", start)
        if path:
            self.open_output_dir(Path(path))

    def _save_scenario(self) -> None:
        try:
            saved = self.code_editor.save()
        except (OSError, UnicodeError) as exc:
            self.console.log_stderr(f"Could not save source: {exc}")
            return
        if saved is not None:
            self.console.log_info(f"saved {saved}")
            self._refresh_scenario_parameters(saved, preserve_values=True)

    def _run_scenario(self) -> None:
        if not self._engine.available:
            QMessageBox.warning(self, "Engine missing", self._engine.describe())
            return
        experiment = self.code_editor.scenario_path()
        if experiment is None:
            QMessageBox.information(self, "No scenario", "Open a scenario .js first.")
            return
        # Save edits before running so what runs matches what is shown.
        try:
            self.code_editor.save()
        except (OSError, UnicodeError) as exc:
            self.console.log_stderr(f"Could not save source: {exc}")
            return
        if not self._refresh_scenario_parameters(experiment, preserve_values=True):
            return

        out_dir = self.settings.output_root / f"studio_{experiment.stem}_{uuid.uuid4().hex[:8]}"
        self.console.log_info(f"running {experiment.name} -> {out_dir}")
        self._runner.run(
            experiment, out_dir, extra_args=(self.scenario_options.command_args() + self._chemistry_command_args() +
                                             self.adaptive_controls.command_args())
        )

    def _on_run_finished(self, exit_code: int, output_dir: Path) -> None:
        if exit_code == 0:
            self.console.log_info(f"run finished OK -> {output_dir}")
            self.open_output_dir(output_dir)
        else:
            self.console.log_stderr(f"run exited with code {exit_code}")

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if not self._resolve_unsaved_sources():
            event.ignore()
            return
        self._preview_export.stop()
        self._quantum_job.stop()
        self._runner.stop()
        super().closeEvent(event)
