"""Offline input preflight and orchestration tests; no physics or network runs."""

from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "validation"))

from trech_validation.pubchem_inputs import COMPOUNDS, cache_errors, main  # noqa: E402


def write_cache(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    formulas = {"water": "H2O", "hydrogen": "H2", "oxygen": "O2"}
    for index, name in enumerate(COMPOUNDS):
        slug = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
        (root / f"{slug}.json").write_text(json.dumps({
            "cid": index + 1, "smiles": "O", "molecular_formula": formulas.get(name, "C"),
            "xlogp": 0, "molecular_weight": "18.015",
        }))


class CachePreflightTests(unittest.TestCase):
    def test_complete_cache_is_read_only_without_network_or_subprocess(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_cache(root)
            before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.iterdir()}
            with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")), \
                    patch("subprocess.run", side_effect=AssertionError("subprocess forbidden")), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--cache-dir", str(root), "--all"]), 0)
            after = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.iterdir()}
            self.assertEqual(before, after)

    def test_missing_and_corrupt_records_are_reported_together(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "water.json").write_text("{bad json")
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(main(["--cache-dir", str(root), "water", "hydrogen"]), 2)
            self.assertIn(str(root / "water.json"), stderr.getvalue())
            self.assertIn(str(root / "hydrogen.json"), stderr.getvalue())
            self.assertIn("No network request was attempted", stderr.getvalue())

    def test_invalid_required_values_fail_with_field_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "benzene.json").write_text(json.dumps({
                "cid": True, "smiles": "", "molecular_formula": "C6H6",
                "xlogp": None, "molecular_weight": "nan",
            }))
            errors = cache_errors(root, ["benzene"])
            self.assertEqual(len(errors), 1)
            for field in ("cid", "smiles", "xlogp", "molecular_weight"):
                self.assertIn(field, errors[0])
            (root / "water.json").write_text(json.dumps({
                "cid": 1, "smiles": "O", "molecular_formula": "H2",
            }))
            self.assertIn("molecular_formula=H2O", cache_errors(root, ["water"])[0])

    def test_no_legacy_fallback_for_an_incomplete_selected_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selected = root / "selected"
            selected.mkdir()
            write_cache(root / "legacy")
            errors = cache_errors(selected, ["water"])
            self.assertEqual(len(errors), 1)
            self.assertIn(str(selected / "water.json"), errors[0])


class OfflineOrchestratorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.runs = self.root / "runs"
        self.runs.mkdir()
        self.cache = self.root / "cache"
        write_cache(self.cache)
        self.log = self.root / "calls.jsonl"
        self.bin = self.root / "bin"
        self.bin.mkdir()
        # The engine and non-input Python drivers only record their command.
        # The actual cache preflight executes, ensuring the script is wired to
        # real local reads while this test cannot run physics or fetch PubChem.
        wrapper = f"""#!{sys.executable}
import json, os, subprocess, sys
with open(os.environ['VALIDATION_TEST_LOG'], 'a') as out:
    out.write(json.dumps([os.path.basename(sys.argv[0]), *sys.argv[1:]]) + '\\n')
if sys.argv[1:3] == ['-m', 'trech_validation.pubchem_inputs']:
    sys.exit(subprocess.run([{sys.executable!r}, *sys.argv[1:]]).returncode)
if sys.argv[1:3] == ['-m', 'trech_pubchem'] and os.environ.get('PUBCHEM_MODE') == 'cache-only':
    sys.exit('network-capable PubChem command forbidden in cache-only mode')
"""
        for path in (self.bin / "python3", self.bin / "cmake", self.runs / "trech"):
            path.write_text(wrapper)
            path.chmod(0o755)
        self.env = {
            **os.environ,
            "PATH": str(self.bin) + os.pathsep + os.environ.get("PATH", ""),
            "VALIDATION_TEST_LOG": str(self.log), "RUNS_DIR": str(self.runs),
            "PUBCHEM_CACHE": str(self.cache), "PUBCHEM_MODE": "cache-only",
            "SKIP_BUILD": "1", "SKIP_SCENARIOS": "0", "SKIP_FLUID": "0",
            "SKIP_GOW": "1", "SKIP_BULK": "1", "SKIP_GLASS": "1",
            "SKIP_DIFFUSION_T": "1", "SKIP_SURROGATE": "1",
            "SKIP_MR": "1", "SKIP_MR_TISSUES": "1", "SKIP_MR_IMAGING": "1",
            "SKIP_MR_BRAIN": "1", "REPORT_MD": str(self.root / "report.md"),
            "REPORT_JSON": str(self.root / "report.json"),
        }

    def run_script(self, **overrides):
        return subprocess.run(["bash", str(ROOT / "scripts" / "run_validation_suite.sh")],
                              env={**self.env, **overrides}, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_complete_offline_suite_checks_cache_and_runs_every_pubchem_family(self):
        before = {p.name: p.read_bytes() for p in self.cache.iterdir()}
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout)
        calls = self.calls()
        checks = [call for call in calls if call[1:3] == ["-m", "trech_validation.pubchem_inputs"]]
        self.assertEqual(len(checks), 6)  # all-input preflight + five fetch sites
        self.assertIn("--all", checks[0])
        self.assertFalse(any("trech_pubchem" in call for call in calls))
        for scenario in ("testscenario_efflux", "beaker_water_n_pentane",
                         "testscenario_h2o_electrolysis_combustion", "polyurethane_foam",
                         "elephants_toothpaste"):
            self.assertTrue(any(call[0] == "trech" and any(scenario in arg for arg in call[1:])
                                for call in calls), scenario)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.cache.iterdir()})

    def test_incomplete_cache_fails_before_build_or_scenario_output_removal(self):
        (self.cache / "water.json").unlink()
        stale = self.runs / "out_efflux" / "sentinel"
        stale.parent.mkdir()
        stale.write_text("preserve prior run")
        result = self.run_script(SKIP_BUILD="0")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("water.json", result.stdout)
        self.assertEqual(stale.read_text(), "preserve prior run")
        self.assertFalse(any(call[0] in ("trech", "cmake") for call in self.calls()))

    def test_skipped_scenarios_or_fluid_group_do_not_need_unused_cache(self):
        empty = self.root / "absent_cache"
        for switch in ("SKIP_SCENARIOS", "SKIP_FLUID"):
            with self.subTest(switch=switch):
                self.log.unlink(missing_ok=True)
                result = self.run_script(PUBCHEM_CACHE=str(empty), **{switch: "1"})
                self.assertEqual(result.returncode, 0, result.stdout)
                self.assertFalse(any("trech_validation.pubchem_inputs" in call for call in self.calls()))

    def test_default_mode_still_fetches_the_original_compound_groups(self):
        env = self.env.copy()
        env.pop("PUBCHEM_MODE")
        with patch.dict(self.env, env, clear=True):
            result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout)
        fetches = [call for call in self.calls() if call[1:4] == ["-m", "trech_pubchem", "fetch"]]
        self.assertEqual(len(fetches), 5)
        self.assertTrue(all(call[4:7] == ["--cache-dir", str(self.cache), "--no-png"] for call in fetches))
        self.assertEqual([call[7:] for call in fetches], [
            ["benzene", "D-glucose"], ["water", "n-pentane"],
            ["water", "hydrogen", "oxygen"], ["glycerol", "toluene 2,4-diisocyanate", "water"],
            ["hydrogen peroxide", "potassium iodide", "water"],
        ])

    def test_invalid_mode_fails_before_any_work(self):
        result = self.run_script(PUBCHEM_MODE="sometimes", SKIP_BUILD="0")
        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("PUBCHEM_MODE must be refresh or cache-only", result.stdout)
        self.assertEqual(self.calls(), [])


if __name__ == "__main__":
    unittest.main()
