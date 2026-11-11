"""Scenario purity report: how much behaviour is inferred versus authored.

Writes ``docs/TRECH_current_scenarios_purity.md`` with one section per scenario
bundle under ``examples/scenarios/``. The report is generated only from
committed inputs, so its content is deterministic and ``--check`` can guard it:

* the reviewed law ledger ``tools/validation/js_law_audit.json``;
* each bundle's ``<name>.validation.js`` (declared ``physics_status``, scope,
  limitations);
* static evidence from the scenario's normal-path JavaScript (the physics
  entry point plus the non-utility modules it includes): engine inference
  call sites, law-shaped math, embedded numeric coefficients and Geant4 fact
  reads, with comparison/reference/teacher code excluded;
* the provenance of every model file the scenario references
  (Geant4-trained, distilled from an authored teacher, anchor-trained or
  hand-authored);
* recorded performance: ``docs/validation_report.json`` cases mapped to
  scenarios through the suite's run names, plus other committed
  ``docs/validation_*.json`` reports attributed through their validator.

The static evidence is a heuristic. It does not run the engine and cannot prove
that a code path is reached; the reviewed ledger stays authoritative and the
report flags disagreements rather than overriding it.

Usage (from the repository root)::

    PYTHONPATH=tools/validation python3 -m trech_validation.purity          # rewrite
    PYTHONPATH=tools/validation python3 -m trech_validation.purity --check  # fail if stale
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

ROOT = Path(__file__).resolve().parents[3]
SCENARIOS_DIR = ROOT / "examples" / "scenarios"
AUDIT_PATH = ROOT / "tools" / "validation" / "js_law_audit.json"
VALIDATION_REPORT = ROOT / "docs" / "validation_report.json"
DEFAULT_OUTPUT = ROOT / "docs" / "TRECH_current_scenarios_purity.md"
SCHEMA = "trech_scenario_purity_v1"

# Shared modules that hold no material law: numeric/random/geometry utilities
# and recorded fact tables. They are listed but not counted.
UTILITY_MODULES = {
    "js/trech_helpers.js",
    "js/trech_math.js",
    "js/trech_random.js",
    "js/trech_geometry.js",
    "js/trech_material_facts.js",
}

INFERENCE_OPS = ("predict", "cascade", "evolve", "react", "interact")
RE_INFERENCE = re.compile(r"\bctx\.(predict|cascade|evolve|react|interact)\s*\(")
RE_AUTO_CASCADE = re.compile(r"\bctx\.cascade\s*\(\s*\)")
# Transcendental shapes typical of authored rate/decay/power laws.
RE_LAW_MATH = re.compile(
    r"\bMath\.(exp|expm1|log|log1p|log2|log10|pow|tanh|sinh|cosh|atanh|asinh|acosh)\s*\(|\*\*"
)
# Geometry/kinematics helpers; reported, not treated as forced laws.
RE_GEOM_MATH = re.compile(r"\bMath\.(sqrt|cbrt|hypot|sin|cos|tan|asin|acos|atan2?)\s*\(")
RE_G4_READ = re.compile(
    r"\bctx\.(materials|optics|step)\b|\bctx\.event\.(?!id\b)[A-Za-z_]\w*"
)
RE_RNG = re.compile(r"\bctx\.rng\b")
RE_NUMBER = re.compile(r"(?<![\w.$])(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?(?![\w.])")
RE_INCLUDE = re.compile(r"TRECH_INCLUDE\(\s*[\"']([^\"']+)[\"']\s*\)")
RE_DATA_PATH = re.compile(r"[\"'`](data/[A-Za-z0-9_./-]+?)/?[\"'`\s]")
RE_RUNTIME_MODEL_PATH = re.compile(r"\bpath\s*:\s*(?![\"'`\s])[A-Za-z_$][\w$.]*")
RE_SCALE_TAG = re.compile(r"\bscale\s*:\s*[\"'](atomic|nano|micro|meso|macro)[\"']")
# Function or branch names that mark validation/teacher code, not the normal path.
RE_COMPARISON_NAME = re.compile(
    r"reference|classical|analytic|comparison|teacher|oracle|crosscheck|cross_check|expected",
    re.IGNORECASE,
)
SCALE_ORDER = ("atomic", "nano", "micro", "meso", "macro")
# Numeric literals that are units, halves or numeric guards rather than physics.
TRIVIAL_DECIMALS = {0.0, 0.5, 0.25, 0.75, 1.0, 2.0, 3.0, 4.0, 10.0, 100.0, 1000.0, 1e3, 1e6, 1e9,
                    1e-3, 1e-6, 1e-9, 1e-12, 1e-15}

NO_LAW_STATUSES = {"no_active_material_law", "configuration_or_transport",
                   "learned_geant4_transport_candidate", ""}

GRADES = [
    ("A", "Geant4-learned", "Normal path runs engine inference whose models were trained on Geant4 "
     "Monte Carlo output; no authored material law remains on it."),
    ("B", "Learned, not from Geant4", "Normal path runs engine inference with trained models, but "
     "they were distilled from an authored teacher law or fitted to external anchors rather than "
     "Geant4 output, so the behaviour's origin is not yet the particle base."),
    ("C", "Partially operator-backed", "Inference supplies part of the normal path; named "
     "authored laws remain in the ledger residual."),
    ("D", "Authored law, inferred coefficients", "The cascade infers coefficients, but an "
     "authored forward law integrates the behaviour."),
    ("E", "Authored forward law", "Behaviour is driven by an authored law with no engine "
     "inference on the normal path (labelled comparison physics; a migration target)."),
    ("M", "Inference mechanism demo", "Uses engine inference without a declared material law, "
     "but at least one normal-path model is a hand-authored response surface (or none could be "
     "resolved). It shows the mechanism, not learned physics."),
    ("G", "Geant4 transport / configuration", "Pure Geant4 transport or configuration. Nothing "
     "is forced, but nothing is lifted up the scale ladder either."),
    ("V", "Analytic cross-check", "Classical formulas fed from Geant4's own data, used only to "
     "validate transport. This is the permitted use of closed-form laws."),
    ("R", "Independent comparison reference", "An explicitly separate comparison solver, kept "
     "outside TRECH's learned path. It must not become training truth."),
]
GRADE_TITLES = {g: t for g, t, _ in GRADES}


# ---------------------------------------------------------------- JS lexing

def mask_js(src: str) -> str:
    """Return ``src`` with comments and string/template/regex bodies blanked.

    Offsets and newlines are preserved, so spans found on the masked text index
    the original. Quotes are kept so string positions stay recognisable.
    """
    out = list(src)
    i, n = 0, len(src)
    last_sig = ""  # last significant (non-space) code character
    last_word = ""

    def blank(a: int, b: int) -> None:
        for k in range(a, min(b, n)):
            if out[k] != "\n":
                out[k] = " "

    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        if c == "/" and nxt == "/":
            j = src.find("\n", i)
            j = n if j < 0 else j
            blank(i, j)
            i = j
            continue
        if c == "/" and nxt == "*":
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            blank(i, j)
            i = j
            continue
        if c in "\"'`":
            j = i + 1
            while j < n and src[j] != c:
                if src[j] == "\\":
                    j += 1
                elif c != "`" and src[j] == "\n":
                    break
                j += 1
            blank(i + 1, j)
            i = j + 1
            last_sig = c
            last_word = ""
            continue
        if c == "/" and (last_sig in "" "(,=:[!&|?{};+-*%<>~^" or last_word in {"return", "typeof", "case"}):
            j = i + 1
            in_class = False
            while j < n and src[j] != "\n":
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == "[":
                    in_class = True
                elif src[j] == "]":
                    in_class = False
                elif src[j] == "/" and not in_class:
                    break
                j += 1
            if j < n and src[j] == "/":
                blank(i + 1, j)
                j += 1
                while j < n and (src[j].isalpha()):
                    j += 1
                i = j
                last_sig = "/"
                last_word = ""
                continue
        if not c.isspace():
            if c.isalnum() or c in "_$":
                j = i
                while j < n and (src[j].isalnum() or src[j] in "_$"):
                    j += 1
                last_word = src[i:j]
                last_sig = src[j - 1]
                i = j
                continue
            last_sig = c
            last_word = ""
        i += 1
    return "".join(out)


def match_brace(masked: str, open_at: int) -> int:
    """Index just past the brace/paren closing the one at ``open_at``."""
    pairs = {"{": "}", "(": ")", "[": "]"}
    opener = masked[open_at]
    closer = pairs[opener]
    depth = 0
    for k in range(open_at, len(masked)):
        ch = masked[k]
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return k + 1
    return len(masked)


RE_FN_DECL = re.compile(r"\bfunction\s*\*?\s*([A-Za-z_$][\w$]*)?\s*\(")
RE_FN_ASSIGN = re.compile(r"([A-Za-z_$][\w$]*)\s*[:=]\s*(?:async\s+)?(?:function\b[^(]*\(|\([^()]*\)\s*=>\s*\{|[A-Za-z_$][\w$]*\s*=>\s*\{)")
RE_METHOD = re.compile(r"(?m)^[ \t]*(?:async\s+)?([A-Za-z_$][\w$]*)\s*\([^()]*\)\s*\{")
RE_IF = re.compile(r"\bif\s*\(")
KEYWORDS = {"if", "for", "while", "switch", "catch", "function", "return", "with"}


@dataclass
class Span:
    start: int
    end: int
    name: str


def function_spans(masked: str) -> List[Span]:
    spans: List[Span] = []
    seen: Set[int] = set()

    def add(name: str, search_from: int) -> None:
        brace = masked.find("{", search_from)
        if brace < 0 or brace in seen:
            return
        seen.add(brace)
        spans.append(Span(brace, match_brace(masked, brace), name or ""))

    for m in RE_FN_DECL.finditer(masked):
        paren = m.end() - 1
        name = m.group(1) or ""
        if not name:
            # anonymous: borrow the assigned name, if any (`name = function (`).
            before = masked[max(0, m.start() - 80):m.start()]
            am = re.search(r"([A-Za-z_$][\w$]*)\s*[:=]\s*(?:async\s+)?$", before)
            name = am.group(1) if am else ""
        add(name, match_brace(masked, paren))
    for m in RE_FN_ASSIGN.finditer(masked):
        if "=>" in m.group(0):
            add(m.group(1), m.end() - 1)
    for m in RE_METHOD.finditer(masked):
        if m.group(1) not in KEYWORDS:
            add(m.group(1), m.end() - 1)
    return spans


def comparison_spans(src: str, masked: str, spans: Sequence[Span]) -> List[Tuple[int, int]]:
    """Code regions that are comparison/teacher/reference only."""
    zones = [(s.start, s.end) for s in spans if s.name and RE_COMPARISON_NAME.search(s.name)]
    for m in RE_IF.finditer(masked):
        paren = m.end() - 1
        close = match_brace(masked, paren)
        cond = src[paren:close]
        if re.search(r"(?<![!=])==+\s*[\"']reference[\"']|[\"']reference[\"']\s*==+", cond) or \
                re.search(r"\b\w*[Rr]eference\w*\b", masked[paren:close]) and "!" not in masked[paren:close]:
            k = close
            while k < len(masked) and masked[k].isspace():
                k += 1
            if k < len(masked) and masked[k] == "{":
                zones.append((k, match_brace(masked, k)))
    return merge(zones)


def merge(zones: Iterable[Tuple[int, int]]) -> List[Tuple[int, int]]:
    out: List[Tuple[int, int]] = []
    for a, b in sorted(zones):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def inside(pos: int, zones: Sequence[Tuple[int, int]]) -> bool:
    for a, b in zones:
        if a <= pos < b:
            return True
        if a > pos:
            return False
    return False


# ---------------------------------------------------------- code evidence

@dataclass
class CodeEvidence:
    files: List[str] = field(default_factory=list)
    code_lines: int = 0
    inference: Dict[str, int] = field(default_factory=lambda: {op: 0 for op in INFERENCE_OPS})
    auto_cascade: int = 0
    law_math: int = 0
    geom_math: int = 0
    coefficients: int = 0
    toplevel_literals: int = 0
    g4_reads: int = 0
    rng: int = 0
    comparison_law_math: int = 0
    comparison_functions: List[str] = field(default_factory=list)
    scale_tags: Set[str] = field(default_factory=set)
    data_paths: Dict[str, bool] = field(default_factory=dict)  # path -> seen on normal path
    hooks: bool = False
    runtime_model_paths: int = 0
    sites: List[Tuple[str, int, str, str]] = field(default_factory=list)  # file, line, kind, text

    @property
    def inference_total(self) -> int:
        return sum(self.inference.values())

    def absorb(self, other: "CodeEvidence") -> None:
        self.files += other.files
        self.code_lines += other.code_lines
        for op in INFERENCE_OPS:
            self.inference[op] += other.inference[op]
        for name in ("runtime_model_paths", "auto_cascade", "law_math", "geom_math", "coefficients", "toplevel_literals",
                     "g4_reads", "rng", "comparison_law_math"):
            setattr(self, name, getattr(self, name) + getattr(other, name))
        self.comparison_functions += other.comparison_functions
        self.scale_tags |= other.scale_tags
        for p, normal in other.data_paths.items():
            self.data_paths[p] = self.data_paths.get(p, False) or normal
        self.hooks = self.hooks or other.hooks
        self.sites += other.sites


def is_coefficient(token: str) -> bool:
    if "." not in token and "e" not in token.lower():
        return False  # integers: indices, counts, sizes
    try:
        value = abs(float(token))
    except ValueError:
        return False
    if value == 0.0 or value in TRIVIAL_DECIMALS:
        return False
    return value >= 1e-6  # tiny literals are numeric guards/tolerances


RE_INT_EXPONENT = re.compile(r"\s*\(?\s*-?\d+\s*\)?\s*(?:[^\w.(]|$)")


def is_integer_power(masked: str, m: "re.Match[str]") -> bool:
    """``x ** 3`` / ``Math.pow(x, 2)``: polynomial geometry, not a law shape."""
    if m.group(0) == "**":
        return bool(RE_INT_EXPONENT.match(masked, m.end()))
    if m.group(1) != "pow":
        return False
    close = match_brace(masked, m.end() - 1)
    args = masked[m.end():close - 1]
    depth, split = 0, -1
    for k, ch in enumerate(args):
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            split = k
    return split >= 0 and re.fullmatch(r"\s*-?\d+\s*", args[split + 1:]) is not None


def analyse_source(src: str, relative: str, whole_file_comparison: bool) -> CodeEvidence:
    ev = CodeEvidence(files=[relative])
    masked = mask_js(src)
    spans = function_spans(masked)
    zones = [(0, len(src))] if whole_file_comparison else comparison_spans(src, masked, spans)
    bodies = merge((s.start, s.end) for s in spans)
    ev.comparison_functions = sorted({s.name for s in spans if s.name and RE_COMPARISON_NAME.search(s.name)})
    ev.hooks = "TRECH_HOOKS" in masked
    ev.code_lines = sum(1 for line in masked.splitlines() if line.strip())
    src_lines = src.splitlines()

    def site(pos: int, kind: str) -> None:
        line = src.count("\n", 0, pos) + 1
        ev.sites.append((relative, line, kind, src_lines[line - 1].strip()[:110] if line <= len(src_lines) else ""))

    for m in RE_INFERENCE.finditer(masked):
        if not inside(m.start(), zones):
            ev.inference[m.group(1)] += 1
            site(m.start(), "inference")
    ev.auto_cascade = sum(1 for m in RE_AUTO_CASCADE.finditer(masked) if not inside(m.start(), zones))
    for m in RE_LAW_MATH.finditer(masked):
        if is_integer_power(masked, m):
            if not inside(m.start(), zones):
                ev.geom_math += 1
            continue
        if inside(m.start(), zones):
            ev.comparison_law_math += 1
        else:
            ev.law_math += 1
            site(m.start(), "law")
    ev.geom_math += sum(1 for m in RE_GEOM_MATH.finditer(masked) if not inside(m.start(), zones))
    ev.g4_reads = sum(1 for m in RE_G4_READ.finditer(masked) if not inside(m.start(), zones))
    ev.rng = sum(1 for m in RE_RNG.finditer(masked) if not inside(m.start(), zones))
    for m in RE_NUMBER.finditer(masked):
        token = m.group(0)
        if not is_coefficient(token) or inside(m.start(), zones):
            continue
        if inside(m.start(), bodies):
            ev.coefficients += 1
            site(m.start(), "coefficient")
        else:
            ev.toplevel_literals += 1
    ev.runtime_model_paths = sum(1 for m in RE_RUNTIME_MODEL_PATH.finditer(masked)
                                 if not inside(m.start(), zones) and re.search(r"\bmodels?\b|scale\s*:", masked[max(0, m.start() - 120):m.end() + 60]))
    ev.scale_tags = {m.group(1) for m in RE_SCALE_TAG.finditer(src) if masked[m.start()] != " "}
    for m in RE_DATA_PATH.finditer(src):
        # only string literals in code (masked keeps the quote, blanks the body)
        if masked[m.start()] not in "\"'`" or masked[m.start() + 1] != " ":
            continue
        path = m.group(1).rstrip("/")
        normal = not inside(m.start(), zones)
        ev.data_paths[path] = ev.data_paths.get(path, False) or normal
    return ev


def resolve_includes(entry: Path) -> List[Path]:
    """Transitive TRECH_INCLUDE closure of ``entry`` (excluding itself), in load order."""
    ordered: List[Path] = []
    seen: Set[Path] = {entry.resolve()}

    def walk(path: Path) -> None:
        try:
            masked_src = path.read_text(encoding="utf-8")
        except OSError:
            return
        code = mask_js(masked_src)
        for m in RE_INCLUDE.finditer(masked_src):
            if code[m.start()] == " ":
                continue  # inside a comment
            target = (path.parent / m.group(1)).resolve()
            if target in seen or not target.exists():
                continue
            seen.add(target)
            ordered.append(target)
            walk(target)

    walk(entry)
    return ordered


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


# ---------------------------------------------------------------- models

@dataclass
class ModelInfo:
    path: str
    origin: str  # geant4_trained | distilled | anchor_trained | trained | hand_authored
    scale: str
    r2_min: Optional[float]
    holdout_n: Optional[int]
    normal_path: bool

    @property
    def label(self) -> str:
        return {
            "geant4_trained": "Geant4-trained",
            "distilled": "distilled from authored teacher",
            "anchor_trained": "trained on measured anchors",
            "trained": "trained (source unrecorded)",
            "hand_authored": "hand-authored response surface",
        }[self.origin]


def _note_text(doc: Dict) -> str:
    note = doc.get("note")
    return json.dumps(note) if isinstance(note, (dict, list)) else str(note or "")


def classify_model(path: Path, normal: bool) -> Optional[ModelInfo]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict) or "model" not in doc:
        return None
    note = _note_text(doc)
    trained_from = doc.get("trained_from")
    tf_text = json.dumps(trained_from) if trained_from else ""
    note_obj = doc.get("note") if isinstance(doc.get("note"), dict) else {}
    if (note_obj.get("geant4_trained") is True) or re.search(r"geant4 monte carlo", tf_text, re.I):
        origin = "geant4_trained"
    elif trained_from and (re.search(r"teacher|distill|reference", note + tf_text, re.I)):
        origin = "distilled"
    elif trained_from:
        origin = "trained"
    elif doc.get("materials_trained") or re.search(r"anchor-trained|leave-one-out", note, re.I):
        origin = "anchor_trained"
    else:
        origin = "hand_authored"
    holdout = doc.get("holdout") or {}
    r2 = holdout.get("r2_min") if isinstance(holdout, dict) else None
    n = holdout.get("n") if isinstance(holdout, dict) else None
    bands = doc.get("trained_scale_bands") or []
    scale = doc.get("scale") or (bands[0] if bands else "")
    return ModelInfo(rel(path), origin, str(scale), r2 if isinstance(r2, (int, float)) else None,
                     n if isinstance(n, int) else None, normal)


def collect_models(data_paths: Dict[str, bool]) -> List[ModelInfo]:
    paths = dict(data_paths)
    # An untrained set referenced next to its ``<set>_trained`` sibling is the
    # teacher set of a reference switch: files the trained set replaces are
    # comparison-only; files it does not replace stay on the normal path.
    replaced: Set[str] = set()
    for p in list(paths):
        trained = ROOT / (p + "_trained")
        if p + "_trained" in paths and trained.is_dir():
            replaced |= {rel(f) for f in (ROOT / p).glob("*.json") if (trained / f.name).exists()}
    models: Dict[str, ModelInfo] = {}
    for p, normal in sorted(paths.items()):
        target = ROOT / p
        files: List[Path] = []
        if target.is_dir():
            files = sorted(f for f in target.glob("*.json") if not f.name.endswith(".manifest.json"))
        elif target.suffix == ".json" and target.exists():
            files = [target]
        for f in files:
            info = classify_model(f, normal and rel(f) not in replaced)
            if info is None:
                continue
            prev = models.get(info.path)
            if prev is None or (normal and not prev.normal_path):
                models[info.path] = info
    return [models[k] for k in sorted(models)]


# ----------------------------------------------------------- performance

@dataclass
class CaseRecord:
    name: str
    status: str
    summary: str


def run_to_scenario_map() -> List[Tuple[re.Pattern, str]]:
    """Map validation run names (``out_*``) to scenario bundles.

    Shell orchestration is read through ``--output`` lines (the run follows its
    scenario path); Python drivers attribute ``out_*`` tokens to the scenario
    path last mentioned before them. ``${VAR}`` parts become wildcards.
    """
    mapping: Dict[str, str] = {}
    scen_re = re.compile(r"examples/scenarios/([A-Za-z0-9_]+)/")
    out_re = re.compile(r"\bout_[A-Za-z0-9_${}]+")
    scripts = ROOT / "scripts"
    for sh in sorted(scripts.glob("*.sh")):
        last = None
        for line in sh.read_text(encoding="utf-8").splitlines():
            for m in scen_re.finditer(line):
                last = m.group(1)
            if "--output" in line and last:
                for m in out_re.finditer(line):
                    mapping.setdefault(m.group(0), last)
    for py in sorted(scripts.glob("*.py")):
        last = None
        for line in py.read_text(encoding="utf-8").splitlines():
            for m in scen_re.finditer(line):
                last = m.group(1)
            if last:
                for m in out_re.finditer(line):
                    mapping.setdefault(m.group(0), last)
    out: List[Tuple[re.Pattern, str]] = []
    for token, scenario in sorted(mapping.items()):
        pattern = re.escape(token).replace(r"\$\{", "${").replace(r"\}", "}")
        pattern = re.sub(r"\$\{[^}]*\}", ".+", pattern)
        out.append((re.compile("^" + pattern + "$"), scenario))
    return out


def case_runs() -> Dict[str, List[str]]:
    sys.path.insert(0, str(ROOT / "tools" / "validation"))
    try:
        from trech_validation.cases import ALL_CASES  # noqa: WPS433 (local import keeps CLI light)
    except Exception:  # pragma: no cover - mapping degrades to name matching
        return {}
    runs: Dict[str, List[str]] = {}
    for case in ALL_CASES:
        try:
            runs[case.name] = list(case.required_runs())
        except Exception:
            runs[case.name] = []
    return runs


def load_performance(scenarios: Sequence[str]) -> Tuple[Dict[str, List[CaseRecord]], Dict[str, str]]:
    per: Dict[str, List[CaseRecord]] = {s: [] for s in scenarios}
    meta: Dict[str, str] = {}
    if not VALIDATION_REPORT.exists():
        return per, meta
    report = json.loads(VALIDATION_REPORT.read_text(encoding="utf-8"))
    meta = {"git_sha": str(report.get("git_sha", "")),
            "generated": str(report.get("generated_at_utc", "")),
            "counts": json.dumps(report.get("counts", {}), sort_keys=True)}
    patterns = run_to_scenario_map()
    runs = case_runs()
    names = sorted(scenarios, key=len, reverse=True)
    for result in report.get("results", []):
        name = result.get("name", "")
        targets: Set[str] = set()
        for run in runs.get(name, []):
            for pattern, scenario in patterns:
                if pattern.match(run):
                    targets.add(scenario)
                    break
        if not targets:
            prefix = next((s for s in names if name.startswith(s)), None)
            if prefix:
                targets.add(prefix)
        for scenario in targets:
            if scenario in per:
                per[scenario].append(CaseRecord(name, str(result.get("status", "")),
                                                " ".join(str(result.get("summary", "")).split())))
    for s in per:
        per[s].sort(key=lambda c: c.name)
    return per, meta


RE_ERR_KEY = re.compile(r"(rel_error|relative_error|^mae|_mae$|mae_|^r2|rmse|^delta$)", re.I)


def aux_reports(scenarios: Sequence[str]) -> Dict[str, List[Tuple[str, List[str]]]]:
    """Other committed ``docs/validation_*.json`` reports, attributed via their validator."""
    out: Dict[str, List[Tuple[str, List[str]]]] = {s: [] for s in scenarios}
    scen_re = re.compile(r"examples/scenarios/([A-Za-z0-9_]+)")
    for report in sorted((ROOT / "docs").glob("validation_*.json")):
        if report.name == VALIDATION_REPORT.name:
            continue
        validator = ROOT / "scripts" / f"validate_{report.stem[len('validation_'):]}.py"
        if not validator.exists():
            continue
        targets = {m.group(1) for m in scen_re.finditer(validator.read_text(encoding="utf-8"))}
        try:
            doc = json.loads(report.read_text(encoding="utf-8"))
        except ValueError:
            continue
        lines: List[str] = []

        def walk(node, path: str) -> None:
            if isinstance(node, list):
                for item in node:
                    walk(item, path)
                return
            if not isinstance(node, dict):
                return
            label = node.get("interface") or node.get("material") or node.get("label")
            here = f"{path}[{label}]" if label and path else path
            for k in sorted(node):
                v = node[k]
                sub = f"{here}.{k}" if here else k
                if isinstance(v, (dict, list)):
                    walk(v, f"{here}.{k}" if here else k)
                elif isinstance(v, bool):
                    if re.search(r"improves|within|pass", k):
                        lines.append(f"`{sub}` = {v}")
                elif isinstance(v, (int, float)) and RE_ERR_KEY.search(k) and v == v and abs(v) != float("inf"):
                    lines.append(f"`{sub}` = {v:.4g}")

        walk(doc, "")
        for t in sorted(targets):
            if t in out:
                out[t].append((rel(report), lines[:12] + ([f"… {len(lines) - 12} more"] if len(lines) > 12 else [])))
    return out


# ------------------------------------------------------------- companions

def companion_fields(path: Path) -> Dict[str, str]:
    fields: Dict[str, str] = {}
    if not path.exists():
        return fields
    text = path.read_text(encoding="utf-8")
    for key in ("physics_status", "scope", "limitations", "reference"):
        m = re.search(r"(?<![\w])[\"']?%s[\"']?\s*:\s*\"((?:[^\"\\]|\\.)*)\"" % key, text)
        if m:
            try:
                fields[key] = json.loads('"' + m.group(1) + '"')
            except ValueError:
                fields[key] = m.group(1)
    return fields


# ------------------------------------------------------------------ grade

@dataclass
class ScenarioReport:
    name: str
    entry: str
    ledger_status: str
    ledger_residual: str
    ledger_note: str
    declared_status: str
    scope: str
    limitations: str
    validator: str
    own: CodeEvidence
    inherited: CodeEvidence
    total: CodeEvidence
    utility_modules: List[str]
    data_includes: List[str]
    comparison_modules: List[str]
    models: List[ModelInfo]
    cases: List[CaseRecord]
    aux: List[Tuple[str, List[str]]]
    grade: str = ""
    flags: List[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        return self.ledger_status or self.declared_status

    @property
    def normal_models(self) -> List[ModelInfo]:
        return [m for m in self.models if m.normal_path]

    @property
    def inference_share(self) -> Optional[float]:
        i = self.total.inference_total
        denominator = i + self.total.law_math
        return None if denominator == 0 else i / denominator

    @property
    def coefficient_density(self) -> float:
        lines = max(self.total.code_lines, 1)
        return 100.0 * self.total.coefficients / lines

    @property
    def scales(self) -> List[str]:
        found = set(self.total.scale_tags)
        found |= {m.scale for m in self.normal_models if m.scale in SCALE_ORDER}
        return [s for s in SCALE_ORDER if s in found]


def grade(rep: ScenarioReport) -> Tuple[str, List[str]]:
    status = rep.status
    models = rep.normal_models
    infer = rep.total.inference_total > 0
    g4_models = bool(models) and all(m.origin == "geant4_trained" for m in models)
    learned = bool(models) and all(m.origin != "hand_authored" for m in models)
    flags: List[str] = []
    if status in {"operator_backed", "operator_native"}:
        g = "A" if g4_models else "B"
    elif status == "operator_partial":
        g = "C"
    elif status == "reference_only":
        if rep.name.endswith("_reference"):
            g = "R"
        elif infer:
            g = "D"
        else:
            g = "E"
    else:
        if infer and g4_models:
            g = "A"
        elif rep.name.startswith("analytic_"):
            g = "V"
        elif infer and learned:
            g = "B"
        elif infer:
            g = "M"
        else:
            g = "G"
        if g in {"G", "M"} and rep.total.law_math >= 3:
            flags.append(
                f"declared `{status or 'unset'}` but {rep.total.law_math} law-shaped math sites sit "
                "outside comparison-labelled code; review whether an authored law drives behaviour")
    if rep.ledger_status and rep.declared_status and rep.ledger_status != rep.declared_status and \
            not {rep.ledger_status, rep.declared_status} <= NO_LAW_STATUSES:
        flags.append(f"ledger says `{rep.ledger_status}`, validation companion says "
                     f"`{rep.declared_status}`")
    if rep.own.hooks and not rep.ledger_status:
        flags.append("declares `TRECH_HOOKS` but has no entry in `tools/validation/js_law_audit.json`")
    if not models and rep.total.inference["predict"] + rep.total.inference["cascade"] > 0:
        flags.append("calls inference but no model file could be resolved statically")
    stale = [m for m in models if m.origin == "hand_authored"]
    if stale and g in {"A", "B", "C", "D"}:
        flags.append(f"{len(stale)} normal-path model(s) are hand-authored response surfaces, not trained")
    if any(c.status in {"fail", "error"} for c in rep.cases):
        flags.append("a recorded validation case is failing")
    return g, flags


def build_reports() -> Tuple[List[ScenarioReport], Dict[str, str]]:
    audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8")) if AUDIT_PATH.exists() else {}
    ledger = audit.get("experiments") or {}
    names = sorted(p.name for p in SCENARIOS_DIR.iterdir()
                   if p.is_dir() and (p / f"{p.name}.js").exists())
    performance, meta = load_performance(names)
    aux = aux_reports(names)
    reports: List[ScenarioReport] = []
    for name in names:
        entry = SCENARIOS_DIR / name / f"{name}.js"
        own = analyse_source(entry.read_text(encoding="utf-8"), rel(entry), False)
        inherited = CodeEvidence()
        utility: List[str] = []
        data_inc: List[str] = []
        comparison_mods: List[str] = []
        for inc in resolve_includes(entry):
            r = rel(inc)
            if r in UTILITY_MODULES:
                utility.append(r)
                continue
            if r.startswith("data/"):
                data_inc.append(r)
                continue
            if inc.name.endswith(".view.js") or inc.name.endswith(".ui.js") or inc.name.endswith(".validation.js"):
                continue
            whole = "_reference" in inc.stem
            if whole:
                comparison_mods.append(r)
            inherited.absorb(analyse_source(inc.read_text(encoding="utf-8"), r, whole))
        total = CodeEvidence()
        total.absorb(own)
        total.absorb(inherited)
        entry_rel = rel(entry)
        led = ledger.get(entry_rel) or {}
        comp = companion_fields(SCENARIOS_DIR / name / f"{name}.validation.js")
        rep = ScenarioReport(
            name=name, entry=entry_rel,
            ledger_status=str(led.get("status", "")), ledger_residual=str(led.get("residual", "")),
            ledger_note=str(led.get("note", "")), declared_status=comp.get("physics_status", ""),
            scope=comp.get("scope", ""), limitations=comp.get("limitations", ""),
            validator=comp.get("reference", ""), own=own, inherited=inherited, total=total,
            utility_modules=utility, data_includes=data_inc, comparison_modules=comparison_mods,
            models=collect_models(total.data_paths), cases=performance.get(name, []),
            aux=aux.get(name, []))
        rep.grade, rep.flags = grade(rep)
        reports.append(rep)
    return reports, meta


# ----------------------------------------------------------------- render

def pct(value: Optional[float]) -> str:
    return "—" if value is None else f"{100.0 * value:.0f}%"


def case_tally(cases: Sequence[CaseRecord]) -> str:
    if not cases:
        return "none recorded"
    counts: Dict[str, int] = {}
    for c in cases:
        counts[c.status] = counts.get(c.status, 0) + 1
    return ", ".join(f"{counts[k]} {k}" for k in sorted(counts))


def model_tally(models: Sequence[ModelInfo]) -> str:
    normal = [m for m in models if m.normal_path]
    if not normal:
        return "—"
    short = {"geant4_trained": "G4", "distilled": "dist", "anchor_trained": "anchor",
             "trained": "trained", "hand_authored": "hand"}
    counts: Dict[str, int] = {}
    for m in normal:
        counts[short[m.origin]] = counts.get(short[m.origin], 0) + 1
    return " ".join(f"{v}×{k}" for k, v in sorted(counts.items()))


def anchor(name: str) -> str:
    return name.lower()


def esc(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ").strip()


def render(reports: Sequence[ScenarioReport], meta: Dict[str, str]) -> str:
    out: List[str] = []
    w = out.append
    w("# TRECH — current scenarios purity report")
    w("")
    w("<!-- GENERATED FILE: do not edit by hand. Regenerate with")
    w("     PYTHONPATH=tools/validation python3 -m trech_validation.purity")
    w(f"     schema: {SCHEMA} -->")
    w("")
    w("This report shows, for every bundle in [`examples/scenarios/`](../examples/scenarios), how much of "
      "its behaviour comes from **TRECH statistical inference over the Geant4 base** and how much is "
      "**forced by authored laws, fixed constants and closed-form functions**. It follows the "
      "[engine thesis](../AGENTS.md#essential-project-principles): elementary Geant4 truth is lifted scale by "
      "scale through learned models, and classical formulas stay comparison/validation references only.")
    w("")
    w("It is regenerated from committed inputs only, so it is reproducible and guarded by CTest "
      "(`trech_scenario_purity_report`). Adding, removing or editing a scenario, the law ledger, a "
      "referenced model or the committed validation report makes that test fail until the file is "
      "regenerated. `scripts/run_validation_suite.sh` also regenerates it after each validation report. "
      "**Purity is a static and declared measure. Performance is whatever the last committed validation "
      "run recorded.** Neither is proof that a run is correct.")
    w("")
    w("## How to read it")
    w("")
    w("### Purity grade")
    w("")
    w("The reviewed law ledger ([`tools/validation/js_law_audit.json`](../tools/validation/js_law_audit.json)) "
      "is authoritative. Bundles outside the ledger fall back to the `physics_status` declared in their "
      "`.validation.js` companion. Model provenance then decides between A and B (or A and M).")
    w("")
    w("| Grade | Meaning | Rule |")
    w("| --- | --- | --- |")
    for g, title, rule in GRADES:
        w(f"| **{g}** | {title} | {rule} |")
    w("")
    w("Purity order for TRECH's goal: **A > B > C > D > E**. **M** is mechanism-only. **G** forces "
      "nothing but lifts nothing. **V** and **R** are validation roles, not lift attempts.")
    w("")
    w("### Static evidence (normal path)")
    w("")
    w("The generator lexes the physics entry point and every non-utility module it `TRECH_INCLUDE`s "
      "(`.view.js`, `.ui.js` and `.validation.js` companions are presentation/expectations and are excluded). "
      "Code inside functions whose names say *reference/classical/analytic/comparison/teacher/oracle/expected*, "
      "inside `if (… \"reference\" …)` branches, and inside `*_reference.js` modules counts as comparison "
      "code, not normal path.")
    w("")
    w("- **Inference sites**: `ctx.predict/cascade/evolve/react/interact` call sites. `ctx.cascade()` "
      "with no argument auto-seeds from the Geant4 base.")
    w("- **Law-shaped math**: `Math.exp/log/pow/tanh/sinh/cosh…` and `**`, the usual signatures of "
      "authored rate, decay or power laws.")
    w("- **Inference share** = inference sites ÷ (inference sites + law-shaped math). It reads 100% when "
      "no authored law shape remains on the normal path, and — when the bundle has neither.")
    w("- **Embedded coefficients**: non-trivial decimal/exponent literals inside function bodies, per "
      "100 code lines. These are forced numbers in behavioural code. Top-level literals "
      "(apparatus, inputs) are reported separately and not counted against purity.")
    w("- **Geant4 reads**: `ctx.materials/optics/step` and per-event `ctx.event.*` facts consumed "
      "by the hooks.")
    w("- Geometry/kinematics math (`sqrt`, trig) is listed but not treated as a forced law.")
    w("")
    w("Model provenance comes from each referenced model file's own metadata: `trained_from`, `holdout`, "
      "`note.teacher` and `note.geant4_trained`.")
    w("")
    if meta:
        w(f"Performance source: [`docs/validation_report.json`](validation_report.json), generated "
          f"{meta.get('generated', '?')} at `{meta.get('git_sha', '?')}` (totals {meta.get('counts', '{}')}). "
          "Bundles that the suite does not run show *none recorded*. Their dedicated validators "
          "(when declared) are listed per section.")
        w("")

    # summary
    w("## Summary")
    w("")
    counts: Dict[str, int] = {}
    for r in reports:
        counts[r.grade] = counts.get(r.grade, 0) + 1
    w(f"{len(reports)} scenario bundles. Grade distribution: " +
      ", ".join(f"**{g}** {counts[g]}" for g, _, _ in GRADES if g in counts) + ".")
    w("")
    flagged = [r for r in reports if r.flags]
    if flagged:
        w(f"{len(flagged)} bundles carry review flags (see their sections).")
        w("")
    w("| Scenario | Grade | Status | Inference share | Inference / law sites | Coeff. /100 lines | "
      "Models (normal path) | Scales | Validation |")
    w("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for r in reports:
        flag = " ⚠" if r.flags else ""
        w(f"| [{r.name}](#{anchor(r.name)}) | **{r.grade}**{flag} | `{r.status or 'unset'}` | "
          f"{pct(r.inference_share)} | {r.total.inference_total} / {r.total.law_math} | "
          f"{r.coefficient_density:.1f} | {model_tally(r.models)} | "
          f"{'→'.join(r.scales) or '—'} | {case_tally(r.cases)} |")
    w("")

    w("## Scenarios")
    w("")
    for r in reports:
        w(f"### {r.name}")
        w("")
        w(f"**Grade {r.grade} — {GRADE_TITLES[r.grade]}** · entry [`{r.entry}`](../{r.entry})")
        w("")
        if r.scope:
            w(f"> {esc(r.scope)}")
            w("")
        w("**Purity**")
        w("")
        w(f"- Status: ledger `{r.ledger_status or '—'}`, companion `{r.declared_status or '—'}`.")
        if r.ledger_residual:
            w(f"- Authored residual still forcing behaviour: {esc(r.ledger_residual)}")
        elif r.limitations and r.grade not in {"A"}:
            w(f"- Declared limitations: {esc(r.limitations)}")
        if r.ledger_note:
            w(f"- Ledger note: {esc(r.ledger_note)}")
        t = r.total
        ops = ", ".join(f"`{op}` {t.inference[op]}" for op in INFERENCE_OPS if t.inference[op])
        w(f"- Inference sites: {t.inference_total}" + (f" ({ops}" + (f"; {t.auto_cascade} auto-seeded `cascade()`" if t.auto_cascade else "") + ")" if ops else "") +
          f" · law-shaped math: {t.law_math} · inference share: {pct(r.inference_share)}")
        w(f"- Embedded coefficients: {t.coefficients} in {t.code_lines} code lines "
          f"({r.coefficient_density:.1f}/100) · top-level literals: {t.toplevel_literals} · "
          f"geometry math: {t.geom_math}")
        w(f"- Geant4 fact reads: {t.g4_reads} · seeded RNG draws: {t.rng} · hooks: {'yes' if r.own.hooks else 'no'}")
        if t.comparison_law_math or t.comparison_functions or r.comparison_modules:
            parts = []
            if t.comparison_law_math:
                parts.append(f"{t.comparison_law_math} law-shaped sites in comparison code")
            if t.comparison_functions:
                names = t.comparison_functions[:8]
                more = f" +{len(t.comparison_functions) - 8}" if len(t.comparison_functions) > 8 else ""
                parts.append("functions " + ", ".join(f"`{n}`" for n in names) + more)
            if r.comparison_modules:
                parts.append("modules " + ", ".join(f"`{m}`" for m in r.comparison_modules))
            w("- Comparison-only (excluded): " + "; ".join(parts))
        if r.inherited.files:
            i = r.inherited
            w(f"- Inherited from modules: {', '.join(f'`{f}`' for f in i.files)} — "
              f"{i.inference_total} inference / {i.law_math} law-shaped / {i.coefficients} coefficients")
        if r.utility_modules or r.data_includes:
            w(f"- Utility/data includes (not counted): {', '.join(f'`{f}`' for f in r.utility_modules + r.data_includes)}")
        if t.runtime_model_paths:
            w(f"- Runtime-supplied model paths: {t.runtime_model_paths} (chosen by parameters at run time; "
              "not graded)")
        if r.scales:
            w(f"- Scale bands reached by declared models: {' → '.join(r.scales)}")
        w("")
        if r.models:
            w("**Models**")
            w("")
            normal = r.normal_models
            if normal:
                w("| Normal-path model | Origin | Scale | Held-out R² (min) | n |")
                w("| --- | --- | --- | --- | --- |")
                for m in normal:
                    r2 = "—" if m.r2_min is None else f"{m.r2_min:.4f}"
                    n = "—" if m.holdout_n is None else str(m.holdout_n)
                    w(f"| [`{m.path}`](../{m.path}) | {m.label} | {m.scale or '—'} | {r2} | {n} |")
                w("")
            teachers = [m for m in r.models if not m.normal_path]
            if teachers:
                dirs = sorted({str(Path(m.path).parent) for m in teachers})
                kinds = sorted({m.label for m in teachers})
                w(f"Comparison/teacher models off the normal path: {len(teachers)} ({', '.join(kinds)}) in "
                  + ", ".join(f"`{d}/`" for d in dirs) + ".")
                w("")
        w("**Performance**")
        w("")
        if r.cases:
            for c in r.cases:
                w(f"- `{c.name}` — **{c.status}**" + (f": {esc(c.summary)}" if c.summary else ""))
        else:
            w("- No case in the committed validation report runs this bundle.")
        for report, lines in r.aux:
            w(f"- [`{report}`](../{report}): " + ("; ".join(lines) if lines else "recorded"))
        if r.validator and r.validator != "tools/validation/trech_validation/cases.py":
            w(f"- Dedicated validator: [`{r.validator}`](../{r.validator})")
        w("")
        if r.flags:
            w("**Review flags**")
            w("")
            for f in r.flags:
                w(f"- ⚠ {f}")
            w("")
    return "\n".join(out).rstrip() + "\n"


def generate() -> str:
    reports, meta = build_reports()
    return render(reports, meta)


# ------------------------------------------------------------ pre-commit

# Staged paths that can change the report: bundle sources, shared JS, models and
# data, JS subprojects, the ledger/validation package, committed validation
# reports and the orchestration scripts that map runs to scenarios.
RELEVANT_PREFIXES = (
    "examples/scenarios/",
    "js/",
    "data/",
    "projects/",
    "tools/validation/",
    "scripts/",
)
RE_RELEVANT_DOC = re.compile(r"^docs/validation_[^/]*\.json$")
DEFAULT_MAX_AGE_DAYS = 30


def is_relevant(path: str) -> bool:
    """Whether a changed repository path may affect the purity report."""
    return path.startswith(RELEVANT_PREFIXES) or bool(RE_RELEVANT_DOC.match(path))


def benchmark_age_days(now: Optional["datetime"] = None) -> Optional[float]:
    """Age of the committed validation report's run, or None if unknown."""
    from datetime import datetime, timezone
    try:
        stamp = json.loads(VALIDATION_REPORT.read_text(encoding="utf-8")).get("generated_at_utc", "")
        when = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (OSError, ValueError, TypeError):
        return None
    now = now or datetime.now(timezone.utc)
    return (now - when).total_seconds() / 86400.0


