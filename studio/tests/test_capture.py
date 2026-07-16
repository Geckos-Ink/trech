"""Tests for the headless capture module.

The pure parts (PNG encoder, scene selection, particle bounds, always-written provenance
sidecar) run everywhere. The actual GPU render is best-effort: asserted only if wgpu can
init a device, otherwise we assert the graceful-degradation path (sidecar + render_error).

Run: ``python tests/test_capture.py``
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trech_studio.capture import (  # noqa: E402
    _clip_sample_times,
    _playback_window,
    _scene_for,
    _write_png,
    capture_run,
)
from trech_studio.render.playback import (  # noqa: E402
    EMPTY,
    build_material_frame_playback,
    build_particle_playback,
)


class _Emit:
    def __init__(self, tag, payload):
        self.tag = tag
        self.payload = payload


def test_write_png_valid_signature() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "x.png"
        rgb = np.zeros((4, 6, 3), dtype=np.uint8)
        rgb[..., 0] = 255  # red
        _write_png(p, rgb)
        data = p.read_bytes()
        assert data[:8] == b"\x89PNG\r\n\x1a\n"
        assert b"IHDR" in data[:32] and data.rstrip().endswith(b"IEND" + bytes.fromhex("ae426082"))


def test_scene_for_particles_is_grid_only() -> None:
    emits = [_Emit("fluid_frame", {"time_s": 0.0, "xyz": [[0.0, 0.0, 0.0], [0.05, 0.0, 0.1]]})]
    pb = build_particle_playback(emits, tag="fluid_frame", unit_scale_mm=1000.0)
    with tempfile.TemporaryDirectory() as tmp:
        scene = _scene_for(Path(tmp), pb)      # no viz scene in the dir
        assert not scene.volumes                # grid-only stage, no fake volume
        assert scene.world_size_mm > 0


def test_scene_for_empty_is_placeholder() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        scene = _scene_for(Path(tmp), EMPTY)
        assert scene.volumes                    # labelled placeholder cube


def test_particle_bounds() -> None:
    emits = [
        _Emit("fluid_frame", {"time_s": 0.0, "xyz": [[0.0, 0.0, 0.0]]}),
        _Emit("fluid_frame", {"time_s": 1.0, "xyz": [[0.01, 0.02, 0.03]]}),
    ]
    pb = build_particle_playback(emits, tag="fluid_frame", unit_scale_mm=1000.0)
    lo, hi = pb.particle_bounds()
    assert np.allclose(lo, [0, 0, 0]) and np.allclose(hi, [10, 20, 30])
    assert EMPTY.particle_bounds() is None      # no frames -> no bounds


def test_capture_excerpt_maps_retained_physical_clock() -> None:
    emits = [
        _Emit("material_frame", {
            "physical_time_s": physical, "playback_time_s": physical / 100.0,
            "time_scale": 100.0, "positions_mm": [[0, 0, physical]],
            "colors_rgba": [[1, 0.2, 0.05, 0.8]],
        })
        for physical in (0.0, 60.0, 600.0)
    ]
    playback = build_material_frame_playback(emits)
    window = _playback_window(playback, physical_start_s=0.0, physical_duration_s=60.0)
    assert np.allclose(window, [0.0, 0.6, 0.0, 60.0])


def test_capture_uses_one_post_tick_state_per_gif_frame() -> None:
    emits = [
        _Emit("material_frame", {
            "physical_time_s": tick * 0.6, "playback_time_s": tick * 0.1,
            "time_scale": 6.0, "positions_mm": [[tick, 0, 0]],
            "colors_rgba": [[1, 0.2, 0.05, 0.8]],
        })
        for tick in range(101)
    ]
    playback = build_material_frame_playback(emits)
    times = _clip_sample_times(playback, 100, playback.t_min, playback.t_max)
    indices = [playback.frame_index_at(float(time)) for time in times]
    assert np.allclose(times, playback.frame_times[1:])
    assert indices == list(range(1, 101))


def test_capture_writes_sidecar_and_degrades() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        run_dir = Path(tmp) / "run"
        run_dir.mkdir()
        (run_dir / "trech_hook_emits.jsonl").write_text(
            json.dumps({"phase": "hook_emit", "hook": "onEventStart", "tag": "fluid_frame",
                        "event_id": 1, "step_index": -1,
                        "payload": {"time_s": 0.0, "phase": "pour", "xyz": [[0.0, 0.0, 0.0], [0.05, 0.0, 0.1]]}}) + "\n",
            encoding="utf-8",
        )
        out = Path(tmp) / "cap" / "run"
        res = capture_run(run_dir, out, still=True, width=128, height=96)
        # The provenance sidecar is always written and records the playback kind.
        assert res.meta is not None and res.meta.is_file()
        meta = json.loads(res.meta.read_text())
        assert meta["playback_kind"] == "particles"
        if res.ok:
            assert res.png is not None and res.png.is_file()   # GPU available
        else:
            assert "render_error" in meta                       # graceful degradation


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
