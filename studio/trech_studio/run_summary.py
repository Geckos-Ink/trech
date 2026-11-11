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
from typing import Any, Dict, List, Optional, Tuple


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


# Engine species classes of the per-event secondary split, in score-key spelling, with
# display labels (include/trech/sim/SecondarySpecies.hpp owns the classes).
_SECONDARY_SPECIES = (
    ("gamma", "gamma secondaries"),
    ("electron", "electron secondaries"),
    ("positron", "positron secondaries"),
    ("optical_photon", "optical-photon secondaries"),
    ("neutron", "neutron secondaries"),
    ("other", "other secondaries (hadrons, ions, …)"),
)


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


def _histogram_section(title: str, hist: Any, edges_key: str, unit: str, note: str,
                       integer_bins: bool,
                       zero_note: str = "events that deposited nothing"
                       ) -> Optional[SummarySection]:
    """Engine histogram rows, one per populated bin plus the engine's special slots.

    Counts and edges are copied from the engine record; the only Studio arithmetic is each
    count's share of the listed total, and the bar is a drawing of that share.
    """
    if not isinstance(hist, dict):
        return None
    counts = hist.get("counts")
    edges = hist.get(edges_key)
    if not isinstance(counts, list) or not isinstance(edges, list):
        return None
    if counts and len(edges) != len(counts) + 1:
        section = SummarySection(title, note=note)
        section.rows.append(SummaryRow(
            "histogram", "malformed", "edge count does not match bin count; not drawn",
            warn=True))
        return section
    special = [("exactly zero", hist.get("zero_count"), zero_note),
               ("below lowest bin", hist.get("underflow_count"), ""),
               ("above highest bin", hist.get("overflow_count"), "")]
    total = sum(int(c) for c in counts) + sum(int(v) for _, v, _ in special if v is not None)
    peak = max([int(c) for c in counts] + [0])
    section = SummarySection(title, note=note)

    def share(count: int) -> str:
        return f"{count / total * 100:.3g}% of events" if total > 0 else ""

    for label, value, why in special[:1]:
        if value is not None:
            section.rows.append(SummaryRow(label, _fmt(value), "; ".join(
                part for part in (share(int(value)), why) if part)))
    for i, raw in enumerate(counts):
        count = int(raw)
        lo, hi = edges[i], edges[i + 1]
        if integer_bins:
            label = str(lo) if hi - lo == 1 else f"{lo}–{hi - 1}"
        else:
            label = f"[{_fmt(float(lo))}, {_fmt(float(hi))}) {unit}"
        bar = "█" * (round(count / peak * 20) if peak else 0)
        section.rows.append(SummaryRow(label, f"{count} {bar}".rstrip(), share(count)))
    for label, value, why in special[1:]:
        if value:
            section.rows.append(SummaryRow(label, _fmt(value), share(int(value)), warn=True))
    return section


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

    manifest = result.model_artifacts()
    loaded_names = pick("models_loaded")
    if manifest is not None or loaded_names:
        artifacts = SummarySection(
            "Model artifacts",
            note=(
                "Recorded scenario model and separate-loader snapshots, including point/cascade "
                "models and failed loads. "
                "SHA-256 identifies loaded bytes; it does not certify physical validity or show "
                "that inference ran."
            ),
        )
        if manifest is None:
            artifacts.rows.append(SummaryRow(
                "manifest", "not recorded", "Older output records loaded names only.", warn=True,
            ))
            for name in loaded_names if isinstance(loaded_names, list) else []:
                artifacts.rows.append(SummaryRow(str(name), "loaded; byte identity not recorded"))
        elif manifest.get("schema") != "trech_model_artifacts_v1" or not isinstance(manifest.get("models"), list):
            artifacts.rows.append(SummaryRow(
                "manifest", "unsupported schema", str(manifest.get("schema") or "unknown"), warn=True,
            ))
        else:
            for model in manifest["models"]:
                if not isinstance(model, dict):
                    continue
                loaded = model.get("loaded") is True
                details = [str(model.get("path") or "path unrecorded")]
                for key in ("scale", "operator_role", "element_kind"):
                    if model.get(key):
                        details.append(f"{key}: {model[key]}")
                if loaded:
                    sha256 = model.get("sha256")
                    details.append(f"SHA-256: {sha256}" if sha256 else "SHA-256: not recorded")
                    if model.get("size_bytes") is not None:
                        details.append(f"{model['size_bytes']} bytes")
                elif model.get("load_note"):
                    details.append(str(model["load_note"]))
                artifacts.rows.append(SummaryRow(
                    str(model.get("name") or "unnamed model"), "loaded" if loaded else "not loaded",
                    " · ".join(details), warn=not loaded,
                ))
            loaders = manifest.get("loaders", [])
            if not isinstance(loaders, list):
                artifacts.rows.append(SummaryRow(
                    "loader manifest", "unsupported entries", "Expected a recorded loader list.", warn=True,
                ))
                loaders = []
            for loader in loaders:
                if not isinstance(loader, dict):
                    continue
                loaded = loader.get("loaded") is True
                status = loader.get("status")
                if not isinstance(status, str):
                    status = None
                disabled = not loaded and status in ("disabled", "disabled_strict")
                value = "loaded" if loaded else {
                    "disabled_strict": "disabled in strict mode",
                    "disabled": "disabled", "failed": "failed",
                }.get(status, "not loaded")
                details = [str(loader.get("path") or "path unrecorded")]
                if loaded:
                    sha256 = loader.get("sha256")
                    details.append(f"SHA-256: {sha256}" if sha256 else "SHA-256: not recorded")
                    if loader.get("size_bytes") is not None:
                        details.append(f"{loader['size_bytes']} bytes")
                if loader.get("load_note"):
                    details.append(str(loader["load_note"]))
                artifacts.rows.append(SummaryRow(
                    f"{loader.get('loader') or 'unnamed'} loader", value,
                    " · ".join(details), warn=not loaded and not disabled,
                ))
        out.sections.append(artifacts)

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

    # --- 2a. event-deposit distribution (engine-computed shape, read verbatim) -----------
    # Older runs have no shape keys; the section then stays absent instead of guessing.
    if pick("system_event_edep_zero_fraction") is not None:
        deposit = SummarySection(
            "Event deposit distribution",
            note=(
                "Per-event energy deposit moments computed by the engine from this run's Geant4 "
                "events (descriptive statistics, not a physics law). Studio recomputes nothing."
            ),
        )
        n_events = pick("system_event_count")
        if n_events is not None:
            deposit.rows.append(SummaryRow("events summarised", _fmt(n_events)))
        mean = _as_float(pick("system_event_edep_mean_mev"))
        stderr = _as_float(pick("system_event_edep_stderr_mev"))
        if mean is not None:
            deposit.rows.append(SummaryRow(
                "mean deposit (MeV)",
                f"{mean:.6g}" + (f" ± {stderr:.2g}" if stderr is not None else ""),
                "± = engine-reported standard error of the mean" if stderr is not None else "",
            ))
        for label, key in (
            ("stddev (MeV)", "system_event_edep_stddev_mev"),
            ("min deposit (MeV)", "system_event_edep_min_mev"),
            ("max deposit (MeV)", "system_event_edep_max_mev"),
        ):
            value = pick(key)
            if value is not None:
                deposit.rows.append(SummaryRow(label, _fmt(value)))
        deposit.rows.append(SummaryRow(
            "zero-deposit fraction", _fmt(pick("system_event_edep_zero_fraction")),
            "events that left no energy in the world (e.g. uncollided photons)",
        ))
        if pick("system_event_edep_shape_defined") is True:
            deposit.rows.append(SummaryRow("skewness", _fmt(pick("system_event_edep_skewness"))))
            deposit.rows.append(SummaryRow(
                "excess kurtosis", _fmt(pick("system_event_edep_excess_kurtosis"))))
        else:
            deposit.rows.append(SummaryRow(
                "shape", "not defined",
                "fewer than three events, a constant deposit, or spread below the engine's "
                "precision floor: skewness/kurtosis are withheld rather than shown as noise",
                warn=True,
            ))
        out.sections.append(deposit)

    # --- 2a'. event multiplicity (engine-computed shape, read verbatim) ------------------
    # Secondary tracks per event and summed track length per event. Older runs lack the
    # keys and show no section; Studio never derives these from the deposit moments.
    if pick("system_event_secondaries_zero_fraction") is not None:
        multiplicity = SummarySection(
            "Event multiplicity",
            note=(
                "Secondary tracks created per event (every stepped track minus the event's "
                "primaries, optical photons included when optics is on) and the summed step "
                "length of all tracks, computed by the engine from this run's Geant4 events. "
                "Descriptive statistics only; Studio recomputes nothing."
            ),
        )
        mean = _as_float(pick("system_event_secondaries_mean"))
        stderr = _as_float(pick("system_event_secondaries_stderr"))
        if mean is not None:
            multiplicity.rows.append(SummaryRow(
                "mean secondaries per event",
                f"{mean:.6g}" + (f" ± {stderr:.2g}" if stderr is not None else ""),
                "± = engine-reported standard error of the mean" if stderr is not None else "",
            ))
        for label, key in (
            ("stddev", "system_event_secondaries_stddev"),
            ("min secondaries", "system_event_secondaries_min"),
            ("max secondaries", "system_event_secondaries_max"),
        ):
            value = pick(key)
            if value is not None:
                multiplicity.rows.append(SummaryRow(label, _fmt(value)))
        multiplicity.rows.append(SummaryRow(
            "zero-secondary fraction", _fmt(pick("system_event_secondaries_zero_fraction")),
            "events whose primaries created no secondary track",
        ))
        dispersion = pick("system_event_secondaries_dispersion_index")
        if dispersion is not None:
            multiplicity.rows.append(SummaryRow(
                "dispersion index (var/mean)", _fmt(dispersion),
                "1 for a Poisson count; >1 clustered, <1 more regular",
            ))
        # Engine-side species split of the same secondaries (absent in older runs).
        # Only species Geant4 actually produced in this run are listed.
        for species, label in _SECONDARY_SPECIES:
            prefix = f"system_event_secondaries_{species}"
            species_mean = _as_float(pick(prefix + "_mean"))
            if species_mean is None or species_mean <= 0.0:
                continue
            species_stderr = _as_float(pick(prefix + "_stderr"))
            zero = _as_float(pick(prefix + "_zero_fraction"))
            multiplicity.rows.append(SummaryRow(
                f"{label} per event",
                f"{species_mean:.6g}"
                + (f" ± {species_stderr:.2g}" if species_stderr is not None else ""),
                (f"max {_fmt(pick(prefix + '_max'))}; "
                 f"{(1.0 - zero) * 100:.3g}% of events have one" if zero is not None else ""),
            ))
        if pick("system_event_secondaries_shape_defined") is True:
            multiplicity.rows.append(SummaryRow(
                "skewness", _fmt(pick("system_event_secondaries_skewness"))))
            multiplicity.rows.append(SummaryRow(
                "excess kurtosis", _fmt(pick("system_event_secondaries_excess_kurtosis"))))
        else:
            multiplicity.rows.append(SummaryRow(
                "shape", "not defined",
                "fewer than three events, a constant multiplicity, or spread below the engine's "
                "precision floor: skewness/kurtosis are withheld rather than shown as noise",
                warn=True,
            ))
        tl_mean = _as_float(pick("system_event_track_length_mean_mm"))
        tl_stderr = _as_float(pick("system_event_track_length_stderr_mm"))
        if tl_mean is not None:
            multiplicity.rows.append(SummaryRow(
                "mean track length per event (mm)",
                f"{tl_mean:.6g}" + (f" ± {tl_stderr:.2g}" if tl_stderr is not None else ""),
            ))
        for label, key in (
            ("track length min (mm)", "system_event_track_length_min_mm"),
            ("track length max (mm)", "system_event_track_length_max_mm"),
        ):
            value = pick(key)
            if value is not None:
                multiplicity.rows.append(SummaryRow(label, _fmt(value)))
        out.sections.append(multiplicity)

    # --- 2a'''. engine histograms of the same events (fixed bins, read verbatim) ------
    # Absent in runs recorded before the engine binned per-event values; Studio never
    # reconstructs a distribution from the moments above.
    deposit_hist = _histogram_section(
        "Event deposit histogram", pick("system_event_edep_histogram"), "edges_mev", "MeV",
        "Per-event energy deposit counted by the engine into fixed log10 bins (10 per decade, "
        "1 eV–1 TeV); only populated bins are listed. Counts are exact and independent of the "
        "worker count.", integer_bins=False)
    if deposit_hist is not None:
        out.sections.append(deposit_hist)
    secondaries_hist = _histogram_section(
        "Secondary multiplicity histogram", pick("system_event_secondaries_histogram"), "edges",
        "", "Secondary tracks per event counted by the engine (exact counts below 16, then "
        "octaves); only populated bins are listed.", integer_bins=True)
    if secondaries_hist is not None:
        out.sections.append(secondaries_hist)
    # Per-species split of the same events (absent in older runs). Only species Geant4
    # produced in this run get a section; an all-zero species histogram is one bin.
    for species, label in _SECONDARY_SPECIES:
        species_raw = pick(f"system_event_secondaries_{species}_histogram")
        if not isinstance(species_raw, dict):
            continue
        species_edges = species_raw.get("edges") or []
        species_counts = species_raw.get("counts") or []
        if not any(int(c) > 0 and int(e) > 0 for e, c in zip(species_edges, species_counts)) \
                and not species_raw.get("overflow_count"):
            continue
        species_hist = _histogram_section(
            f"Secondary multiplicity histogram · {label}", species_raw, "edges", "",
            f"{label.capitalize()} per event, counted by the engine on the same bins as the "
            "total; only populated bins are listed.", integer_bins=True)
        if species_hist is not None:
            out.sections.append(species_hist)
    track_length_hist = _histogram_section(
        "Event track length histogram", pick("system_event_track_length_histogram"),
        "edges_mm", "mm",
        "Summed step length of every track per event, counted by the engine into fixed log10 "
        "bins (10 per decade, 1 nm–1 km); only populated bins are listed. Counts are exact and "
        "independent of the worker count.", integer_bins=False,
        zero_note="events whose tracks took no step length")
    if track_length_hist is not None:
        out.sections.append(track_length_hist)

    # --- 2a''. per-volume event deposit (engine-computed shape, read verbatim) ----------
    # One row per `scoreEdep` volume Geant4 deposited energy in; unhit volumes are counted
    # in the note rather than listed as zero rows. Older runs lack the block.
    volume_shapes = pick("volume_event_edep")
    if isinstance(volume_shapes, dict) and volume_shapes:
        hit = {name: shape for name, shape in volume_shapes.items()
               if isinstance(shape, dict) and (_as_float(shape.get("zero_fraction")) or 0.0) < 1.0}
        unhit = len(volume_shapes) - len(hit)
        per_volume = SummarySection(
            "Per-volume event deposit",
            note=(
                "Energy Geant4 deposited per event in each scored volume (a step counts in the "
                "deepest volume containing it), computed by the engine from this run's events. "
                "Descriptive statistics only; Studio recomputes nothing."
                + (f" {unhit} scored volume(s) received no deposit." if unhit else "")
            ),
        )
        for name in sorted(hit, key=lambda key: -(_as_float(hit[key].get("mean_mev")) or 0.0)):
            shape = hit[name]
            mean = _as_float(shape.get("mean_mev"))
            stderr = _as_float(shape.get("stderr_mev"))
            zero = _as_float(shape.get("zero_fraction"))
            notes = [f"max {_fmt(shape.get('max_mev'))} MeV"]
            if zero is not None:
                notes.append(f"{(1.0 - zero) * 100:.3g}% of events deposit")
            if shape.get("shape_defined") is True:
                notes.append(f"skewness {_fmt(shape.get('skewness'))}")
            per_volume.rows.append(SummaryRow(
                f"{name} mean (MeV/event)",
                (f"{mean:.6g}" if mean is not None else "—")
                + (f" ± {stderr:.2g}" if stderr is not None and mean is not None else ""),
                "; ".join(notes),
            ))
        out.sections.append(per_volume)

    # --- 2a-v. per-volume step length and created secondaries (engine, verbatim) --------
    # Attributed by pre-step volume like the deposit. Volumes nothing stepped in are
    # counted in the note, not listed. Runs before 2026-11-12 lack both blocks.
    volume_lengths = pick("volume_event_track_length")
    volume_secondaries = pick("volume_event_secondaries")
    if isinstance(volume_lengths, dict) and volume_lengths:
        created = volume_secondaries if isinstance(volume_secondaries, dict) else {}
        stepped = {name: shape for name, shape in volume_lengths.items()
                   if isinstance(shape, dict)
                   and (_as_float(shape.get("zero_fraction")) or 0.0) < 1.0}
        unstepped = len(volume_lengths) - len(stepped)
        activity = SummarySection(
            "Per-volume track length and secondaries",
            note=(
                "Step length Geant4 took per event in each scored volume and the secondary "
                "tracks created there (each step and creation vertex counts in the deepest "
                "volume containing it), computed by the engine. Descriptive statistics only."
                + (f" Nothing stepped in {unstepped} scored volume(s)." if unstepped else "")
            ),
        )
        for name in sorted(stepped,
                           key=lambda key: -(_as_float(stepped[key].get("mean_mm")) or 0.0)):
            shape = stepped[name]
            mean = _as_float(shape.get("mean_mm"))
            stderr = _as_float(shape.get("stderr_mm"))
            zero = _as_float(shape.get("zero_fraction"))
            notes = [f"max {_fmt(shape.get('max_mm'))} mm"]
            if zero is not None:
                notes.append(f"{(1.0 - zero) * 100:.3g}% of events step here")
            born = created.get(name)
            if isinstance(born, dict):
                born_mean = _as_float(born.get("mean"))
                if born_mean is not None:
                    split = born.get("species") if isinstance(born.get("species"), dict) else {}
                    # Engine species split of the same secondaries; absent species omitted.
                    parts = [f"{species} {_as_float(split[species].get('mean')):.4g}"
                             for species, _ in _SECONDARY_SPECIES
                             if isinstance(split.get(species), dict)
                             and (_as_float(split[species].get("mean")) or 0.0) > 0.0]
                    notes.append(f"secondaries created {born_mean:.4g}/event "
                                 f"(max {_fmt(born.get('max'))})"
                                 + (": " + ", ".join(parts) if parts else ""))
            activity.rows.append(SummaryRow(
                f"{name} track length (mm/event)",
                (f"{mean:.6g}" if mean is not None else "—")
                + (f" ± {stderr:.2g}" if stderr is not None and mean is not None else ""),
                "; ".join(notes),
            ))
        out.sections.append(activity)

    # --- 2b. geometry resolution (engine-recorded substitutions, read verbatim) ----------
    # DetectorConstruction records a material it could not resolve, a parent it could not
    # find and a volume it did not build. The block is absent when nothing was substituted.
    geometry = prov_end.get("geometry_resolution") or prov.get("geometry_resolution")
    if isinstance(geometry, dict) and isinstance(geometry.get("issues"), list):
        resolution = SummarySection(
            "Geometry resolution",
            note=(
                "Geant4 built a different geometry than the config declared, or the declared "
                "volumes overlap (Geant4 then navigates ambiguously). Each row is an "
                "engine-recorded issue; fix the scenario rather than trusting the run."
            ),
        )
        for label, key in (
            ("material fallbacks", "material_fallback_count"),
            ("parent fallbacks", "parent_fallback_count"),
            ("volumes not built", "volume_skipped_count"),
            ("overlaps", "overlap_count"),
        ):
            value = geometry.get(key)
            if value:
                resolution.rows.append(SummaryRow(label, _fmt(value), warn=True))
        for issue in geometry["issues"]:
            if not isinstance(issue, dict):
                continue
            target = issue.get("volume") or issue.get("role") or "?"
            requested = issue.get("requested") or "(unnamed)"
            if issue.get("kind") == "overlap":
                depth = issue.get("depth_mm")
                depth_text = f" by ≥ {_fmt(depth)} mm" if isinstance(depth, (int, float)) else ""
                verb = ("protrudes from" if issue.get("reason") == "protrudes_parent"
                        else "overlaps")
                value_text = f"{verb} {requested}{depth_text}"
            else:
                value_text = f"{requested} → {issue.get('resolved') or 'not built'}"
            resolution.rows.append(SummaryRow(
                f"{issue.get('kind', '?')}: {target}",
                value_text,
                str(issue.get("reason", "")),
                warn=True,
            ))
        if resolution.rows:
            out.sections.append(resolution)
            out.caveats.append(
                "The engine substituted part of the declared geometry or found overlapping "
                "volumes (see Geometry resolution); results describe what Geant4 built, not the "
                "config as written."
            )

    # --- 2c. geometry overlap check (engine-recorded, read verbatim) ----------------------
    overlap_check = prov_end.get("geometry_overlap_check") or prov.get("geometry_overlap_check")
    if isinstance(overlap_check, dict):
        clean = overlap_check.get("clean") is True
        check = SummarySection(
            "Geometry overlap check",
            note=(
                "Geant4 solids tested at sampled surface points after construction. A clean "
                "result is a sampling bound, not a proof; overlaps shallower than the "
                "tolerance are not reported."
            ),
        )
        check.rows.append(SummaryRow(
            "result", "clean" if clean else f"{_fmt(overlap_check.get('overlap_count'))} overlap(s)",
            warn=not clean))
        for label, key in (
            ("volumes checked", "volumes_checked"),
            ("sibling pairs checked", "pairs_checked"),
            ("samples per volume", "samples_per_volume"),
            ("tolerance (mm)", "tolerance_mm"),
        ):
            value = overlap_check.get(key)
            if value is not None:
                check.rows.append(SummaryRow(label, _fmt(value)))
        out.sections.append(check)

    if scores.get("time_budget_seconds"):
        out.sections.append(SummarySection(
            "Adaptive simulation budget",
            rows=[SummaryRow("events completed / requested", f"{scores.get('n_events')} / {scores.get('requested_events')}"),
                  SummaryRow("stop reason", str(scores.get("stop_reason"))),
                  SummaryRow("simulation seconds / budget", f"{scores.get('simulation_wall_seconds', 0):.3g} / {scores.get('time_budget_seconds'):g}")],
            note="Predictive scheduling; soft event-boundary limit. Initialization is excluded.",
        ))

    # --- 2b. precision profile (what the scenario actually refined) -----------------------
    profile = pick("precision_profile")
    axes = scores.get("precision_axes")
    if profile or isinstance(axes, list):
        precision = SummarySection(
            "Precision profile",
            note=(
                "TRECH has no single quality number: a profile is a named rung the scenario "
                "maps onto its OWN axes, and each axis below says what it actually changed."
            ),
        )
        if profile:
            precision.rows.append(
                SummaryRow(
                    "profile",
                    _fmt(profile),
                    "custom: at least one control overrode the profile, so this run is not a "
                    "named rung" if str(profile) == "custom" else "",
                )
            )
        note = pick("precision_note")
        if note:
            precision.rows.append(SummaryRow("note", _fmt(note)))
        for axis in axes or []:
            if not isinstance(axis, dict):
                continue
            value = _fmt(axis.get("value"))
            baseline = _as_float(axis.get("baseline_value"))
            current = _as_float(axis.get("value"))
            detail = f"role {axis.get('role') or '?'}"
            unit = axis.get("unit")
            if unit:
                value = f"{value} {unit}"
            if baseline and current is not None and baseline != current:
                detail += f" · balanced reference {baseline:g}"
            if axis.get("control"):
                detail += f" · control {axis['control']}"
            if axis.get("overridden"):
                detail += " · overridden by an explicit control value"
            if axis.get("representation_only"):
                detail += " · REPRESENTATION ONLY (display; changes no simulated state)"
            precision.rows.append(
                SummaryRow(str(axis.get("name") or "axis"), value, detail)
            )
        out.sections.append(precision)

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


