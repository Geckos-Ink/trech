"""Offline checks of ``geometry_refusal_guard_refuses_defects`` on synthetic run outputs.

No Geant4 run is needed: each test writes the provenance/score files of the two
``geometry_refusal_guard.js`` runs (clean default and ``inject_defects=true``)
into a temporary runs directory, loads them like the suite does and checks that
the recorded outputs pass and that each corrupted invariant fails by name.
Figures come from Release runs of 2026-11-14.
"""

from __future__ import annotations

from pathlib import Path
import copy
import json
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "validation"))

from trech_validation.cases import (  # noqa: E402
    GEOMETRY_REFUSE_KINDS, RUN_GEOMETRY_REFUSAL_CLEAN, RUN_GEOMETRY_REFUSAL_INJECTED,
    SUITE_EXIT_STATUS_FILE, GeometryRefusalGuardRefusesDefects)
from trech_validation.runner import RunContext, load_runs  # noqa: E402

SCENARIO = "examples/scenarios/geometry_refusal_guard/geometry_refusal_guard.js"
CONFIG = {"geometry": {"refuseOn": list(GEOMETRY_REFUSE_KINDS), "volumes": []},
          "run": {"nEvents": 200}}
OVERLAP_CLEAN = {"clean": True, "method": "geant4_solid_surface_sampling", "overlap_count": 0,
                 "pairs_checked": 1, "samples_per_volume": 1000,
                 "schema": "trech_geometry_overlap_check_v1", "tolerance_mm": 0.0,
                 "volumes_checked": 2}
INJECTED_ISSUES = [
    {"kind": "material_fallback", "reason": "unknown_material", "requested": "G4_UNOBTAINIUM",
     "resolved": "G4_AIR", "role": "volume", "volume": "shield"},
    {"depth_mm": 5.0, "kind": "overlap", "reason": "overlaps_sibling", "requested": "probe",
     "resolved": "", "role": "volume", "volume": "target"},
]


def clean_rows():
    base = {"config_json": json.dumps(CONFIG), "n_events": 200,
            "cli_args": ["trech", "run", SCENARIO], "geometry_overlap_check": OVERLAP_CLEAN}
    return [dict(base, phase="run_start"), dict(base, phase="run_end")]


def clean_scores():
    return {"phase": "run_end", "n_events": 200,
            "volume_edep_mev": {"target": 21.7, "dosimeter": 0.43}}


def injected_rows():
    return [{
        "phase": "geometry_refused", "n_events": 0, "requested_events": 200,
        "config_json": json.dumps(CONFIG),
        "cli_args": ["trech", "run", SCENARIO, "--param", "inject_defects=true"],
        "geometry_resolution": {"schema": "trech_geometry_resolution_v1",
                                "issues": copy.deepcopy(INJECTED_ISSUES),
                                "material_fallback_count": 1, "overlap_count": 1,
                                "parent_fallback_count": 0, "volume_skipped_count": 0},
        "geometry_overlap_check": dict(OVERLAP_CLEAN, clean=False, overlap_count=1,
                                       pairs_checked=6, volumes_checked=4),
        "geometry_refusal": {"schema": "trech_geometry_refusal_v1",
                             "refuse_on": list(GEOMETRY_REFUSE_KINDS), "refused_count": 2},
    }]


