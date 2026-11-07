"""Spectrum-prediction workspace model, built from a run's hook emits (pure: no Qt, no numpy).

The `spectrum_prediction` scenario emits one ``spectrum_prediction`` record per target, a
``spectrum_summary`` and, in Studio mode, a ``spectrum_model_report`` leaderboard plus an
optional ``spectrum_geant4_context``. Studio shows exactly those engine-emitted numbers: it never
evaluates a model, recomputes a metric or fills a missing prediction. A null prediction (strict
mode, missing atomic stage) stays null and is reported in words.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

INPUT_SCHEMA = "trech_spectrum_inputs_v1"
EXTENSION = "spectrum_prediction"
TAGS = ("spectrum_prediction", "spectrum_summary", "spectrum_model_report", "spectrum_geant4_context")


def _finite_list(values: Any, length: int, name: str) -> Optional[Tuple[float, ...]]:
    if values is None:
        return None
    if not isinstance(values, list) or len(values) != length:
        raise ValueError(f"{name} must list {length} values")
    out = tuple(float(v) for v in values)
    if not all(math.isfinite(v) for v in out):
        raise ValueError(f"{name} contains non-finite values")
    return out


@dataclass(frozen=True)
class StageTrust:
    model: str
    element: Optional[str]
    in_domain: Optional[bool]
    out_of_domain_inputs: Tuple[str, ...]
    starved_inputs: Tuple[str, ...]
    joint_starved: Optional[bool]
    joint_measured: Optional[bool]
    holdout_r2: Optional[float]
    holdout_samples: Optional[int]

    @property
    def badges(self) -> Tuple[str, ...]:
        """Engine-set flags only; an unchecked joint test is stated, never shown as clean."""
        out: List[str] = []
        if self.in_domain is False:
            out.append("EXTRAPOLATING")
        if self.starved_inputs:
            out.append("STARVED REGION")
        if self.joint_measured is False:
            out.append("JOINT NOT CHECKED")
        elif self.joint_starved:
            out.append("STARVED REGION (JOINT)")
        if self.holdout_r2 is None:
            out.append("NO MEASURED ACCURACY")
        return tuple(out)


@dataclass(frozen=True)
class SpectrumRecord:
    kind: str
    id: str
    label: str
    split: str
    unit: str
    centers: Tuple[float, ...]
    measured: Tuple[float, ...]
    predicted: Optional[Tuple[float, ...]]
    inference: str
    metrics: Optional[Dict[str, Any]]
    stages: Tuple[StageTrust, ...]
    measured_bands: Tuple[Dict[str, Any], ...]
    sources: Dict[str, Any]
    display: Dict[str, Any]
    honesty: str
    payload: Dict[str, Any] = field(repr=False, compare=False, default_factory=dict)

    @property
    def held_out(self) -> bool:
        return self.split == "test"

    def summary_line(self) -> str:
        m = self.metrics or {}
        split = {"test": "held-out", "train": "training member"}.get(self.split, self.split)
        if self.predicted is None:
            return f"{self.label} · {split} · no prediction ({self.inference})"
        return f"{self.label} · {split} · RMSE {m.get('rmse', float('nan')):.3f} · cos {m.get('cosine', float('nan')):.3f}"


@dataclass(frozen=True)
class LeaderboardRow:
    name: str
    task: str
    family: str
    cv_rmse: Optional[float]
    cv_rmse_std: Optional[float]
    family_cv_rmse: Optional[float]
    test_rmse: Optional[float]
    test_r2: Optional[float]
    test_cosine: Optional[float]
    test_peak_error_nm: Optional[float]
    exported: Optional[str]
    note: str


@dataclass(frozen=True)
class SpectrumWorkspace:
    records: Tuple[SpectrumRecord, ...]
    summary: Optional[Dict[str, Any]]
    leaderboard: Tuple[LeaderboardRow, ...]
    ablation: Tuple[Dict[str, Any], ...]
    report: Optional[Dict[str, Any]]
    geant4_context: Optional[Dict[str, Any]]

    @property
    def is_empty(self) -> bool:
        return not self.records

    def header(self) -> str:
        if self.is_empty:
            return "No spectrum_prediction records in this run."
        held = sum(1 for r in self.records if r.held_out)
        predicted = sum(1 for r in self.records if r.predicted is not None)
        honesty = self.records[0].honesty
        return (f"{len(self.records)} target(s), {predicted} predicted, {held} held-out. {honesty}")


def _stat(block: Any, key: str = "mean") -> Optional[float]:
    if isinstance(block, dict):
        value = block.get(key)
        return float(value) if isinstance(value, (int, float)) else None
    return float(block) if isinstance(block, (int, float)) else None


def _stage(raw: Dict[str, Any]) -> StageTrust:
    r2 = raw.get("holdoutR2")
    return StageTrust(model=str(raw.get("model", "")), element=raw.get("element"),
                      in_domain=raw.get("inDomain"), out_of_domain_inputs=tuple(raw.get("outOfDomainInputs") or ()),
                      starved_inputs=tuple(raw.get("starvedInputs") or ()), joint_starved=raw.get("jointStarved"),
                      joint_measured=raw.get("jointMeasured"),
                      holdout_r2=float(r2) if isinstance(r2, (int, float)) else None,
                      holdout_samples=raw.get("holdoutSamples"))


def record_from_payload(payload: Dict[str, Any]) -> SpectrumRecord:
    grid = payload.get("grid") or {}
    centers = tuple(float(c) for c in grid.get("centers") or ())
    if not centers:
        raise ValueError("spectrum_prediction record has no grid centers")
    measured = _finite_list(payload.get("measured"), len(centers), "measured")
    predicted = _finite_list(payload.get("predicted"), len(centers), "predicted")
    honesty = (payload.get("honesty") or {}).get("statement") or "Learned prediction; not a Geant4 result."
    return SpectrumRecord(kind=str(payload.get("kind")), id=str(payload.get("id")), label=str(payload.get("label")),
                          split=str(payload.get("split", "unknown")), unit=str(grid.get("unit", "nm")),
                          centers=centers, measured=measured, predicted=predicted,
                          inference=str(payload.get("inference", "unknown")), metrics=payload.get("metrics"),
                          stages=tuple(_stage(s) for s in payload.get("stages") or ()),
                          measured_bands=tuple(payload.get("measured_bands") or ()),
                          sources=dict(payload.get("sources") or {}), display=dict(payload.get("display") or {}),
                          honesty=honesty, payload=payload)


def _leaderboard(report: Dict[str, Any]) -> Tuple[LeaderboardRow, ...]:
    rows = []
    order = {name: i for task in ("atomic", "molecular") for i, name in enumerate((report.get("ranking") or {}).get(task, []))}
    for a in report.get("architectures") or ():
        test = a.get("test") or {}
        rows.append(LeaderboardRow(name=a["name"], task=a["task"], family=a["family"],
                                   cv_rmse=_stat(a.get("cv_rmse")), cv_rmse_std=_stat(a.get("cv_rmse"), "std"),
                                   family_cv_rmse=_stat(a.get("family_cv_rmse")), test_rmse=_stat(test.get("rmse")),
                                   test_r2=_stat(test.get("r2")), test_cosine=_stat(test.get("cosine")),
                                   test_peak_error_nm=_stat(test.get("peak_error_nm")), exported=a.get("exported"),
                                   note=str(a.get("note", ""))))
    rows.sort(key=lambda r: (r.task, order.get(r.name, 1 << 30), r.name))
    return tuple(rows)


def build_spectrum_workspace(emits: Iterable[Any]) -> SpectrumWorkspace:
    """Collect spectrum records from duck-typed emits exposing ``.tag``/``.payload``."""
    records: List[SpectrumRecord] = []
    summary = report = context = None
    for emit in emits:
        tag, payload = getattr(emit, "tag", None), getattr(emit, "payload", None)
        if tag not in TAGS or not isinstance(payload, dict):
            continue
        if tag == "spectrum_prediction":
            records.append(record_from_payload(payload))
        elif tag == "spectrum_summary":
            summary = payload
        elif tag == "spectrum_model_report":
            report = payload
        else:
            context = payload
    return SpectrumWorkspace(records=tuple(records), summary=summary,
                             leaderboard=_leaderboard(report) if report else (),
                             ablation=tuple((report or {}).get("ablation") or ()), report=report,
                             geant4_context=context)


def is_spectrum_mode(config: Dict[str, Any], studio: Dict[str, Any]) -> bool:
    """The Studio extension is active when the scenario declares it (its studio_mode switch)."""
    inputs = (config.get("hooks") or {}).get("inputs") or {}
    return inputs.get("schema") == INPUT_SCHEMA or EXTENSION in (studio.get("extensions") or ())


def plot_bounds(record: SpectrumRecord) -> Tuple[float, float, float, float]:
    """Axis extents for display: data range plus a small margin (a rendering choice)."""
    values = list(record.measured) + list(record.predicted or ())
    top = max(values) if values else 1.0
    return record.centers[0], record.centers[-1], 0.0, max(top * 1.08, 1e-6)


def format_stage(stage: StageTrust) -> str:
    where = f"{stage.model}" + (f" [{stage.element}]" if stage.element else "")
    r2 = "held-out R² unmeasured" if stage.holdout_r2 is None else f"held-out worst-bin R² {stage.holdout_r2:.2f} (n={stage.holdout_samples})"
    badges = ", ".join(stage.badges) or "in trained domain"
    extra = f"; out-of-domain inputs: {', '.join(stage.out_of_domain_inputs)}" if stage.out_of_domain_inputs else ""
    return f"{where}: {badges}; {r2}{extra}"


def records_for(workspace: SpectrumWorkspace, kind: Optional[str] = None) -> Sequence[SpectrumRecord]:
    return [r for r in workspace.records if kind is None or r.kind == kind]
