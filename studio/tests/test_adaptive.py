"""Adaptive controls change representation work, never the emitted state."""
import math
import os
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
from trech_studio.render.adaptive import RenderBudget, suggested_memory_mib
from trech_studio.render.mesh import for_shape
from trech_studio.scene.model import Shape


def test_frame_feedback_is_continuous_bounded_and_optional():
    policy = RenderBudget(target_fps=60)
    for _ in range(16):
        policy.observe(0.1)
    assert 0.125 <= policy.detail < 1
    slow = policy.detail
    for _ in range(80):
        policy.observe(0.001)
    assert policy.detail > slow
    before = policy.detail
    assert not policy.observe(math.nan)
    assert policy.detail == before
    policy.adaptive = False
    for _ in range(40):
        policy.observe(1)
    assert policy.detail == before


def test_memory_and_tessellation_are_dynamic():
    low, high = RenderBudget(memory_mib=16), RenderBudget(memory_mib=512)
    assert low.trajectory_limits()[0] < high.trajectory_limits()[0]
    assert low.trajectory_limits()[1] < high.trajectory_limits()[1]
    assert low.cache_frames(16 * 2**20) == 1
    assert high.cache_frames(16 * 2**20) == 8
    assert 64 <= suggested_memory_mib() <= 1024
    shape = Shape(type="sphere", outer_radius_mm=2)
    indices = [for_shape(shape, x).index_count for x in (0.5, 0.75, 1, 1.25, 1.5, 2)]
    assert len(set(indices)) == 6


def test_controls_enable_only_supported_simulation_axes():
    from PySide6.QtWidgets import QApplication
    from trech_studio.ui.adaptive_controls import AdaptiveControls
    app = QApplication.instance() or QApplication([])
    panel = AdaptiveControls()
    panel.set_config({"determinism": {"mode": "strict"}})
    assert not panel.refine.isEnabled() and not panel.seconds.isEnabled()
    panel.set_config({"precision": {"axes": [{"role": "spatial"}]},
                      "determinism": {"mode": "predictive"}})
    panel.refine.setChecked(True)
    panel.refinement.setValue(3.125)
    panel.seconds.setValue(0.25)
    assert panel.command_args() == ["--refinement", "3.125", "--time-budget", "0.25"]
    panel.set_config({"determinism": {"mode": "strict"}})
    assert panel.command_args() == []
    panel.close()


def test_budgeted_output_reports_completed_counts_and_limit_badges(tmp_path):
    import json
    from trech_studio.engine.outputs import load_run_result
    from trech_studio.precision import build_precision_report
    from trech_studio.render.playback import Playback
    from trech_studio.run_summary import build_run_summary
    from trech_studio.cascade import build_scale_ladder
    scores = {"phase": "run_end", "n_events": 4, "requested_events": 400,
              "time_budget_seconds": 0.5, "simulation_wall_seconds": 0.6,
              "stop_reason": "time_budget"}
    (tmp_path / "trech_scores.jsonl").write_text(json.dumps(scores))
    (tmp_path / "trech_hook_emits.jsonl").write_text(json.dumps({
        "tag": "depth", "payload": {"trace": [
            {"model": "stage", "scale": "nano", "ran": False,
             "outputs": [], "skipReason": "stage_budget"}]}}))
    run = load_run_result(tmp_path)
    precision = build_precision_report(run, Playback(kind="empty"))
    assert precision.simulation["events"] == 4
    assert precision.simulation["requested_events"] == 400
    assert build_run_summary(run).section("Adaptive simulation budget") is not None
    ladder = build_scale_ladder(run)
    assert "STAGE BUDGET" in ladder.passes[0].stages[0].badges


def test_actual_renderer_detail_preserves_native_state_and_camera():
    import pytest
    from types import SimpleNamespace
    from trech_studio.capture import _offscreen_renderer, _frame_rgb
    from trech_studio.scene.model import SceneModel
    from trech_studio.render.playback import build_material_frame_playback
    canvas, renderer, reason = _offscreen_renderer(320, 240, "dark")
    if renderer is None:
        pytest.skip(reason)
    payload = {"positions": [[-1, 0, 0], [1, 0, 0]], "radii": [0.5, 0.7],
               "colors_rgba": [[1, 0, 0, 1], [0, 1, 0, 1]],
               "length_unit": "angstrom", "time_s": 0}
    pb = build_material_frame_playback([SimpleNamespace(tag="material_frame", payload=payload)])
    renderer.set_scene(SceneModel())
    renderer.set_playback(pb)
    original = pb.frames[0].positions.copy()
    yaw, distance = renderer.camera.yaw, renderer.camera.distance
    for detail in [0.5, 1.375, 3]:
        renderer.set_render_budget(RenderBudget(adaptive=False, detail=detail, memory_mib=16))
        assert _frame_rgb(canvas, 320, 240) is not None
        assert renderer.precision_info()["sphere_sectors"] == round(16 * detail)
        assert renderer.camera.yaw == yaw and renderer.camera.distance == distance
        np.testing.assert_array_equal(pb.frames[0].positions, original)
    surface_payload = dict(payload, length_unit="mm", render_surface={
        "mode": "metaball", "grid_spacing_mm": 0.5, "sigma_mm": 0.6,
        "iso_level": 0.52})
    surface_pb = build_material_frame_playback([
        SimpleNamespace(tag="material_frame", payload=surface_payload)])
    renderer.set_playback(surface_pb)
    for detail in [0.5, 1.5]:
        renderer.set_render_budget(RenderBudget(adaptive=False, detail=detail, memory_mib=16))
        assert _frame_rgb(canvas, 320, 240) is not None
        info = renderer.precision_info()
        assert info["particle_representation"] == "gaussian_density_surface"
        assert info["surface_grid_spacing_mm"] == 0.5 / detail
        assert surface_pb.frames[0].surface.grid_spacing_mm == 0.5