def write_jsonl(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def evaluate(tmp: Path, *, clean=None, scores="default", injected=None, exit_status="1",
             injected_scores=None):
    clean_dir = tmp / RUN_GEOMETRY_REFUSAL_CLEAN
    injected_dir = tmp / RUN_GEOMETRY_REFUSAL_INJECTED
    write_jsonl(clean_dir / "trech_provenance.jsonl", clean if clean is not None else clean_rows())
    if scores is not None:
        write_jsonl(clean_dir / "trech_scores.jsonl",
                    [clean_scores() if scores == "default" else scores])
    write_jsonl(injected_dir / "trech_provenance.jsonl",
                injected if injected is not None else injected_rows())
    if exit_status is not None:
        (injected_dir / SUITE_EXIT_STATUS_FILE).write_text(exit_status + "\n", encoding="utf-8")
    if injected_scores is not None:
        write_jsonl(injected_dir / "trech_scores.jsonl", [injected_scores])
    case = GeometryRefusalGuardRefusesDefects()
    return case.evaluate(load_runs(tmp, case.required_runs()))


class GeometryRefusalCaseTests(unittest.TestCase):
    def test_recorded_runs_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = evaluate(Path(tmp))
        self.assertEqual(result.status, "pass", result.summary)
        self.assertIn("refused 2 (material_fallback,overlap), exit 1", result.summary)
        self.assertEqual(result.measured["refused_kinds"], ["material_fallback", "overlap"])

    def test_missing_runs_skip(self):
        case = GeometryRefusalGuardRefusesDefects()
        self.assertEqual(case.evaluate(RunContext()).status, "skip")
        with tempfile.TemporaryDirectory() as tmp:
            write_jsonl(Path(tmp) / RUN_GEOMETRY_REFUSAL_CLEAN / "trech_provenance.jsonl",
                        clean_rows())
            result = case.evaluate(load_runs(Path(tmp), case.required_runs()))
        self.assertEqual(result.status, "skip")
        self.assertIn(RUN_GEOMETRY_REFUSAL_INJECTED, result.summary)

    def test_each_corrupted_invariant_fails(self):
        def clean_with(**fields):
            rows = clean_rows()
            rows[-1].update(fields)
            return rows

        def injected_with(**fields):
            rows = injected_rows()
            rows[0].update(fields)
            return rows

        def refusal_with(**fields):
            rows = injected_rows()
            rows[0]["geometry_refusal"].update(fields)
            return rows

        unarmed = copy.deepcopy(CONFIG)
        unarmed["geometry"].pop("refuseOn")
        no_overlap = injected_rows()
        no_overlap[0]["geometry_resolution"]["issues"] = INJECTED_ISSUES[:1]
        no_material = injected_rows()
        no_material[0]["geometry_resolution"]["issues"] = INJECTED_ISSUES[1:]
        cases = {
            "clean_run_start_and_end": dict(clean=clean_rows()[:1]),
            "clean_guard_armed": dict(clean=clean_with(config_json=json.dumps(unarmed))),
            "clean_overlap_check_ran_clean": dict(
                clean=clean_with(geometry_overlap_check=dict(OVERLAP_CLEAN, clean=False))),
            "clean_no_issues": dict(clean=clean_with(geometry_resolution={
                "issues": INJECTED_ISSUES[:1]})),
            "clean_no_refusal_block": dict(clean=clean_with(geometry_refusal={})),
            "clean_all_events_scored": dict(scores=dict(clean_scores(), n_events=199)),
            "clean_target_scored": dict(scores=dict(clean_scores(), volume_edep_mev={})),
            "injected_single_refused_record": dict(
                injected=injected_rows() + [dict(injected_rows()[0], phase="run_start")]),
            "injected_param_recorded": dict(injected=injected_with(
                cli_args=["trech", "run", SCENARIO])),
            "injected_no_events": dict(injected=injected_with(n_events=200)),
            "injected_refusal_schema": dict(injected=refusal_with(schema="v0")),
            "injected_refuse_on_any": dict(injected=refusal_with(refuse_on=["overlap"])),
            "injected_refused_count_matches_issues": dict(
                injected=refusal_with(refused_count=1)),
            "injected_material_fallback_reported": dict(injected=no_material),
            "injected_overlap_reported": dict(injected=no_overlap),
            "injected_no_scores": dict(injected_scores={"n_events": 0}),
            "injected_exit_status_1": dict(exit_status="0"),
        }
        for check, kwargs in cases.items():
            with self.subTest(check=check), tempfile.TemporaryDirectory() as tmp:
                result = evaluate(Path(tmp), **kwargs)
                self.assertEqual(result.status, "fail", check)
                self.assertIn(check, result.summary)

    def test_missing_exit_status_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = evaluate(Path(tmp), exit_status=None)
        self.assertEqual(result.status, "fail")
        self.assertIn("injected_exit_status_1", result.summary)


if __name__ == "__main__":
    unittest.main()
