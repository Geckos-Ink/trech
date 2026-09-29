"""Charts derived from recorded Geant4 trajectories (+ the engine's own formula values).

Each builder turns the recorded population into the plot a physicist would draw for that
experiment — an attenuation curve, a Bragg curve, an interaction-channel split, a dispersion
scatter, a reaction timeline — revealing each sample at the Geant4 time it happened. The only
non-recorded curves are the engine's analytic predictions (``trech_scores.jsonl``
``analytic_checks``, computed by the engine from Geant4 cross sections), drawn dashed and labelled
"formula". Charts are statistics of the *recorded subset* (capped by ``--viz-max-trajectories``);
the engine's full-run tally stays in the HUD.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np

from .charts import Chart, Series
from .tracks_view import Track, find_reactions, pretty_particle
from .trajectories import wavelength_nm_for_energy_ev

MEASURED = "#ffd24d"
FORMULA = "#9ad0ff"
ALT = "#ff7ad9"


def last_scores(path: Optional[str]) -> Dict:
    if not path or not Path(path).exists():
        return {}
    record: Dict = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
    return record if isinstance(record, dict) else {}


def _check(scores: Dict, kind: str) -> Dict:
    for check in scores.get("analytic_checks") or []:
        if isinstance(check, dict) and check.get("type") == kind:
            return check
    return {}


def _primaries(tracks: Sequence[Track], particle: Optional[str] = None) -> List[Track]:
    return [t for t in tracks if t.primary and t.points.shape[0] >= 2
            and (particle is None or t.particle == particle)]


def _depth_axis(primaries: Sequence[Track]):
    starts = np.asarray([t.points[0] for t in primaries])
    dirs = np.asarray([(t.points[1] - t.points[0]) / max(np.linalg.norm(t.points[1] - t.points[0]),
                                                        1e-12) for t in primaries])
    axis = np.mean(dirs, axis=0)
    axis /= max(float(np.linalg.norm(axis)), 1e-12)
    return starts, axis


def _slab_entry(primaries: Sequence[Track], axis: np.ndarray) -> float:
    """Depth (along the beam) of the first recorded boundary: where the medium begins."""
    entries = []
    for t in primaries:
        for k in range(1, len(t.interactions)):
            if t.interactions[k] == "boundary":
                entries.append(float(np.dot(t.points[k] - t.points[0], axis)))
                break
    return float(np.median(entries)) if entries else 0.0


# --------------------------------------------------------------------------- attenuation


def attenuation_charts(tracks: Sequence[Track], scores: Dict) -> List[Chart]:
    """Uncollided survival vs depth + first-interaction channel split, vs the engine formula."""
    check = _check(scores, "beer_lambert") or _check(scores, "photo_fraction")
    primaries = _primaries(tracks, "gamma")
    if not primaries:
        return []
    _, axis = _depth_axis(primaries)
    entry = _slab_entry(primaries, axis)
    length = float(check.get("path_length_mm") or 50.0)
    # Each photon's uncollided leg as (time, depth) at slab entry and at its first interaction
    # (or slab exit), so the estimator only uses depths a photon has actually reached by `now`.
    t_in, d_in, t_out, d_out, hit, channel = [], [], [], [], [], []
    for t in primaries:
        rel = (t.points - t.points[0]) @ axis - entry
        stop = t.first_hit if t.first_hit is not None else t.points.shape[0] - 1
        leg_d, leg_t = rel[:stop + 1], t.times[:stop + 1]
        inside = np.nonzero(leg_d >= -1e-6)[0]
        if inside.size == 0:
            continue
        k0 = int(inside[0])
        t_in.append(float(leg_t[k0]))
        d_in.append(max(0.0, float(leg_d[k0])))
        t_out.append(float(leg_t[-1]))
        d_out.append(float(leg_d[-1]))  # unclipped: the leg's true end (may be past the slab)
        hit.append(t.first_hit is not None and float(leg_d[-1]) <= length + 1e-6)
        channel.append(t.processes[t.first_hit] if hit[-1] else "none")
    t_in, d_in, t_out, d_out = (np.asarray(v) for v in (t_in, d_in, t_out, d_out))
    hit, channel = np.asarray(hit), np.asarray(channel)
    grid = np.linspace(0.0, length, 120)

    def reached(now: float) -> np.ndarray:
        span = np.maximum(t_out - t_in, 1e-12)
        frac = np.clip((now - t_in) / span, 0.0, 1.0)
        depth = np.minimum(d_in + frac * (d_out - d_in), length)
        return np.where(now < t_in, -1.0, depth)

    def survival(now: float):
        # Kaplan-Meier over depth: a photon still flying is censored at the depth it has reached,
        # so the curve is never biased toward the early (shallow) interactions.
        depth = reached(now)
        entered = depth >= 0.0
        event = hit & (now >= t_out) & entered
        observed = np.where(event, d_out, depth)[entered]
        event = event[entered]
        if observed.size == 0:
            return grid[:1], np.array([1.0])
        order = np.argsort(observed, kind="stable")
        observed, event = observed[order], event[order]
        at_risk = observed.size - np.arange(observed.size)
        factors = np.where(event, 1.0 - 1.0 / at_risk, 1.0)
        cumulative = np.cumprod(factors)
        xs, values = [], []
        for x in grid:
            k = int(np.searchsorted(observed, x, side="right"))
            if observed.size - k < 20 and x > 0:  # too few photons have reached this depth yet
                break
            xs.append(x)
            values.append(cumulative[k - 1] if k > 0 else 1.0)
        return np.asarray(xs), np.asarray(values)

    reveal = np.where(hit, t_out, t_out)
    depth = d_out
    mu = float(check.get("mu_total_per_mm") or 0.0)
    charts: List[Chart] = []
    surv = Chart("photons still un-interacted vs depth in water", "depth (mm)",
                 "surviving fraction", xlim=(0.0, length), ylim=(0.0, 1.05))
    surv.series.append(Series(f"Geant4 recorded ({channel.size} photons)", MEASURED,
                              np.array([]), np.array([]), dynamic=survival, style="step",
                              width=2.2))
    if mu > 0:
        surv.series.append(Series("formula exp(−μx), μ from Geant4 σ", FORMULA, grid,
                                  np.exp(-mu * grid), dashed=True))
    if check.get("type") == "beer_lambert":
        surv.vlines.append((length, f"exit: formula {check.get('classical_predicted', 0):.3f}"
                                    f" · Geant4 {check.get('geant4_measured', 0):.3f}", "#c9d3e6"))
    charts.append(surv)

    names = [("none", "no interaction"), ("compt", "Compton"), ("Rayl", "Rayleigh"),
             ("phot", "photo-\nelectric")]
    photo_mode = check.get("type") == "photo_fraction"
    if photo_mode:
        names = names[1:]
    predicted = []
    total = mu or 1.0
    transmission = math.exp(-mu * length) if mu > 0 else 0.0
    for key, _ in names:
        part = {"compt": check.get("mu_compton_per_mm"), "Rayl": check.get("mu_rayleigh_per_mm"),
                "phot": check.get("mu_photoelectric_per_mm")}.get(key)
        if key == "none":
            predicted.append(transmission)
        elif part is not None:
            predicted.append(float(part) / total * (1.0 if photo_mode else 1.0 - transmission))
        else:
            predicted.append(float("nan"))
    idx = np.arange(len(names), dtype=float)

    population = int((channel != "none").sum()) if photo_mode else channel.size

    def split(now: float):
        # Fractions of ALL photons whose outcome is already known, so bars grow to their
        # final value instead of over-weighting the early (shallow) interactions.
        seen = channel[reveal <= now]
        return idx, np.array([(seen == key).sum() for key, _ in names]) / max(1, population)

    bars = Chart("first interaction: what each photon did first" if photo_mode
                 else "outcome of each photon in the slab", "", "fraction",
                 ylim=(0.0, 1.0), xlim=(-0.6, len(names) - 0.4),
                 categories=[label for _, label in names])
    bars.series.append(Series("Geant4 recorded", MEASURED, idx, np.zeros(len(names)),
                              dynamic=split, style="bars", offset=-0.19, bar_width=0.36))
    bars.series.append(Series("formula σᵢ/σ (Geant4 cross sections)", FORMULA, idx,
                              np.asarray(predicted), style="bars", offset=0.19, bar_width=0.36,
                              hatch=True))
    if photo_mode and check:
        bars.title = (f"first interaction (full run: formula {check.get('classical_predicted', 0):.3f}"
                      f" vs Geant4 {check.get('geant4_measured', 0):.3f} photo)")
    charts.append(bars)
    return charts


# --------------------------------------------------------------------------- Bragg / range


def bragg_charts(tracks: Sequence[Track], scores: Dict) -> List[Chart]:
    check = _check(scores, "csda_range")
    primaries = _primaries(tracks)
    if not primaries:
        return []
    _, axis = _depth_axis(primaries)
    xs, ws, ts, ends, end_t = [], [], [], [], []
    for t in primaries:
        rel = (t.points - t.points[0]) @ axis
        de = np.maximum(-np.diff(t.energy) / 1e6, 0.0)  # MeV lost on each recorded step
        # Spread each recorded step's loss evenly over the depth it spans (Geant4 records the
        # step's total loss, not where inside the step it happened).
        sub = 12
        frac = (np.arange(sub) + 0.5) / sub
        xs.append((rel[:-1, None] + frac[None, :] * np.diff(rel)[:, None]).ravel())
        ws.append(np.repeat(de / sub, sub))
        ts.append((t.times[:-1, None] + frac[None, :] * np.diff(t.times)[:, None]).ravel())
        ends.append(float(rel[-1]))
        end_t.append(float(t.times[-1]))
    xs, ws, ts = np.concatenate(xs), np.concatenate(ws), np.concatenate(ts)
    reach = float(check.get("csda_range_mm") or max(ends))
    bins = np.linspace(0.0, reach * 1.15, 46)
    bin_width = float(bins[1] - bins[0])
    n = len(primaries)
    bragg = Chart("energy lost per mm of depth (Bragg curve)", "depth (mm)",
                  "MeV / mm per proton")
    bragg.series.append(Series(f"Geant4 recorded steps ({n} protons)", MEASURED, xs, xs, t=ts,
                               style="hist", bins=bins, weights=ws, normalize=n * bin_width))
    if check:
        bragg.vlines.append((reach, f"CSDA formula {reach:.2f} mm", FORMULA))
    counts, _ = np.histogram(xs, bins=bins, weights=ws)
    bragg.ylim = (0.0, float(counts.max()) / (n * bin_width) * 1.12)
    bragg.xlim = (0.0, float(bins[-1]))
    charts = [bragg]
    ends, end_t = np.asarray(ends), np.asarray(end_t)
    rng = Chart("where each proton stops", "track end depth (mm)", "protons")
    rbins = np.linspace(reach * 0.85, reach * 1.08, 30)
    rng.series.append(Series("Geant4 recorded", MEASURED, ends, ends, t=end_t, style="hist",
                             bins=rbins))
    if check:
        rng.vlines.append((reach, "formula R_CSDA", FORMULA))
        measured = check.get("geant4_measured")
        if isinstance(measured, (int, float)):
            rng.vlines.append((float(measured), f"Geant4 mean {measured:.2f} mm", MEASURED))
    counts, _ = np.histogram(ends, bins=rbins)
    rng.ylim = (0.0, float(counts.max()) * 1.2 + 1)
    rng.xlim = (float(rbins[0]), float(rbins[-1]))
    charts.append(rng)
    return charts


# --------------------------------------------------------------------------- optics


def optical_charts(tracks: Sequence[Track], *, sampling: bool = False,
                   scene=None) -> List[Chart]:
    photons = [t for t in tracks if t.particle == "opticalphoton" and t.points.shape[0] >= 2]
    if not photons:
        return []
    charts: List[Chart] = []
    kinds = [("refraction", "refracted"), ("reflection", "reflected"),
             ("total_internal_reflection", "total internal\nreflection"),
             ("absorption", "absorbed")]
    xs, ts = [], []
    for t in photons:
        for k, outcome in enumerate(t.boundaries):
            for index, (key, _) in enumerate(kinds):
                if outcome == key:
                    xs.append(index)
                    ts.append(float(t.times[k]))
    xs, ts = np.asarray(xs, dtype=float), np.asarray(ts)
    idx = np.arange(len(kinds), dtype=float)

    def counts(now: float):
        seen = xs[ts <= now]
        return idx, np.array([(seen == i).sum() for i in range(len(kinds))], dtype=float)

    if xs.size and not sampling:
        bars = Chart("what happened at each surface", "", "boundary events (log)",
                     categories=[label for _, label in kinds], log_y=True,
                     xlim=(-0.6, len(kinds) - 0.4),
                     ylim=(0.8, max(10.0, float(counts(float("inf"))[1].max()) * 3.0)))
        bars.series.append(Series("recorded", MEASURED, idx, idx, dynamic=counts, style="bars"))
        charts.append(bars)

    wl = np.asarray([wavelength_nm_for_energy_ev(float(t.energy[0])) for t in photons])
    birth = np.asarray([float(t.times[0]) for t in photons])
    if sampling:
        starts = np.asarray([t.points[0] for t in photons])
        dirs = np.asarray([(t.points[1] - t.points[0]) / max(np.linalg.norm(t.points[1] - t.points[0]), 1e-12)
                           for t in photons])
        mean_dir = dirs.mean(axis=0)
        mean_dir /= np.linalg.norm(mean_dir)
        centre = starts.mean(axis=0)
        radial = starts - centre
        radial -= np.outer(radial @ mean_dir, mean_dir)
        radius = np.linalg.norm(radial, axis=1)
        angle = np.degrees(np.arccos(np.clip(dirs @ mean_dir, -1.0, 1.0)))
        for values, title, xlabel in ((radius, "sampled beam spot", "radius from axis (mm)"),
                                      (angle, "sampled divergence", "angle to beam axis (deg)")):
            chart = Chart(title, xlabel, "photons")
            bins = np.linspace(0.0, max(float(values.max()), 1e-6) * 1.05, 24)
            chart.series.append(Series("recorded emission", MEASURED, values, values, t=birth,
                                       style="hist", bins=bins))
            charts.append(chart)
    spectrum = Chart("sampled wavelengths", "wavelength (nm)", "photons")
    spectrum.series.append(Series("recorded emission", "#b9f27c", wl, wl, t=birth, style="hist",
                                  bins=np.linspace(380, 780, 41)))
    charts.append(spectrum)
    if not sampling and scene is not None:
        # Dispersion measured geometrically: at each photon's first refraction, the recorded
        # refraction angle against Snell's law with the engine-derived n(lambda) of both media.
        derived = scene.derived_by_name()

        def n_at(material: str, lam: float) -> Optional[float]:
            entry = derived.get((material or "").lower())
            if entry is None or not entry.available or not entry.samples:
                return None
            curve = sorted((smp.wavelength_nm, smp.refractive_index) for smp in entry.samples)
            return float(np.interp(lam, [c[0] for c in curve], [c[1] for c in curve]))

        px, measured, predicted, pt = [], [], [], []
        pair = ""
        for t, lam in zip(photons, wl):
            for k in range(1, t.points.shape[0] - 1):
                if t.boundaries[k] != "refraction":
                    continue
                d_in = t.points[k] - t.points[k - 1]
                d_out = t.points[k + 1] - t.points[k]
                n_in, n_out = n_at(t.materials[k - 1], lam), n_at(t.materials[k], lam)
                if n_in is None or n_out is None or abs(n_out - n_in) < 0.05:
                    break
                d_in = d_in / max(np.linalg.norm(d_in), 1e-12)
                d_out = d_out / max(np.linalg.norm(d_out), 1e-12)
                normal = np.zeros(3)
                axis = int(np.argmax(np.abs(d_in)))  # axis-aligned faces
                normal[axis] = 1.0
                theta_i = math.acos(min(1.0, abs(float(d_in @ normal))))
                theta_t = math.acos(min(1.0, abs(float(d_out @ normal))))
                if theta_i < math.radians(3.0) or math.sin(theta_t) <= 0:
                    break
                px.append(lam)
                # Snell inverted per photon: the index Geant4 actually refracted it with.
                measured.append(n_in * math.sin(theta_i) / math.sin(theta_t))
                predicted.append(n_out)
                pt.append(float(t.times[k]))
                pair = f"{t.materials[k - 1]} → {t.materials[k]}"
                break
        if len(px) >= 10:
            chart = Chart(f"dispersion: index seen at the first surface ({pair})",
                          "wavelength (nm)", "n  =  n_air sin θᵢ / sin θₜ")
            chart.series.append(Series("Geant4 recorded photons", "#ffffff", np.asarray(px),
                                       np.asarray(measured), t=np.asarray(pt), style="points",
                                       alpha=0.7))
            order = np.argsort(px)
            chart.series.append(Series("engine-derived n(λ)", FORMULA,
                                       np.asarray(px)[order], np.asarray(predicted)[order],
                                       dashed=True))
            chart.xlim = (380.0, 780.0)
            lo, hi = float(np.percentile(measured, 2)), float(np.percentile(measured, 98))
            chart.ylim = (lo - 0.3 * (hi - lo) - 1e-3, hi + 0.3 * (hi - lo) + 1e-3)
            charts.append(chart)
    return charts[:3]


def refraction_compare_chart(runs: Sequence[Sequence[Track]], labels: Sequence[str],
                             indices: Sequence[Optional[float]], incidence_deg: float) -> List[Chart]:
    """Measured bend at the first refraction vs Snell with each run's engine-derived n."""
    chart = Chart("bending at the entry face", "", "deflection (deg)",
                  categories=[label.replace(" ", "\n", 1) for label in labels])
    idx = np.arange(len(runs), dtype=float)
    measured, snell = [], []
    for tracks, n in zip(runs, indices):
        values = []
        for t in tracks:
            for k, outcome in enumerate(t.boundaries):
                if outcome == "refraction" and 0 < k < t.points.shape[0] - 1:
                    d0, d1 = t.points[k] - t.points[k - 1], t.points[k + 1] - t.points[k]
                    c = float(np.dot(d0, d1) / max(np.linalg.norm(d0) * np.linalg.norm(d1), 1e-12))
                    values.append(math.degrees(math.acos(max(-1.0, min(1.0, c)))))
                    break
        measured.append(float(np.median(values)) if values else float("nan"))
        if n:
            ti = math.radians(incidence_deg)
            snell.append(incidence_deg - math.degrees(math.asin(math.sin(ti) / n)))
        else:
            snell.append(float("nan"))
    chart.series.append(Series("Geant4 recorded (median)", MEASURED, idx, np.asarray(measured),
                               style="bars", offset=-0.19, bar_width=0.36))
    chart.series.append(Series("Snell with engine n", FORMULA, idx, np.asarray(snell),
                               style="bars", offset=0.19, bar_width=0.36, hatch=True))
    top = np.nanmax(np.asarray(measured + snell)) if any(np.isfinite(measured + snell)) else 1.0
    chart.ylim = (0.0, float(top) * 1.3)
    chart.xlim = (-0.6, len(runs) - 0.4)
    return [chart]


