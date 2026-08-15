"""Offscreen Qt tests for the scenario browser, timeline, run-summary and emit panels.

Run with an offscreen platform so no display is needed::

    QT_QPA_PLATFORM=offscreen python tests/test_ui_panels.py

These are behavioural (tree population, activation signal, timeline enable/scrub), not pixel
tests — the wgpu viewport is exercised only through its pending-state passthrough elsewhere.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from trech_studio.render.playback import Playback, ParticleFrame  # noqa: E402
from trech_studio.engine.outputs import load_run_result  # noqa: E402
from trech_studio.engine.parameters import ScenarioParameter, inspection_from_json  # noqa: E402
from trech_studio.run_summary import build_run_summary  # noqa: E402
from trech_studio.ui.emits import EmitInspector  # noqa: E402
from trech_studio.ui.run_summary import RunSummaryPanel  # noqa: E402
from trech_studio.ui.scenarios import ScenarioBrowser  # noqa: E402
from trech_studio.ui.scenario_options import ScenarioOptions  # noqa: E402
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


def test_scenario_inspection_and_typed_options() -> None:
    inspection = inspection_from_json(
        '{"config":{"run":{"nEvents":20}},"parameters":['
        '{"id":"temperature_k","type":"number","label":"Temperature",'
        '"group":"Environment","unit":"K","default":293.15,"value":293.15,'
        '"min":250,"max":350,"step":0.5},'
        '{"id":"quality","type":"choice","default":"balanced",'
        '"value":"balanced","choices":["fast","balanced","fine"]},'
        '{"id":"show_labels","type":"boolean","default":true,"value":true}'
        ']}'
    )
    assert len(inspection.parameters) == 3
    options = ScenarioOptions()
    options.set_parameters(inspection.parameters)
    assert options.values() == {
        "temperature_k": 293.15,
        "quality": "balanced",
        "show_labels": True,
    }
    options._widgets["temperature_k"].setValue(310.5)
    options._widgets["quality"].setCurrentIndex(2)
    assert options.command_args() == [
        "--param", "temperature_k=310.5",
        "--param", 'quality="fine"',
        "--param", "show_labels=true",
    ]
    # Reinspection after saving source preserves compatible user choices.
    options.set_parameters(inspection.parameters, preserve_values=True)
    assert options.values()["temperature_k"] == 310.5
    options.reset_defaults()
    assert options.values()["temperature_k"] == 293.15


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


def test_timeline_discloses_accelerated_physical_time() -> None:
    frame = ParticleFrame(
        time=12.0, positions=np.zeros((1, 3), dtype=np.float32),
        phase="accelerated_30c_evaporation", physical_time_s=3605.4, time_scale=545.0,
    )
    pb = Playback(
        kind="particles", unit="playback s", t_min=0.0, t_max=12.0,
        frames=[frame], frame_times=np.asarray([12.0]), time_accelerated=True,
    )
    tl = Timeline()
    tl.set_playback(pb)
    assert "physical 60.1 min" in tl._time_label.text()
    assert "545× clock" in tl._time_label.text()


# --- run summary + emit inspector ---------------------------------------------------------

_PROVENANCE = [
    {"phase": "run_start", "seed": 424242, "n_events": 100, "determinism_mode": "predictive",
     "predictive_mode": True, "physics_list": "QBBC+Optical", "geant4_version": "geant4-11-2",
     "rng_engine": "MixMaxRng", "config_hash": "df1188206ab7f5ec",
     "hooks_registered": ["onEventEnd"]},
]
_SCORES = [
    {"phase": "run_end", "seed": 424242, "n_events": 100, "determinism_mode": "predictive",
     "predictive_mode": True, "physics_list": "QBBC+Optical", "total_edep_mev": 2.1641,
     "primaries_emitted": 100, "primaries_uncollided": 42,
     "primaries_uncollided_fraction": 0.42,
     "analytic_checks": [
         {"type": "beer_lambert", "label": "Beer-Lambert transmission", "available": True,
          "measured_field": "primaries_uncollided_fraction", "classical_predicted": 0.4265,
          "geant4_measured": 0.42, "delta": -0.0065, "relative_error": -0.0152,
          "tolerance_rel": 0.05, "within_tolerance": True}],
     "analytic_checks_within_tolerance": True,
     "hook_predict_count": 240, "hook_predict_out_of_domain_count": 6,
     "hook_emit_count": 3, "hook_emit_dropped_count": 0,
     "precision_profile": "custom",
     "precision_note": "spatial/temporal axes refine the solver",
     "precision_axes": [
         {"name": "parcels", "role": "spatial", "control": "wax_representatives",
          "unit": "parcels", "value": 180.0, "baseline_value": 240.0,
          "representation_only": False, "overridden": True},
         {"name": "surface_grid", "role": "representation",
          "control": "render_surface_grid_mm", "unit": "mm", "value": 0.75,
          "baseline_value": 1.25, "representation_only": True, "overridden": False}]},
]
_EMITS = [
    {"phase": "hook_emit", "hook": "onEventEnd", "tag": "material_frame", "event_id": 0,
     "step_index": -1, "payload": {"time_s": 0.0, "positions_mm": [[0, 0, 0]] * 40}},
    {"phase": "hook_emit", "hook": "onEventEnd", "tag": "material_frame", "event_id": 1,
     "step_index": -1, "payload": {"time_s": 0.5, "positions_mm": [[0, 0, 1]] * 40}},
    {"phase": "hook_emit", "hook": "onRunEnd", "tag": "lava_lamp_summary", "event_id": -1,
     "step_index": -1, "payload": {"merges": 8, "splits": 10}},
]


def _write_run(root: Path) -> Path:
    out = root / "run"
    out.mkdir()
    def dump(name, records):
        (out / name).write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    dump("trech_provenance.jsonl", _PROVENANCE)
    dump("trech_scores.jsonl", _SCORES)
    dump("trech_hook_emits.jsonl", _EMITS)
    return out


def test_run_summary_reports_provenance_gaps_and_inference() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = load_run_result(_write_run(Path(tmp)))
        summary = build_run_summary(result)
        panel = RunSummaryPanel()
        panel.show_summary(summary)
        assert panel.summary() is summary

        prov = summary.section("Determinism & provenance")
        rows = {r.label: r for r in prov.rows}
        assert rows["seed"].value == "424242"
        assert rows["physics list"].value == "QBBC+Optical"
        # Predictive mode must be flagged: an inferred result is not a strict Geant4 tally.
        assert rows["determinism mode"].warn and "not strict" in rows["determinism mode"].note

        # A tallied fraction carries its labelled binomial sampling error, nothing more.
        transport = {r.label: r for r in summary.section("Primaries & transport").rows}
        assert transport["uncollided fraction"].value.startswith("0.42 ±")
        assert "binomial standard error" in transport["uncollided fraction"].note

        # The analytic check shows the GAP, not just a pass/fail.
        analytic = summary.section("Analytic cross-checks").rows[0]
        assert "classical 0.4265 vs Geant4 0.42" in analytic.value
        assert "-1.520% relative" in analytic.note and "tolerance 5.000%" in analytic.note

        # Out-of-domain inference is surfaced as a caution with its share.
        inference = {r.label: r for r in summary.section("Learned inference").rows}
        assert inference["inferences run"].value == "240"
        assert inference["out of trained domain"].warn
        assert "2.50% of inferences" in inference["out of trained domain"].value
        assert any("learned prediction" in c for c in summary.caveats)


def test_run_summary_reports_precision_axes_not_one_quality_number() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        summary = build_run_summary(load_run_result(_write_run(Path(tmp))))
        section = summary.section("Precision profile")
        rows = {r.label: r for r in section.rows}
        # A half-followed rung is reported as custom, with the reason.
        assert rows["profile"].value == "custom"
        assert "overrode the profile" in rows["profile"].note
        # Each axis says what it changed, in its own unit, against the reference.
        assert rows["parcels"].value == "180 parcels"
        assert "role spatial" in rows["parcels"].note
        assert "balanced reference 240" in rows["parcels"].note
        assert "overridden" in rows["parcels"].note
        # A display axis can never read as improved physics.
        assert "REPRESENTATION ONLY" in rows["surface_grid"].note


def test_run_summary_survives_an_empty_output_dir() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        summary = build_run_summary(load_run_result(Path(tmp)))
        panel = RunSummaryPanel()
        panel.show_summary(summary)
        assert summary.is_empty
        assert any("No trech_provenance.jsonl" in c for c in summary.caveats)


def test_emit_inspector_filters_and_jumps_to_the_emitted_frame() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = load_run_result(_write_run(Path(tmp)))
        panel = EmitInspector()
        panel.set_run(result)
        assert len(panel.visible_emits()) == 3

        # Tag filter (combo entries are "tag (count)"), then a payload text filter.
        panel._tag_combo.setCurrentIndex(panel._tag_combo.findData("material_frame"))
        assert [e.tag for e in panel.visible_emits()] == ["material_frame", "material_frame"]
        panel._search.setText("nothing-matches-this")
        assert panel.visible_emits() == []
        panel._search.setText("")

        # Long arrays are truncated for DISPLAY only, and say so.
        panel.select_row(0)
        assert "display-truncated" in panel._payload.toPlainText()

        # With the timeline playing this tag, the n-th emit maps to the n-th emitted frame;
        # the cursor is the frame's own engine-emitted time, never an invented one.
        pb = _fake_particle_playback(2)
        pb.source_tag = "material_frame"
        panel.set_playback(pb)
        seen = []
        panel.cursor_requested.connect(lambda t: seen.append(t))
        panel.select_row(1)
        panel._jump_to_selected()
        assert seen == [pb.frames[1].time]

        # A tag the timeline is not playing has no frame to jump to.
        panel._tag_combo.setCurrentIndex(panel._tag_combo.findData("lava_lamp_summary"))
        panel.select_row(0)
        assert not panel._jump_button.isEnabled()


def test_timeline_set_cursor_rejects_times_outside_the_run() -> None:
    tl = Timeline()
    pb = _fake_particle_playback(5)
    tl.set_playback(pb)
    assert tl.set_cursor(pb.frames[2].time)
    assert abs(tl.cursor_time() - pb.frames[2].time) < 1e-9
    assert not tl.set_cursor(pb.t_max + 10.0)      # a moment this run never emitted
    assert abs(tl.cursor_time() - pb.frames[2].time) < 1e-9


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
