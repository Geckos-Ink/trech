"""Declarative scenario checks owned by each bundle's ``<name>.validation.js``.

A validation companion registers ``TRECH_VALIDATIONS[name]`` with schema
``trech_scenario_validation_v1``. ``checks`` hold the output-integrity contract
(completed run, positive events, no dropped emits). Optional ``family_case`` +
``family_checks`` export a suite family gate as data: the suite case named by
``family_case`` takes its pass/fail verdict from these checks, so the tolerance
lives beside the scenario instead of only inside Python.

Each check selects one record and reads one field from it:

``file``    run-relative JSONL path. Default: ``trech_hook_emits.jsonl`` when
            ``tag`` is given, otherwise ``trech_scores.jsonl``.
``phase``   keep rows whose ``phase`` equals this value.
``tag``     keep hook emits with this ``tag`` and read inside their ``payload``.
``field``   dotted path; ``name[key=value]`` selects the first list element with a
            matching key and ``name[2]`` an index. ``name[*]`` projects over every
            element and ``name[?key=value]`` over every matching element; the rest
            of the path is then read from each projected element.
``aggregate`` reduces a projected (or list-valued) field to one value:
            ``count``, ``min``, ``max``, ``max_abs``, ``sum``, ``mean`` (finite
            numbers only) or ``all``/``any`` (booleans only). A projection must be
            aggregated. Every reduction except ``count`` fails (``None``) on an
            empty projection, an element lacking the field or a wrongly typed
            element -- a vacuous ``all`` never passes.
``derive``  computes one statistic from the selected element (or from each
            projected element, before ``aggregate``): ``{"fn": name, "args": [...]}``
            where each argument is a path relative to that element or a nested
            ``derive`` object. Functions: ``abs(x)``, ``difference(a, b)`` = a - b,
            ``ratio(a, b)`` (b != 0), ``list_sum(list)``, ``list_length(list)`` and
            ``chi2_sf(chi2, dof)`` (the chi-square survival probability, dof a
            positive integer). Any absent, non-finite or wrongly typed argument
            makes the derived value undefined, which fails the check.

The last matching row is used (the runtime appends records in run order).
Comparisons use ``expected`` or a second operand ``reference`` (a selector
with the same keys), optionally multiplied by ``scale``:

``eq ne gt ge lt le`` -- ordinary comparisons (booleans compare only to booleans).
``within``           -- ``|value - expected| <= abs_tol`` or
                        ``<= rel_tol * max(|value|, |expected|)``.

Absent files or rows never pass; an absent field on a selected row passes only
through an explicit ``missing`` substitute.
Checks grade recorded state; they never advance or alter it.
"""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

SCHEMA = "trech_scenario_validation_v1"
OPERATIONS = frozenset({"eq", "ne", "gt", "ge", "lt", "le", "within"})
AGGREGATES = frozenset({"count", "min", "max", "max_abs", "sum", "mean", "all", "any"})
DERIVATIONS = {"abs": 1, "difference": 2, "ratio": 2, "list_sum": 1, "list_length": 1, "chi2_sf": 2}
_SEGMENT = re.compile(r"^([^\[\]]*)((?:\[[^\[\]]+\])*)$")
_ABSENT = object()   # the selected row lacks the field
_NO_ROW = object()   # no row matched the selector


def chi2_sf(x: float, dof: int) -> float:
    """Chi-square survival function P(X >= x) for `dof` degrees of freedom.

    The regularized upper incomplete gamma Q(dof/2, x/2), by series below
    a + 1 and a Lentz continued fraction above (Numerical Recipes gammq), so
    validators need no SciPy.
    """
    if dof <= 0:
        return 1.0
    if x <= 0.0:
        return 1.0
    a = 0.5 * dof
    t = 0.5 * x
    gln = math.lgamma(a)
    if t < a + 1.0:
        term = 1.0 / a
        total = term
        ap = a
        for _ in range(1000):
            ap += 1.0
            term *= t / ap
            total += term
            if abs(term) < abs(total) * 1e-15:
                break
        return max(0.0, 1.0 - total * math.exp(-t + a * math.log(t) - gln))
    tiny = 1e-300
    b = t + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / b
    h = d
    for i in range(1, 1000):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        d = tiny if abs(d) < tiny else d
        c = b + an / c
        c = tiny if abs(c) < tiny else c
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-15:
            break
    return min(1.0, math.exp(-t + a * math.log(t) - gln) * h)


