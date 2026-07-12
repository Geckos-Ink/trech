"""Unit tests for the pure playback model (no Qt, no GPU).

Runnable directly (``python tests/test_playback.py``) since the repo ships no pytest; each
``test_*`` is also plain-pytest compatible. Uses tiny duck-typed stand-ins for the engine's
``Trajectory`` / ``HookEmit`` so the render layer stays decoupled from ``engine`` (see
render/playback.py's layering note).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trech_studio.render.playback import (  # noqa: E402
    build_particle_playback,
    build_playback,
    build_trajectory_playback,
    wavelength_rgb,
)


@dataclass
class FakeTrajectory:
    particle: str
    points: List[Any]
    times_ns: List[float]
    energies_ev: List[float] = field(default_factory=list)


@dataclass
class FakeEmit:
    tag: str
    payload: Any


def test_trajectory_playback_sorted_and_growing() -> None:
    trajs = [
        FakeTrajectory("gamma", [(0, 0, 0), (0, 0, 10), (0, 0, 20)], [0.0, 2.0, 5.0]),
        FakeTrajectory("e-", [(1, 0, 0), (1, 0, 5)], [0.0, 1.0]),
    ]
    pb = build_trajectory_playback(trajs)
    assert pb.kind == "trajectory"
    # 2 + 1 = 3 segments, 2 verts each with 6 floats.
    assert pb.segment_count == 3
    assert pb.segment_vertices.shape == (6, 6)
    # End-times must be ascending (the growing-beam invariant).
    assert list(pb.segment_t_end) == sorted(pb.segment_t_end)
    assert pb.t_max == 5.0
    # count_at is a monotonic prefix over time.
    assert pb.count_at(-1.0) == 0
    assert pb.count_at(1.0) == 1        # only the e- 0->1ns segment
    assert pb.count_at(2.0) == 2
    assert pb.count_at(100.0) == 3
    prev = -1
    for t in np.linspace(0, 6, 20):
        c = pb.count_at(float(t))
        assert c >= prev
        prev = c


def test_trajectory_optical_colour_from_wavelength() -> None:
    # A red-ish photon (~1.9 eV -> ~650 nm) should colour its segment red-dominant.
    tr = FakeTrajectory("opticalphoton", [(0, 0, 0), (0, 0, 1)], [0.0, 0.5], [1.9, 1.9])
    pb = build_trajectory_playback([tr])
    r, g, b = pb.segment_vertices[0, 3], pb.segment_vertices[0, 4], pb.segment_vertices[0, 5]
    assert r > g and r > b
    # And the helper agrees for a blue photon (~2.75 eV -> ~450 nm).
    br, bg, bb = wavelength_rgb(2.75)
    assert bb >= br


def test_single_point_trajectory_ignored() -> None:
    pb = build_trajectory_playback([FakeTrajectory("gamma", [(0, 0, 0)], [0.0])])
    assert pb.is_empty and pb.kind == "empty"


def test_particle_playback_scales_to_mm_and_orders() -> None:
    emits = [
        FakeEmit("fluid_frame", {"time_s": 0.02, "phase": "settle", "xyz": [[0.01, 0.0, 0.1]]}),
        FakeEmit("fluid_frame", {"time_s": 0.00, "phase": "pour", "xyz": [[0.02, 0.0, 0.11], [0.0, 0.0, 0.09]]}),
        FakeEmit("other", {"xyz": [[9, 9, 9]]}),  # ignored: wrong tag
    ]
    pb = build_particle_playback(emits, tag="fluid_frame", unit_scale_mm=1000.0)
    assert pb.kind == "particles" and pb.frame_count == 2
    # Sorted by time: pour (0.0) first.
    assert pb.frames[0].phase == "pour"
    assert list(pb.frame_times) == sorted(pb.frame_times)
    # Metres -> millimetres.
    assert np.allclose(pb.frames[0].positions[0], [20.0, 0.0, 110.0])
    # Hold-last frame selection.
    assert pb.frame_index_at(-1.0) == 0
    assert pb.frame_index_at(0.019) == 0
    assert pb.frame_index_at(0.02) == 1
    assert pb.frame_index_at(9.9) == 1


def test_fluid_frame_remaps_z_up_to_y_up() -> None:
    # fluid_frame positions are z-up (the glass fill runs along z); the viewport is y-up. A
    # frame whose tallest coordinate is z must come out with that height on the y (vertical)
    # axis, else the water renders lying on its side (the bug this remap fixes).
    fluid = FakeEmit("fluid_frame", {"time_s": 0.0, "xyz": [[0.01, 0.02, 0.09]]})  # metres, z tallest
    pb = build_playback([], [fluid])
    assert pb.kind == "particles"
    # (x, y, z_up) * 1000 -> (x, z_up, y): height 90 lands on the y axis.
    assert np.allclose(pb.frames[0].positions[0], [10.0, 90.0, 20.0])
    # Explicit up_axis="y" is a no-op (backward-compatible default).
    pb_y = build_particle_playback([fluid], tag="fluid_frame", unit_scale_mm=1000.0, up_axis="y")
    assert np.allclose(pb_y.frames[0].positions[0], [10.0, 20.0, 90.0])


def test_build_playback_prefers_trajectories_then_particles() -> None:
    traj = FakeTrajectory("gamma", [(0, 0, 0), (0, 0, 1)], [0.0, 1.0])
    fluid = FakeEmit("fluid_frame", {"time_s": 0.0, "xyz": [[0.0, 0.0, 0.0]]})
    # Trajectories win when present.
    assert build_playback([traj], [fluid]).kind == "trajectory"
    # Fall back to a known particle family.
    assert build_playback([], [fluid]).kind == "particles"
    # Neither -> empty.
    assert build_playback([], []).is_empty


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
