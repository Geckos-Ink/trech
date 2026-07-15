"""Pure precision-report tests (no Qt/GPU)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trech_studio.precision import build_precision_report  # noqa: E402
from trech_studio.render.playback import build_trajectory_playback  # noqa: E402


class _Trajectory:
    particle = "opticalphoton"
    points = [(0, 0, 0), (0, 0, 2), (1, 0, 4)]
    times_ns = [0, 1, 2]
    energies_ev = [2.25, 2.25, 2.25]
    materials = ["G4_AIR", "G4_WATER", "G4_WATER"]
    interactions = ["emission", "boundary", "scatter"]


class _Result:
    def run_end_scores(self):
        return {
            "n_events": 10, "viz_trajectories": 1, "viz_segments": 2,
            "primaries_transmitted_fraction": 0.4,
        }

    def summary(self):
        return {"n_events": 10, "determinism_mode": "strict", "physics_list": "QBBC"}


def test_medium_and_interaction_precision() -> None:
    playback = build_trajectory_playback([_Trajectory()])
    assert playback.medium_counts == {"G4_AIR": 1, "G4_WATER": 1}
    assert playback.medium_interaction_counts["G4_AIR:boundary"] == 1
    assert playback.medium_interaction_counts["G4_WATER:scatter"] == 1
    # One weak photon: both width scale and opacity stay deliberately low.
    assert playback.ribbon_width_scale < 0.3
    assert playback.ribbon_opacity < 0.15
    report = build_precision_report(_Result(), playback, output_px=(800, 600), supersample=2)
    assert report.simulation["medium_label_coverage"] == 1.0
    assert report.simulation["recorded_trajectory_vertices"] == 2
    assert report.representation["rendered_trajectory_segments"] == 2
    assert report.representation["trajectory_load_limit_applied"] is False
    assert report.simulation["primaries_transmitted_fraction_standard_error"] > 0.0
    assert report.representation["internal_render_pixels"] == [1600, 1200]


if __name__ == "__main__":
    test_medium_and_interaction_precision()
    print("1/1 passed")
