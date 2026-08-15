"""Scale-ladder builder + panel: the inference cascade made legible, honestly.

The fixtures below are trimmed copies of emits produced by real runs (``glass_from_sand.js`` for
the cascade shape, ``polyurethane_foam.js`` for the operator shape), so the tests fail if the
engine's emitted trust vocabulary and Studio's reader drift apart.

What is asserted is mostly the honesty contract: a stage with no measured accuracy must SAY it has
none, an extrapolating/starved/off-band stage must be badged, and Studio must not invent a count
the scenario did not emit.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from trech_studio.cascade import (  # noqa: E402
    BADGE_EXTRAPOLATING,
    BADGE_JOINT_STARVED,
    BADGE_HEURISTIC_DOMAIN,
    BADGE_NO_HOLDOUT,
    BADGE_OFF_BAND,
    BADGE_STARVED,
    build_scale_ladder,
)
from trech_studio.engine.outputs import load_run_result  # noqa: E402
from trech_studio.ui.cascade import ScaleLadderPanel, stage_summaries  # noqa: E402

_APP = QApplication.instance() or QApplication([])


def _cascade_stage(model, scale, **over):
    """A `__cascade.trace[i]` entry with the fields the engine actually emits."""
    stage = {
        "model": model, "scale": scale, "ran": True,
        "missingInputs": [], "outputs": ["y_" + model],
        "inDomain": True, "domainMeasured": True, "extrapolation": 0.0,
        "maxStandardizedDeviation": 1.2, "outOfDomainInputs": [], "starvedInputs": [],
        "scaleMismatch": False, "trainedScale": scale,
        "holdoutR2": 0.97, "holdoutSamples": 6000,
        "outputAccuracy": {"y_" + model: {"r2": 0.97, "mae": 0.01, "rmse": 0.02}},
    }
    stage.update(over)
    return stage


# A two-band cascade seeded from the Geant4 base: the nano stage is trained, the macro stage is an
# illustrative hand-authored map extrapolating past its heuristic domain.
_CASCADE_EMIT = {
    "phase": "hook_emit", "hook": "onEventEnd", "tag": "furnace", "event_id": 0,
    "step_index": -1,
    "payload": {"cascade": {
        "seedKeys": [
            "context.heater_temperature_k", "edep_mev", "track_count",
            "material.G4_AIR.density_g_per_cm3", "material.SiO2.number_density.Si",
        ],
        "stagesRun": 2, "stagesExtrapolating": 1, "stagesScaleMismatched": 0,
        "stagesStarved": 1,
        "trace": [
            _cascade_stage("nano_batch_material_response", "nano", starvedInputs=["edep_mev"]),
            _cascade_stage(
                "macro_furnace_response", "macro",
                inDomain=False, domainMeasured=False, extrapolation=2.5,
                outOfDomainInputs=["melt_fraction"], scaleMismatch=True, trainedScale="meso",
                holdoutR2=None, holdoutSamples=None, outputAccuracy={},
                missingInputs=["carrier_temperature_k"],
            ),
        ],
    }},
}

# The operator shape: a scenario nests the ctx.evolve report under its own key and renames the
# batched counters, so detection must key on the STAGE record, not the container name.
_OPERATOR_EMIT = {
    "phase": "hook_emit", "hook": "onEventEnd", "tag": "polyurethane_foam_scenario",
    "event_id": 1, "step_index": -1,
    "payload": {"chemistry_inference": {
        "source": "operator",
        "parcel_step_inferences": 2812320,
        "selection": {"mode": "contextual", "status": "selected"},
        "stage_trace": [{
            "model": "meso_reaction_operator", "scale": "meso", "ran": True,
            "elementKind": "", "elementsMatched": 620, "elementsOutOfDomain": 0,
            "elementsStarved": 0, "maxExtrapolation": 0.0,
            "maxStandardizedDeviation": 2.69, "missingInputs": [],
            "integratedFields": ["gel", "blow", "temperature_k"],
            "assignedFields": ["rigidity"], "intermediateOutputs": [],
            "unappliedFieldOutputs": [], "domainMeasured": True,
            "outOfDomainInputs": [], "starvedInputs": [],
            "scaleMismatch": False, "trainedScale": "meso",
            "holdoutR2": 0.992945481258875, "holdoutSamples": 38565,
            "outputAccuracy": {
                "d_gel_dt": {"r2": 0.9995940310343969, "mae": 6.3e-05, "rmse": 8.248e-05},
                "d_blow_dt": {"r2": 0.9997531260682152, "mae": 6.7e-05, "rmse": 9.536e-05},
            },
        }],
    }},
}


def _write_emits(root: Path, records) -> Path:
    out = root / "run"
    out.mkdir()
    (out / "trech_hook_emits.jsonl").write_text(
        "\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8"
    )
    return out


def test_ladder_reads_the_cascade_bands_and_geant4_seed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = load_run_result(_write_emits(Path(tmp), [_CASCADE_EMIT]))
        ladder = build_scale_ladder(result, "run")
        assert not ladder.is_empty
        assert ladder.bands_bridged == ["nano", "macro"]  # ladder order, not emitted order

        pass_ = ladder.passes[0]
        assert pass_.kind == "cascade"
        assert pass_.bands == ["nano", "macro"]
        # The Geant4-derived subset of the seed is separated from scenario-supplied context.
        assert pass_.geant4_seed_keys == [
            "edep_mev", "track_count",
            "material.G4_AIR.density_g_per_cm3", "material.SiO2.number_density.Si",
        ]
        assert "context.heater_temperature_k" not in pass_.geant4_seed_keys
        assert pass_.stages_extrapolating == 1


def test_ladder_badges_only_flags_the_engine_set() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = load_run_result(_write_emits(Path(tmp), [_CASCADE_EMIT]))
        ladder = build_scale_ladder(result)
        nano, macro = ladder.passes[0].stages

        # Trained stage: in-domain against a MEASURED hull, on its band, with metrics -- the only
        # flag it earns is the starved-region one the engine set.
        assert nano.badges == [BADGE_STARVED]
        assert nano.starved_inputs == ["edep_mev"]

        # Illustrative map: every honesty flag, including "nobody measured this".
        assert BADGE_EXTRAPOLATING in macro.badges
        assert BADGE_OFF_BAND in macro.badges
        assert BADGE_HEURISTIC_DOMAIN in macro.badges
        assert BADGE_NO_HOLDOUT in macro.badges
        assert macro.trained_scale == "meso"
        assert macro.missing_inputs == ["carrier_temperature_k"]


def test_absent_accuracy_is_stated_not_shown_as_zero() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = load_run_result(_write_emits(Path(tmp), [_CASCADE_EMIT]))
        nano, macro = build_scale_ladder(result).passes[0].stages

        # Measured: the per-output split is reported with its measured 1-sigma residual.
        assert nano.holdout_r2 == 0.97
        assert [a.name for a in nano.output_accuracy] == ["y_nano_batch_material_response"]
        assert nano.output_accuracy[0].rmse == 0.02
        assert "σ=0.02" in nano.accuracy_note()

        # Absent: said in words, and no number is invented for it.
        assert macro.holdout_r2 is None
        assert macro.output_accuracy == []
        assert "no held-out accuracy" in macro.accuracy_note()
        assert "0" not in macro.accuracy_note().split("—")[0]


def test_operator_report_is_found_under_a_scenario_chosen_key() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = load_run_result(_write_emits(Path(tmp), [_OPERATOR_EMIT]))
        ladder = build_scale_ladder(result)
        assert len(ladder.passes) == 1
        pass_ = ladder.passes[0]
        assert pass_.kind == "operator"          # no seedKeys/stagesRun -> not a cascade
        assert pass_.path == "chemistry_inference.stage_trace"
        assert pass_.selection_status == "selected"
        # The scenario renamed the batched counter, so Studio reports it as unrecorded rather
        # than guessing a total from the stage trace.
        assert pass_.inference_count is None

        stage = pass_.stages[0]
        assert stage.badges == []                # trained, in-domain, on band, measured
        assert stage.predicts == ["gel", "blow", "temperature_k", "rigidity"]
        assert stage.elements_matched == 620
        assert [a.name for a in stage.output_accuracy] == ["d_blow_dt", "d_gel_dt"]  # sorted
        assert "σ=9.536e-05" in stage.accuracy_note()


def test_joint_starvation_is_distinguished_from_unchecked() -> None:
    """The multivariate density check has three outcomes, not two.

    Covered, jointly starved, and NOT CHECKED (the model carries no joint
    reference) must read differently — an unchecked stage shown as clean would
    be exactly the silent guess the trust profile exists to prevent.
    """
    covered = dict(_CASCADE_EMIT)
    stages = [
        _cascade_stage("covered", "nano", jointMeasured=True, jointStarved=False,
                       jointDistance=0.21, jointRadius=0.5, starvedInputs=[]),
        _cascade_stage("in_the_hole", "micro", jointMeasured=True, jointStarved=True,
                       jointDistance=3.4, jointRadius=0.5, starvedInputs=[]),
        _cascade_stage("never_checked", "macro", starvedInputs=[]),  # no joint fields
    ]
    covered["payload"] = {"cascade": {"seedKeys": [], "stagesRun": 3, "trace": stages}}

    with tempfile.TemporaryDirectory() as tmp:
        result = load_run_result(_write_emits(Path(tmp), [covered]))
        ok, hole, unchecked = build_scale_ladder(result).passes[0].stages

        assert ok.joint_measured is True and ok.joint_starved is False
        assert BADGE_JOINT_STARVED not in ok.badges
        assert "inside a region training covered" in ok.joint_note()

        assert BADGE_JOINT_STARVED in hole.badges
        # The whole point: nothing else flags it.
        assert hole.in_domain is True and hole.starved_inputs == []
        assert BADGE_EXTRAPOLATING not in hole.badges
        assert BADGE_STARVED not in hole.badges
        assert "interpolation across untrained space" in hole.joint_note()

        assert unchecked.joint_measured is None
        assert BADGE_JOINT_STARVED not in unchecked.badges  # not a false alarm
        assert "was not checked" in unchecked.joint_note()  # but not silent either


def test_repeated_passes_collapse_and_disclose_the_count() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        # The same cascade re-emitted every event (emits are append-mode).
        repeated = [dict(_CASCADE_EMIT, event_id=i) for i in range(5)]
        result = load_run_result(_write_emits(Path(tmp), repeated + [_OPERATOR_EMIT]))
        ladder = build_scale_ladder(result)
        assert [p.occurrences for p in ladder.passes] == [5, 1]
        assert len(ladder.passes) == 2


def test_panel_renders_the_ladder_and_an_empty_run() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        result = load_run_result(_write_emits(Path(tmp), [_CASCADE_EMIT, _OPERATOR_EMIT]))
        panel = ScaleLadderPanel()
        panel.show_ladder(build_scale_ladder(result, "run"))
        shown = panel.ladder()
        assert shown is not None and len(shown.passes) == 2
        assert stage_summaries(shown) == [
            "furnace · nano · nano_batch_material_response [STARVED REGION]",
            "furnace · macro · macro_furnace_response [EXTRAPOLATING, OFF TRAINED BAND, "
            "HEURISTIC DOMAIN, NO MEASURED ACCURACY]",
            "polyurethane_foam_scenario · meso · meso_reaction_operator",
        ]

    with tempfile.TemporaryDirectory() as tmp:
        # A run with no inference (strict mode, or a scenario that emits no trace) says so.
        empty = load_run_result(_write_emits(Path(tmp), [
            {"phase": "hook_emit", "hook": "onRunEnd", "tag": "summary", "event_id": -1,
             "step_index": -1, "payload": {"merges": 8}},
        ]))
        ladder = build_scale_ladder(empty, "run")
        assert ladder.is_empty
        panel = ScaleLadderPanel()
        panel.show_ladder(ladder)
        assert panel.ladder() is None  # the empty case falls through to the message view


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