def _git(*args: str) -> str:
    import subprocess
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True,
                          text=True).stdout


def pre_commit(output: Path, max_age_days: float) -> int:
    """Git pre-commit entry: regenerate and stage the report only when needed.

    Runs when a staged path may affect the report, or when the benchmark data
    it embeds is older than ``max_age_days``. Regeneration cannot refresh the
    benchmarks themselves (that needs a full validation suite run), so an old
    benchmark also prints a non-blocking warning. Never fails the commit.
    """
    import os
    if os.environ.get("TRECH_PURITY_HOOK", "1") == "0":
        return 0
    target = rel(output)
    staged = [p for p in _git("diff", "--cached", "--name-only", "-z").split("\0") if p]
    relevant = sorted(p for p in staged if p != target and is_relevant(p))
    age = benchmark_age_days()
    too_old = age is not None and age > max_age_days
    if not relevant and not too_old:
        return 0
    try:
        text = generate()
    except Exception as exc:  # never block a commit on the report
        print(f"purity hook: report not regenerated ({exc})", file=sys.stderr)
        return 0
    current = output.read_text(encoding="utf-8") if output.exists() else ""
    reason = (f"{len(relevant)} relevant staged path(s)" if relevant else
              f"benchmarks {age:.0f} days old")
    if current != text:
        output.write_text(text, encoding="utf-8")
        _git("add", "--", target)
        print(f"purity hook: regenerated and staged {target} ({reason})")
    if too_old:
        print(f"purity hook: the benchmarks in {rel(VALIDATION_REPORT)} are {age:.0f} days old "
              f"(limit {max_age_days:g}); refresh them with scripts/run_validation_suite.sh",
              file=sys.stderr)
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m trech_validation.purity",
        description="Write docs/TRECH_current_scenarios_purity.md (scenario inference purity + performance).")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true",
                        help="Exit 1 when the committed report differs from a fresh generation.")
    parser.add_argument("--explain", metavar="SCENARIO",
                        help="Print every counted inference/law/coefficient site of one scenario and exit.")
    parser.add_argument("--pre-commit", action="store_true",
                        help="Git hook mode: regenerate and stage only when staged changes are relevant "
                             "or the benchmarks are older than --max-age-days.")
    parser.add_argument("--max-age-days", type=float,
                        default=None, help=f"Benchmark age limit for --pre-commit "
                        f"(default: $TRECH_PURITY_MAX_AGE_DAYS or {DEFAULT_MAX_AGE_DAYS}).")
    args = parser.parse_args(argv)
    if args.pre_commit:
        import os
        limit = args.max_age_days
        if limit is None:
            try:
                limit = float(os.environ.get("TRECH_PURITY_MAX_AGE_DAYS", DEFAULT_MAX_AGE_DAYS))
            except ValueError:
                limit = float(DEFAULT_MAX_AGE_DAYS)
        return pre_commit(args.output, limit)
    if args.explain:
        reports, _ = build_reports()
        match = [r for r in reports if r.name == args.explain]
        if not match:
            print(f"unknown scenario {args.explain!r}", file=sys.stderr)
            return 2
        r = match[0]
        print(f"{r.name}: grade {r.grade}; flags: {r.flags or 'none'}")
        for m in r.models:
            print(f"  model {m.path} [{m.origin}, {'normal' if m.normal_path else 'comparison'}]")
        for f, line, kind, text in r.total.sites:
            print(f"  {kind:<11} {f}:{line}  {text}")
        return 0
    text = generate()
    if args.check:
        current = args.output.read_text(encoding="utf-8") if args.output.exists() else ""
        if current != text:
            print(f"{rel(args.output)} is stale; regenerate with:\n"
                  "  PYTHONPATH=tools/validation python3 -m trech_validation.purity", file=sys.stderr)
            return 1
        print(f"{rel(args.output)} is current")
        return 0
    args.output.write_text(text, encoding="utf-8")
    print(f"wrote {rel(args.output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