class Projection(list):
    """Values gathered by ``[*]`` / ``[?key=value]``; may contain ``_ABSENT``."""


def _rows(path: Path) -> List[Dict[str, Any]]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _step(value: Any, name: str, selectors: List[str]) -> Any:
    if name:
        if not isinstance(value, dict) or name not in value:
            return _ABSENT
        value = value[name]
    for selector in selectors:
        if not isinstance(value, list):
            return _ABSENT
        if "=" in selector:
            key, wanted = selector.split("=", 1)
            value = next((item for item in value if isinstance(item, dict)
                          and str(item.get(key)) == wanted), _ABSENT)
        else:
            index = int(selector)
            value = value[index] if -len(value) <= index < len(value) else _ABSENT
        if value is _ABSENT:
            return _ABSENT
    return value


def resolve_path(value: Any, path: str) -> Any:
    """Follow a dotted path with optional ``[key=value]`` / ``[index]`` selectors.

    A ``[*]`` or ``[?key=value]`` selector returns a :class:`Projection` holding the
    remaining path read from each projected element (``_ABSENT`` where it is missing).
    """
    if path == "":
        return value
    segments = path.split(".")
    for position, segment in enumerate(segments):
        match = _SEGMENT.match(segment)
        if match is None:
            raise ValueError(f"malformed field path segment {segment!r}")
        name, selectors = match.group(1), re.findall(r"\[([^\[\]]+)\]", match.group(2))
        projector = next((i for i, sel in enumerate(selectors) if sel == "*" or sel.startswith("?")), None)
        if projector is None:
            value = _step(value, name, selectors)
            if value is _ABSENT:
                return _ABSENT
            continue
        items = _step(value, name, selectors[:projector])
        if not isinstance(items, list):
            return _ABSENT
        wanted = selectors[projector]
        if wanted != "*":
            if "=" not in wanted:
                raise ValueError(f"malformed filter selector [{wanted}]")
            key, expected = wanted[1:].split("=", 1)
            items = [item for item in items if isinstance(item, dict) and str(item.get(key)) == expected]
        rest = "".join(f"[{sel}]" for sel in selectors[projector + 1:])
        tail = ".".join(([rest] if rest else []) + segments[position + 1:])
        if any(sel == "*" or sel.startswith("?") for sel in selectors[projector + 1:]) or \
                any(("[*]" in seg or "[?" in seg) for seg in segments[position + 1:]):
            raise ValueError("a field path may contain only one projection")
        return Projection(resolve_path(item, tail) if tail else item for item in items)
    return value


def aggregate(values: Any, how: str) -> Any:
    """Reduce a projection or list; ``None`` whenever the reduction is undefined."""
    if how not in AGGREGATES:
        raise ValueError(f"Unsupported validation aggregate: {how}")
    if not isinstance(values, list):
        return None
    if how == "count":
        return len(values)
    if not values or any(v is _ABSENT for v in values):
        return None
    if how in ("all", "any"):
        if not all(isinstance(v, bool) for v in values):
            return None
        return all(values) if how == "all" else any(values)
    numbers = [_number(v) for v in values]
    if any(n is None for n in numbers):
        return None
    if how == "min":
        return min(numbers)
    if how == "max":
        return max(numbers)
    if how == "max_abs":
        return max(abs(n) for n in numbers)
    total = math.fsum(numbers)
    return total if how == "sum" else total / len(numbers)


def _check_derive(spec: Any) -> None:
    if not isinstance(spec, dict) or spec.get("fn") not in DERIVATIONS:
        raise ValueError(f"unsupported derive specification {spec!r}")
    args = spec.get("args")
    if not isinstance(args, list) or len(args) != DERIVATIONS[spec["fn"]]:
        raise ValueError(f"derive {spec['fn']} takes {DERIVATIONS[spec['fn']]} argument(s)")
    for arg in args:
        if isinstance(arg, dict):
            _check_derive(arg)
        elif not isinstance(arg, str):
            raise ValueError(f"derive argument must be a path or derive object, not {arg!r}")