def geometry_resolution_marks(result: Any) -> Dict[Tuple[str, str], List[str]]:
    """Engine-recorded geometry substitutions and overlaps keyed by Outliner node ``(kind, name)``.

    Reads the provenance ``geometry_resolution`` block verbatim (run_end first, then
    run_start for an interrupted run). A volume issue maps to ``("volume", name)``; a world
    material fallback maps to ``("world", "")``. The medium box has no Outliner node, so its
    fallback is keyed ``("medium", "")`` for callers that want it. A sibling overlap marks both
    volumes; a protrusion marks the protruding volume. Each value lists one short line per
    issue. No block (nothing substituted, or an older run) gives ``{}``.
    """
    block = _run_end_provenance(result).get("geometry_resolution")
    if not isinstance(block, dict):
        for rec in reversed(getattr(result, "provenance", []) or []):
            if isinstance(rec.get("geometry_resolution"), dict):
                block = rec["geometry_resolution"]
                break
    if not isinstance(block, dict) or not isinstance(block.get("issues"), list):
        return {}
    marks: Dict[Tuple[str, str], List[str]] = {}
    for issue in block["issues"]:
        if not isinstance(issue, dict):
            continue
        kind = str(issue.get("kind", ""))
        role = str(issue.get("role", ""))
        volume = str(issue.get("volume") or "")
        requested = str(issue.get("requested") or "(unnamed)")
        resolved = str(issue.get("resolved") or "")
        reason = str(issue.get("reason") or "")
        if kind == "volume_skipped":
            line = f"not built by the engine ({reason or 'skipped'})"
        elif kind == "parent_fallback":
            line = f"placed in the world, not in '{requested}' ({reason or 'parent fallback'})"
        elif kind == "material_fallback":
            line = f"material '{requested}' → {resolved or '?'} ({reason or 'fallback'})"
        elif kind == "overlap":
            depth = issue.get("depth_mm")
            depth_text = f" by ≥ {depth:.4g} mm" if isinstance(depth, (int, float)) else ""
            if reason == "protrudes_parent":
                line = f"protrudes from '{requested}'{depth_text} (overlap)"
            else:
                line = f"overlaps '{requested}'{depth_text} (overlap)"
                # The sibling is equally ambiguous for Geant4 navigation: mark it too.
                if role == "volume" and issue.get("requested"):
                    marks.setdefault(("volume", requested), []).append(
                        f"overlaps '{volume}'{depth_text} (overlap)")
        else:
            line = f"{kind or 'substitution'}: {requested} → {resolved or '?'}"
        if role == "volume" and volume:
            key = ("volume", volume)
        elif role in ("world", "medium"):
            key = (role, "")
        else:
            continue
        marks.setdefault(key, []).append(line)
    return marks


def _run_end_provenance(result: Any) -> Dict[str, Any]:
    for rec in reversed(result.provenance):
        if rec.get("phase") == "run_end":
            return rec
    return {}
