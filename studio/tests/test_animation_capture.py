"""Animation-preview tests: Studio renders a run's *motion* in-program, and can encode it.

Two things are asserted when a GPU (and ffmpeg) are available:

1. **Motion** — driving the timeline cursor through a moving ``fluid_frame`` playback yields
   *different* pixels at the start vs the end. This is the "video preview of animation directly
   in program" capability: the same offscreen renderer the desktop viewport uses, stepped over
   the engine's clock.
2. **Encode** — ``capture_run`` writes an MP4/GIF, and the compact ``capture_reference`` writes
   a small GIF suitable for committing as a repo reference.

All GPU/ffmpeg-dependent assertions degrade gracefully: with no device or no ffmpeg the test
prints SKIP for that leg instead of failing (matches the suite's honesty about missing deps).

Run: ``QT_QPA_PLATFORM=offscreen python tests/test_animation_capture.py``
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trech_studio.capture import (  # noqa: E402
    _frame_rgb,
    _have_ffmpeg,
    _offscreen_renderer,
    capture_reference,
    capture_run,
)
from trech_studio.render.playback import build_particle_playback  # noqa: E402
from trech_studio.scene.model import SceneModel  # noqa: E402


class _Emit:
    def __init__(self, tag, payload):
        self.tag = tag
        self.payload = payload


def _moving_run(tmp: Path) -> Path:
    """A run dir whose fluid_frame emits move a cloud of particles over time."""
    run_dir = tmp / "run"
    run_dir.mkdir()
    lines = []
    rng = np.random.default_rng(0)
    base = rng.uniform(-0.03, 0.03, size=(24, 3))
    for i in range(6):
        xyz = (base + np.array([0.0, 0.0, 0.02 * i])).tolist()  # drift up in z
        lines.append(json.dumps({
            "phase": "hook_emit", "hook": "onEventStart", "tag": "fluid_frame",
            "event_id": i, "step_index": -1,
            "payload": {"time_s": 0.01 * i, "phase": "pour", "xyz": xyz},
        }))
    (run_dir / "trech_hook_emits.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return run_dir


def test_animation_frames_differ_over_time() -> None:
    """The renderer must draw different pixels at the start vs the end of a moving playback."""
    emits = [
        _Emit("fluid_frame", {"time_s": 0.0, "phase": "pour", "xyz": [[0.0, 0.0, 0.0]]}),
        _Emit("fluid_frame", {"time_s": 1.0, "phase": "pour", "xyz": [[0.06, 0.02, 0.09]]}),
    ]
    pb = build_particle_playback(emits, tag="fluid_frame", unit_scale_mm=1000.0)
    canvas, renderer, reason = _offscreen_renderer(240, 160, "dark")
    if renderer is None:
        print(f"SKIP motion: {reason}")
        return
    renderer.set_scene(SceneModel(world_size_mm=200.0))
    renderer.set_playback(pb)
    lo = np.array([-30.0, -30.0, -30.0]); hi = np.array([90.0, 30.0, 120.0])
    renderer.camera.fit_bounds(lo, hi)

    renderer.set_playback_time(pb.t_min)
    first = _frame_rgb(canvas, 240, 160)
    renderer.set_playback_time(pb.t_max)
    last = _frame_rgb(canvas, 240, 160)
    assert first is not None and last is not None
    assert not np.array_equal(first, last), "playback did not change the rendered frame"


def test_capture_run_writes_animation_when_possible() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = _moving_run(Path(tmp))
        res = capture_run(run_dir, Path(tmp) / "cap" / "anim", width=200, height=140,
                          seconds=1.0, fps=8)
        assert res.meta is not None and res.meta.is_file()
        if not res.ok:
            print("SKIP encode: no GPU device")
            return
        if _have_ffmpeg():
            assert res.mp4 is not None and res.mp4.is_file()
            assert res.gif is not None and res.gif.is_file()
        else:
            print("SKIP mp4/gif: ffmpeg missing (still PNG written)")


def test_capture_reference_is_compact_gif() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = _moving_run(Path(tmp))
        gif = Path(tmp) / "ref" / "moving.gif"
        res = capture_reference(run_dir, gif, width=200, height=140, seconds=1.0, fps=8)
        if res.gif is None:
            print("SKIP reference: no GPU/ffmpeg")
            return
        assert gif.is_file()
        # A reference GIF must stay small (repo-space discipline): well under 1 MiB at this size.
        assert gif.stat().st_size < 1_000_000
        # The compact helper leaves no stray PNG/MP4 next to it.
        assert not gif.with_suffix(".mp4").exists()


def _run_all() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL {t.__name__}: {exc}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