def derive(element: Any, spec: Dict[str, Any]) -> Any:
    """Evaluate ``spec`` against one element; ``None`` when undefined."""
    _check_derive(spec)
    values = []
    for arg in spec["args"]:
        value = derive(element, arg) if isinstance(arg, dict) else resolve_path(element, arg)
        if value is _ABSENT or value is None or isinstance(value, Projection):
            return None
        values.append(value)
    fn = spec["fn"]
    if fn in ("list_sum", "list_length"):
        items = values[0]
        if not isinstance(items, list):
            return None
        if fn == "list_length":
            return len(items)
        numbers = [_number(v) for v in items]
        return None if any(n is None for n in numbers) else math.fsum(numbers)
    numbers = [_number(v) for v in values]
    if any(n is None for n in numbers):
        return None
    if fn == "abs":
        return abs(numbers[0])
    if fn == "difference":
        return numbers[0] - numbers[1]
    if fn == "ratio":
        return None if numbers[1] == 0.0 else numbers[0] / numbers[1]
    chi2, dof = numbers
    if dof <= 0 or dof != int(dof) or chi2 < 0.0:
        return None
    return chi2_sf(chi2, int(dof))


def _relative_file(selector: Dict[str, Any]) -> Path:
    default = "trech_hook_emits.jsonl" if "tag" in selector else "trech_scores.jsonl"
    relative = Path(selector.get("file", default))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("validation file must be relative to the run directory")
    return relative


def select(selector: Dict[str, Any], output: Path, cache: Optional[Dict[Path, list]] = None) -> Any:
    """Return the selected field value, ``_ABSENT`` or ``_NO_ROW``."""
    target = output / _relative_file(selector)
    if cache is not None and target in cache:
        rows = cache[target]
    else:
        rows = _rows(target)
        if cache is not None:
            cache[target] = rows
    if "phase" in selector:
        rows = [row for row in rows if row.get("phase") == selector["phase"]]
    if "tag" in selector:
        rows = [row.get("payload") for row in rows
                if row.get("tag") == selector["tag"] and isinstance(row.get("payload"), dict)]
    if not rows:
        return _NO_ROW
    if "field" not in selector:
        raise ValueError("validation check requires a field")
    value = resolve_path(rows[-1], selector["field"])
    if "derive" in selector and value is not _ABSENT:
        if isinstance(value, Projection):
            value = Projection(_ABSENT if item is _ABSENT else derive(item, selector["derive"])
                               for item in value)
        else:
            value = derive(value, selector["derive"])
    if "aggregate" in selector:
        return _ABSENT if value is _ABSENT else aggregate(value, selector["aggregate"])
    if isinstance(value, Projection):
        raise ValueError(f"field {selector['field']!r} projects a list; declare an aggregate")
    return value


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def compare(value: Any, op: str, expected: Any, check: Dict[str, Any]) -> bool:
    if op not in OPERATIONS:
        raise ValueError(f"Unsupported validation operation: {op}")
    if value is None or expected is None:
        return False
    if isinstance(expected, bool) or isinstance(value, bool):
        if not (isinstance(expected, bool) and isinstance(value, bool)):
            return False
        if op == "eq":
            return value is expected
        if op == "ne":
            return value is not expected
        raise ValueError(f"operation {op} is not defined for booleans")
    if op in ("eq", "ne") and not isinstance(expected, (int, float)):
        return (value == expected) == (op == "eq")
    a, b = _number(value), _number(expected)
    if a is None or b is None:
        return False
    if op == "eq":
        return a == b
    if op == "ne":
        return a != b
    if op == "gt":
        return a > b
    if op == "ge":
        return a >= b
    if op == "lt":
        return a < b
    if op == "le":
        return a <= b
    abs_tol = float(check.get("abs_tol", 0.0))
    rel_tol = float(check.get("rel_tol", 0.0))
    if abs_tol <= 0.0 and rel_tol <= 0.0:
        raise ValueError("within requires a positive abs_tol or rel_tol")
    diff = abs(a - b)
    return diff <= abs_tol or (rel_tol > 0.0 and diff <= rel_tol * max(abs(a), abs(b)))


