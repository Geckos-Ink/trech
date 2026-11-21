#!/usr/bin/env python3
"""Same-input JavaScript engine differential: TRECH's QuickJS host vs an installed Node/V8.

Runs one scenario's top-level JavaScript in both engines -- `trech inspect <scenario>` (the
embedded QuickJS host) and `node scripts/js_engine_differential_node.js <scenario>` (a minimal
Node/V8 host with TRECH_INCLUDE/TRECH_READ_JSON only) -- and compares the resulting configs.
For the probe fixture (tests/fixtures/js_engine_differential/probe.js) every double is recorded
as its IEEE-754 bit pattern, so the report counts bit-identical values and the largest distance
in units in the last place (ulp) per section.

This is a measurement of hook-layer numerical portability, not an embedded-V8 TRECH backend and
not physics validation. `--check` applies the gates the probe is expected to meet on any host:
the integer mulberry32 stream, Math.sqrt (correctly rounded by IEEE-754) and the CHILL+ phase
labels are identical, and no Math builtin differs by more than 1 ulp. Trajectory divergence is
reported, never gated.

`--dmath` installs TRECH's deterministic host math in the Node context first
(js/trech_dmath_v8.js: the QuickJS host's trech_dmath compiled to WebAssembly), so both
engines evaluate Math.* with the same code; `--require-identical` then also fails unless every
section, the water trajectory included, is bit-identical.

    python3 scripts/js_engine_differential.py --trech build/dev/trech [--json report.json] [--check]
    python3 scripts/js_engine_differential.py --trech build/dev/trech --dmath --check --require-identical
"""
from __future__ import annotations

import argparse
import json
import shutil
import struct
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "tests" / "fixtures" / "js_engine_differential" / "probe.js"
NODE_HOST = ROOT / "scripts" / "js_engine_differential_node.js"
SCHEMA = "trech_js_engine_differential_v1"
REPORT_SCHEMA = "trech_js_engine_differential_report_v1"
EXACT_SECTIONS = ("random.uniforms", "builtins.sqrt")
MAX_BUILTIN_ULP = 1


def _ordered(bits: str) -> int:
    """Map an IEEE-754 bit pattern onto a monotonic integer line (ulp distance = difference)."""
    value = struct.unpack(">q", bytes.fromhex(bits))[0]
    return value if value >= 0 else -(value & 0x7FFFFFFFFFFFFFFF)


def compare_bits(left: List[str], right: List[str]) -> Dict[str, Any]:
    if len(left) != len(right):
        return {"values": max(len(left), len(right)), "length_mismatch": [len(left), len(right)],
                "identical": 0, "different": max(len(left), len(right)), "max_ulp": None}
    distances = [abs(_ordered(a) - _ordered(b)) for a, b in zip(left, right)]
    return {"values": len(distances), "identical": sum(1 for d in distances if d == 0),
            "different": sum(1 for d in distances if d), "max_ulp": max(distances, default=0)}


def _probe_result(payload: Dict[str, Any], engine: str) -> Dict[str, Any]:
    try:
        result = payload["config"]["hooks"]["inputs"]["js_engine_differential"]
    except (KeyError, TypeError) as error:
        raise SystemExit(f"{engine}: no hooks.inputs.js_engine_differential in the config ({error})")
    if result.get("schema") != SCHEMA:
        raise SystemExit(f"{engine}: probe schema {result.get('schema')!r} is not {SCHEMA}")
    return result


def run_quickjs(trech: Path, scenario: Path) -> Dict[str, Any]:
    proc = subprocess.run([str(trech), "inspect", str(scenario)], capture_output=True, text=True, cwd=ROOT)
    if proc.returncode != 0:
        raise SystemExit(f"quickjs: trech inspect failed: {proc.stderr.strip()[-800:]}")
    return json.loads(proc.stdout)


def run_v8(node: str, scenario: Path, dmath: bool = False) -> Dict[str, Any]:
    cmd = [node, str(NODE_HOST)] + (["--dmath"] if dmath else []) + [str(scenario)]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
    if proc.returncode != 0:
        raise SystemExit(f"v8: node host failed: {proc.stderr.strip()[-800:]}")
    return json.loads(proc.stdout)


