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

    def test_derived_statistics(self):
        def check(field, derive, op, expected, how=None):
            c = {"phase": "run_end", "field": field, "derive": derive, "op": op, "expected": expected}
            if how:
                c["aggregate"] = how
            return c
        items = [{"type": "k", "chi2": 10.54, "dof": 19, "hist": [3, 4, 5], "n": 12, "z": -0.6,
                  "top": 0.72, "edge": 0.7214},
                 {"type": "k", "chi2": 12.57, "dof": 19, "hist": [6, 6], "n": 12, "z": 1.2,
                  "top": 0.71, "edge": 0.7214}]
        scores = {"phase": "run_end", "n_events": 1, "items": items, "one": items[0]}
        with tempfile.TemporaryDirectory() as tmp:
            out = self.run_dir(tmp, {}, scores)
            sf = declarative.chi2_sf(10.54, 19)
            self.assertAlmostEqual(sf, cases._chi2_sf(10.54, 19), places=15)
            self.assertGreater(sf, 0.9)
            passing = [
                check("one", {"fn": "chi2_sf", "args": ["chi2", "dof"]}, "within", sf),
                check("items[*]", {"fn": "chi2_sf", "args": ["chi2", "dof"]}, "ge", 1e-3, "min"),
                check("items[?type=k]", {"fn": "difference", "args": [{"fn": "list_sum", "args": ["hist"]}, "n"]},
                      "eq", 0, "max_abs"),
                check("items[*]", {"fn": "list_length", "args": ["hist"]}, "eq", 2, "min"),
                check("items[*]", {"fn": "ratio", "args": ["top", "edge"]}, "le", 1.0, "max"),
                check("one", {"fn": "abs", "args": ["z"]}, "lt", 4.0),
            ]
            passing[0]["abs_tol"] = 1e-15
            self.assertEqual([r["passed"] for r in declarative.evaluate_family(
                self.contract(passing), "sample_case", out)], [True] * len(passing))
            failing = [
                check("items[*]", {"fn": "ratio", "args": ["top", "missing"]}, "le", 1.0, "max"),
                check("one", {"fn": "ratio", "args": ["top", "zero"]}, "le", 1.0),
                check("one", {"fn": "chi2_sf", "args": ["chi2", "half"]}, "ge", 0.0),
                check("one", {"fn": "list_sum", "args": ["type"]}, "ge", 0.0),
                check("one", {"fn": "abs", "args": ["type"]}, "ge", 0.0),
            ]
            items[0].update(zero=0.0, half=1.5)
            out = self.run_dir(tmp, {}, scores)
            self.assertEqual([r["passed"] for r in declarative.evaluate_family(
                self.contract(failing), "sample_case", out)], [False] * len(failing))
            for bad in ({"fn": "median", "args": ["hist"]}, {"fn": "ratio", "args": ["top"]},
                        {"fn": "abs", "args": [3]}):
                with self.assertRaises(ValueError, msg=bad):
                    declarative.evaluate_family(self.contract([check("one", bad, "ge", 0)]), "sample_case", out)


@unittest.skipIf(_trech() is None, "trech binary not built")
def _sweep_run(root: Path, name: str, check: dict, params: dict) -> Path:
    run = root / name
    run.mkdir(parents=True, exist_ok=True)
    _write_jsonl(run / "trech_scores.jsonl", [{"phase": "run_end", "n_events": 10, "analytic_checks": [check]}])
    args = ["trech", "run", "scenario.js"]
    for key, value in params.items():
        args += ["--param", f"{key}={value}"]
    _write_jsonl(run / "trech_provenance.jsonl", [{"phase": "run_end", "cli_args": args + ["--output", str(run)]}])
    return run


