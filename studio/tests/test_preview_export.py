"""Recorded annotations and nonblocking export ownership; no physics generation."""
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication
from trech_studio.engine.preview import PreviewExport
from trech_studio.engine.locator import locate_engine
from trech_studio.engine.parameters import inspect_scenario
from trech_studio.render.frame_notes import frame_notes
from trech_studio.render.playback import build_material_frame_playback
from trech_studio.ui.processes import ProcessesPanel

_APP = QApplication.instance() or QApplication([])


def test_relative_engine_override_survives_scenario_working_directory():
    repo = Path(__file__).resolve().parents[2]
    relative = Path(os.path.relpath(repo / "build/rel/trech"))
    engine = locate_engine(repo, relative)
    assert engine.path.is_absolute()
    inspection = inspect_scenario(engine, repo / "examples/scenarios/aerodynamics_reference/aerodynamics_reference.js")
    assert inspection.parameters


def test_annotations_follow_held_frames_and_keep_nonphysical_clock():
    def emit(time, count):
        return SimpleNamespace(tag="material_frame", payload={"time": time, "time_unit": "step",
            "positions_mm": [[1, 2, 3]], "colors_rgba": [[1, 1, 1, 1]], "phase": "COMPARISON",
            "hud_lines": [f"Solid parcels: {count}"], "clock_text": f"Step {time}; no physical time",
            "legend": [{"label": "White: solid", "color_rgba": [1, 1, 1, 1]}]})
    playback = build_material_frame_playback([emit(0, 0), emit(4, 9)])
    assert "Solid parcels: 0" in frame_notes(playback, 3)
    assert "Solid parcels: 9" in frame_notes(playback, 4)
    assert all(" s" not in line for line in frame_notes(playback, 0)[:2])
    panel = ProcessesPanel()
    panel.set_playback(playback)
    assert "Solid parcels: 9" in panel.notes.text()
    panel.set_cursor(0)
    assert "Solid parcels: 0" in panel.notes.text()
    panel.set_playback(None)
    assert "No recorded" in panel.notes.text()


def test_optional_malformed_annotations_degrade_without_losing_geometry():
    e = SimpleNamespace(tag="material_frame", payload={"positions_mm": [[1, 2, 3]],
        "colors_rgba": [[1, 1, 1, 1]], "hud_lines": {"bad": "object"}, "legend": "bad"})
    playback = build_material_frame_playback([e])
    assert not playback.is_empty
    assert playback.frames[0].hud_lines == playback.frames[0].legend == ()


def _fixture(tmp_path):
    package = tmp_path / "studio/trech_studio"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "capture.py").write_text('''
import json, pathlib, sys
args=sys.argv[1:]
prefix=pathlib.Path(args[args.index('--out')+1])
prefix.with_suffix('.args.json').write_text(json.dumps(args))
prefix.with_suffix('.png').write_bytes(b'fixture')
if '--still' not in args and '--stream' in args:
    prefix.with_suffix('.gif').write_bytes(b'fixture')
''')
    return PreviewExport(tmp_path, _APP)


def _wait(job, action):
    loop = QEventLoop()
    completed, failed = [], []
    job.finished.connect(lambda path: (completed.append(path), loop.quit()))
    job.failed.connect(lambda message: (failed.append(message), loop.quit()))
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(5000)
    action()
    loop.exec()
    timer.stop()
    _APP.processEvents()
    assert completed or failed, "Export subprocess did not complete"
    return completed, failed


def test_export_subprocess_keeps_stream_and_does_not_run_engine(tmp_path):
    from trech_studio.render.adaptive import RenderBudget
    job = _fixture(tmp_path)
    prefix = tmp_path / "preview"
    completed, failed = _wait(job, lambda: job.start(tmp_path / "run", prefix, video=True, stream="pressure",
        render_budget=RenderBudget(detail=2.25, memory_mib=512, merge_radius_scale=1.2)))
    assert completed == [prefix] and not failed and job.process is None
    args = json.loads(prefix.with_suffix(".args.json").read_text())
    assert args[args.index("--stream") + 1] == "pressure"
    assert "--annotations" in args and "--still" not in args
    assert "--engine-bin" not in args
    assert args[args.index('--render-detail')+1] == '2.25'
    assert args[args.index('--render-memory-mib')+1] == '512'
    assert args[args.index('--merge-radius-scale')+1] == '1.2'


def test_video_failure_is_not_reported_as_successful_export(tmp_path):
    job = _fixture(tmp_path)
    completed, failed = _wait(job, lambda: job.start(tmp_path / "run", tmp_path / "partial", video=True))
    assert not completed and len(failed) == 1 and "incomplete" in failed[0]
