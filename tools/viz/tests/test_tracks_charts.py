from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path

import numpy as np

from trech_viz.playback import load_material_frames
from trech_viz.trajectories import Trajectory


def _traj(event, track, particle, points, times, energies, processes, interactions,
          boundaries=None):
    traj = Trajectory(event_id=event, track_id=track, particle=particle, capped=False)
    traj.points = [tuple(p) for p in points]
    traj.times_ns = list(times)
    traj.energies_ev = list(energies)
    traj.processes = list(processes)
    traj.interactions = list(interactions)
    traj.boundaries = list(boundaries or [""] * len(points))
    traj.materials = [""] * len(points)
    traj.volumes = [""] * len(points)
    return traj


def test_reactions_are_reconstructed_from_recorded_products():
    from trech_viz.tracks_view import Track, find_reactions, pretty_particle, target_from_conservation

    assert pretty_particle("C14") == "¹⁴C" and pretty_particle("anti_nu_e") == "ν̄"
    # n + ? -> 14C + p conserves A and Z only if the target was 14N.
    assert target_from_conservation("neutron", ["C14", "proton"]) == "¹⁴N"
    vertex, decay_at = (1.0, 2.0, 3.0), (1.0, 2.0, 3.00001)
    trajs = [
        _traj(0, 1, "neutron", [(0, 0, 0), vertex], [0.0, 50.0], [0.025, 0.025],
              ["source", "neutronInelastic"], ["emission", "interaction"]),
        _traj(0, 2, "proton", [vertex, (1, 2, 8)], [50.0, 51.0], [5.8e5, 0.0],
              ["source", "hIoni"], ["emission", "interaction"]),
        _traj(0, 3, "C14", [vertex, decay_at], [50.0, 1.0e20], [4e4, 0.0],
              ["source", "RadioactiveDecay"], ["emission", "interaction"]),
        _traj(0, 4, "N14", [decay_at], [1.0e20], [0.0], ["source"], ["emission"]),
        _traj(0, 5, "e-", [decay_at, (1, 3, 3)], [1.0e20, 1.0e20 + 1], [5e4, 0.0],
              ["source", "eIoni"], ["emission", "interaction"]),
        _traj(0, 6, "anti_nu_e", [decay_at, (9, 9, 9)], [1.0e20, 1.0e20 + 1], [1e5, 1e5],
              ["source", "Transportation"], ["emission", "world_boundary"]),
    ]
    reactions = find_reactions([Track(t) for t in trajs])
    labels = [r.label for r in reactions]
    assert labels[0] == "n + ¹⁴N → ¹⁴C + p"
    assert labels[1].startswith("¹⁴C → ¹⁴N") and "e⁻" in labels[1] and "ν̄" in labels[1]
    assert [r.kind for r in reactions] == ["reaction", "decay"]


def test_attenuation_survival_is_unbiased_while_photons_are_in_flight():
    from trech_viz.track_charts import attenuation_charts
    from trech_viz.tracks_view import Track

    rng = np.random.default_rng(3)
    mu, length, c = 0.02, 50.0, 300.0  # 1/mm, mm, mm/ns
    trajs = []
    for event in range(600):
        depth = rng.exponential(1.0 / mu)
        entry_t = 20.0 / c
        if depth < length:
            hit_t = entry_t + depth / c
            trajs.append(_traj(event, 1, "gamma",
                               [(0, 0, -45), (0, 0, -25), (0, 0, -25 + depth), (5, 0, 60)],
                               [0.0, entry_t, hit_t, hit_t + 0.3], [1e5] * 4,
                               ["source", "Transportation", "compt", "Transportation"],
                               ["emission", "boundary", "scatter", "world_boundary"]))
        else:
            trajs.append(_traj(event, 1, "gamma", [(0, 0, -45), (0, 0, -25), (0, 0, 100)],
                               [0.0, entry_t, entry_t + 125.0 / c], [1e5] * 3,
                               ["source", "Transportation", "Transportation"],
                               ["emission", "boundary", "world_boundary"]))
    check = {"type": "beer_lambert", "mu_total_per_mm": mu, "path_length_mm": length,
             "classical_predicted": math.exp(-mu * length), "geant4_measured": 0.37}
    survival = attenuation_charts([Track(t) for t in trajs], {"analytic_checks": [check]})[0]
    for now in (20.0 / c + 20.0 / c, 1.0):  # wavefront at 20 mm, then everything known
        x, y = survival.series[0].visible(now)
        assert x.size > 5
        # Kaplan-Meier stays on exp(-mu x) up to the wavefront (no early-interaction bias).
        assert np.max(np.abs(y - np.exp(-mu * x))) < 0.08


