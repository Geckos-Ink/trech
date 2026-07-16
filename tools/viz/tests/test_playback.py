from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np

from trech_viz.playback import load_material_frames
from trech_viz.renderer import _render_hints, _rotation_matrix


def test_material_frames_keep_rgba_and_observer_clocks():
    rows = [
        {"tag": "material_frame", "payload": {
            "time_s": 600.0, "physical_time_s": 600.0, "playback_time_s": 6.0,
            "time_scale": 100.0, "phase": "falling",
            "positions_mm": [[1, 2, 3]], "colors_rgba": [[1, 0.2, 0.05, 0.8]],
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


def test_shared_render_hints_and_tube_rotation():
    hints = _render_hints([
        "viz_shell", "viz_opacity=0.2", "viz_color=#ff7a18", "viz_emissive",
    ])
    assert hints["shell"] and hints["emissive"] and hints["opacity"] == 0.2
    assert np.allclose(hints["color"], [1.0, 122 / 255.0, 24 / 255.0])
    # Local +Z becomes global -Y for Geant4's +90-degree X placement convention.
    rotated = _rotation_matrix((90.0, 0.0, 0.0)) @ np.array([0.0, 0.0, 1.0, 0.0])
    assert np.allclose(rotated[:3], [0.0, -1.0, 0.0], atol=1e-7)