def differential(quickjs: Dict[str, Any], v8: Dict[str, Any]) -> Dict[str, Any]:
    q, v = _probe_result(quickjs, "quickjs"), _probe_result(v8, "v8")
    sections: Dict[str, Dict[str, Any]] = {}
    for name in sorted(q["builtins"]):
        sections[f"builtins.{name}"] = compare_bits(q["builtins"][name], v["builtins"].get(name, []))
    for name in ("uniforms", "gaussians"):
        sections[f"random.{name}"] = compare_bits(q["random"][name], v["random"][name])
    for name in ("x", "y", "z", "temperatures"):
        sections[f"water_mw.{name}"] = compare_bits(q["water_mw"][name], v["water_mw"][name])
    phases_q, phases_v = q["water_mw"]["phases"], v["water_mw"]["phases"]
    phases = {"values": len(phases_q), "identical": sum(1 for a, b in zip(phases_q, phases_v) if a == b)}
    phases["different"] = phases["values"] - phases["identical"] + abs(len(phases_q) - len(phases_v))
    return {"schema": REPORT_SCHEMA, "engines": {"quickjs": "trech inspect (embedded QuickJS)",
                                                 "v8": v8.get("engine", {})},
            "sections": sections, "water_mw_phases": phases,
            "bit_identical": all(s["different"] == 0 for s in sections.values()) and phases["different"] == 0}


def gate_failures(report: Dict[str, Any]) -> List[str]:
    failures = []
    for name in EXACT_SECTIONS:
        if report["sections"][name]["different"]:
            failures.append(f"{name} differs ({report['sections'][name]['different']} value(s))")
    for name, section in report["sections"].items():
        if name.startswith("builtins.") and (section["max_ulp"] is None or section["max_ulp"] > MAX_BUILTIN_ULP):
            failures.append(f"{name} differs by {section['max_ulp']} ulp (> {MAX_BUILTIN_ULP})")
    if report["water_mw_phases"]["different"]:
        failures.append(f"CHILL+ phases differ ({report['water_mw_phases']['different']} site(s))")
    return failures


def format_report(report: Dict[str, Any]) -> str:
    engine = report["engines"]["v8"]
    lines = [f"QuickJS (trech inspect) vs V8 {engine.get('v8', '?')} (Node {engine.get('node', '?')}), "
             f"V8 Math: {engine.get('math', 'v8 builtin')}",
             f"{'section':24s} {'identical':>9s} {'different':>9s} {'max ulp':>8s}"]
    for name, s in report["sections"].items():
        lines.append(f"{name:24s} {s['identical']:9d} {s['different']:9d} {str(s['max_ulp']):>8s}")
    p = report["water_mw_phases"]
    lines.append(f"{'water_mw.phases':24s} {p['identical']:9d} {p['different']:9d} {'-':>8s}")
    lines.append("bit-identical" if report["bit_identical"] else "NOT bit-identical across engines")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--trech", type=Path, default=ROOT / "build" / "dev" / "trech")
    parser.add_argument("--node", default=shutil.which("node") or shutil.which("nodejs"))
    parser.add_argument("--scenario", type=Path, default=PROBE)
    parser.add_argument("--json", type=Path, help="write the report here")
    parser.add_argument("--check", action="store_true", help="fail when a portability gate fails")
    parser.add_argument("--dmath", action="store_true",
                        help="install trech_dmath (WebAssembly) as Math in the V8 context")
    parser.add_argument("--require-identical", action="store_true",
                        help="with --check, also fail unless every section is bit-identical")
    args = parser.parse_args(argv)
    if not args.node:
        print("node was not found; set --node", file=sys.stderr)
        return 2
    report = differential(run_quickjs(args.trech, args.scenario),
                          run_v8(args.node, args.scenario, args.dmath))
    print(format_report(report))
    if args.json:
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.check:
        failures = gate_failures(report)
        if args.require_identical and not report["bit_identical"]:
            different = [name for name, s in report["sections"].items() if s["different"]]
            failures.append("not bit-identical: " + ", ".join(different or ["water_mw.phases"]))
        for failure in failures:
            print("GATE FAIL: " + failure, file=sys.stderr)
        return 1 if failures else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
