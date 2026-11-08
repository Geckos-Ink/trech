"""Output contract failures must remain visible after scenario-file separation.

Family checks exported into ``<name>.validation.js`` must keep the suite verdict
strict: absent rows, mistyped flags and corrupted references fail.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tools" / "validation"))
from validate_scenario import evaluate  # noqa: E402
from trech_validation import cases, declarative  # noqa: E402
from trech_validation.runner import RunContext, RunOutputs  # noqa: E402


OUTPUT_CHECKS = [
    {"file": "trech_scores.jsonl", "phase": "run_end", "field": "n_events", "op": "gt", "expected": 0},
    {"file": "trech_scores.jsonl", "phase": "run_end", "field": "hook_emit_dropped_count", "op": "eq", "expected": 0, "missing": 0},
]


def _write_jsonl(path: Path, rows) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def _trech() -> Path | None:
    for candidate in (os.environ.get("TRECH_BIN"), ROOT / "build/dev/trech", ROOT / "build/rel/trech"):
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return Path(candidate)
    return None


class ScenarioContracts(unittest.TestCase):
    def test_missing_or_dropped_output_fails(self):
        contract = {"sample": {"schema": "trech_scenario_validation_v1", "checks": OUTPUT_CHECKS}}
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            self.assertFalse(any(r["passed"] for r in evaluate(contract, output)))
            scores = output / "trech_scores.jsonl"
            scores.write_text(json.dumps({"phase": "run_start", "n_events": 3}) + "\n")
            self.assertFalse(any(r["passed"] for r in evaluate(contract, output)))
            scores.write_text(json.dumps({"phase": "run_end", "n_events": 3, "hook_emit_dropped_count": 2}) + "\n")
            self.assertEqual([r["passed"] for r in evaluate(contract, output)], [True, False])
            scores.write_text(json.dumps({"phase": "run_end", "n_events": 3}) + "\n")
            self.assertTrue(all(r["passed"] for r in evaluate(contract, output)))

    def test_no_declarations_do_not_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "no output checks"):
                evaluate({}, Path(tmp))
            family_only = {"s": {"schema": "trech_scenario_validation_v1", "family_case": "x",
                                 "family_checks": [{"field": "n", "op": "gt", "expected": 0}]}}
            with self.assertRaisesRegex(ValueError, "no output checks"):
                evaluate(family_only, Path(tmp))


class FamilyChecks(unittest.TestCase):
    def contract(self, checks):
        return {"s": {"schema": "trech_scenario_validation_v1", "checks": OUTPUT_CHECKS,
                      "family_case": "sample_case", "family_checks": checks}}

    def run_dir(self, tmp, payload, scores=None):
        out = Path(tmp)
        _write_jsonl(out / "trech_scores.jsonl", [scores or {"phase": "run_end", "n_events": 2}])
        _write_jsonl(out / "trech_hook_emits.jsonl", [
            {"tag": "summary", "payload": {"validation": {"ok": False}}},
            {"tag": "other", "payload": {"validation": {"ok": True}}},
            {"tag": "summary", "payload": payload},
        ])
        return out

    def test_last_tagged_emit_and_strict_booleans(self):
        checks = [{"id": "ok", "tag": "summary", "field": "validation.ok", "op": "eq", "expected": True}]
        with tempfile.TemporaryDirectory() as tmp:
            out = self.run_dir(tmp, {"validation": {"ok": True}})
            self.assertTrue(declarative.evaluate_family(self.contract(checks), "sample_case", out)[0]["passed"])
            for corrupted in ({"validation": {"ok": 1}}, {"validation": {"ok": "true"}}, {"validation": {}}, {}):
                out = self.run_dir(tmp, corrupted)
                self.assertFalse(declarative.evaluate_family(self.contract(checks), "sample_case", out)[0]["passed"],
                                 corrupted)
            (Path(tmp) / "trech_hook_emits.jsonl").unlink()
            self.assertFalse(declarative.evaluate_family(self.contract(checks), "sample_case", Path(tmp))[0]["passed"])

    def test_scaled_reference_and_list_selectors(self):
        checks = [
            {"id": "contrast", "tag": "summary", "field": "wall.deform", "op": "gt",
             "reference": {"tag": "summary", "field": "wall.rigid"}, "scale": 10},
            {"id": "match", "tag": "summary", "field": "density", "op": "within", "rel_tol": 1e-6,
             "reference": {"phase": "run_end", "field": "probes[name=W].density.H"}},
            {"id": "index", "tag": "summary", "field": "series[1]", "op": "le", "expected": 3},
        ]
        scores = {"phase": "run_end", "n_events": 1,
                  "probes": [{"name": "X", "density": {"H": 1.0}}, {"name": "W", "density": {"H": 6.0e22}}]}
        good = {"wall": {"deform": 2.0, "rigid": 0.1}, "density": 6.00000001e22, "series": [9, 3]}
        with tempfile.TemporaryDirectory() as tmp:
            out = self.run_dir(tmp, good, scores)
            results = declarative.evaluate_family(self.contract(checks), "sample_case", out)
            self.assertEqual([r["passed"] for r in results], [True, True, True])
            self.assertAlmostEqual(results[0]["expected"], 1.0)
            bad = {"wall": {"deform": 0.9, "rigid": 0.1}, "density": 6.1e22, "series": [9, 4]}
            out = self.run_dir(tmp, bad, scores)
            self.assertEqual([r["passed"] for r in declarative.evaluate_family(
                self.contract(checks), "sample_case", out)], [False, False, False])
            # A missing reference row never makes a comparison pass.
            out = self.run_dir(tmp, good, {"phase": "run_start", "n_events": 1})
            self.assertFalse(declarative.evaluate_family(self.contract(checks), "sample_case", out)[1]["passed"])

    def test_malformed_declarations_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self.run_dir(tmp, {"x": 1})
            for check in ({"tag": "summary", "field": "x", "op": "approx", "expected": 1},
                          {"tag": "summary", "field": "x", "op": "within", "expected": 1},
                          {"tag": "summary", "field": "x", "op": "gt"},
                          {"file": "../escape.jsonl", "field": "x", "op": "gt", "expected": 0}):
                with self.assertRaises(ValueError, msg=check):
                    declarative.evaluate_family(self.contract([check]), "sample_case", out)
            with self.assertRaisesRegex(ValueError, "no validation companion"):
                declarative.evaluate_family(self.contract([]), "other_case", out)

    def test_projection_aggregates(self):
        def check(field, how, op, expected):
            return {"phase": "run_end", "field": field, "aggregate": how, "op": op, "expected": expected}
        items = [{"type": "a", "ok": True, "err": 0.01, "n": 3},
                 {"type": "b", "ok": True, "err": -0.04, "n": 0},
                 {"type": "a", "ok": True, "err": 0.02, "n": 5}]
        scores = {"phase": "run_end", "n_events": 1, "items": items}
        checks = [
            check("items[*]", "count", "eq", 3),
            check("items[?type=a]", "count", "eq", 2),
            check("items[?type=a].ok", "all", "eq", True),
            check("items[*].err", "max_abs", "within", 0.04),
            check("items[?type=a].err", "mean", "within", 0.015),
            check("items[?type=a].n", "min", "gt", 0),
            check("items[*].n", "sum", "eq", 8),
            check("items[?type=b].ok", "any", "eq", True),
        ]
        for c in checks:
            if c["op"] == "within":
                c["abs_tol"] = 1e-12
        with tempfile.TemporaryDirectory() as tmp:
            out = self.run_dir(tmp, {}, scores)
            self.assertEqual([r["passed"] for r in declarative.evaluate_family(
                self.contract(checks), "sample_case", out)], [True] * len(checks))
            # A vacuous projection, a missing element field or a wrong type never passes.
            failing = [check("items[?type=z].ok", "all", "eq", True),
                       check("items[?type=z].err", "max", "le", 1.0),
                       check("items[*].missing", "all", "eq", True),
                       check("items[*].type", "max", "ge", 0),
                       check("items[*].err", "all", "eq", True)]
            self.assertEqual([r["passed"] for r in declarative.evaluate_family(
                self.contract(failing), "sample_case", out)], [False] * len(failing))
            items[1]["ok"] = False
            out = self.run_dir(tmp, {}, scores)
            self.assertFalse(declarative.evaluate_family(
                self.contract([check("items[*].ok", "all", "eq", True)]), "sample_case", out)[0]["passed"])
            for bad in ({"phase": "run_end", "field": "items[*].ok", "op": "eq", "expected": True},
                        check("items[*].ok", "median", "eq", True),
                        check("items[*].n[*]", "count", "ge", 0),
                        check("items[?type].n", "count", "ge", 0)):
                with self.assertRaises(ValueError, msg=bad):
                    declarative.evaluate_family(self.contract([bad]), "sample_case", out)


@unittest.skipIf(_trech() is None, "trech binary not built")
class BundleFamilyExports(unittest.TestCase):
    """Every exported family case is a real suite case whose verdict follows the bundle."""

    EXPORTED = {
        "testscenario_pascal", "testscenario_osmotic", "h2o_molecule_stability", "h2o_cluster_fluid",
        "h2o_bulk_water", "glass_of_water_shaken", "h2o_diffusion_temperature", "cnt_band_structure",
        "cnt_logic_gates", "testscenario_magnetic_resonance", "testscenario_magnetic_resonance_imaging",
        "analytic_beer_lambert", "analytic_csda_range", "analytic_photo_fraction",
        "testscenario_magnetic_resonance_tissues", "testscenario_magnetic_resonance_brain",
    }

    def test_companions_name_existing_cases(self):
        names = {case.name for case in cases.ALL_CASES}
        found = set()
        for companion in sorted((ROOT / "examples/scenarios").glob("*/*.validation.js")):
            if '"family_case"' not in companion.read_text():
                continue
            scenario = companion.name[:-len(".validation.js")]
            declared = declarative.load_declarations(companion.with_name(scenario + ".js"), _trech())
            contract = declared[scenario]
            self.assertIn(contract["family_case"], names, scenario)
            self.assertTrue(contract["family_checks"], scenario)
            found.add(scenario)
        self.assertEqual(found, self.EXPORTED)

    def test_pascal_case_verdict_follows_declared_checks(self):
        case = next(c for c in cases.ALL_CASES if c.name == "pascal_principle_holds")
        payload = {"validation": {"pascal_principle_holds": True, "plastic_damping_observed": True,
                                  "rigid_wall_displacement": 1e-5, "deformable_wall_displacement": 3.0},
                   "results": []}
        old = os.environ.get("TRECH_BIN")
        os.environ["TRECH_BIN"] = str(_trech())
        try:
            with tempfile.TemporaryDirectory() as tmp:
                run = Path(tmp) / cases.RUN_PASCAL
                run.mkdir()
                _write_jsonl(run / "trech_scores.jsonl", [{"phase": "run_end", "n_events": 1}])
                for deform, status in ((3.0, "pass"), (5e-5, "fail")):
                    payload["validation"]["deformable_wall_displacement"] = deform
                    _write_jsonl(run / "trech_hook_emits.jsonl", [{"tag": "pascal_summary", "payload": payload}])
                    result = case.evaluate(RunContext(runs={cases.RUN_PASCAL: RunOutputs.load(run)}))
                    self.assertEqual(result.status, status)
                    self.assertIn("testscenario_pascal.validation.js", result.notes[0])
                    if status == "fail":
                        self.assertIn("deformable_wall_contrast", result.notes[0])
        finally:
            if old is None:
                os.environ.pop("TRECH_BIN", None)
            else:
                os.environ["TRECH_BIN"] = old

    def test_csda_case_verdict_follows_declared_aggregates(self):
        case = next(c for c in cases.ALL_CASES if c.name == "analytic_csda_range_cross_check")
        check = {"type": "csda_range", "available": True, "within_tolerance": True, "label": "p",
                 "classical_predicted": 4.28, "geant4_measured": 4.27, "relative_error": 0.004,
                 "primaries_transmitted": 0, "primaries_emitted": 10}
        old = os.environ.get("TRECH_BIN")
        os.environ["TRECH_BIN"] = str(_trech())
        try:
            with tempfile.TemporaryDirectory() as tmp:
                run = Path(tmp) / cases.RUN_ANALYTIC_CSDA
                run.mkdir()
                for patch, status, failed in (({}, "pass", None),
                                              ({"primaries_transmitted": 2}, "fail", "primaries_contained"),
                                              ({"relative_error": 0.07}, "fail", "worst_relative_error")):
                    row = dict(check, **patch)
                    _write_jsonl(run / "trech_scores.jsonl",
                                 [{"phase": "run_end", "n_events": 10, "analytic_checks": [row]}])
                    result = case.evaluate(RunContext(runs={cases.RUN_ANALYTIC_CSDA: RunOutputs.load(run)}))
                    self.assertEqual(result.status, status, patch)
                    self.assertIn("analytic_csda_range.validation.js", result.notes[0])
                    if failed:
                        self.assertIn(failed, result.notes[0])
        finally:
            if old is None:
                os.environ.pop("TRECH_BIN", None)
            else:
                os.environ["TRECH_BIN"] = old


if __name__ == "__main__":
    unittest.main()