# --------------------------------------------------------------------------- nuclear


def nuclear_charts(tracks: Sequence[Track]) -> List[Chart]:
    reactions = find_reactions(tracks)
    elastic_t = [float(t.times[0]) for t in tracks if t.is_ion and not t.primary
                 and t.particle.startswith(("C12", "C13", "N14", "N15"))
                 and all(abs(float(t.times[0]) - r.time_ns) > 1e-6 for r in reactions)]
    series_spec = [("neutron elastic recoils", "#9aa4b8", sorted(elastic_t))]
    for kind, colour, title in (("reaction", "#ff5cf2", "neutron reactions"),
                                ("decay", "#5dff8a", "β⁻ decays")):
        times = sorted(r.time_ns for r in reactions if r.kind == kind)
        series_spec.append((title, colour, times))
    chart = Chart("what Geant4 did, on its own clock", "Geant4 time (s)", "cumulative count",
                  log_x=True)
    lo, hi = math.inf, 0.0
    for title, colour, times in series_spec:
        if not times:
            continue
        t = np.maximum(np.asarray(times), 1e-3)
        chart.series.append(Series(f"{title} ({len(times)})", colour, t * 1e-9,
                                   np.arange(1, len(t) + 1, dtype=float), t=t, style="step"))
        lo, hi = min(lo, float(t.min())), max(hi, float(t.max()))
    if math.isfinite(lo):
        chart.xlim = (lo * 1e-9 * 0.3, hi * 1e-9 * 3.0)
    charts = [chart]
    labels: Dict[str, List[float]] = {}
    for reaction in reactions:
        labels.setdefault(reaction.label, []).append(reaction.time_ns)
    if labels:
        names = sorted(labels, key=lambda k: -len(labels[k]))[:4]
        idx = np.arange(len(names), dtype=float)
        times = [np.asarray(labels[n]) for n in names]

        def tally(now: float):
            return idx, np.array([(t <= now).sum() for t in times], dtype=float)

        bars = Chart("reaction channels Geant4 sampled", "", "events",
                     categories=[n.replace(" → ", "\n→ ") for n in names],
                     xlim=(-0.6, len(names) - 0.4),
                     ylim=(0.0, max(len(t) for t in times) * 1.2))
        bars.series.append(Series("recorded", "#ff5cf2", idx, idx, dynamic=tally, style="bars"))
        charts.append(bars)
    return charts


