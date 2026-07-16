from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np

from trech_viz.metaballs import gaussian_density_grid
from trech_viz.playback import load_material_frames, sample_animation_frames, select_physical_window
from trech_viz.renderer import _gif_frame_duration_ms, _render_hints, _rotation_matrix


def test_material_frames_keep_rgba_and_observer_clocks():
    rows = [
        {"tag": "material_frame", "payload": {
            "time_s": 600.0, "physical_time_s": 600.0, "playback_time_s": 6.0,
            "time_scale": 100.0, "phase": "falling",
            "positions_mm": [[1, 2, 3]], "colors_rgba": [[1, 0.2, 0.05, 0.8]],
            "render_surface": {
                "mode": "metaball", "grid_spacing_mm": 1.25, "sigma_mm": 2.2,
                "iso_level": 0.52, "positions_unmodified": True,
                "clip_cylinder": {"axis": "z", "radius_mm": 39.0},
            },
        }},
        {"tag": "material_frame", "payload": {
            "time_s": 0.0, "physical_time_s": 0.0, "playback_time_s": 0.0,
            "time_scale": 100.0, "phase": "heating",
            "positions_mm": [], "colors_rgba": [],
        }},
    ]
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "trech_hook_emits.jsonl"
        path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
        frames = load_material_frames(path)
    assert len(frames) == 2
    assert frames[0].positions_mm.shape == (0, 3)
    assert frames[-1].playback_time_s == 6.0 and frames[-1].physical_time_s == 600.0
    assert frames[-1].time_scale == 100.0
    assert np.allclose(frames[-1].colors_rgba[0], [1.0, 0.2, 0.05, 0.8])
    assert frames[-1].surface is not None and frames[-1].surface.clip_axis == "y"
    grid = gaussian_density_grid(
        frames[-1].positions_mm[:, [0, 2, 1]], frames[-1].surface
    )
    assert grid.values.max() > frames[-1].surface.iso_level


def test_shared_render_hints_and_tube_rotation():
    hints = _render_hints([
        "viz_shell", "viz_opacity=0.2", "viz_color=#ff7a18", "viz_emissive",
    ])
    assert hints["shell"] and hints["emissive"] and hints["opacity"] == 0.2
    assert np.allclose(hints["color"], [1.0, 122 / 255.0, 24 / 255.0])
    # Local +Z becomes global -Y for Geant4's +90-degree X placement convention.
    rotated = _rotation_matrix((90.0, 0.0, 0.0)) @ np.array([0.0, 0.0, 1.0, 0.0])
    assert np.allclose(rotated[:3], [0.0, -1.0, 0.0], atol=1e-7)


def test_physical_window_selects_one_minute_without_retiming():
    frames = [
        type("Frame", (), {"physical_time_s": float(t), "playback_time_s": t / 100.0})()
        for t in range(0, 601, 10)
    ]
    selected = select_physical_window(frames, start_s=0.0, duration_s=60.0)
    assert len(selected) == 7
    assert selected[0].physical_time_s == 0.0
    assert selected[-1].physical_time_s == 60.0
    assert selected[-1].playback_time_s == 0.6
    assert _gif_frame_duration_ms(10) == 100


def test_animation_uses_each_post_tick_state_once():
    frames = [
        type("Frame", (), {"physical_time_s": tick * 0.6, "playback_time_s": tick * 0.1})()
        for tick in range(101)
    ]
    sampled = sample_animation_frames(frames, 100)
    assert [frame.playback_time_s for frame in sampled] == [tick * 0.1 for tick in range(1, 101)]
