#!/usr/bin/env python3
"""Guard docs/TRECH_current_scenarios_purity.md.

Fails when the committed purity report differs from a fresh generation, so any
added/removed/edited scenario bundle, law-ledger entry, referenced model or
committed validation report forces the report to be regenerated in the same
change. Also checks the generator's own invariants (lexer balance, one section
per bundle, comparison zones excluded from the normal path).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "validation"))

from trech_validation import purity  # noqa: E402

REGENERATE = "PYTHONPATH=tools/validation python3 -m trech_validation.purity"


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def check_lexer() -> None:
    """Every analysed file must lex to balanced brackets with offsets preserved."""
    for bundle in sorted(purity.SCENARIOS_DIR.iterdir()):
        entry = bundle / f"{bundle.name}.js"
        if not entry.exists():
            continue
        for path in [entry, *purity.resolve_includes(entry)]:
            src = path.read_text(encoding="utf-8")
            masked = purity.mask_js(src)
            if len(masked) != len(src) or masked.count("\n") != src.count("\n"):
                fail(f"{purity.rel(path)}: masking changed offsets")
            for opener, closer in ("{}", "()", "[]"):
                if masked.count(opener) != masked.count(closer):
                    fail(f"{purity.rel(path)}: unbalanced {opener}{closer} after masking "
                         "(lexer mis-read a string, comment or regex)")


def check_zones() -> None:
    """Comparison code is excluded; normal-path law shapes and integer powers are told apart."""
    src = (
        "function referenceDecay(k, t) { return Math.exp(-k * t); }\n"
        "function step(ctx, s) {\n"
        "  const v = Math.pow(s.size, 3);\n"
        "  if (mode === \"reference\") { s.x = Math.exp(-0.37 * s.t); }\n"
        "  s.rate = 1.0 - Math.exp(-0.42 * s.dt);  // Math.exp in a comment\n"
        "  const label = \"Math.exp(\";\n"
        "  return ctx.evolve({dt: s.dt});\n"
        "}\n"
    )
    ev = purity.analyse_source(src, "fixture.js", False)
    if ev.inference["evolve"] != 1:
        fail(f"zone fixture: expected 1 evolve site, got {ev.inference}")
    if ev.law_math != 1 or ev.comparison_law_math != 2:
        fail(f"zone fixture: expected 1 normal / 2 comparison law sites, got "
             f"{ev.law_math} / {ev.comparison_law_math}")
    if ev.geom_math != 1:
        fail(f"zone fixture: integer power must count as geometry, got {ev.geom_math}")
    if ev.comparison_functions != ["referenceDecay"]:
        fail(f"zone fixture: comparison functions {ev.comparison_functions}")


def check_pre_commit_rules() -> None:
    """The opt-in hook's relevance filter and benchmark-age reading."""
    from datetime import datetime, timedelta, timezone
    relevant = ["examples/scenarios/lava_lamp/lava_lamp.js", "js/trech_water_md.js",
                "data/lava_lamp_cascade/nano_material_response.json", "tools/validation/js_law_audit.json",
                "docs/validation_report.json", "scripts/run_validation_suite.sh",
                "projects/spectrum_prediction/lib/index.js"]
    irrelevant = ["studio/trech_studio/app.py", "src/engine.cpp", "README.md",
                  "docs/validation_report.md", "AGENTS/tooling/validation/ROADMAP.md"]
    for path in relevant:
        if not purity.is_relevant(path):
            fail(f"pre-commit filter: {path} should be relevant")
    for path in irrelevant:
        if purity.is_relevant(path):
            fail(f"pre-commit filter: {path} should not be relevant")
    import json
    stamp = json.loads(purity.VALIDATION_REPORT.read_text(encoding="utf-8"))["generated_at_utc"]
    when = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    age = purity.benchmark_age_days(when + timedelta(days=45))
    if age is None or abs(age - 45.0) > 1e-6:
        fail(f"benchmark age: expected 45 days, got {age}")


def main() -> int:
    check_lexer()
    check_zones()
    check_pre_commit_rules()
    reports, _ = purity.build_reports()
    bundles = sorted(p.name for p in purity.SCENARIOS_DIR.iterdir()
                     if p.is_dir() and (p / f"{p.name}.js").exists())
    if [r.name for r in reports] != bundles:
        fail("purity report does not cover exactly the scenario bundles")
    expected = purity.render(reports, purity.load_performance([])[1])
    path = purity.DEFAULT_OUTPUT
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    if current != expected:
        missing = [b for b in bundles if f"\n### {b}\n" not in current]
        detail = f" (missing sections: {missing})" if missing else ""
        fail(f"{purity.rel(path)} is stale{detail}; regenerate with:\n  {REGENERATE}")
    for bundle in bundles:
        if f"\n### {bundle}\n" not in current:
            fail(f"{purity.rel(path)}: no section for {bundle}")
    print(f"scenario purity report covers {len(bundles)} bundles and is current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