# --------------------------------------------------------------------------- deposits


def deposit_charts(tracks: Sequence[Track], scores: Dict,
                   material_labels: Optional[Dict[str, str]] = None) -> List[Chart]:
    """Where recorded charged tracks left their energy, by material, + Geant4-scored edep."""
    by_material: Dict[str, List[float]] = {}
    times: Dict[str, List[float]] = {}
    for t in tracks:
        if t.particle not in ("e-", "e+", "proton", "alpha") or t.points.shape[0] < 2:
            continue
        loss = np.maximum(-np.diff(t.energy) / 1e6, 0.0)
        for k in range(1, t.points.shape[0]):
            name = t.volumes[k - 1] or "?"
            by_material.setdefault(name, []).append(float(loss[k - 1]))
            times.setdefault(name, []).append(float(t.times[k]))
    charts: List[Chart] = []
    if by_material:
        top = max(sum(v) for v in by_material.values())
        names = [n for n in sorted(by_material, key=lambda k: -sum(by_material[k]))
                 if sum(by_material[n]) > 0.01 * top and n.lower() != "world"][:4]
        idx = np.arange(len(names), dtype=float)
        loss = [np.asarray(by_material[n]) for n in names]
        when = [np.asarray(times[n]) for n in names]

        def total(now: float):
            return idx, np.array([l[w <= now].sum() for l, w in zip(loss, when)])

        chart = Chart("energy left by recorded electrons, per volume", "", "MeV",
                      categories=[(material_labels or {}).get(n, n) for n in names],
                      xlim=(-0.6, len(names) - 0.4),
                      ylim=(0.0, max(float(l.sum()) for l in loss) * 1.2 + 1e-9))
        chart.series.append(Series("recorded tracks", MEASURED, idx, idx, dynamic=total,
                                   style="bars"))
        charts.append(chart)
    edep = scores.get("volume_edep_mev") or {}
    if edep:
        names = list(edep)[:4]
        idx = np.arange(len(names), dtype=float)
        chart = Chart("Geant4-scored deposit (full run)", "", "MeV",
                      categories=[(material_labels or {}).get(n, n) for n in names],
                      xlim=(-0.6, len(names) - 0.4))
        chart.series.append(Series(f"{scores.get('n_events', '?')} events", FORMULA, idx,
                                   np.asarray([float(edep[n]) for n in names]), style="bars"))
        charts.append(chart)
    return charts