def test_optical_bundles_merge_only_identical_histories():
    from trech_viz.tracks_view import Track, bundle_optical

    def photon(event, dy, boundaries):
        return Track(_traj(event, 1, "opticalphoton", [(0, dy, 0), (10, dy, 0), (20, dy, 5)],
                           [0.0, 0.03, 0.06], [2.2] * 3, ["source", "Transportation", "x"],
                           ["emission", "boundary", "world_boundary"], boundaries))
    tracks = [photon(0, 0.0, ["", "refraction", ""]), photon(1, 1.0, ["", "refraction", ""]),
              photon(2, 2.0, ["", "reflection", ""])]
    merged = bundle_optical(tracks)
    assert len(merged) == 2
    bundle = next(t for t in merged if getattr(t, "count", 1) == 2)
    assert np.allclose(bundle.points[:, 1], 0.5) and bundle.width_scale > 1.0


def test_frame_charts_grid_and_labels_contract():
    from trech_viz.charts import FrameCharts

    rows = []
    for tick in range(4):
        payload = {
            "physical_time_s": float(tick), "playback_time_s": float(tick),
            "positions": [[0, 0, 0]], "colors_rgba": [[1, 1, 1, 1]], "length_unit": "sim_unit",
            "samples": {"inside": 80 - 10 * tick},
            "curves": [{"chart": "g", "x": [1, 2, 3], "y": [0, tick, 1]}],
            "labels": [{"position": [0, 1, 0], "text": "voxel", "color_rgba": [1, 0, 0, 1]}],
            "grid": {"origin": [0, 0, 0], "spacing": [1, 1, 1], "shape": [2, 1, 1],
                     "values": [0, 1], "replaces_points": True,
                     "classes": [{"id": 0, "label": "batch", "style": "grains"},
                                 {"id": 1, "label": "melt", "style": "liquid"}]},
        }
        if tick == 0:
            payload["charts"] = [
                {"id": "n", "title": "inside", "x": "time", "series": [{"key": "inside"}]},
                {"id": "g", "title": "g(r)"}]
        rows.append({"tag": "material_frame", "payload": payload})
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "trech_hook_emits.jsonl"
        path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
        frames = load_material_frames(path)
    assert frames[0].samples == {"inside": 80.0} and frames[0].labels[0][1] == "voxel"
    grid = frames[0].grid
    assert grid is not None and grid.replaces_points and grid.values.shape == (2, 1, 1)
    assert grid.values[1, 0, 0] == 1
    panel = FrameCharts(frames, 200, 240)
    assert [c.title for c in panel.charts] == ["inside", "g(r)"]
    # The time series reveals only what exists at `now`.
    series = panel.charts[0].series[0]
    assert series.visible(1.0)[1].tolist() == [80.0, 70.0]
    image = panel.render(2.0, 2.0)
    assert image.shape == (240, 200, 3)


def test_clock_spanning_millennia_formats_each_value_in_its_own_unit():
    from trech_viz.animate import format_clock

    span = 2.0e11
    assert format_clock(5.0e-6, span).strip().endswith("µs")
    assert format_clock(1.8e11, span).endswith("yr")


def test_offscreen_track_render_with_split_and_charts():
    pytest = __import__("pytest")
    pytest.importorskip("pyvista")
    from trech_viz.charts import Chart, Series
    from trech_viz.tracks_view import load_run, render_tracks

    trajs = [_traj(e, 1, "gamma", [(0, 0, -10), (0, 0, 0), (3, 0, 10)], [0.0, 0.03, 0.07],
                   [1e5] * 3, ["source", "compt", "Transportation"],
                   ["emission", "scatter", "world_boundary"]) for e in range(3)]
    chart = Chart("t", series=[Series("s", "#ffffff", np.array([0.0, 1.0]),
                                      np.array([0.0, 1.0]), t=np.array([0.0, 0.05]))])
    with tempfile.TemporaryDirectory() as tmp:
        gif = Path(tmp) / "t.gif"
        render_tracks([load_run(trajs, label="a"), load_run(trajs, label="b", run_index=1)],
                      gif=str(gif), window_size=(240, 120), fps=4, seconds=1.0, split=True,
                      charts=[chart], caption=["caption line"])
        assert gif.stat().st_size > 0