def evaluate_check(name: str, check: Dict[str, Any], output: Path,
                   cache: Optional[Dict[Path, list]] = None) -> Dict[str, Any]:
    op = check.get("op")
    if op not in OPERATIONS:
        raise ValueError(f"Unsupported validation operation: {op}")
    for selector in (check, check.get("reference") or {}):
        if "aggregate" in selector and selector["aggregate"] not in AGGREGATES:
            raise ValueError(f"{name}: unsupported validation aggregate {selector['aggregate']!r}")
        if "derive" in selector:
            _check_derive(selector["derive"])
    value = select(check, output, cache)
    # ``missing`` covers an absent field on a recorded row, never an absent row.
    value = check.get("missing") if value is _ABSENT else (None if value is _NO_ROW else value)
    if "reference" in check:
        if "expected" in check:
            raise ValueError(f"{name}: a check uses either expected or reference, not both")
        expected = select(check["reference"], output, cache)
        expected = None if expected is _ABSENT or expected is _NO_ROW else expected
    else:
        if "expected" not in check:
            raise ValueError(f"{name}: validation check requires expected or reference")
        expected = check["expected"]
    if "scale" in check:
        factor = _number(check["scale"])
        number = _number(expected)
        if factor is None:
            raise ValueError(f"{name}: scale must be a finite number")
        expected = None if number is None else number * factor
    record = {"scenario": name, "field": check["field"], "actual": value,
              "op": op, "expected": expected, "passed": compare(value, op, expected, check)}
    if "derive" in check:
        record["derive"] = check["derive"]["fn"]
    for key in ("id", "tag", "phase", "aggregate"):
        if key in check:
            record[key] = check[key]
    return record


def _contracts(contracts: Dict[str, Any]) -> Iterable[Tuple[str, Dict[str, Any]]]:
    for name, contract in contracts.items():
        if not isinstance(contract, dict) or contract.get("schema") != SCHEMA:
            raise ValueError(f"{name}: unsupported validation schema")
        yield name, contract


def evaluate_contracts(contracts: Dict[str, Any], output: Path, *,
                       include_family: bool = True) -> List[Dict[str, Any]]:
    """Evaluate every output check, then every exported family check."""
    cache: Dict[Path, list] = {}
    results = []
    for name, contract in _contracts(contracts):
        for check in contract.get("checks", []):
            results.append(evaluate_check(name, check, output, cache))
        if include_family:
            for check in contract.get("family_checks", []):
                record = evaluate_check(name, check, output, cache)
                record["family_case"] = contract.get("family_case")
                results.append(record)
    return results


def family_contract(contracts: Dict[str, Any], case_name: str) -> Optional[Tuple[str, Dict[str, Any]]]:
    for name, contract in _contracts(contracts):
        if contract.get("family_case") == case_name:
            return name, contract
    return None


def evaluate_family(contracts: Dict[str, Any], case_name: str, output: Path) -> List[Dict[str, Any]]:
    """Evaluate only the family gate exported for ``case_name``."""
    found = family_contract(contracts, case_name)
    if found is None:
        raise ValueError(f"no validation companion exports family case {case_name}")
    name, contract = found
    checks = contract.get("family_checks") or []
    if not checks:
        raise ValueError(f"{name}: family case {case_name} declares no family_checks")
    cache: Dict[Path, list] = {}
    return [evaluate_check(name, check, output, cache) for check in checks]


def locate_trech(runs_dir: Optional[Path] = None) -> Optional[Path]:
    """``TRECH_BIN``, then the suite convention ``RUNS_DIR/trech``."""
    configured = os.environ.get("TRECH_BIN")
    candidates = [Path(configured)] if configured else []
    if runs_dir is not None:
        candidates.append(Path(runs_dir) / "trech")
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate.resolve()
    return None


@lru_cache(maxsize=None)
def _inspect_declarations(trech: str, scenario: str) -> str:
    output = subprocess.run([trech, "inspect", scenario], check=True, text=True,
                            capture_output=True).stdout
    return json.dumps(json.loads(output).get("authoring", {}).get("validation", {}))


def load_declarations(scenario: Path, trech: Path) -> Dict[str, Any]:
    """Read ``authoring.validation`` through the engine's own JS loader."""
    return json.loads(_inspect_declarations(str(Path(trech).resolve()), str(Path(scenario).resolve())))