# --------------------------------------------------------------------------- MR tissue contrast


def tissue_compare_charts(scores: Sequence[Dict], labels: Sequence[str], tissues: Sequence[str],
                          edep_prefix: str = "receiver_coil") -> List[Chart]:
    """Per-tissue Geant4 1H density vs the Geant4-scored detector signal of each run."""
    density, signal = [], []
    for record, tissue in zip(scores, tissues):
        n_h = float("nan")
        for probe in record.get("material_probes") or []:
            if isinstance(probe, dict) and probe.get("name") == tissue:
                n_h = float((probe.get("numberDensityPerCm3") or {}).get("H", float("nan")))
        density.append(n_h / 1e22)
        edep = record.get("volume_edep_mev") or {}
        signal.append(sum(float(v) for k, v in edep.items() if str(k).startswith(edep_prefix)))
    idx = np.arange(len(labels), dtype=float)
    cats = [label.replace(" (", "\n(") for label in labels]
    first = Chart("¹H nuclei per cm³ (Geant4 material, ×10²²)", "", "10²² / cm³",
                  categories=cats, xlim=(-0.6, len(labels) - 0.4))
    first.series.append(Series("Geant4 composition", "#9ad0ff", idx, np.asarray(density),
                               style="bars"))
    first.ylim = (0.0, float(np.nanmax(density)) * 1.25)
    second = Chart("signal detected in the NaI shell", "", "MeV (Geant4 scored)",
                   categories=cats, xlim=(-0.6, len(labels) - 0.4))
    second.series.append(Series("measured", MEASURED, idx, np.asarray(signal), style="bars",
                                offset=-0.19, bar_width=0.36))
    if density and np.isfinite(density[0]) and density[0] > 0:
        expected = [signal[0] * d / density[0] for d in density]
        second.series.append(Series("if ∝ ¹H density", FORMULA, idx, np.asarray(expected),
                                    style="bars", offset=0.19, bar_width=0.36, hatch=True))
    second.ylim = (0.0, max(signal) * 1.3)
    if len(signal) == 2 and signal[0] > 0:
        second.note = (f"bone/water: detected {signal[1] / signal[0]:.2f}, "
                       f"¹H density {density[1] / density[0]:.2f}")
    return [first, second]