class SweepChecks(unittest.TestCase):
    """Multi-run gates: identity, run subsets and cross-run reductions stay strict."""

    FIELD = "analytic_checks[?type=t]"

    def contract(self, checks, runs=None):
        runs = runs or [{"id": "a", "params": {"e": 1}}, {"id": "b", "params": {"e": 2}},
                        {"id": "c", "params": {}}]
        return {"s": {"schema": "trech_scenario_validation_v1", "checks": OUTPUT_CHECKS,
                      "family_sweeps": [{"family_case": "sweep_case", "runs": runs, "checks": checks}]}}

    def runs(self, tmp, values, params=None):
        params = params or {"a": {"e": "1.000"}, "b": {"e": "2"}, "c": {}}
        return {rid: _sweep_run(Path(tmp), rid, {"type": "t", "v": v, "m": 0.3, "p": 0.3, "n": 100}, params[rid])
                for rid, v in values.items()}

    def test_identity_each_run_and_series(self):
        checks = [{"id": "positive", "each_run": True, "phase": "run_end", "field": self.FIELD + ".v",
                   "aggregate": "min", "op": "gt", "expected": 0},
                  {"id": "rising", "phase": "run_end", "field": self.FIELD + ".v", "aggregate": "max",
                   "series_aggregate": "strictly_increasing", "op": "eq", "expected": True},
                  {"id": "span", "runs": ["a", "c"], "phase": "run_end", "field": self.FIELD + ".v",
                   "aggregate": "max", "series_aggregate": "last_over_first", "op": "ge", "expected": 3},
                  {"id": "peak", "phase": "run_end", "field": self.FIELD + ".v", "aggregate": "max",
                   "series_aggregate": "argmax", "op": "eq", "expected": "c"},
                  {"id": "z", "run": "b", "phase": "run_end", "field": self.FIELD,
                   "derive": {"fn": "abs", "args": [{"fn": "binomial_z", "args": ["m", "p", "n"]}]},
                   "aggregate": "max", "op": "lt", "expected": 4}]
        with tempfile.TemporaryDirectory() as tmp:
            runs = self.runs(tmp, {"a": 1.0, "b": 2.0, "c": 3.0})
            results = declarative.evaluate_sweep(self.contract(checks), "sweep_case", runs)
            self.assertTrue(all(r["passed"] for r in results), [r for r in results if not r["passed"]])
            ids = [r["id"] for r in results]
            self.assertEqual(ids[:3], ["run_identity@a", "run_identity@b", "run_identity@c"])
            self.assertIn("positive@b", ids)
            self.assertIn("z@b", ids)
            # A tie has no argmax; a falling point breaks strict monotonicity.
            runs = self.runs(tmp, {"a": 1.0, "b": 3.0, "c": 3.0})
            failed = {r["id"] for r in declarative.evaluate_sweep(self.contract(checks), "sweep_case", runs)
                      if not r["passed"]}
            self.assertEqual(failed, {"rising", "peak"})

    def test_identity_and_missing_runs_fail(self):
        checks = [{"id": "positive", "each_run": True, "phase": "run_end", "field": self.FIELD + ".v",
                   "aggregate": "min", "op": "gt", "expected": 0}]
        with tempfile.TemporaryDirectory() as tmp:
            runs = self.runs(tmp, {"a": 1.0, "b": 2.0, "c": 3.0},
                             params={"a": {"e": "1.5"}, "b": {"e": "2", "x": "1"}, "c": {}})
            failed = {r["id"] for r in declarative.evaluate_sweep(self.contract(checks), "sweep_case", runs)
                      if not r["passed"]}
            self.assertEqual(failed, {"run_identity@a", "run_identity@b"})
            del runs["c"]
            failed = {r["id"] for r in declarative.evaluate_sweep(self.contract(checks), "sweep_case", runs)
                      if not r["passed"]}
            self.assertIn("run_identity@c", failed)
            self.assertIn("positive@c", failed)

    def test_binomial_z_domain(self):
        self.assertAlmostEqual(declarative.derive({"m": 0.6, "p": 0.5, "n": 100},
                                                  {"fn": "binomial_z", "args": ["m", "p", "n"]}), 2.0)
        for bad in ({"m": 0.1, "p": 0.0, "n": 10}, {"m": 0.1, "p": 1.0, "n": 10},
                    {"m": 0.1, "p": 0.5, "n": 0}, {"m": 0.1, "p": 0.5, "n": 2.5}):
            self.assertIsNone(declarative.derive(bad, {"fn": "binomial_z", "args": ["m", "p", "n"]}))

    def test_malformed_sweeps_raise(self):
        good = {"id": "x", "each_run": True, "phase": "run_end", "field": "n_events", "op": "gt", "expected": 0}
        for checks, runs in (([dict(good, run="a")], None),                       # two modes
                             ([{k: v for k, v in good.items() if k != "each_run"}], None),  # no mode
                             ([dict(good, each_run=["z"])], None),                # undeclared run
                             ([{"id": "s", "field": "n_events", "series_aggregate": "median",
                                "op": "gt", "expected": 0}], None),
                             ([good], [{"id": "a"}, {"id": "a"}]),                # duplicate id
                             ([], None)):
            with self.assertRaises(ValueError):
                declarative.evaluate_sweep(self.contract(checks, runs), "sweep_case", {})


