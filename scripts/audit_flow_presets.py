#!/usr/bin/env python3
"""Audit scenario configs against the TRECH_FLOW validation presets.

Each scenario is wrapped (in a temporary directory, never next to the source)
by a tiny JS entry that includes it, builds its config exactly as `trech
inspect` would, and runs `TRECH_FLOW.check(config, presets)`. Any issue makes
`trech inspect` fail with an `AUDIT` message, which this script reports.

The presets only read the config; they never change what a scenario runs.
They catch authoring defects the engine tolerates silently, for example a
material name that is neither a G4_* NIST material nor declared in
`materials[]` (the detector would substitute a fallback medium).

    python3 scripts/audit_flow_presets.py --all
    python3 scripts/audit_flow_presets.py optics_surrogate_demo --presets materials
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "examples" / "scenarios"

WRAPPER = """TRECH_INCLUDE({entry});
(function() {{
  const presets = {presets};
  const original = globalThis.TRECH_CONFIG;
  globalThis.TRECH_CONFIG = function() {{
    const built = typeof original === "function" ? original.apply(this, arguments) : original;
    const config = built && typeof built.build === "function" ? built.build() : built;
    const issues = TRECH_FLOW.check(config, presets);
    if (issues.length) {{
      throw new Error("AUDIT " + JSON.stringify(issues));
    }}
    return built;
  }};
}})();
"""


def find_trech(explicit: str | None) -> Path:
    for candidate in (explicit, os.environ.get("TRECH_BIN")):
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return Path(candidate)
    # Presets live in the binary's JS bootstrap: prefer the most recent build.
    builds = [p for p in (ROOT / "build/rel/trech", ROOT / "build/dev/trech")
              if p.is_file() and os.access(p, os.X_OK)]
    if builds:
        return max(builds, key=lambda p: p.stat().st_mtime)
    raise SystemExit("trech binary not found (pass --trech or set TRECH_BIN)")


def scenario_entry(name_or_path: str) -> Path:
    path = Path(name_or_path)
    if path.suffix == ".js" and path.is_file():
        return path.resolve()
    entry = SCENARIOS / name_or_path / f"{name_or_path}.js"
    if not entry.is_file():
        raise SystemExit(f"scenario not found: {name_or_path}")
    return entry


def all_entries() -> list[Path]:
    return sorted(d / f"{d.name}.js" for d in SCENARIOS.iterdir()
                  if d.is_dir() and (d / f"{d.name}.js").is_file())


def audit(trech: Path, entry: Path, presets: str | list[str], timeout: float) -> dict:
    """Return {"scenario", "status": pass|issues|error, "issues", "error"}."""
    with tempfile.TemporaryDirectory(prefix="trech_flow_audit_") as tmp:
        wrapper = Path(tmp) / "audit.js"
        wrapper.write_text(WRAPPER.format(entry=json.dumps(str(entry)),
                                          presets=json.dumps(presets)))
        try:
            proc = subprocess.run([str(trech), "inspect", str(wrapper)], capture_output=True,
                                  text=True, timeout=timeout, cwd=str(ROOT))
        except subprocess.TimeoutExpired:
            return {"scenario": entry.parent.name, "status": "error", "issues": [],
                    "error": f"inspect timed out after {timeout:g}s"}
    text = proc.stdout + proc.stderr
    marker = text.find("AUDIT ")
    if marker >= 0:
        payload = text[marker + len("AUDIT "):].splitlines()[0]
        try:
            issues = json.loads(payload)
        except json.JSONDecodeError:
            issues = [payload]
        return {"scenario": entry.parent.name, "status": "issues", "issues": issues, "error": ""}
    if proc.returncode != 0:
        lines = [line for line in text.splitlines() if "error" in line.lower()]
        return {"scenario": entry.parent.name, "status": "error", "issues": [],
                "error": (lines[0] if lines else text.strip()[-300:])}
    return {"scenario": entry.parent.name, "status": "pass", "issues": [], "error": ""}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("scenarios", nargs="*", help="scenario names or .js paths")
    parser.add_argument("--all", action="store_true", help="audit every examples/scenarios entry")
    parser.add_argument("--presets", default="all",
                        help="comma-separated preset names (default: all registered presets)")
    parser.add_argument("--trech", help="trech binary (default: TRECH_BIN, else newest of build/rel, build/dev)")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--json", action="store_true", help="print a JSON report")
    args = parser.parse_args(argv)
    if not args.all and not args.scenarios:
        parser.error("name scenarios or pass --all")
    trech = find_trech(args.trech)
    entries = all_entries() if args.all else [scenario_entry(s) for s in args.scenarios]
    presets: str | list[str] = "all" if args.presets == "all" else [
        p.strip() for p in args.presets.split(",") if p.strip()]
    results = [audit(trech, entry, presets, args.timeout) for entry in entries]
    if args.json:
        print(json.dumps({"schema": "trech_flow_preset_audit_v1", "presets": presets,
                          "results": results}, indent=2))
    else:
        for r in results:
            if r["status"] == "pass":
                print(f"pass    {r['scenario']}")
            elif r["status"] == "issues":
                print(f"ISSUES  {r['scenario']}")
                for issue in r["issues"]:
                    print(f"          {issue}")
            else:
                print(f"ERROR   {r['scenario']}: {r['error']}")
        counts = {k: sum(r["status"] == k for r in results) for k in ("pass", "issues", "error")}
        print(f"{counts['pass']} pass, {counts['issues']} with issues, {counts['error']} not audited")
    return 0 if all(r["status"] == "pass" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
