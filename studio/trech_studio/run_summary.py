"""The honest run header: what the engine actually recorded for one run.

Every row here is a straight read of ``trech_provenance.jsonl`` / ``trech_scores.jsonl`` (the
schema in ``docs/output_schema.md``). Studio derives **nothing physical**: the only computed
numbers are the binomial standard error of a fraction the engine already tallied and simple
percentages of counts the engine already emitted, and both are labelled as such.

The two honesty rules this module exists to enforce in the UI:

* a ``predictive``-mode result is **not** a strict Geant4 tally — say so next to the mode;
* an analytic cross-check is a closed-form prediction fed by *Geant4's own* cross sections
  compared against this run's Monte-Carlo tally — a self-consistency check, never an external
  calibration, and the gap is shown rather than hidden.

Pure (no Qt, no engine IO): it consumes an already-parsed ``engine.outputs.RunResult`` and
returns data the panel renders, so it is unit-testable headless.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SummaryRow:
    label: str
    value: str
    note: str = ""          # provenance / honesty label for this row
    warn: bool = False      # render as a caution (out-of-domain, failed tolerance, ...)

    def to_dict(self) -> Dict[str, Any]:
        return {"label": self.label, "value": self.value, "note": self.note, "warn": self.warn}


@dataclass
class SummarySection:
    title: str
    rows: List[SummaryRow] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"title": self.title, "note": self.note, "rows": [r.to_dict() for r in self.rows]}


@dataclass
class RunSummary:
    output_dir: str = ""
    sections: List[SummarySection] = field(default_factory=list)
    caveats: List[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.sections

    def section(self, title: str) -> Optional[SummarySection]:
        for s in self.sections:
            if s.title == title:
                return s
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "output_dir": self.output_dir,
            "sections": [s.to_dict() for s in self.sections],
            "caveats": list(self.caveats),
        }

    def headline(self) -> str:
        det = ""
        events = ""
        seed = ""
        prov = self.section("Determinism & provenance")
        if prov is not None:
            for row in prov.rows:
                if row.label == "determinism mode":
                    det = row.value
                elif row.label == "events":
                    events = row.value
                elif row.label == "seed":
                    seed = row.value
        parts = [p for p in (f"{events} events" if events else "", f"seed {seed}" if seed else "", det) if p]
        return "run · " + " · ".join(parts) if parts else "run · no provenance recorded"


# --- formatting helpers (display only) --------------------------------------------------


def _fmt(value: Any) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def _as_float(value: Any) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _binomial_stderr(p: Any, n: int) -> Optional[float]:
    """Standard error of a proportion the ENGINE tallied over n primaries/events.

    This is the one derived number in the panel; it is a statement about Monte-Carlo sampling
    of the engine's own count, not a physics derivation, and it is labelled where it is shown.
    """
    value = _as_float(p)
    if value is None or n <= 0 or not (0.0 <= value <= 1.0):
        return None
    return math.sqrt(max(0.0, value * (1.0 - value)) / n)


def _fraction_row(label: str, value: Any, events: int, note: str) -> Optional[SummaryRow]:
    v = _as_float(value)
    if v is None:
        return None
    err = _binomial_stderr(v, events)
    text = f"{v:.6g}" + (f" ± {err:.2g}" if err is not None else "")
    suffix = " (± = binomial standard error over the engine's own tally, Studio-computed)"
    return SummaryRow(label, text, note + suffix if err is not None else note)


def build_run_summary(result: Any) -> RunSummary:
    """Build the structured run header from a parsed :class:`engine.outputs.RunResult`."""
    prov = result.run_start_provenance() or {}
    prov_end = _run_end_provenance(result)
    scores = result.run_end_scores() or {}
    summary = result.summary()
    out = RunSummary(output_dir=str(result.output_dir))

    def pick(key: str) -> Any:
        for source in (scores, prov_end, prov):
            if key in source and source[key] is not None:
                return source[key]
        return None

    events = int(_as_float(summary.get("n_events")) or 0)

    # --- 1. determinism & provenance -----------------------------------------------------
    det_mode = summary.get("determinism_mode")
    predictive = summary.get("predictive_mode")
    determinism = SummarySection("Determinism & provenance")
    if det_mode is not None:
        note = (
            "predictive: learned inference is ENABLED — inferred results are not strict "
            "Geant4 tallies"
            if str(det_mode) == "predictive"
            else "strict: byte-reproducible; ctx.predict/cascade/evolve/react/interact return null"
        )
        determinism.rows.append(
            SummaryRow("determinism mode", _fmt(det_mode), note, warn=str(det_mode) == "predictive")
        )
    elif predictive is not None:
        determinism.rows.append(SummaryRow("predictive mode", _fmt(predictive), ""))
    for label, key in (
        ("seed", "seed"),
        ("events", "n_events"),
        ("physics list", "physics_list"),
        ("Geant4 version", "geant4_version"),
        ("RNG engine", "rng_engine"),
        ("config hash", "config_hash"),
    ):
        value = summary.get(key, None)
        if value in (None, ""):
            value = pick(key)
        if value not in (None, ""):
            determinism.rows.append(SummaryRow(label, _fmt(value)))
    registered = pick("hooks_registered")
    if registered:
        determinism.rows.append(SummaryRow("hooks registered", ", ".join(str(h) for h in registered)))
    if determinism.rows:
        out.sections.append(determinism)

    # --- 2. primaries & transport (Geant4 tallies) ---------------------------------------
    transport = SummarySection(
        "Primaries & transport",
        note="Monte-Carlo tallies recorded by Geant4 for this run.",
    )
    for label, key in (
        ("primaries emitted", "primaries_emitted"),
        ("primaries transmitted", "primaries_transmitted"),
        ("primaries uncollided", "primaries_uncollided"),
        ("primaries absorbed", "primaries_absorbed"),
        ("total edep (MeV)", "total_edep_mev"),
        ("primary mean track length (mm)", "primary_mean_track_length_mm"),
        ("optical photon tracks", "optical_photon_tracks"),
        ("optical photon steps", "optical_photon_steps"),
        ("optical photon track length (mm)", "optical_photon_track_length_mm"),
    ):
        value = pick(key)
        if value is not None:
            transport.rows.append(SummaryRow(label, _fmt(value)))
    emitted = int(_as_float(pick("primaries_emitted")) or 0) or events
    for label, key in (
        ("transmitted fraction", "primaries_transmitted_fraction"),
        ("uncollided fraction", "primaries_uncollided_fraction"),
        ("photoelectric-first fraction", "primaries_photoelectric_first_fraction"),
    ):
        row = _fraction_row(label, pick(key), emitted, "")
        if row is not None:
            transport.rows.append(row)
    if transport.rows:
        out.sections.append(transport)

    # --- 3. analytic cross-checks (prediction vs this run's tally) ------------------------
    checks = scores.get("analytic_checks")
    if isinstance(checks, list) and checks:
        analytic = SummarySection(
            "Analytic cross-checks",
            note=(
                "Closed-form prediction fed by Geant4's OWN cross sections vs this run's "
                "measured tally — a self-consistency check, never an external calibration."
            ),
        )
        for check in checks:
            if not isinstance(check, dict):
                continue
            label = str(check.get("label") or check.get("type") or "check")
            if not check.get("available", True):
                analytic.rows.append(
                    SummaryRow(label, "unavailable", str(check.get("note") or ""), warn=True)
                )
                continue
            predicted = _as_float(check.get("classical_predicted"))
            measured = _as_float(check.get("geant4_measured"))
            rel = _as_float(check.get("relative_error"))
            within = check.get("within_tolerance")
            value = (
                f"classical {predicted:.6g} vs Geant4 {measured:.6g}"
                if predicted is not None and measured is not None
                else "—"
            )
            gap = f"Δ {_fmt(check.get('delta'))}"
            if rel is not None:
                gap += f" ({rel:.3%} relative"
                tol = _as_float(check.get("tolerance_rel"))
                gap += f", tolerance {tol:.3%})" if tol is not None else ")"
            note = f"{gap} · measured field {check.get('measured_field') or '?'}"
            analytic.rows.append(SummaryRow(label, value, note, warn=within is False))
        overall = scores.get("analytic_checks_within_tolerance")
        if overall is not None:
            analytic.rows.append(
                SummaryRow("all checks within tolerance", _fmt(overall), warn=overall is False)
            )
        out.sections.append(analytic)

    # --- 4. learned inference (the gap-to-truth counters) --------------------------------
    predict_count = _as_float(pick("hook_predict_count"))
    if predict_count is not None:
        inference = SummarySection(
            "Learned inference",
            note=(
                "Counts every model evaluation: a K-stage cascade is K, and a batched operator "
                "over N elements (or P pairs) is N×K (P×K) — batching hides nothing."
            ),
        )
        inference.rows.append(SummaryRow("inferences run", _fmt(int(predict_count))))
        ood = _as_float(pick("hook_predict_out_of_domain_count"))
        if ood is not None:
            share = (ood / predict_count) if predict_count > 0 else 0.0
            inference.rows.append(
                SummaryRow(
                    "out of trained domain",
                    f"{int(ood)}" + (f" ({share:.2%} of inferences)" if predict_count > 0 else ""),
                    "inputs outside the model's trained hull — an extrapolated, low-confidence "
                    "prediction, not a measured one",
                    warn=ood > 0,
                )
            )
        low_conf = _as_float(pick("stratify_low_confidence_count"))
        if low_conf is not None and low_conf > 0:
            inference.rows.append(
                SummaryRow(
                    "events routed to resim (low confidence)",
                    _fmt(int(low_conf)),
                    "stratify.resimOnLowConfidence acted on the coverage flag",
                    warn=True,
                )
            )
        exceptional = _as_float(pick("stratify_exceptional_count"))
        if exceptional is not None:
            inference.rows.append(
                SummaryRow("events labelled exceptional", _fmt(int(exceptional)),
                           "feature-based stratifier, distinct from the coverage flag")
            )
        out.sections.append(inference)

    # --- 5. hooks & emitted sidebands ----------------------------------------------------
    hooks = SummarySection(
        "Hook sideband",
        note="Scenario emits are hook-layer data (physics for comparison), not Geant4 tallies.",
    )
    for label, key in (
        ("emits recorded", "hook_emit_count"),
        ("emits dropped", "hook_emit_dropped_count"),
        ("override patches applied", "hook_patch_count"),
    ):
        value = pick(key)
        if value is not None:
            hooks.rows.append(
                SummaryRow(label, _fmt(value), warn=bool(key == "hook_emit_dropped_count" and value))
            )
    tag_counts: Dict[str, int] = {}
    for emit in result.emits:
        tag_counts[emit.tag] = tag_counts.get(emit.tag, 0) + 1
    if tag_counts:
        hooks.rows.append(
            SummaryRow(
                "emit tags",
                ", ".join(f"{tag} ×{count}" for tag, count in sorted(tag_counts.items())),
            )
        )
    if hooks.rows:
        out.sections.append(hooks)

    # --- caveats -------------------------------------------------------------------------
    if str(det_mode) == "predictive":
        out.caveats.append(
            "This run had inference enabled: any cascade/operator result is a learned "
            "prediction carrying its own trained domain, not a Geant4 measurement."
        )
    if not result.provenance:
        out.caveats.append(
            "No trech_provenance.jsonl in this output directory — determinism and seed "
            "cannot be shown."
        )
    if not result.scores:
        out.caveats.append("No trech_scores.jsonl in this output directory — no run tallies.")
    out.caveats.append(
        "Every value above is read from the engine's own provenance/scores; Studio computes "
        "only the labelled sampling error and percentages."
    )
    return out


def _run_end_provenance(result: Any) -> Dict[str, Any]:
    for rec in reversed(result.provenance):
        if rec.get("phase") == "run_end":
            return rec
    return {}