class BundleFamilyExports(unittest.TestCase):
    """Every exported family case is a real suite case whose verdict follows the bundle."""

    EXPORTED = {
        "testscenario_pascal", "testscenario_osmotic", "h2o_molecule_stability", "h2o_cluster_fluid",
        "h2o_bulk_water", "glass_of_water_shaken", "h2o_diffusion_temperature", "cnt_band_structure",
        "cnt_logic_gates", "testscenario_magnetic_resonance", "testscenario_magnetic_resonance_imaging",
        "analytic_beer_lambert", "analytic_csda_range", "analytic_photo_fraction",
        "testscenario_magnetic_resonance_tissues", "testscenario_magnetic_resonance_brain",
        "analytic_compton_transfer", "analytic_pair_production", "hooks_track_ledger",
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

    def test_track_ledger_case_verdict_follows_declared_checks(self):
        case = next(c for c in cases.ALL_CASES if c.name == "hooks_track_ledger_consistent")
        # Ledger of a 300-event Release run (2026-11-14).
        ledger = {"events": 300, "starts": 461, "ends": 461, "tracksFromEvents": 461,
                  "primaries": 300, "stepMismatch": 0, "lengthMismatch": 0, "energyGain": 0,
                  "unknownEnd": 0, "unclosed": 0, "consistent": True,
                  "creators": {"compt": 147, "eBrem": 4, "eIoni": 9, "phot": 1, "primary": 300},
                  "endProcesses": {"Transportation": 308, "eIoni": 152, "phot": 1}}
        scores = {"phase": "run_end", "n_events": 300, "hook_emit_dropped_count": 0,
                  "hook_on_track_start_count": 461, "hook_on_track_end_count": 461,
                  "hook_on_track_end_dropped_count": 0}
        old = os.environ.get("TRECH_BIN")
        os.environ["TRECH_BIN"] = str(_trech())
        try:
            with tempfile.TemporaryDirectory() as tmp:
                run = Path(tmp) / cases.RUN_HOOKS_TRACK_LEDGER
                run.mkdir()
                for ledger_patch, score_patch, failed in (
                        ({}, {}, None),
                        ({"ends": 460, "consistent": False}, {}, "every_start_ends"),
                        ({"tracksFromEvents": 462, "consistent": False}, {},
                         "starts_match_engine_track_count"),
                        ({"primaries": 299, "consistent": False}, {}, "one_primary_per_event"),
                        ({"stepMismatch": 1, "consistent": False}, {}, "step_counts_agree"),
                        ({"lengthMismatch": 2, "consistent": False}, {}, "lengths_agree"),
                        ({"energyGain": 1, "consistent": False}, {}, "no_energy_gain"),
                        ({"creators": {"primary": 300}}, {}, "secondaries_created"),
                        ({}, {"hook_on_track_start_count": 400}, "engine_start_counter_matches"),
                        ({}, {"hook_on_track_end_dropped_count": 61}, "no_track_callbacks_dropped")):
                    _write_jsonl(run / "trech_hook_emits.jsonl",
                                 [{"tag": "track_ledger", "payload": dict(ledger, **ledger_patch)}])
                    _write_jsonl(run / "trech_scores.jsonl", [dict(scores, **score_patch)])
                    result = case.evaluate(
                        RunContext(runs={cases.RUN_HOOKS_TRACK_LEDGER: RunOutputs.load(run)}))
                    self.assertEqual(result.status, "fail" if failed else "pass", failed)
                    self.assertIn("hooks_track_ledger.validation.js", result.notes[0])
                    if failed:
                        self.assertIn(failed, result.notes[0])
                (run / "trech_hook_emits.jsonl").write_text("")
                result = case.evaluate(
                    RunContext(runs={cases.RUN_HOOKS_TRACK_LEDGER: RunOutputs.load(run)}))
                self.assertEqual(result.status, "fail")
                self.assertIn("no track_ledger emit", result.summary)
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


    def test_compton_case_verdict_follows_declared_statistics(self):
        case = next(c for c in cases.ALL_CASES if c.name == "analytic_compton_transfer_cross_check")
        check = {"type": "compton_energy_transfer", "available": True, "within_tolerance": True,
                 "label": "kn", "classical_predicted": 0.3816, "geant4_measured": 0.3825,
                 "relative_error": 0.0026, "z_score": 0.56, "primaries_compton_first": 10,
                 "compton_edge_fraction": 0.7214, "measured_max_transfer_fraction": 0.7213,
                 "measured_transfer_histogram": [4, 6], "transfer_histogram_entries": 10,
                 "transfer_histogram_chi2": 1.0, "transfer_histogram_dof": 1,
                 "measured_cos_theta_histogram": [5, 5], "cos_theta_histogram_entries": 10,
                 "cos_theta_histogram_chi2": 0.5, "cos_theta_histogram_dof": 1,
                 "cos_theta_z_score": -0.4, "klein_nishina_mean_cos_theta": 0.3187,
                 "measured_mean_cos_theta": 0.3168, "measured_max_kinematic_residual": 3e-16}
        old = os.environ.get("TRECH_BIN")
        os.environ["TRECH_BIN"] = str(_trech())
        try:
            with tempfile.TemporaryDirectory() as tmp:
                run = Path(tmp) / cases.RUN_ANALYTIC_COMPTON
                run.mkdir()
                for patch, status, failed in (({}, "pass", None),
                                              ({"transfer_histogram_chi2": 30.0}, "fail", "spectrum_shape_p"),
                                              ({"measured_max_transfer_fraction": 0.73}, "fail", "edge_respected"),
                                              ({"cos_theta_histogram_entries": 9}, "fail", "angular_entries_match_samples")):
                    row = dict(check, **patch)
                    _write_jsonl(run / "trech_scores.jsonl",
                                 [{"phase": "run_end", "n_events": 10, "analytic_checks": [row]}])
                    result = case.evaluate(RunContext(runs={cases.RUN_ANALYTIC_COMPTON: RunOutputs.load(run)}))
                    self.assertEqual(result.status, status, patch)
                    self.assertIn("analytic_compton_transfer.validation.js", result.notes[0])
                    if failed:
                        self.assertIn(failed, result.notes[0])
        finally:
            if old is None:
                os.environ.pop("TRECH_BIN", None)
            else:
                os.environ["TRECH_BIN"] = old


    SWEEP_EXPORTS = {
        "analytic_photo_fraction": {"analytic_photo_fraction_energy_sweep"},
        "analytic_pair_production": {"analytic_pair_fraction_energy_sweep",
                                     "analytic_photonuclear_fraction_giant_dipole"},
    }

    def test_sweep_companions_name_existing_cases(self):
        names = {case.name for case in cases.ALL_CASES}
        found = {}
        for companion in sorted((ROOT / "examples/scenarios").glob("*/*.validation.js")):
            if '"family_sweeps"' not in companion.read_text():
                continue
            scenario = companion.name[:-len(".validation.js")]
            declared = declarative.load_declarations(companion.with_name(scenario + ".js"), _trech())
            sweeps = declared[scenario]["family_sweeps"]
            found[scenario] = {sweep["family_case"] for sweep in sweeps}
            for sweep in sweeps:
                self.assertIn(sweep["family_case"], names, scenario)
                self.assertTrue(sweep["runs"] and sweep["checks"], scenario)
        self.assertEqual(found, self.SWEEP_EXPORTS)

    def test_photo_fraction_sweep_verdict_follows_declared_sweep(self):
        case = next(c for c in cases.ALL_CASES if c.name == "analytic_photo_fraction_energy_sweep")
        fractions = dict(zip(cases.PHOTO_FRACTION_SWEEP_KEV, (0.93, 0.6, 0.39, 0.15, 0.016)))
        old = os.environ.get("TRECH_BIN")
        os.environ["TRECH_BIN"] = str(_trech())
        try:
            with tempfile.TemporaryDirectory() as tmp:
                for patch, status, failed in (({}, "pass", None),
                                              ({20: {"geant4_measured": 0.64}}, "fail", "binomial_z@e20keV"),
                                              ({30: {"energy_mev": "0.031"}}, "fail", "run_identity@e30keV"),
                                              ({100: {"geant4_measured": 0.2, "classical_predicted": 0.2}},
                                               "fail", "strictly_decreasing")):
                    runs = {}
                    for kev, name in zip(cases.PHOTO_FRACTION_SWEEP_KEV, cases.RUN_ANALYTIC_PHOTO_FRACTION_SWEEP):
                        f = fractions[kev]
                        row = {"type": "photo_fraction", "available": True, "within_tolerance": True,
                               "classical_predicted": f, "geant4_measured": f,
                               "primaries_first_interaction": 20000,
                               "primaries_photoelectric_first": int(f * 20000)}
                        override = dict(patch.get(kev, {}))
                        energy = override.pop("energy_mev", f"{kev / 1000.0:.3f}")
                        row.update(override)
                        runs[name] = RunOutputs.load(_sweep_run(Path(tmp), name, row, {"energy_mev": energy}))
                    result = case.evaluate(RunContext(runs=runs))
                    self.assertEqual(result.status, status, patch)
                    self.assertIn("analytic_photo_fraction.validation.js", result.notes[0])
                    if failed:
                        self.assertIn(failed, result.notes[0])
        finally:
            if old is None:
                os.environ.pop("TRECH_BIN", None)
            else:
                os.environ["TRECH_BIN"] = old


if __name__ == "__main__":
    unittest.main()
