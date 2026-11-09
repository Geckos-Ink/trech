"""Headless tests for grading a loaded run against its bundle's declared checks.

The declarations come from an injected inspection callable (the real app uses
``trech inspect``); grading uses the validation suite's own evaluator from this
checkout, so Studio and the suite cannot disagree.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trech_studio.bundle_checks import (  # noqa: E402
    SECTION_TITLE, bundle_check_section, grade_run, load_evaluator, recorded_invocation, resolve_scenario)
from trech_studio.engine.locator import locate_engine  # noqa: E402
from trech_studio.engine.outputs import load_run_result  # noqa: E402
from trech_studio.engine.parameters import inspect_scenario, inspection_from_json  # noqa: E402
from trech_studio.run_summary import build_run_summary  # noqa: E402

REPO = Path(__file__).resolve().parents[2]

CONTRACTS = {"sample": {
    "schema": "trech_scenario_validation_v1",
    "checks": [{"phase": "run_end", "field": "n_events", "op": "gt", "expected": 0},
               {"phase": "run_end", "field": "hook_emit_dropped_count", "op": "eq", "expected": 0, "missing": 0}],
    "family_case": "sample_case",
    "family_checks": [{"id": "within", "phase": "run_end", "field": "analytic_checks[?type=t].within_tolerance",
                       "aggregate": "all", "op": "eq", "expected": True}],
    "family_sweeps": [{"family_case": "sample_sweep", "runs": [{"id": "a"}], "checks": []}],
}}


def _run(root: Path, within: bool = True, args=None) -> Path:
    scenario = root / "examples" / "sample" / "sample.js"
    scenario.parent.mkdir(parents=True, exist_ok=True)
    scenario.write_text("// fixture\n")
    out = root / "build" / "runs" / "out_sample"
    out.mkdir(parents=True, exist_ok=True)
    cli = args if args is not None else ["trech", "run", "examples/sample/sample.js", "--param", "energy=1.5",
                                         "--output", str(out)]
    (out / "trech_provenance.jsonl").write_text(
        json.dumps({"phase": "run_start", "cli_args": cli, "n_events": 4}) + "\n")
    (out / "trech_scores.jsonl").write_text(json.dumps(
        {"phase": "run_end", "n_events": 4, "analytic_checks": [{"type": "t", "within_tolerance": within}]}) + "\n")
    return out


def test_invocation_and_scenario_resolution() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        out = _run(Path(tmp))
        result = load_run_result(out)
        argument, params = recorded_invocation(result)
        assert argument == "examples/sample/sample.js" and params == ["--param", "energy=1.5"]
        # Found through an ancestor of the output folder; never guessed.
        assert resolve_scenario(argument, out) == (Path(tmp) / "examples/sample/sample.js").resolve()
        assert resolve_scenario("examples/absent.js", out) is None


def test_graded_run_uses_the_suite_evaluator() -> None:
    evaluator = load_evaluator(REPO)
    assert evaluator is not None and hasattr(evaluator, "evaluate_sweep")
    seen = []

    def inspect(path, params):
        seen.append((path.name, params))
        return CONTRACTS

    with tempfile.TemporaryDirectory() as tmp:
        report = grade_run(load_run_result(_run(Path(tmp))), inspect, REPO)
        assert seen == [("sample.js", ["--param", "energy=1.5"])]
        assert report.status == "graded" and report.passed == 3 and report.failed == 0
        assert report.sweeps == ["sample_sweep"]
        section = bundle_check_section(report)
        rows = {row.label: row for row in section.rows}
        assert rows["verdict"].value == "3/3 declared checks pass" and not rows["verdict"].warn
        assert "sample.validation.js" in rows["verdict"].note
        assert rows["sample_case · within"].value == "pass"
        assert rows["sweep · sample_sweep"].value == "not graded"
        assert "current source on disk" in section.note

        failing = grade_run(load_run_result(_run(Path(tmp), within=False)), inspect, REPO)
        row = {r.label: r for r in bundle_check_section(failing).rows}["sample_case · within"]
        assert row.value == "FAIL" and row.warn and "[all]" in row.note and "= False" in row.note


@pytest.mark.parametrize("inspect, args, reason", [
    (None, None, "engine unavailable"),
    (lambda p, a: CONTRACTS, ["trech", "inspect", "x.js"], "no `trech run"),
    (lambda p, a: CONTRACTS, ["trech", "run", "examples/missing.js"], "not found on disk"),
    (lambda p, a: (_ for _ in ()).throw(RuntimeError("boom")), None, "inspection failed: boom"),
    (lambda p, a: {}, None, "declares no validation companion"),
])
def test_unavailable_reasons_are_shown(inspect, args, reason) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        report = grade_run(load_run_result(_run(Path(tmp), args=args)), inspect, REPO)
        assert report.status == "unavailable" and reason in report.reason
        row = bundle_check_section(report).rows[0]
        assert row.value == "not graded" and row.warn


def test_malformed_declarations_are_unavailable_not_passing() -> None:
    bad = {"sample": {"schema": "other", "checks": []}}
    with tempfile.TemporaryDirectory() as tmp:
        report = grade_run(load_run_result(_run(Path(tmp))), lambda p, a: bad, REPO)
        assert report.status == "unavailable" and "could not be graded" in report.reason


def test_inspection_carries_validation_declarations() -> None:
    raw = {"config": {}, "parameters": [], "authoring": {"sources": [], "validation": CONTRACTS}}
    assert inspection_from_json(json.dumps(raw)).validation == CONTRACTS
    raw["authoring"]["validation"] = []
    with pytest.raises(ValueError):
        inspection_from_json(json.dumps(raw))


def test_real_bundle_through_engine_inspection() -> None:
    engine = locate_engine(REPO)
    if not engine.available:
        pytest.skip("no trech binary")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out"
        out.mkdir()
        scenario = REPO / "examples/scenarios/analytic_photo_fraction/analytic_photo_fraction.js"
        (out / "trech_provenance.jsonl").write_text(json.dumps(
            {"phase": "run_start", "cli_args": ["trech", "run", str(scenario), "--output", str(out)]}) + "\n")
        (out / "trech_scores.jsonl").write_text(json.dumps({"phase": "run_end", "n_events": 5, "analytic_checks": [
            {"type": "photo_fraction", "available": True, "within_tolerance": True, "relative_error": 0.01,
             "primaries_photoelectric_first": 3}]}) + "\n")
        result = load_run_result(out)
        report = grade_run(result, lambda p, a: inspect_scenario(engine, p, a).validation, REPO)
        assert report.status == "graded" and report.failed == 0 and report.passed == 7
        assert report.sweeps == ["analytic_photo_fraction_energy_sweep"]
        summary = build_run_summary(result)
        summary.sections.append(bundle_check_section(report))
        assert summary.section(SECTION_TITLE) is not None
