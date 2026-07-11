"""The Studio main window: a dockable editor shell wiring the panels to the engine.

Layout (industry-standard editor shape):
    ┌──────────────┬───────────────────────────┬──────────────┐
    │  Outliner    │                           │  Inspector   │
    ├──────────────┤        3D Viewport        ├──────────────┤
    │ Code editor  │        (wgpu)             │              │
    └──────────────┴───────────────────────────┴──────────────┘
    │                    Console / Run summary                 │
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
from ..engine.runner import EngineRunner
from ..render.viewport import WGPU_AVAILABLE, create_viewport
from ..scene.loader import placeholder_scene, scene_from_output_dir, scene_from_viz_json
from ..scene.model import SceneModel
from ..settings import StudioSettings
from .console import Console
from .inspector import Inspector
from .outliner import Outliner
from .code_editor import CodeEditor


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
        self.outliner = Outliner(self)
        self.inspector = Inspector(self)
        self.console = Console(self)
        self.code_editor = CodeEditor(self)

        self._add_dock("Outliner", self.outliner, Qt.LeftDockWidgetArea)
        self._add_dock("Scenario", self.code_editor, Qt.LeftDockWidgetArea)
        self._add_dock("Inspector", self.inspector, Qt.RightDockWidgetArea)
        self._add_dock("Console", self.console, Qt.BottomDockWidgetArea)

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
        if hasattr(self.viewport, "set_scene"):
            self.viewport.set_scene(scene)

    def open_output_dir(self, output_dir: Path) -> None:
        output_dir = Path(output_dir)
        scene = scene_from_output_dir(output_dir)
        if scene is not None:
            self._apply_scene(scene)
        else:
            self.console.log_stderr(f"no trech_viz_scene.json in {output_dir}")
        result = load_run_result(output_dir)
        self.console.show_run(result)

    def open_scenario(self, path: Path) -> None:
        self.code_editor.load_file(Path(path))

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

        out_dir = self.settings.output_root / f"studio_{experiment.stem}"
        self.console.log_info(f"running {experiment.name} -> {out_dir}")
        self._runner.run(experiment, out_dir)

    def _on_run_finished(self, exit_code: int, output_dir: Path) -> None:
        if exit_code == 0:
            self.console.log_info(f"run finished OK -> {output_dir}")
            self.open_output_dir(output_dir)
        else:
            self.console.log_stderr(f"run exited with code {exit_code}")

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        self._runner.stop()
        super().closeEvent(event)
