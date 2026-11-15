"""TRECH_FLOW validation-preset audit: a clean scenario passes, seeded defects are reported."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import audit_flow_presets as audit_mod  # noqa: E402


def _trech() -> Path | None:
    try:
        return audit_mod.find_trech(None)
    except SystemExit:
        return None


@unittest.skipIf(_trech() is None, "trech binary not built")
class FlowPresetAudit(unittest.TestCase):
    def test_example_scenario_passes(self):
        entry = audit_mod.scenario_entry("optics_surrogate_demo")
        result = audit_mod.audit(_trech(), entry, "all", 120.0)
        self.assertEqual(result["status"], "pass", result)

    def test_seeded_defects_are_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            entry = Path(tmp) / "bad" / "bad.js"
            entry.parent.mkdir()
            entry.write_text(
                "globalThis.TRECH_CONFIG = {\n"
                "  detector: { worldMaterial: 'G4_AIR', mediumMaterial: 'watre' },\n"
                "  materials: [{ name: 'water', components: [] }],\n"
                "  geometry: { volumes: [{ name: 'v', placement: { parent: 'nowhere' },\n"
                "    shape: { type: 'box', sizeMm: [1, 1, 1] }, material: 'water' }] },\n"
                "  beam: { particle: 'gamma', energyMeV: 0.1, direction: [0, 0, 1] },\n"
                "  run: { nEvents: 1 } };\n")
            result = audit_mod.audit(_trech(), entry, ["materials", "geometry"], 120.0)
            self.assertEqual(result["status"], "issues", result)
            self.assertEqual(len(result["issues"]), 2, result)
            self.assertIn("detector.mediumMaterial: 'watre'", result["issues"][0])
            self.assertIn("placement.parent: unknown volume 'nowhere'", result["issues"][1])
            clean = audit_mod.audit(_trech(), entry, ["beam", "run"], 120.0)
            self.assertEqual(clean["status"], "pass", clean)

    def test_unknown_config_keys_are_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            entry = Path(tmp) / "typo" / "typo.js"
            entry.parent.mkdir()
            entry.write_text(
                "globalThis.TRECH_CONFIG = {\n"
                "  beam: { particle: 'gamma', energyMeV: 0.1, positionMm: [0, 0, -5] },\n"
                "  run: { nEvents: 1, nEvent: 5 } };\n")
            result = audit_mod.audit(_trech(), entry, ["keys"], 120.0)
            self.assertEqual(result["status"], "issues", result)
            self.assertEqual(result["issues"], [
                "beam.positionMm: unknown config key (the engine never reads it)",
                "run.nEvent: unknown config key (the engine never reads it)"])
            self.assertEqual(audit_mod.audit(_trech(), entry, ["beam"], 120.0)["status"], "pass")
            self.assertEqual(audit_mod.audit(_trech(), entry, "all", 120.0)["status"], "issues")


if __name__ == "__main__":
    unittest.main()
