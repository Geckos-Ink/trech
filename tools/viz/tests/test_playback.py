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
                "fluid_necking": {
                    "mode": "pair_gaussian", "min_distance_mm": 3.0,
                    "max_distance_mm": 8.0, "samples_per_pair": 2,
                    "weight": 0.35, "preserves_component_topology": True,
                },
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
    assert frames[-1].surface.neck_mode == "pair_gaussian"
    assert frames[-1].surface.neck_preserves_topology is True
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


def test_classic_fluid_neck_raises_midpoint_density_without_moving_centres():
    surface = type("Surface", (), {
        "grid_spacing_mm": 0.25, "sigma_mm": 1.2,
        "clip_axis": "y", "clip_radius_mm": None,
        "clip_min_mm": None, "clip_max_mm": None,
        "neck_mode": "pair_gaussian", "neck_min_distance_mm": 2.0,
        "neck_max_distance_mm": 7.0, "neck_samples": 2, "neck_weight": 0.6,
    })()
    points = np.asarray([[-3.0, 0.0, 0.0], [3.0, 0.0, 0.0]], dtype=np.float32)
    original = points.copy()
    necked = gaussian_density_grid(points, surface)
    surface.neck_mode = "none"
    plain = gaussian_density_grid(points, surface)
    neck_mid = np.rint((np.zeros(3) - necked.origin_mm) / necked.spacing_mm).astype(int)
    plain_mid = np.rint((np.zeros(3) - plain.origin_mm) / plain.spacing_mm).astype(int)
    assert necked.values[tuple(neck_mid)] > plain.values[tuple(plain_mid)]
    assert np.array_equal(points, original)


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


def _write_emits(tmp: str, payloads) -> Path:
    path = Path(tmp) / "trech_hook_emits.jsonl"
    path.write_text("\n".join(json.dumps({"tag": "material_frame", "payload": payload})
                              for payload in payloads), encoding="utf-8")
    return path


def _molecule_frame(time_s: float, shift: float) -> dict:
    return {
        "physical_time_s": time_s, "playback_time_s": time_s * 1e15, "phase": "md",
        "length_unit": "angstrom", "up_axis": "y",
        "positions": [[0.0 + shift, 0.0, 0.0], [0.96, 0.0, 0.0], [-0.24, 0.93, 0.0]],
        "colors_rgba": [[1, 0.2, 0.2, 1], [0.9, 0.9, 0.9, 1], [0.9, 0.9, 0.9, 1]],
        "radii": [0.33, 0.22, 0.22],
        "bonds": [[0, 1], [0, 2], [0, 9]],
        "vectors": [[0.0, 0.5, 0.0], [0, 0, 0], [0, 0, 0]],
        "apparatus": [{"shape": "box", "center": [0, 0, 0], "size": [4, 4, 4],
                       "style": "wire", "color_rgba": [0.5, 0.6, 0.7, 0.5]},
                      {"shape": "unknown"}],
        "legend": [{"label": "O", "color_rgba": [1, 0.2, 0.2]}],
        "hud_lines": ["bond 0.957 A"],
    }


def test_material_frames_parse_atoms_bonds_vectors_and_apparatus():
    with tempfile.TemporaryDirectory() as tmp:
        frames = load_material_frames(_write_emits(tmp, [_molecule_frame(1e-15, 0.0)]))
    frame = frames[0]
    assert frame.length_unit == "angstrom" and frame.up_axis == "y"
    assert np.allclose(frame.radii, [0.33, 0.22, 0.22])
    # An out-of-range bond index is dropped instead of guessed into shape.
    assert frame.bonds.tolist() == [[0, 1], [0, 2]]
    assert frame.vectors.shape == (3, 3)
    assert len(frame.apparatus) == 1 and frame.apparatus[0].style == "wire"
    assert frame.legend[0][0] == "O" and frame.hud_lines == ["bond 0.957 A"]
    # y-up frames are kept verbatim; z-up frames keep the historical relabel.
    assert np.allclose(frame.points_view(), frame.positions_mm)
    frame.up_axis = "z"
    assert np.allclose(frame.points_view()[2], [-0.24, 0.0, 0.93])


def test_clock_formats_in_the_unit_the_clip_spans():
    from trech_viz.animate import format_clock

    assert format_clock(90.0, 600.0) == "01:30"
    assert format_clock(2.5e-12, 5e-12).strip() == "2.50 ps"
    assert format_clock(4.0e-15, 1e-13).strip() == "4.00 fs"


def test_trajectory_reveal_follows_recorded_steps_and_clock():
    from trech_viz.animate import _Track, activity_clock
    from trech_viz.trajectories import Trajectory

    traj = Trajectory(event_id=0, track_id=1, particle="gamma", capped=False)
    traj.points = [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (10.0, 5.0, 0.0)]
    traj.times_ns = [0.0, 1.0, 3.0]
    traj.energies_ev = [1e5, 1e5, 6e4]
    traj.interactions = ["emission", "scatter", "world_boundary"]
    track = _Track(traj)
    prefix, head = track.prefix(0.5)
    # The head sits on the recorded chord between the first two Geant4 points.
    assert np.allclose(head, [5.0, 0.0, 0.0]) and prefix.shape[0] == 2
    full, head = track.prefix(10.0)
    assert head is None and full.shape[0] == 3
    assert track.marks == [(1, "scatter")]
    clock = activity_clock([track], 5)
    assert clock[0] == 0.0 and clock[-1] == 3.0 and np.all(np.diff(clock) >= 0)


def test_score_hud_reads_engine_checks_only():
    from trech_viz.animate import score_hud_lines

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "trech_scores.jsonl"
        path.write_text(json.dumps({"analytic_checks": [
            {"name": "beer_lambert", "classical_predicted": 0.4265, "geant4_measured": 0.4217,
             "within_tolerance": True}]}), encoding="utf-8")
        lines = score_hud_lines(path)
    assert lines and "0.4265" in lines[0] and "0.4217" in lines[0] and "within tol" in lines[0]


def test_offscreen_gifs_render_material_and_trajectory_paths():
    pytest = __import__("pytest")
    pytest.importorskip("pyvista")
    from trech_viz.animate import render_material_animation, render_trajectory_animation
    from trech_viz.trajectories import Trajectory

    with tempfile.TemporaryDirectory() as tmp:
        frames = load_material_frames(_write_emits(
            tmp, [_molecule_frame(t * 1e-15, 0.05 * t) for t in range(4)]))
        gif = Path(tmp) / "md.gif"
        render_material_animation(None, frames, gif=str(gif), window_size=(96, 96),
                                  fps=4, seconds=1.0)
        assert gif.stat().st_size > 0
        traj = Trajectory(event_id=0, track_id=1, particle="proton", capped=False)
        traj.points = [(0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (4.0, 0.2, 0.0)]
        traj.times_ns = [0.0, 0.01, 0.03]
        traj.energies_ev = [2e7, 1e7, 0.0]
        traj.interactions = ["emission", "interaction", "interaction"]
        gif = Path(tmp) / "traj.gif"
        render_trajectory_animation(None, [traj], gif=str(gif), window_size=(96, 96),
                                    fps=4, seconds=1.0)
        assert gif.stat().st_size > 0
