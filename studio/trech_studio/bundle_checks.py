"""Grade a loaded run against the checks its scenario bundle declares.

A scenario's ``<name>.validation.js`` companion (schema
``trech_scenario_validation_v1``) declares output-integrity ``checks`` and,
optionally, an exported suite family gate (``family_case`` + ``family_checks``)
and multi-run ``family_sweeps``. Studio shows how the *recorded* outputs of the
loaded run fare against them:

* the scenario is the one the run's provenance ``cli_args`` names, found on disk
  (absolute, or relative to the repository or an ancestor of the output folder);
* its declarations are read through the engine's own loader (``trech inspect``
  with the recorded ``--param`` values), never parsed by Studio;
* grading uses the validation suite's shared evaluator
  (``tools/validation/trech_validation/declarative.py``), loaded from the
  installed ``trech_validation`` package or the repository checkout. Studio has
  no second copy of the rules, so the verdict here equals the suite's.

Nothing is re-run and nothing physical is derived. Declarations come from the
current source on disk, which may differ from the source the run was made with;
sweep gates span several runs and are listed, not graded, for a single run. A
passing check only says the recorded value met the declared tolerance.

Pure (no Qt): the engine inspection is passed in as a callable so this module is
unit-testable headless.
"""
from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Dict, List, Optional, Sequence

from .run_summary import SummaryRow, SummarySection

SECTION_TITLE = "Bundle validation checks"
_EVALUATOR_NAME = "_trech_studio_declarative"

Inspect = Callable[[Path, List[str]], Dict[str, Any]]


@dataclass
class BundleCheckReport:
    status: str                      # "graded" | "unavailable"
    reason: str = ""
    scenario: Optional[Path] = None
    records: List[Dict[str, Any]] = field(default_factory=list)
    sweeps: List[str] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for record in self.records if record.get("passed") is True)

    @property
    def failed(self) -> int:
        return len(self.records) - self.passed


def _run_provenance(result: Any) -> Dict[str, Any]:
    for record in reversed(getattr(result, "provenance", None) or []):
        if isinstance(record, dict) and isinstance(record.get("cli_args"), list):
            return record
    return {}


def recorded_invocation(result: Any) -> Optional[tuple]:
    """``(scenario argument, [--param, k=v, ...])`` from the run's provenance."""
    args = _run_provenance(result).get("cli_args")
    if not isinstance(args, list) or len(args) < 3 or args[1] != "run" or not isinstance(args[2], str):
        return None
    params: List[str] = []
    for index, arg in enumerate(args):
        if arg == "--param" and index + 1 < len(args) and isinstance(args[index + 1], str):
            params += ["--param", args[index + 1]]
        elif isinstance(arg, str) and arg.startswith("--param="):
            params += ["--param", arg[len("--param="):]]
    return args[2], params


def resolve_scenario(argument: str, output_dir: Path, roots: Sequence[Path] = ()) -> Optional[Path]:
    """Find the recorded scenario path on disk; ``None`` rather than a guess."""
    candidate = Path(argument)
    if candidate.is_absolute():
        return candidate if candidate.is_file() else None
    bases = list(roots) + list(Path(output_dir).resolve().parents)
    for base in bases:
        path = Path(base) / candidate
        if path.is_file():
            return path.resolve()
    return None


def load_evaluator(repo_root: Optional[Path]) -> Optional[ModuleType]:
    """The suite's declarative evaluator: installed package, else the repository copy."""
    try:
        from trech_validation import declarative  # type: ignore
        return declarative
    except ImportError:
        pass
    if repo_root is None:
        return None
    source = Path(repo_root) / "tools" / "validation" / "trech_validation" / "declarative.py"
    if not source.is_file():
        return None
    spec = importlib.util.spec_from_file_location(_EVALUATOR_NAME, source)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:  # a broken checkout must read as unavailable, not crash the viewer
        return None
    return module


def grade_run(result: Any, inspect: Optional[Inspect], repo_root: Optional[Path],
              evaluator: Optional[ModuleType] = None) -> BundleCheckReport:
    if inspect is None:
        return BundleCheckReport("unavailable", "engine unavailable: declarations are read through trech inspect")
    invocation = recorded_invocation(result)
    if invocation is None:
        return BundleCheckReport("unavailable", "run provenance records no `trech run <scenario>` invocation")
    roots = [Path(repo_root)] if repo_root is not None else []
    scenario = resolve_scenario(invocation[0], Path(result.output_dir), roots)
    if scenario is None:
        return BundleCheckReport("unavailable", f"recorded scenario {invocation[0]} was not found on disk")
    try:
        contracts = inspect(scenario, invocation[1])
    except Exception as exc:  # inspection failures are shown, never hidden
        return BundleCheckReport("unavailable", f"inspection failed: {exc}", scenario)
    if not isinstance(contracts, dict) or not contracts:
        return BundleCheckReport("unavailable", "the scenario declares no validation companion", scenario)
    evaluator = evaluator or load_evaluator(repo_root)
    if evaluator is None:
        return BundleCheckReport("unavailable", "validation evaluator (trech_validation) not available", scenario)
    try:
        records = evaluator.evaluate_contracts(contracts, Path(result.output_dir))
    except (ValueError, OSError) as exc:
        return BundleCheckReport("unavailable", f"declarations could not be graded: {exc}", scenario)
    sweeps = [sweep.get("family_case", "?") for contract in contracts.values() if isinstance(contract, dict)
              for sweep in contract.get("family_sweeps") or [] if isinstance(sweep, dict)]
    return BundleCheckReport("graded", "", scenario, records, sweeps)


def _value(value: Any) -> str:
    if value is None:
        return "absent"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def bundle_check_section(report: BundleCheckReport) -> SummarySection:
    if report.status != "graded":
        return SummarySection(SECTION_TITLE, [SummaryRow("status", "not graded", report.reason, warn=True)],
                              note="Read-only: checks are graded against recorded outputs only.")
    rows = [SummaryRow("verdict", f"{report.passed}/{len(report.records)} declared checks pass",
                       f"declared in {report.scenario.with_name(report.scenario.stem + '.validation.js').name}",
                       warn=report.failed > 0)]
    for record in report.records:
        scope = record.get("family_case") or "output"
        label = f"{scope} · {record.get('id') or record.get('field')}"
        reduction = "".join(f" [{record[key]}]" for key in ("derive", "aggregate") if key in record)
        detail = (f"{record.get('field')}{reduction} = {_value(record.get('actual'))} "
                  f"{record.get('op')} {_value(record.get('expected'))}")
        rows.append(SummaryRow(label, "pass" if record.get("passed") is True else "FAIL", detail,
                               warn=record.get("passed") is not True))
    for case in report.sweeps:
        rows.append(SummaryRow(f"sweep · {case}", "not graded",
                               "multi-run gate: grade it with validate_scenario.py --sweep over its sibling runs"))
    note = ("Recorded outputs graded against the bundle's declared checks through the validation suite's "
            "own evaluator. Declarations come from the current source on disk (it may have changed since "
            "the run); nothing is re-run, and a pass means only that the recorded value met the declared "
            "tolerance.")
    return SummarySection(SECTION_TITLE, rows, note)
