"""Offscreen Qt tests for the scenario browser + timeline panels.

Run with an offscreen platform so no display is needed::

    QT_QPA_PLATFORM=offscreen python tests/test_ui_panels.py

These are behavioural (tree population, activation signal, timeline enable/scrub), not pixel
tests — the wgpu viewport is exercised only through its pending-state passthrough elsewhere.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from trech_studio.render.playback import Playback, ParticleFrame  # noqa: E402
from trech_studio.ui.scenarios import ScenarioBrowser  # noqa: E402
from trech_studio.ui.timeline import Timeline  # noqa: E402

_APP = QApplication.instance() or QApplication([])


def test_scenario_browser_lists_and_prunes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "experiments").mkdir()
        (root / "experiments" / "a.js").write_text("// a", encoding="utf-8")
        (root / "experiments" / "notes.txt").write_text("skip me", encoding="utf-8")
        (root / "empty_branch").mkdir()          # no scenario files -> pruned
        (root / "lab").mkdir()
        (root / "lab" / "cfg.json").write_text("{}", encoding="utf-8")

        browser = ScenarioBrowser([root])
        top = browser.tree.topLevelItem(0)
        labels = {top.child(i).text(0) for i in range(top.childCount())}
        assert "experiments" in labels
        assert "lab" in labels
        assert "empty_branch" not in labels     # pruned: holds no scenarios
        # notes.txt is not a scenario suffix, so experiments/ shows only a.js.
        exp = next(top.child(i) for i in range(top.childCount()) if top.child(i).text(0) == "experiments")
        assert exp.childCount() == 1 and exp.child(0).text(0) == "a.js"


def test_scenario_activation_emits_path() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "s.js").write_text("// s", encoding="utf-8")
        browser = ScenarioBrowser([root])
        seen = []
        browser.scenario_activated.connect(lambda p: seen.append(p))
        top = browser.tree.topLevelItem(0)
        file_item = top.child(0)
        browser._on_activated(file_item)
        assert len(seen) == 1
        assert Path(seen[0]).name == "s.js"


def _fake_particle_playback(n_frames: int) -> Playback:
    frames = [
        ParticleFrame(time=float(i) * 0.5, positions=np.zeros((3, 3), dtype=np.float32), phase="pour")
        for i in range(n_frames)
    ]
    times = np.asarray([f.time for f in frames], dtype=np.float64)
    return Playback(kind="particles", unit="s", t_min=times[0], t_max=times[-1],
                    frames=frames, frame_times=times, label="fake")


def test_timeline_enable_and_scrub() -> None:
    tl = Timeline()
    # Empty -> disabled.
    tl.set_playback(None)
    assert not tl._play_button.isEnabled()
    assert "no playback" in tl._time_label.text()

    pb = _fake_particle_playback(5)
    seen = []
    tl.cursor_changed.connect(lambda t: seen.append(t))
    tl.set_playback(pb)
    assert tl._play_button.isEnabled() and tl._slider.isEnabled()
    # On load the cursor sits at the end (full result shown).
    assert seen and abs(seen[-1] - pb.t_max) < 1e-9
    assert "frame 5/5" in tl._time_label.text()

    # A user scrub to the middle emits the mapped cursor and updates the label.
    seen.clear()
    tl._slider.setValue(500)
    assert seen and abs(seen[-1] - (pb.t_min + 0.5 * (pb.t_max - pb.t_min))) < 1e-9
    assert "frame 3/5" in tl._time_label.text()


def test_timeline_single_frame_not_scrubbable() -> None:
    tl = Timeline()
    tl.set_playback(_fake_particle_playback(1))     # t_min == t_max
    assert not tl._slider.isEnabled()
    assert not tl._play_button.isEnabled()


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
