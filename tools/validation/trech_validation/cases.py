"""Validation cases.

Each ValidationCase wraps:
- a human-readable name + description
- the run directories whose outputs it consumes
- an `evaluate(ctx)` method that produces a CaseResult

The runner produces results in a stable alphabetical order so commits show
clean Markdown diffs of regressions / improvements.
"""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .runner import RunContext, RunOutputs


# Run output directory names that cases will look for under --runs-dir.
RUN_VIZ_REFRACTION = "out_viz_refraction"
RUN_VIZ_REFRACTION_REPLAY = "out_viz_refraction_replay"
RUN_NITROGEN_CYCLE = "out_nitrogen_cycle"
RUN_H2O_FLUID = "out_h2o_fluid"
RUN_PASCAL = "out_pascal"
RUN_OSMOTIC = "out_osmotic"
RUN_EFFLUX = "out_efflux"
RUN_BEAKER_WATER_PENTANE = "out_beaker_water_n_pentane"
RUN_H2O_CYCLE = "out_h2o_cycle"
RUN_OPTICS_SURROGATE = "out_optics_surrogate"
RUN_SURROGATE_GENERIC = "out_surrogate_generic"
RUN_GOW_VARIED = "out_gow_varied"
RUN_H2O_MOLECULE = "out_h2o_molecule"
RUN_H2O_CLUSTER = "out_h2o_cluster"
RUN_H2O_BULK = "out_h2o_bulk"
RUN_GLASS_SHAKEN = "out_glass_shaken"
RUN_H2O_DIFFUSION_T = "out_h2o_diffusion_T"
RUN_CNT_BAND_STRUCTURE = "out_cnt_band_structure"
RUN_CNT_LOGIC_GATES = "out_cnt_logic_gates"
RUN_MAGNETIC_RESONANCE = "out_mr"
RUN_MR_TISSUES = "out_mr_tissues"
RUN_MR_IMAGING = "out_mr_imaging"
RUN_MR_BRAIN = "out_mr_brain"
RUN_ANALYTIC_BEER_LAMBERT = "out_analytic_beer_lambert"
RUN_ANALYTIC_CSDA = "out_analytic_csda"
RUN_ANALYTIC_PHOTO_FRACTION = "out_analytic_photo_fraction"


@dataclass
class CaseResult:
    name: str
    description: str
    category: str
    status: str  # "pass" | "fail" | "info" | "skip" | "error"
    summary: str = ""
    measured: Optional[Any] = None
    expected: Optional[Any] = None
    delta: Optional[Any] = None
    tolerance: Optional[Any] = None
    references: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "status": self.status,
            "summary": self.summary,
            "measured": self.measured,
            "expected": self.expected,
            "delta": self.delta,
            "tolerance": self.tolerance,
            "references": list(self.references),
            "notes": list(self.notes),
            "description": self.description,
        }


class ValidationCase:
    name: str = ""
    description: str = ""
    category: str = "general"

    def required_runs(self) -> List[str]:
        return []

    def evaluate(self, ctx: "RunContext") -> CaseResult:  # pragma: no cover - abstract
        raise NotImplementedError


# ---------- helpers ----------

def _need_run(ctx: "RunContext", name: str) -> Optional["RunOutputs"]:
    run = ctx.get(name)
    if run is None:
        return None
    return run


def _skip(name: str, description: str, category: str, run_name: str) -> CaseResult:
    return CaseResult(
        name=name,
        description=description,
        category=category,
        status="skip",
        summary=f"run output not found: {run_name}",
    )


def _derived_by_name(scene: Dict) -> Dict[str, Dict]:
    out: Dict[str, Dict] = {}
    for entry in scene.get("derived_optics") or []:
        for key in (entry.get("material_name"), entry.get("config_material_key")):
            if key:
                out[key.lower()] = entry
    return out


def _last_emit_payload(run: "RunOutputs", tag: str) -> Optional[Dict]:
    """Return the payload of the last hook emit with the given tag (or None)."""
    found = None
    for e in run.hook_emits or []:
        if e.get("tag") == tag:
            found = e.get("payload") or {}
    return found


def _approx_equal(a: float, b: float, rel: float = 0.0, abs_tol: float = 0.0) -> bool:
    diff = abs(a - b)
    if diff <= abs_tol:
        return True
    if rel > 0.0 and diff <= rel * max(abs(a), abs(b)):
        return True
    return False


# ---------- optics cases ----------

class _OpticsNCase(ValidationCase):
    """Compare derived n at visible band to a handbook reference."""

    category = "optics"
    material_key: str = ""
    reference_n: float = 1.0
    reference_source: str = ""

    def required_runs(self) -> List[str]:
        return [RUN_VIZ_REFRACTION]

    def evaluate(self, ctx: "RunContext") -> CaseResult:
        run = _need_run(ctx, RUN_VIZ_REFRACTION)
        if run is None or run.viz_scene is None:
            return _skip(self.name, self.description, self.category, RUN_VIZ_REFRACTION)
        derived = _derived_by_name(run.viz_scene).get(self.material_key.lower())
        if derived is None:
            return CaseResult(
                name=self.name,
                description=self.description,
                category=self.category,
                status="fail",
                summary=f"derived_optics missing for {self.material_key!r}",
            )
        n = float(derived.get("mean_refractive_index") or 0.0)
        delta = n - self.reference_n
        # Logged as informational (not gated on a numeric tolerance): after the
        # f-sum valence oscillator the derived n sits at ~handbook (the earlier
        # KK-truncation-low n is gone), and a small material-specific residual
        # remains. The report is a regression watchdog -- the commit-over-commit
        # delta is the signal.
        return CaseResult(
            name=self.name,
            description=self.description,
            category=self.category,
            status="info",
            summary=f"derived n = {n:.6f}, reference = {self.reference_n:.6f}, delta = {delta:+.6f}",
            measured=n,
            expected=self.reference_n,
            delta=delta,
            references=[self.reference_source],
        )


class OpticsNWater(_OpticsNCase):
    name = "optics_n_water_visible"
    description = "Mean refractive index derived for water at the visible band vs CRC handbook."
    material_key = "water"
    reference_n = 1.333
    reference_source = "CRC Handbook of Chemistry & Physics, water @ 589 nm"


class OpticsNGlass(_OpticsNCase):
    name = "optics_n_glass_visible"
    description = "Mean refractive index derived for glass slab (SiO2) at the visible band vs handbook."
    material_key = "glass"
    reference_n = 1.46
    reference_source = "Schott BK7 typical n at 589 nm"


class OpticsNAir(_OpticsNCase):
    name = "optics_n_air_visible"
    description = "Mean refractive index derived for air at the visible band vs handbook."
    material_key = "air"
    reference_n = 1.000293
    reference_source = "CRC Handbook of Chemistry & Physics, dry air @ STP"


class OpticsIndexOrdering(ValidationCase):
    name = "optics_index_ordering"
    description = "Strict invariant: n_glass > n_water > n_air."
    category = "optics"

    def required_runs(self) -> List[str]:
        return [RUN_VIZ_REFRACTION]

    def evaluate(self, ctx: "RunContext") -> CaseResult:
        run = _need_run(ctx, RUN_VIZ_REFRACTION)
        if run is None or run.viz_scene is None:
            return _skip(self.name, self.description, self.category, RUN_VIZ_REFRACTION)
        derived = _derived_by_name(run.viz_scene)
        try:
            n_glass = float(derived["glass"]["mean_refractive_index"])
            n_water = float(derived["water"]["mean_refractive_index"])
            n_air = float(derived["air"]["mean_refractive_index"])
        except (KeyError, TypeError, ValueError):
            return CaseResult(
                name=self.name,
                description=self.description,
                category=self.category,
                status="fail",
                summary="missing derived n for glass / water / air",
            )
        passed = (n_glass > n_water > n_air)
        return CaseResult(
            name=self.name,
            description=self.description,
            category=self.category,
            status="pass" if passed else "fail",
            summary=f"n_glass={n_glass:.6f} > n_water={n_water:.6f} > n_air={n_air:.6f}",
            measured={"glass": n_glass, "water": n_water, "air": n_air},
            expected="n_glass > n_water > n_air",
        )


class OpticsIndexAboveOne(ValidationCase):
    name = "optics_index_above_one"
    description = "Physical invariant: every derived n is >= 1 (Kramers-Kronig output is bounded below by 1)."
    category = "optics"

    def required_runs(self) -> List[str]:
        return [RUN_VIZ_REFRACTION]

    def evaluate(self, ctx: "RunContext") -> CaseResult:
        run = _need_run(ctx, RUN_VIZ_REFRACTION)
        if run is None or run.viz_scene is None:
            return _skip(self.name, self.description, self.category, RUN_VIZ_REFRACTION)
        derived = run.viz_scene.get("derived_optics") or []
        offenders = []
        for entry in derived:
            n = float(entry.get("mean_refractive_index") or 0.0)
            if n < 1.0 - 1.0e-9:
                offenders.append(f"{entry.get('material_name')}={n:.6f}")
        status = "pass" if not offenders else "fail"
        summary = (
            f"all {len(derived)} derived n entries >= 1"
            if not offenders
            else f"materials with n < 1: {', '.join(offenders)}"
        )
        return CaseResult(
            name=self.name,
            description=self.description,
            category=self.category,
            status=status,
            summary=summary,
        )


class OpticsKKWindowSane(ValidationCase):
    name = "optics_kk_integration_window"
    description = (
        "Sanity invariant: KK integration window spans at least three decades of energy "
        "(so the dispersion integral covers UV/X-ray resonances)."
    )
    category = "optics"

    def required_runs(self) -> List[str]:
        return [RUN_VIZ_REFRACTION]

    def evaluate(self, ctx: "RunContext") -> CaseResult:
        run = _need_run(ctx, RUN_VIZ_REFRACTION)
        if run is None or run.viz_scene is None:
            return _skip(self.name, self.description, self.category, RUN_VIZ_REFRACTION)
        # Read derive config out of provenance.
        derive = None
        if run.provenance:
            for entry in reversed(run.provenance):
                if entry.get("phase") != "run_start":
                    continue
                try:
                    config = json.loads(entry.get("config_json") or "{}")
                    derive = (config.get("optics") or {}).get("derive") or {}
                    break
                except json.JSONDecodeError:
                    continue
        if not derive:
            return CaseResult(
                name=self.name,
                description=self.description,
                category=self.category,
                status="skip",
                summary="optics.derive config not found in provenance",
            )
        emin = float(derive.get("kkIntegrationMinEv") or 0.0)
        emax = float(derive.get("kkIntegrationMaxEv") or 0.0)
        ratio = emax / emin if emin > 0 else 0.0
        ok = ratio >= 1000.0
        return CaseResult(
            name=self.name,
            description=self.description,
            category=self.category,
            status="pass" if ok else "fail",
            summary=f"kkIntegration window {emin:g} -> {emax:g} eV (ratio {ratio:.0f})",
            measured=ratio,
            expected=">= 1000",
        )


# ---------- nuclear cases ----------

class NuclearCycleConservation(ValidationCase):
    name = "nuclear_cycle_conservation"
    description = "Every configured nuclear cycle must conserve baryon number and charge in both forward and backward reactions."
    category = "nuclear"

    def required_runs(self) -> List[str]:
        return [RUN_NITROGEN_CYCLE]

    def evaluate(self, ctx: "RunContext") -> CaseResult:
        run = _need_run(ctx, RUN_NITROGEN_CYCLE)
        if run is None or run.scores is None:
            return _skip(self.name, self.description, self.category, RUN_NITROGEN_CYCLE)
        cycles = run.scores.get("nuclear_cycles") or []
        if not cycles:
            return CaseResult(
                name=self.name,
                description=self.description,
                category=self.category,
                status="skip",
                summary="no nuclear_cycles in scores (nuclear analysis disabled?)",
            )
        offenders = []
        for cycle in cycles:
            for direction in ("forward", "backward"):
                reaction = cycle.get(direction) or {}
                if not reaction.get("baryon_conserved", True):
                    offenders.append(f"{cycle.get('name')}.{direction}.baryon")
                if not reaction.get("charge_conserved", True):
                    offenders.append(f"{cycle.get('name')}.{direction}.charge")
        status = "pass" if not offenders else "fail"
        summary = (
            f"{len(cycles)} cycles all conserve baryon/charge"
            if not offenders
            else f"violations: {', '.join(offenders)}"
        )
        return CaseResult(
            name=self.name,
            description=self.description,
            category=self.category,
            status=status,
            summary=summary,
        )


class NuclearCycleQValueClosure(ValidationCase):
    name = "nuclear_cycle_q_value_closure"
    description = "For every cycle, |forward.Q + backward.Q| <= 1 MeV (closure under round-trip)."
    category = "nuclear"

    def required_runs(self) -> List[str]:
        return [RUN_NITROGEN_CYCLE]

    def evaluate(self, ctx: "RunContext") -> CaseResult:
        run = _need_run(ctx, RUN_NITROGEN_CYCLE)
        if run is None or run.scores is None:
            return _skip(self.name, self.description, self.category, RUN_NITROGEN_CYCLE)
        cycles = run.scores.get("nuclear_cycles") or []
        if not cycles:
            return CaseResult(
                name=self.name,
                description=self.description,
                category=self.category,
                status="skip",
                summary="no nuclear_cycles in scores",
            )
        rows = []
        worst = 0.0
        for cycle in cycles:
            qf = float((cycle.get("forward") or {}).get("q_value_mev") or 0.0)
            qb = float((cycle.get("backward") or {}).get("q_value_mev") or 0.0)
            closure = qf + qb
            worst = max(worst, abs(closure))
            rows.append(f"{cycle.get('name')}: Qf={qf:+.3f} Qb={qb:+.3f} sum={closure:+.3f} MeV")
        status = "pass" if worst <= 1.0 else "fail"
        return CaseResult(
            name=self.name,
            description=self.description,
            category=self.category,
            status=status,
            summary=f"worst |Qf+Qb| = {worst:.3f} MeV (tolerance 1 MeV)",
            measured=worst,
            expected=0.0,
            tolerance=1.0,
            notes=rows,
        )


# ---------- determinism / accounting cases ----------

class DeterminismReplay(ValidationCase):
    name = "determinism_replay"
    description = (
        "Re-running a deterministic scenario with the same seed must produce "
        "matching run-end scores (numerically-equal to within ~1e-9 relative; "
        "integer / string / boolean fields must be exactly equal). Strict "
        "byte-identical replay is *not* required because Geant4's MT "
        "accumulators sum doubles in a thread-arrival order that varies "
        "by 1 ULP between runs."
    )
    category = "determinism"

    REL_TOL = 1.0e-9

    def required_runs(self) -> List[str]:
        return [RUN_VIZ_REFRACTION, RUN_VIZ_REFRACTION_REPLAY]

    def _compare(self, a: Any, b: Any, path: str, mismatches: List[str]) -> None:
        if type(a) is not type(b):
            # Allow int/float equivalence.
            if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                pass
            else:
                mismatches.append(f"{path}: type {type(a).__name__} != {type(b).__name__}")
                return
        if isinstance(a, dict):
            keys = set(a.keys()) | set(b.keys())
            for k in sorted(keys):
                self._compare(a.get(k), b.get(k), f"{path}.{k}" if path else k, mismatches)
            return
        if isinstance(a, list):
            if len(a) != len(b):
                mismatches.append(f"{path}: list length {len(a)} != {len(b)}")
                return
            for i, (xa, xb) in enumerate(zip(a, b)):
                self._compare(xa, xb, f"{path}[{i}]", mismatches)
            return
        if isinstance(a, float) or isinstance(b, float):
            fa = float(a)
            fb = float(b)
            if fa == fb:
                return
            denom = max(abs(fa), abs(fb), 1.0e-300)
            if abs(fa - fb) / denom <= self.REL_TOL:
                return
            mismatches.append(
                f"{path}: float diff {fa!r} != {fb!r} (rel = {abs(fa - fb) / denom:.2e})"
            )
            return
        if a != b:
            mismatches.append(f"{path}: {a!r} != {b!r}")

    def evaluate(self, ctx: "RunContext") -> CaseResult:
        a = _need_run(ctx, RUN_VIZ_REFRACTION)
        b = _need_run(ctx, RUN_VIZ_REFRACTION_REPLAY)
        if a is None or b is None or a.scores is None or b.scores is None:
            return _skip(
                self.name,
                self.description,
                self.category,
                f"{RUN_VIZ_REFRACTION_REPLAY} (or original)",
            )
        mismatches: List[str] = []
        self._compare(a.scores, b.scores, "", mismatches)
        ok = not mismatches
        summary = (
            "all numeric fields agree within ~1e-9 relative; "
            "integers/strings/booleans exact-match"
            if ok
            else f"{len(mismatches)} field(s) diverge"
        )
        return CaseResult(
            name=self.name,
            description=self.description,
            category=self.category,
            status="pass" if ok else "fail",
            summary=summary,
            tolerance=f"rel<={self.REL_TOL}",
            notes=mismatches[:10],
        )


class PrimariesAccountingClosure(ValidationCase):
    name = "primaries_accounting_closure"
    description = "primaries_transmitted + primaries_absorbed == primaries_emitted (closure invariant)."
    category = "engine"

    def required_runs(self) -> List[str]:
        return [RUN_VIZ_REFRACTION]

    def evaluate(self, ctx: "RunContext") -> CaseResult:
        run = _need_run(ctx, RUN_VIZ_REFRACTION)
        if run is None or run.scores is None:
            return _skip(self.name, self.description, self.category, RUN_VIZ_REFRACTION)
        e = int(run.scores.get("primaries_emitted") or 0)
        t = int(run.scores.get("primaries_transmitted") or 0)
        a = int(run.scores.get("primaries_absorbed") or 0)
        ok = (t + a) == e
        return CaseResult(
            name=self.name,
            description=self.description,
            category=self.category,
            status="pass" if ok else "fail",
            summary=f"emitted={e}  transmitted={t}  absorbed={a}  (t+a={t+a})",
            measured={"emitted": e, "transmitted": t, "absorbed": a},
        )


class EventFeatureMeanConsistent(ValidationCase):
    name = "event_feature_mean_consistent_with_system_summary"
    description = (
        "OnlineEventStats mean(total_edep_mev) must match system_event_edep_mean_mev "
        "(same data feeds both)."
    )
    category = "engine"

    def required_runs(self) -> List[str]:
        return [RUN_VIZ_REFRACTION]

    def evaluate(self, ctx: "RunContext") -> CaseResult:
        run = _need_run(ctx, RUN_VIZ_REFRACTION)
        if run is None or run.scores is None:
            return _skip(self.name, self.description, self.category, RUN_VIZ_REFRACTION)
        stats = (run.scores.get("event_feature_stats") or {}).get("total_edep_mev") or {}
        stats_mean = float(stats.get("mean") or 0.0)
        system_mean = float(run.scores.get("system_event_edep_mean_mev") or 0.0)
        ok = _approx_equal(stats_mean, system_mean, rel=1.0e-9, abs_tol=1.0e-12)
        return CaseResult(
            name=self.name,
            description=self.description,
            category=self.category,
            status="pass" if ok else "fail",
            summary=f"stats.mean={stats_mean:.6e}  system.mean={system_mean:.6e}",
            measured=stats_mean,
            expected=system_mean,
            delta=stats_mean - system_mean,
        )


class SystemVolumeDensityArithmetic(ValidationCase):
    name = "system_volume_density_arithmetic"
    description = "system_edep_mev_per_mm3 == total_edep_mev / system_volume_mm3 (when volume > 0)."
    category = "engine"

    def required_runs(self) -> List[str]:
        return [RUN_VIZ_REFRACTION]

    def evaluate(self, ctx: "RunContext") -> CaseResult:
        run = _need_run(ctx, RUN_VIZ_REFRACTION)
        if run is None or run.scores is None:
            return _skip(self.name, self.description, self.category, RUN_VIZ_REFRACTION)
        total = float(run.scores.get("total_edep_mev") or 0.0)
        vol = float(run.scores.get("system_volume_mm3") or 0.0)
        emitted_density = float(run.scores.get("system_edep_mev_per_mm3") or 0.0)
        expected = total / vol if vol > 0 else 0.0
        ok = _approx_equal(emitted_density, expected, rel=1.0e-9, abs_tol=1.0e-15)
        return CaseResult(
            name=self.name,
            description=self.description,
            category=self.category,
            status="pass" if ok else "fail",
            summary=f"density={emitted_density:.6e}  total/vol={expected:.6e}",
            measured=emitted_density,
            expected=expected,
        )


# ---------- viz / output schema cases ----------

class VizSceneSchemaV1(ValidationCase):
    name = "viz_scene_schema_v1"
    description = "trech_viz_scene.json must declare schema == 'trech_viz_scene_v1'."
    category = "viz"

    def required_runs(self) -> List[str]:
        return [RUN_VIZ_REFRACTION]

    def evaluate(self, ctx: "RunContext") -> CaseResult:
        run = _need_run(ctx, RUN_VIZ_REFRACTION)
        if run is None or run.viz_scene is None:
            return _skip(self.name, self.description, self.category, RUN_VIZ_REFRACTION)
        schema = run.viz_scene.get("schema")
        ok = schema == "trech_viz_scene_v1"
        return CaseResult(
            name=self.name,
            description=self.description,
            category=self.category,
            status="pass" if ok else "fail",
            summary=f"schema={schema!r}",
        )


class VizTrajectoriesPointCount(ValidationCase):
    name = "viz_trajectories_point_count"
    description = "Recorded viz_segments must equal sum(len(points)) across the trajectories JSONL."
    category = "viz"

    def required_runs(self) -> List[str]:
        return [RUN_VIZ_REFRACTION]

    def evaluate(self, ctx: "RunContext") -> CaseResult:
        run = _need_run(ctx, RUN_VIZ_REFRACTION)
        if run is None or run.scores is None:
            return _skip(self.name, self.description, self.category, RUN_VIZ_REFRACTION)
        reported = int(run.scores.get("viz_segments") or 0)
        actual = sum(len(t.get("points") or []) for t in run.viz_trajectories)
        ok = reported == actual
        return CaseResult(
            name=self.name,
            description=self.description,
            category=self.category,
            status="pass" if ok else "fail",
            summary=f"scores.viz_segments={reported}  jsonl_total_points={actual}",
        )


class VizTrajectoryMinPoints(ValidationCase):
    name = "viz_trajectories_min_points"
    description = "Every recorded trajectory must have at least 2 points (otherwise it isn't a polyline)."
    category = "viz"

    def required_runs(self) -> List[str]:
        return [RUN_VIZ_REFRACTION]

    def evaluate(self, ctx: "RunContext") -> CaseResult:
        run = _need_run(ctx, RUN_VIZ_REFRACTION)
        if run is None or not run.viz_trajectories:
            return _skip(self.name, self.description, self.category, RUN_VIZ_REFRACTION)
        offenders = sum(1 for t in run.viz_trajectories if len(t.get("points") or []) < 2)
        ok = offenders == 0
        return CaseResult(
            name=self.name,
            description=self.description,
            category=self.category,
            status="pass" if ok else "fail",
            summary=f"{offenders}/{len(run.viz_trajectories)} trajectories below min-points threshold",
        )


class MaterialCompositionSumsToOne(ValidationCase):
    name = "material_composition_sums_to_one"
    description = "Every material in scene.materials must have component fractions summing to ~ 1.0."
    category = "config"

    def required_runs(self) -> List[str]:
        return [RUN_VIZ_REFRACTION]

    def evaluate(self, ctx: "RunContext") -> CaseResult:
        run = _need_run(ctx, RUN_VIZ_REFRACTION)
        if run is None or run.viz_scene is None:
            return _skip(self.name, self.description, self.category, RUN_VIZ_REFRACTION)
        offenders = []
        for m in run.viz_scene.get("materials") or []:
            components = m.get("components") or []
            if not components:
                continue
            s = sum(float(c.get("fraction") or 0.0) for c in components)
            if abs(s - 1.0) > 1.0e-6:
                offenders.append(f"{m.get('name')}={s:.6f}")
        status = "pass" if not offenders else "fail"
        summary = (
            "all material fractions sum to 1.0"
            if not offenders
            else f"non-unity fractions: {', '.join(offenders)}"
        )
        return CaseResult(
            name=self.name,
            description=self.description,
            category=self.category,
            status=status,
            summary=summary,
        )


# ---------- ML / Torch cases ----------

class EventFeatureStatsTorchBackedFlag(ValidationCase):
    name = "event_feature_stats_torch_backed_flag"
    description = (
        "Reports whether OnlineEventStats ran with Torch acceleration. "
        "This is informational — the Welford fallback is correct either way."
    )
    category = "ml"

    def required_runs(self) -> List[str]:
        return [RUN_VIZ_REFRACTION]

    def evaluate(self, ctx: "RunContext") -> CaseResult:
        run = _need_run(ctx, RUN_VIZ_REFRACTION)
        if run is None or run.scores is None:
            return _skip(self.name, self.description, self.category, RUN_VIZ_REFRACTION)
        flag = bool(run.scores.get("event_feature_stats_torch_backed"))
        return CaseResult(
            name=self.name,
            description=self.description,
            category=self.category,
            status="info",
            summary=f"torch_backed = {flag}",
            measured=flag,
        )


# ---------- scenario regression cases ----------

class H2oFluidBrineRunCloses(ValidationCase):
    name = "h2o_fluid_brine_run_closes"
    description = (
        "The H2O brine fluid scenario (a Sputnik-milestone scenario) runs to "
        "completion, deposits energy in the brine volume, and closes its primary "
        "accounting. Guards the element-component + fail-safe material build that "
        "fixed the G4_SODIUM_CHLORIDE SIGSEGV: a regression that crashes the run "
        "produces no run-end scores and lands here as a fail."
    )
    category = "scenario"

    def required_runs(self) -> List[str]:
        return [RUN_H2O_FLUID]

    def evaluate(self, ctx: "RunContext") -> CaseResult:
        run = _need_run(ctx, RUN_H2O_FLUID)
        if run is None:
            return _skip(self.name, self.description, self.category, RUN_H2O_FLUID)
        if run.scores is None:
            # Output dir present but no run-end record: the run did not finish.
            # A regression of the material SIGSEGV would surface exactly here.
            return CaseResult(
                name=self.name,
                description=self.description,
                category=self.category,
                status="fail",
                summary="no run-end scores in out_h2o_fluid (run did not complete — crash?)",
            )
        edep = float(run.scores.get("total_edep_mev") or 0.0)
        vol_edep = run.scores.get("volume_edep_mev") or {}
        brine_edep = float(vol_edep.get("fluid_bulk") or 0.0)
        e = int(run.scores.get("primaries_emitted") or 0)
        t = int(run.scores.get("primaries_transmitted") or 0)
        a = int(run.scores.get("primaries_absorbed") or 0)
        closes = (t + a) == e and e > 0
        deposits = edep > 0.0 and brine_edep > 0.0
        ok = closes and deposits
        return CaseResult(
            name=self.name,
            description=self.description,
            category=self.category,
            status="pass" if ok else "fail",
            summary=(
                f"total_edep={edep:.4f} MeV  brine(fluid_bulk)_edep={brine_edep:.4f} MeV  "
                f"primaries emitted={e} transmitted={t} absorbed={a} (closes={closes})"
            ),
            # Round the MT-accumulated edep to keep the committed report
            # byte-stable: thread-arrival summation order perturbs the last ULP
            # (the determinism invariant tolerates this at 1e-9), which is not a
            # meaningful physics signal.
            measured={
                "total_edep_mev": round(edep, 6),
                "fluid_bulk_edep_mev": round(brine_edep, 6),
                "emitted": e,
                "transmitted": t,
                "absorbed": a,
            },
        )


# ---------- fluid statistical-mechanics cases ----------

class PascalPrincipleHolds(ValidationCase):
    name = "pascal_principle_holds"
    description = (
        "Pascal's-principle scenario: a hook-driven 2D H2O bath transmits a "
        "piston pressure to a sensor wall. In the rigid vessel the wall barely "
        "moves (pressure transmitted undiminished -> Pascal holds); in the "
        "Hookean/plastic deformable vessel the wall expands, damps the pressure, "
        "and keeps a bounded permanent set after release. "
        "Asserts the scenario's own validation booleans plus rigid << deformable "
        "wall displacement -- guards the fluid/pressure hook path and the "
        "renderer-facing wall-profile emits."
    )
    category = "fluid"

    def required_runs(self) -> List[str]:
        return [RUN_PASCAL]

    def evaluate(self, ctx: "RunContext") -> CaseResult:
        run = _need_run(ctx, RUN_PASCAL)
        if run is None:
            return _skip(self.name, self.description, self.category, RUN_PASCAL)
        v = _last_emit_payload(run, "pascal_summary")
        if not v or "validation" not in v:
            return CaseResult(
                name=self.name, description=self.description, category=self.category,
                status="fail", summary="no pascal_summary emit (run incomplete?)")
        val = v["validation"]
        rigid = float(val.get("rigid_wall_displacement") or 0.0)
        deform = float(val.get("deformable_wall_displacement") or 0.0)
        deform_result = {}
        for item in v.get("results") or []:
            if item.get("bucket") == "deformable_hookean":
                deform_result = item
                break
        elastic = float(deform_result.get("mean_elastic_wall_displacement") or 0.0)
        plastic = float(deform_result.get("mean_plastic_wall_displacement") or 0.0)
        holds = bool(val.get("pascal_principle_holds"))
        damping = bool(val.get("plastic_damping_observed"))
        contrast = deform > rigid * 10.0  # deformable wall moves much more
        ok = holds and damping and contrast
        return CaseResult(
            name=self.name, description=self.description, category=self.category,
            status="pass" if ok else "fail",
            summary=(f"pascal_holds={holds} damping={damping} "
                     f"rigid_disp={rigid:.3e} deformable_disp={deform:.3e} "
                     f"(contrast x{(deform / rigid) if rigid else float('inf'):.0f})"),
            measured={"rigid_wall_displacement": rigid,
                      "deformable_wall_displacement": deform,
                      "deformable_elastic_wall_displacement": elastic,
                      "deformable_plastic_wall_displacement": plastic})


class OsmoticShiftObserved(ValidationCase):
    name = "osmotic_shift_observed"
    description = (
        "Cell-in-hypertonic-bath scenario: a selectively permeable membrane "
        "passes water but expels wrong-polarized molecules (large glucose by "
        "size, small ions by polarity), and a turgor-driven spring membrane "
        "crenates as water leaves. Asserts dimensional AND polarity exclusion, "
        "net water shift, early pore crossings, macroscopic flux growth, "
        "bounded thermostat energy, the late-phase pressure bias, and a stable "
        "membrane that visibly shrinks (crenation) -- guards the membrane/"
        "diffusion hook path against trivial, overheated or unstable dynamics."
    )
    category = "fluid"

    def required_runs(self) -> List[str]:
        return [RUN_OSMOTIC]

    def evaluate(self, ctx: "RunContext") -> CaseResult:
        run = _need_run(ctx, RUN_OSMOTIC)
        if run is None:
            return _skip(self.name, self.description, self.category, RUN_OSMOTIC)
        v = _last_emit_payload(run, "final_summary")
        if not v or "validation" not in v:
            return CaseResult(
                name=self.name, description=self.description, category=self.category,
                status="fail", summary="no final_summary emit (run incomplete?)")
        val = v["validation"]
        required = {
            "dimensional_exclusion_holds": bool(val.get("dimensional_exclusion_holds")),
            "polarity_exclusion_holds": bool(val.get("polarity_exclusion_holds")),
            "osmotic_shift_observed": bool(val.get("osmotic_shift_observed")),
            "early_crossovers_observed": bool(val.get("early_crossovers_observed")),
            "macroscopic_flux_observed": bool(val.get("macroscopic_flux_observed")),
            "thermal_energy_bounded": bool(val.get("thermal_energy_bounded")),
            "pressure_response_observed": bool(val.get("pressure_response_observed")),
            "membrane_crenation_observed": bool(val.get("membrane_crenation_observed")),
            "membrane_stable": bool(val.get("membrane_stable")),
        }
        ok = all(required.values())
        target_ke = float(v.get("target_mean_kinetic_energy") or 0.0)
        max_ke = float(v.get("max_observed_mean_kinetic_energy") or 0.0)
        late_pressure = v.get("late_pressure_average") or {}
        late_internal = float(late_pressure.get("internal") or 0.0)
        late_external = float(late_pressure.get("external") or 0.0)
        pressure_ratio = late_external / late_internal if late_internal else float("inf")
        return CaseResult(
            name=self.name, description=self.description, category=self.category,
            status="pass" if ok else "fail",
            summary=(f"checks={sum(1 for passed in required.values() if passed)}/"
                     f"{len(required)} net_water_flux_out={v.get('net_water_flux_out')} "
                     f"first_crossing_tick={v.get('first_crossing_tick')} "
                     f"max_ke={max_ke:.3g}/{target_ke:.3g} "
                     f"late_pressure_external/internal={pressure_ratio:.3g}"),
            measured={
                **required,
                "net_water_flux_out": v.get("net_water_flux_out"),
                "wrong_polarized_rejections": v.get("wrong_polarized_rejections"),
                "first_crossing_tick": v.get("first_crossing_tick"),
                "initial_water_gradient": v.get("initial_water_gradient"),
                "final_water_gradient": v.get("final_water_gradient"),
                "target_mean_kinetic_energy": target_ke,
                "max_observed_mean_kinetic_energy": max_ke,
                "late_pressure_average": late_pressure,
                "membrane": v.get("membrane"),
                "milestones": v.get("milestones"),
            },
            expected={
                "all_validation_flags": True,
                "max_observed_mean_kinetic_energy": "<= 2.5 * target",
                "late_pressure_external": "> late_pressure_internal",
                "final_water_gradient": "< initial_water_gradient",
            })


class EffluxFirstOrderKinetics(ValidationCase):
    name = "efflux_first_order_kinetics"
    description = (
        "Membrane-efflux scenario: a cell clears a lipophilic 'waste' molecule "
        "(benzene) by passive permeation across the lipid bilayer into an "
        "extracellular sink while retaining its polar essential (D-glucose). "
        "Runtime-fetched PubChem XLogP (Overton's rule) sets WHICH molecule "
        "permeates (benzene +2.1 vs glucose -2.6); a Geant4-derived "
        "membrane/cytosol EM interaction ratio (G4EmCalculator; illustrative) "
        "and per-event Geant4 transport statistics from ctx.event scale HOW FAST. "
        "Asserts that the "
        "directed-drift/diffusion permeation reproduces the macroscopic "
        "first-order clearance law N(t)=N0*exp(-k t) (log-linear fit R^2 >= 0.97), "
        "the waste is cleared, the essentials are retained, the Geant4 anchors are "
        "present, and the PubChem lipophilicity selectivity holds -- the "
        "PubChem+Geant4 -> mesoscale -> closed-form comparison surface."
    )
    category = "fluid"

    def required_runs(self) -> List[str]:
        return [RUN_EFFLUX]

    def evaluate(self, ctx: "RunContext") -> CaseResult:
        run = _need_run(ctx, RUN_EFFLUX)
        if run is None:
            return _skip(self.name, self.description, self.category, RUN_EFFLUX)
        v = _last_emit_payload(run, "efflux_summary")
        if not v or "validation" not in v:
            return CaseResult(
                name=self.name, description=self.description, category=self.category,
                status="fail", summary="no efflux_summary emit (run incomplete?)")
        val = v["validation"]
        required = {
            "first_order_kinetics": bool(val.get("first_order_kinetics")),
            "waste_cleared": bool(val.get("waste_cleared")),
            "essentials_retained": bool(val.get("essentials_retained")),
            "geant4_param_present": bool(val.get("geant4_param_present")),
            "geant4_event_drive_present": bool(val.get("geant4_event_drive_present")),
            "lipophilicity_selectivity": bool(val.get("lipophilicity_selectivity")),
        }
        ok = all(required.values())
        fit = v.get("fit") or {}
        g4 = v.get("geant4") or {}
        pub = v.get("pubchem") or {}
        r2 = float(fit.get("r_squared") or 0.0)
        half_life = float(fit.get("half_life_ticks") or 0.0)
        ratio = float(g4.get("interaction_ratio") or 0.0)
        event_drive = g4.get("event_drive") or {}
        g4_steps = int(event_drive.get("total_step_count") or 0)
        mean_activation = float(event_drive.get("mean_activation") or 0.0)
        return CaseResult(
            name=self.name, description=self.description, category=self.category,
            status="pass" if ok else "fail",
            summary=(f"checks={sum(1 for p in required.values() if p)}/{len(required)} "
                     f"R2={r2:.3f} half_life={half_life:.0f}t "
                     f"cleared={v.get('total_cleared')}/{v.get('initial_waste')} "
                     f"retained={v.get('retained_inside')} g4_ratio={ratio:.3f} "
                     f"g4_steps={g4_steps}"),
            measured={
                **required,
                "fit_r_squared": r2,
                "rate_per_tick": fit.get("rate_per_tick"),
                "half_life_ticks": half_life,
                "permeability_eff_units_per_tick": fit.get("permeability_eff_units_per_tick"),
                "initial_waste": v.get("initial_waste"),
                "final_waste_inside": v.get("final_waste_inside"),
                "total_cleared": v.get("total_cleared"),
                "retained_inside": v.get("retained_inside"),
                "geant4_interaction_ratio": ratio,
                "geant4_mu_membrane_per_mm": g4.get("mu_membrane_per_mm"),
                "geant4_mu_cytosol_per_mm": g4.get("mu_cytosol_per_mm"),
                "geant4_event_drive": event_drive,
                "geant4_mean_activation": mean_activation,
                "pubchem_permeant": (pub.get("permeant") or {}).get("name"),
                "pubchem_permeant_xlogp": (pub.get("permeant") or {}).get("xlogp"),
                "pubchem_retained": (pub.get("retained") or {}).get("name"),
                "pubchem_retained_xlogp": (pub.get("retained") or {}).get("xlogp"),
            },
            expected={
                "first_order_fit_r_squared": ">= 0.97",
                "waste_cleared": "final inside <= 0.2 * initial",
                "essentials_retained": "all polar molecules kept",
                "geant4_param_present": True,
                "geant4_event_drive_present": "positive event steps/activation from ctx.event",
                "lipophilicity_selectivity": "permeant XLogP > 0 > retained XLogP (Overton)",
            })


class BeakerWaterPentaneInference(ValidationCase):
    name = "beaker_water_n_pentane_inference"
    description = (
        "Open-beaker water+n-pentane observer experiment. Runtime substance facts start from "
        "Geant4 G4_WATER/G4_N-PENTANE material probes and Geant4-derived optics; PubChem is "
        "limited to CID+SMILES structure. A two-stage cascade infers immiscible layer order and "
        "60-minute evaporation. Density, colourlessness, vapour pressure, and disposition "
        "references grade the emitted result only and never feed the scenario state."
    )
    category = "fluid"

    def required_runs(self) -> List[str]:
        return [RUN_BEAKER_WATER_PENTANE]

    def evaluate(self, ctx: "RunContext") -> CaseResult:
        run = _need_run(ctx, RUN_BEAKER_WATER_PENTANE)
        if run is None:
            return _skip(self.name, self.description, self.category, RUN_BEAKER_WATER_PENTANE)
        value = _last_emit_payload(run, "beaker_summary")
        if not value or "validation" not in value:
            return CaseResult(
                name=self.name, description=self.description, category=self.category,
                status="fail", summary="no beaker_summary emit (run incomplete?)")
        validation = value.get("validation") or {}
        required = {
            "geant4_base_present": bool(validation.get("geant4_base_present")),
            "pubchem_structure_only": bool(validation.get("pubchem_structure_only")),
            "colour_from_geant4": bool(validation.get("colour_from_geant4")),
            "immiscible_layers_inferred": bool(validation.get("immiscible_layers_inferred")),
            "volatility_holdout_close": bool(validation.get("volatility_holdout_close")),
            "evaporation_mass_conserved": bool(validation.get("evaporation_mass_conserved")),
            "sixty_minutes_reached": bool(validation.get("sixty_minutes_reached")),
        }
        structure = value.get("structure") or {}
        forbidden = {"xlogp", "molecular_weight", "density", "boiling_point", "vapour_pressure"}
        structure_clean = all(
            not (forbidden & set((compound or {}).keys())) for compound in structure.values()
        )
        required["pubchem_payload_has_no_physical_properties"] = structure_clean
        evaporation = value.get("evaporation") or {}
        disposition = value.get("disposition") or {}
        gaps = value.get("validation_gaps") or {}
        fraction = float(evaporation.get("fraction_evaporated") or 0.0)
        mass = float(evaporation.get("evaporated_mass_g") or 0.0)
        vp = float(evaporation.get("predicted_vapour_pressure_kpa") or 0.0)
        ok = all(required.values()) and 0.0 < fraction < 1.0 and mass > 0.0
        return CaseResult(
            name=self.name, description=self.description, category=self.category,
            status="pass" if ok else "fail",
            summary=(f"checks={sum(required.values())}/{len(required)} "
                     f"pentane_top={disposition.get('n_pentane_on_top')} "
                     f"evaporated={fraction:.1%} ({mass:.3g} g/60 min) "
                     f"heldout_Pvap={vp:.2f} kPa"),
            measured={
                **required,
                "fraction_evaporated_60min": fraction,
                "fraction_sigma": evaporation.get("fraction_sigma"),
                "evaporated_mass_g": mass,
                "remaining_mass_g": evaporation.get("remaining_mass_g"),
                "predicted_vapour_pressure_kpa": vp,
                "vapour_pressure_relative_gap": gaps.get("pentane_vapour_pressure_relative"),
                "density_relative_gap": gaps.get("pentane_density_relative"),
                "phase_separation_score": disposition.get("phase_separation_score"),
                "pentane_upper_score": disposition.get("pentane_upper_score"),
            },
            expected={
                "runtime_inputs": "Geant4 material+optics; PubChem CID+SMILES only",
                "disposition": "immiscible, lower-density n-pentane upper layer",
                "heldout_vapour_pressure": "within 15% of 57.3 kPa @293 K",
                "evaporation": "0 < inferred fraction < 1 with mass closure at 60 min",
            },
            delta={"vapour_pressure_relative": gaps.get("pentane_vapour_pressure_relative")},
            tolerance={"vapour_pressure_relative": 0.15},
        )


class H2oElectrolysisCombustionCycle(ValidationCase):
    name = "h2o_electrolysis_combustion_cycle"
    description = (
        "Two-cathode water-electrolysis scenario followed by inverse combustion: "
        "a deterministic hook-layer reaction-inference bath parses PubChem "
        "formulas for water, hydrogen, and oxygen, splits H/O inventories at two "
        "cathodes plus an oxygen collector, and then ignites H2/O2 back to H2O. "
        "Geant4 contributes event-by-event e- energy deposition / track "
        "statistics plus G4EmCalculator interaction fingerprints for H2O/H2/O2; "
        "those anchors directly scale the stochastic mesoscale rates and are "
        "re-emitted as analytic_checks. "
        "Asserts PubChem grounding, Geant4 anchor presence, 2:1 H2/O2 "
        "electrolysis stoichiometry, both cathodes active and balanced, exact "
        "atom conservation, high water recovery after combustion, and that the "
        "engine did not add a hard-coded reaction rule."
    )
    category = "fluid"

    def required_runs(self) -> List[str]:
        return [RUN_H2O_CYCLE]

    def evaluate(self, ctx: "RunContext") -> CaseResult:
        run = _need_run(ctx, RUN_H2O_CYCLE)
        if run is None:
            return _skip(self.name, self.description, self.category, RUN_H2O_CYCLE)
        v = _last_emit_payload(run, "h2o_cycle_summary")
        if not v or "validation" not in v:
            return CaseResult(
                name=self.name, description=self.description, category=self.category,
                status="fail", summary="no h2o_cycle_summary emit (run incomplete?)")
        val = v["validation"]
        g4 = v.get("geant4") or {}
        drive = g4.get("event_drive") or {}
        required = {
            "pubchem_properties_present": bool(val.get("pubchem_properties_present")),
            "geant4_anchor_present": bool(val.get("geant4_anchor_present")),
            "electrolysis_stoichiometry": bool(val.get("electrolysis_stoichiometry")),
            "two_cathodes_active": bool(val.get("two_cathodes_active")),
            "atom_conservation": bool(val.get("atom_conservation")),
            "inverse_combustion_recovered_water":
                bool(val.get("inverse_combustion_recovered_water")),
            "no_engine_reaction_rule": bool(val.get("no_engine_reaction_rule")),
        }
        checks = {
            (c.get("label") or ""): c
            for c in ((run.scores or {}).get("analytic_checks") or [])
        }
        labels = [
            "h2o_cycle_water_interaction",
            "h2o_cycle_hydrogen_interaction",
            "h2o_cycle_oxygen_interaction",
        ]
        analytic_labels_present = all(
            label in checks and bool(checks[label].get("available"))
            for label in labels
        )
        required["analytic_checks_emitted"] = analytic_labels_present
        geant4_event_drive_present = (
            int(drive.get("events") or 0) > 0 and
            float(drive.get("total_edep_mev") or 0.0) > 0.0 and
            float(drive.get("mean_activation") or 0.0) > 0.0
        )
        required["geant4_event_drive_present"] = geant4_event_drive_present
        ok = all(required.values())
        electro = v.get("electrolysis") or {}
        combust = v.get("combustion") or {}
        h2_to_o2 = float(electro.get("h2_to_o2_ratio") or 0.0)
        recovered = float(combust.get("recovered_water_fraction") or 0.0)
        imbalance = float(electro.get("cathode_imbalance_fraction") or 0.0)
        mu = {
            label: checks.get(label, {}).get("mu_total_per_mm")
            for label in labels
        }
        return CaseResult(
            name=self.name, description=self.description, category=self.category,
            status="pass" if ok else "fail",
            summary=(f"checks={sum(1 for p in required.values() if p)}/{len(required)} "
                     f"H2/O2={h2_to_o2:.3g} recovered={recovered:.1%} "
                     f"cathode_imbalance={imbalance:.3g} "
                     f"water={combust.get('water_recombined')} "
                     f"g4_edep={float(drive.get('total_edep_mev') or 0.0):.3g}MeV"),
            measured={
                **required,
                "h2_to_o2_ratio": h2_to_o2,
                "hydrogen_left_cathode": electro.get("hydrogen_left_cathode"),
                "hydrogen_right_cathode": electro.get("hydrogen_right_cathode"),
                "oxygen_total": electro.get("oxygen_total"),
                "cathode_imbalance_fraction": imbalance,
                "water_dissociated": electro.get("water_dissociated"),
                "water_recombined": combust.get("water_recombined"),
                "recovered_water_fraction": recovered,
                "final_hydrogen": combust.get("final_hydrogen"),
                "final_oxygen": combust.get("final_oxygen"),
                "geant4_mu_total_per_mm": mu,
                "geant4_event_drive": drive,
                "pubchem_cids": {
                    "water": ((v.get("pubchem") or {}).get("water") or {}).get("cid"),
                    "hydrogen": ((v.get("pubchem") or {}).get("hydrogen") or {}).get("cid"),
                    "oxygen": ((v.get("pubchem") or {}).get("oxygen") or {}).get("cid"),
                },
            },
            expected={
                "h2_to_o2_ratio": "2.0 after electrolysis",
                "both_cathodes": "left/right cathodes each collect H2",
                "recovered_water_fraction": ">= 0.94 after combustion",
                "atom_conservation": "initial == after_electrolysis == final",
                "analytic_checks": labels,
                "geant4_event_drive": "positive event edep/activation from ctx.event",
            })


class OpticsSurrogateTransportApplied(ValidationCase):
    name = "optics_surrogate_transport_applied"
    description = (
        "The opt-in ridge optics surrogate (LibTorch-free) corrects a material "
        "the f-sum extractor cannot reach and feeds it to transport. For NaI the "
        "extractor derives n~1.33 (the high-Z valence response is missed); the "
        "anchor-trained surrogate lifts it to ~1.77 (handbook 1.775). Asserts the "
        "surrogate override note is present AND the per-energy RINDEX samples "
        "(not just the scalar mean) sit at the surrogate level -- guarding the "
        "end-to-end curve-shift wiring in GeantRunner."
    )
    category = "ml"

    def required_runs(self) -> List[str]:
        return [RUN_OPTICS_SURROGATE]

    def evaluate(self, ctx: "RunContext") -> CaseResult:
        run = _need_run(ctx, RUN_OPTICS_SURROGATE)
        if run is None or run.viz_scene is None:
            return _skip(self.name, self.description, self.category, RUN_OPTICS_SURROGATE)
        nai = _derived_by_name(run.viz_scene).get("nai")
        if nai is None:
            return CaseResult(
                name=self.name, description=self.description, category=self.category,
                status="fail", summary="nai derived_optics missing from surrogate run")
        mean_n = float(nai.get("mean_refractive_index") or 0.0)
        samples = nai.get("samples") or []
        sample_ns = [float(s.get("refractive_index") or 0.0) for s in samples]
        min_sample = min(sample_ns) if sample_ns else 0.0
        note_applied = "surrogate" in (nai.get("note") or "").lower()
        # Extractor ~1.33, surrogate ~1.77; 1.6 cleanly separates the two, and
        # requiring the *samples* (transport RINDEX source) to clear it proves
        # the curve was actually shifted, not just the reported scalar mean.
        lifted = mean_n > 1.6 and min_sample > 1.6
        ok = note_applied and lifted
        return CaseResult(
            name=self.name, description=self.description, category=self.category,
            status="pass" if ok else "fail",
            summary=(f"nai mean_n={mean_n:.4f} min_sample_n={min_sample:.4f} "
                     f"surrogate_note={note_applied} (extractor would be ~1.33)"),
            measured={"mean_n": mean_n, "min_sample_n": min_sample,
                      "surrogate_note": note_applied},
            expected="n > 1.6 (surrogate level) with override note")


class GenericSurrogateInference(ValidationCase):
    name = "generic_surrogate_inference"
    description = (
        "Generic Torch surrogate usable in ANY scenario: a scenario declares a "
        "model in the physics-agnostic models[] config collection and a hook "
        "calls ctx.predict(name, features) -> named outputs. The demo "
        "(surrogate_generic_demo.js) declares the committed optics ridge model "
        "and, in predictive mode, asks it for water's refractive index each "
        "event. Asserts the model loaded (models_loaded contains 'optics_n'), "
        "ctx.predict was exercised and counted (hook_predict_count > 0), and the "
        "predicted refractive index sits in a physical band (~1.33 for water, "
        "handbook 1.333) -- guarding the models[]/ctx.predict/GenericSurrogate "
        "path end to end."
    )
    category = "ml"

    def required_runs(self) -> List[str]:
        return [RUN_SURROGATE_GENERIC]

    def evaluate(self, ctx: "RunContext") -> CaseResult:
        run = _need_run(ctx, RUN_SURROGATE_GENERIC)
        if run is None or run.scores is None:
            return _skip(self.name, self.description, self.category,
                         RUN_SURROGATE_GENERIC)
        scores = run.scores
        predict_count = int(scores.get("hook_predict_count") or 0)
        models_loaded = scores.get("models_loaded") or []
        model_ok = "optics_n" in models_loaded
        # Predicted refractive index from the per-event emit sideband.
        preds = [e.get("payload", {}).get("refractive_index")
                 for e in run.hook_emits
                 if e.get("tag") == "predicted_optics"]
        preds = [float(p) for p in preds if isinstance(p, (int, float))]
        n_pred = preds[0] if preds else 0.0
        # All events use the same water composition -> identical deterministic n.
        n_stable = bool(preds) and (max(preds) - min(preds) < 1e-9)
        n_physical = 1.2 < n_pred < 1.45  # water ~1.33
        ok = model_ok and predict_count > 0 and n_physical and n_stable
        return CaseResult(
            name=self.name, description=self.description, category=self.category,
            status="pass" if ok else "fail",
            summary=(f"models_loaded={models_loaded} "
                     f"hook_predict_count={predict_count} "
                     f"predicted_water_n={n_pred:.4f} (n_events={len(preds)}, "
                     f"stable={n_stable})"),
            measured={"hook_predict_count": predict_count,
                      "models_loaded": models_loaded,
                      "predicted_water_n": n_pred},
            expected="optics_n loaded, hook_predict_count>0, water n in (1.2,1.45)")


# ---------- anti-degeneration (standing objective) cases ----------

class SamplingDiversityNonDegenerate(ValidationCase):
    name = "sampling_diversity_non_degenerate"
    description = (
        "Anti-degeneration standing objective: a varied-beam run must sample a "
        "real distribution, not one repeated primary (the baseline degenerate "
        "glass-of-water run was 1 exit point / 0deg / 0nm). From the varied run, "
        "asserts >1 distinct primary exit point, a positive incidence-angle "
        "spread (divergence cone), and a positive emission-wavelength spread "
        "(energy band) -- guarding the beam spot/divergence/energy-spread "
        "sampling against a regression back to a degenerate run."
    )
    category = "degeneration"

    def required_runs(self) -> List[str]:
        return [RUN_GOW_VARIED]

    @staticmethod
    def _angle_from_z(dx: float, dy: float, dz: float) -> Optional[float]:
        mag = math.sqrt(dx * dx + dy * dy + dz * dz)
        if mag <= 0.0:
            return None
        return math.degrees(math.acos(min(1.0, abs(dz) / mag)))

    def evaluate(self, ctx: "RunContext") -> CaseResult:
        run = _need_run(ctx, RUN_GOW_VARIED)
        if run is None or not run.viz_trajectories:
            return _skip(self.name, self.description, self.category, RUN_GOW_VARIED)
        exits = set()
        incidence: List[float] = []
        wavelengths: List[float] = []
        for traj in run.viz_trajectories:
            pts = traj.get("points") or []
            if len(pts) < 2:
                continue
            last = pts[-1]
            exits.add((round(last.get("x_mm", 0.0), 1),
                       round(last.get("y_mm", 0.0), 1),
                       round(last.get("z_mm", 0.0), 1)))
            # Use the first-segment displacement (pts[1]-pts[0]) for the
            # incidence direction, matching scripts/degeneration_metrics.py. It
            # is geometry-derived and robust, and now agrees with the per-point
            # stored dx/dy/dz at the emission point (the recorder used to store
            # the post-step direction there; fixed in SteppingAction).
            first, second = pts[0], pts[1]
            ang = self._angle_from_z(
                second.get("x_mm", 0.0) - first.get("x_mm", 0.0),
                second.get("y_mm", 0.0) - first.get("y_mm", 0.0),
                second.get("z_mm", 0.0) - first.get("z_mm", 0.0))
            if ang is not None:
                incidence.append(ang)
            e0 = float(first.get("energy_ev") or 0.0)
            if e0 > 0.0:
                wavelengths.append(1239.841984 / e0)

        def sd(xs: List[float]) -> float:
            return statistics.pstdev(xs) if len(xs) > 1 else 0.0

        n_exits = len(exits)
        inc_sd = sd(incidence)
        wl_sd = sd(wavelengths)
        ok = n_exits > 1 and inc_sd > 0.0 and wl_sd > 0.0
        return CaseResult(
            name=self.name, description=self.description, category=self.category,
            status="pass" if ok else "fail",
            summary=(f"distinct_exit_points={n_exits} "
                     f"incidence_stddev={inc_sd:.3f}deg "
                     f"wavelength_stddev={wl_sd:.2f}nm "
                     f"(degenerate baseline = 1 / 0 / 0)"),
            measured={"distinct_exit_points": n_exits,
                      "incidence_stddev_deg": round(inc_sd, 3),
                      "wavelength_stddev_nm": round(wl_sd, 2)},
            expected="distinct_exit_points>1, incidence_stddev>0, wavelength_stddev>0")


# ---------- Sputnik north-star: single-molecule stability ----------

class H2oMoleculeBondsStable(ValidationCase):
    name = "h2o_molecule_bonds_stable"
    description = (
        "Sputnik north-star item: a single H2O molecule, evolved by a classical "
        "flexible-water MD integrator in the hook layer (the three nuclei bound "
        "by harmonic O-H bonds + H-O-H angle, velocity-Verlet NVE), must stay "
        "bound and energy-conserving over time -- 'stable without exploding'. "
        "Asserts the scenario's own validation: no bond ever exceeds 1.6x "
        "equilibrium, mean bond/angle stay near equilibrium (0.957 A / 104.52 "
        "deg), and total energy drifts <2% over the run."
    )
    category = "molecule"

    def required_runs(self) -> List[str]:
        return [RUN_H2O_MOLECULE]

    def evaluate(self, ctx: "RunContext") -> CaseResult:
        run = _need_run(ctx, RUN_H2O_MOLECULE)
        if run is None:
            return _skip(self.name, self.description, self.category, RUN_H2O_MOLECULE)
        p = _last_emit_payload(run, "molecule_summary")
        if not p or "validation" not in p:
            return CaseResult(
                name=self.name, description=self.description, category=self.category,
                status="fail", summary="no molecule_summary emit (run incomplete?)")
        val = p["validation"]
        ok = bool(val.get("stable_without_exploding"))
        return CaseResult(
            name=self.name, description=self.description, category=self.category,
            status="pass" if ok else "fail",
            summary=(f"stable={ok} mean_bond={p.get('mean_bond_A', 0):.4f}A "
                     f"max_bond={p.get('max_bond_A', 0):.4f}A "
                     f"mean_angle={p.get('mean_angle_deg', 0):.2f}deg "
                     f"energy_drift={p.get('energy_drift_fraction', 0) * 100:.3f}% "
                     f"(r0=0.9572A, theta0=104.52deg)"),
            measured={"mean_bond_A": round(float(p.get("mean_bond_A") or 0.0), 4),
                      "max_bond_A": round(float(p.get("max_bond_A") or 0.0), 4),
                      "mean_angle_deg": round(float(p.get("mean_angle_deg") or 0.0), 2),
                      "energy_drift_fraction": round(float(p.get("energy_drift_fraction") or 0.0), 5),
                      "bonds_stable": bool(val.get("bonds_stable")),
                      "energy_conserved": bool(val.get("energy_conserved"))},
            expected="stable_without_exploding (bonds bounded near r0, energy drift <2%)")


class H2oClusterFluidStable(ValidationCase):
    name = "h2o_cluster_fluid_stable"
    description = (
        "Sputnik 'simulate H2O fluid behavior' step: a small ensemble of water "
        "molecules (classical flexible-SPC MD in the hook layer -- intramolecular "
        "harmonic bonds/angle + intermolecular LJ(O-O)/Coulomb, thermostatted, "
        "with a soft droplet boundary standing in for the bulk) must form a "
        "STABLE, hydrogen-bonded, thermostatted droplet -- emergent liquid-like "
        "behavior. Asserts the scenario's validation: the cluster neither "
        "evaporates nor collapses, temperature holds near target, and O-O "
        "hydrogen-bond contacts persist."
    )
    category = "fluid"

    def required_runs(self) -> List[str]:
        return [RUN_H2O_CLUSTER]

    def evaluate(self, ctx: "RunContext") -> CaseResult:
        run = _need_run(ctx, RUN_H2O_CLUSTER)
        if run is None:
            return _skip(self.name, self.description, self.category, RUN_H2O_CLUSTER)
        p = _last_emit_payload(run, "cluster_summary")
        if not p or "validation" not in p:
            return CaseResult(
                name=self.name, description=self.description, category=self.category,
                status="fail", summary="no cluster_summary emit (run incomplete?)")
        val = p["validation"]
        ok = bool(val.get("fluid_stable"))
        return CaseResult(
            name=self.name, description=self.description, category=self.category,
            status="pass" if ok else "fail",
            summary=(f"stable={ok} molecules={p.get('molecules')} "
                     f"mean_T={p.get('mean_temperature_K', 0):.1f}K "
                     f"mean_hbonds={p.get('mean_hbond_contacts', 0):.2f} "
                     f"mean_Rg={p.get('mean_radius_of_gyration_A', 0):.3f}A "
                     f"max_Rg={p.get('max_radius_of_gyration_A', 0):.3f}A"),
            measured={"mean_temperature_K": round(float(p.get("mean_temperature_K") or 0.0), 1),
                      "mean_hbond_contacts": round(float(p.get("mean_hbond_contacts") or 0.0), 2),
                      "mean_radius_of_gyration_A": round(float(p.get("mean_radius_of_gyration_A") or 0.0), 3),
                      "max_radius_of_gyration_A": round(float(p.get("max_radius_of_gyration_A") or 0.0), 3),
                      "stable_cluster": bool(val.get("stable_cluster")),
                      "hydrogen_bonding_present": bool(val.get("hydrogen_bonding_present"))},
            expected="fluid_stable (bounded droplet, T controlled, H-bonds present)")


class H2oBulkWaterStructure(ValidationCase):
    name = "h2o_bulk_water_structure"
    description = (
        "Sputnik 'H2O fluid behavior' completed toward true BULK: periodic-box "
        "liquid water (classical rigid SPC/E MD in the hook layer; SHAKE/RATTLE "
        "constraints, minimum-image + damped-shifted-force Coulomb) must reproduce "
        "the measured liquid STRUCTURE. The headline observable is the O-O radial "
        "distribution function g(r): real water has its first peak (the "
        "hydrogen-bond distance) at ~2.8 A. Asserts the first peak falls in "
        "[2.6, 3.0] A at a controlled temperature, with the rigid-body constraints "
        "provably held (max bond violation < 1e-6). The ~4.5 A tetrahedral second "
        "shell, the inter-shell depletion depth, and coordination (both to the "
        "model's own first minimum and to the experimental 3.4 A convention) are "
        "reported informationally: the SPC/E charges + rigid geometry bring "
        "coordination into the measured ~4.3-4.7 band, with the small remaining "
        "depletion residual stated honestly rather than tuned away. The "
        "self-diffusion coefficient (from the production-phase O-atom MSD via the "
        "Einstein relation) is also reported and range-checked against the SPC/E "
        "literature ~2.5e-9 / experiment 2.3e-9 m^2/s, with the finite-size + "
        "short-cutoff + weak-thermostat caveats stated."
    )
    category = "fluid"

    def required_runs(self) -> List[str]:
        return [RUN_H2O_BULK]

    def evaluate(self, ctx: "RunContext") -> CaseResult:
        run = _need_run(ctx, RUN_H2O_BULK)
        if run is None:
            return _skip(self.name, self.description, self.category, RUN_H2O_BULK)
        p = _last_emit_payload(run, "bulk_summary")
        if not p or "validation" not in p:
            return CaseResult(
                name=self.name, description=self.description, category=self.category,
                status="fail", summary="no bulk_summary emit (run incomplete?)")
        val = p["validation"]
        ok = bool(val.get("bulk_water_stable"))
        peak = float(p.get("gr_first_peak_A") or 0.0)
        peak2 = float(p.get("gr_second_peak_A") or 0.0)
        return CaseResult(
            name=self.name, description=self.description, category=self.category,
            status="pass" if ok else "fail",
            summary=(f"stable={ok} g(r)_first_peak={peak:.3f}A (exp 2.8) "
                     f"height={p.get('gr_first_peak_height', 0):.2f} "
                     f"first_min={p.get('gr_first_min_A', 0):.2f}A g={p.get('gr_first_min_height', 0):.2f} (exp ~0.75) "
                     f"second_peak={peak2:.2f}A (exp ~4.5) "
                     f"coord#(3.4A)={p.get('coordination_number_to_3p4A', 0):.2f} "
                     f"coord#(own-min)={p.get('coordination_number', 0):.2f} (exp ~4.3-4.7) "
                     f"rigid_held={bool(val.get('rigid_constraints_held'))} (maxviol={p.get('max_constraint_violation', 0):.1e}) "
                     f"D_self={float(p.get('self_diffusion_m2_per_s') or 0.0)*1e9:.2f}e-9 (Einstein) "
                     f"D_gk={float(p.get('green_kubo_self_diffusion_m2_per_s') or 0.0)*1e9:.2f}e-9 (Green-Kubo) m2/s (exp 2.3) "
                     f"mean_T={p.get('mean_temperature_K', 0):.1f}K N={p.get('molecules')}"),
            measured={"gr_first_peak_A": round(peak, 3),
                      "gr_first_peak_height": round(float(p.get("gr_first_peak_height") or 0.0), 2),
                      "gr_first_min_A": round(float(p.get("gr_first_min_A") or 0.0), 2),
                      "gr_first_min_height": round(float(p.get("gr_first_min_height") or 0.0), 2),
                      "gr_second_peak_A": round(peak2, 2),
                      "second_shell_near_tetrahedral": bool(val.get("second_shell_near_tetrahedral")),
                      "coordination_number_to_3p4A": round(float(p.get("coordination_number_to_3p4A") or 0.0), 2),
                      "coordination_number_to_own_min": round(float(p.get("coordination_number") or 0.0), 2),
                      "rigid_constraints_held": bool(val.get("rigid_constraints_held")),
                      "max_constraint_violation": float(p.get("max_constraint_violation") or 0.0),
                      "self_diffusion_einstein_1e9_m2_per_s": round(float(p.get("self_diffusion_m2_per_s") or 0.0) * 1e9, 3),
                      "self_diffusion_green_kubo_1e9_m2_per_s": round(float(p.get("green_kubo_self_diffusion_m2_per_s") or 0.0) * 1e9, 3),
                      "green_kubo_consistent_with_einstein": bool(val.get("green_kubo_consistent_with_einstein")),
                      "self_diffusion_physical": bool(val.get("self_diffusion_physical")),
                      "mean_temperature_K": round(float(p.get("mean_temperature_K") or 0.0), 1)},
            expected="O-O g(r) first peak in [2.6, 3.0] A (experiment 2.8 A), T controlled",
            references=["liquid water O-O g(r) first peak ~2.8 A (neutron/X-ray diffraction)",
                        "liquid water O-O g(r) second (tetrahedral) peak ~4.5 A",
                        "liquid water self-diffusion D ~2.3e-9 m2/s (experiment), ~2.5e-9 (SPC/E)"])


class GlassOfWaterShakenWaves(ValidationCase):
    name = "glass_of_water_shaken_waves"
    description = (
        "Multi-scale-cascade CANONICAL thesis demo -- the 'glass of water while "
        "you shake it'. A short rigid-SPC/E nano MD measures water's number "
        "density and hydrogen-bond coordination; ctx.cascade lifts those facts "
        "nano -> micro -> macro into the macroscopic fluid parameters (rest "
        "density, surface tension, viscosity) with NO macroscopic water property "
        "hand-typed; a Position-Based-Fluid solver (uniform spatial grid) then "
        "POURS ~1 litre of water into a wide tumbler (11 cm across), lets it "
        "SETTLE, and SHAKES it, at ~6 mm particle resolution with an explicit "
        "cascade-scaled cohesion that merges drops on contact. Asserts the "
        "scenario's validation: the water is POURED IN (fills the glass), then "
        "sloshing WAVES and SPLASHES appear, the water stays CONTAINED (no "
        "escape, crest below the rim -> mass conserved), the run is STABLE (no "
        "explosion), and the cascade actually drove the macro parameters (3 scale "
        "bands bridged in one pass). As an honesty check the cascade-recovered "
        "rest density (grounded coarse-graining of the nano number density) is "
        "compared to measured liquid water ~998 kg/m^3 -- a recovery, not an "
        "input. Deterministic (seeded, threads:1, predictive)."
    )
    category = "fluid"

    def required_runs(self) -> List[str]:
        return [RUN_GLASS_SHAKEN]

    def evaluate(self, ctx: "RunContext") -> CaseResult:
        run = _need_run(ctx, RUN_GLASS_SHAKEN)
        if run is None:
            return _skip(self.name, self.description, self.category, RUN_GLASS_SHAKEN)
        p = _last_emit_payload(run, "glass_summary")
        casc = _last_emit_payload(run, "cascade")
        if not p or "validation" not in p:
            return CaseResult(
                name=self.name, description=self.description, category=self.category,
                status="fail", summary="no glass_summary emit (run incomplete?)")
        val = p["validation"]
        ok = bool(val.get("glass_of_water_from_nano"))
        mp = p.get("macro_params_from_cascade", {})
        dyn = p.get("dynamics", {})
        dens_err = float((casc or {}).get("density_recovery_error_pct") or 0.0)
        nano = (casc or {}).get("nano_measured", {})
        scales = (casc or {}).get("cascade", {}).get("scales_bridged", [])
        return CaseResult(
            name=self.name, description=self.description, category=self.category,
            status="pass" if ok else "fail",
            summary=(f"ok={ok} poured={val.get('water_poured_in')} "
                     f"waves={val.get('waves_present')} "
                     f"splash={val.get('splash_present')} "
                     f"contained={val.get('water_contained')} "
                     f"stable={val.get('stable_no_explosion')} "
                     f"particles={p.get('particles')}/{p.get('target_particles')} "
                     f"(~{mp.get('water_mass_g', 0):.0f}g) "
                     f"scales={'->'.join(scales)} "
                     f"nano(coord={nano.get('coordination', 0):.2f}, "
                     f"g(r)peak={nano.get('hbond_peak_A', 0):.2f}A) "
                     f"-> macro(rho={mp.get('rest_density_kg_per_m3', 0):.1f} "
                     f"kg/m3 [{dens_err:.2f}% vs 998], "
                     f"surf_tension={mp.get('surface_tension_coeff', 0):.3f}, "
                     f"visc={mp.get('viscosity_coeff', 0):.3f})  "
                     f"still_level={float(p.get('glass', {}).get('still_water_level_m', 0))*100:.1f}cm "
                     f"peak_wave={float(dyn.get('peak_wave_roughness_m', 0))*1000:.1f}mm "
                     f"peak_splash={float(dyn.get('peak_splash_height_m', 0))*1000:.1f}mm"),
            measured={"rest_density_kg_per_m3": round(float(mp.get("rest_density_kg_per_m3") or 0.0), 1),
                      "water_mass_g": round(float(mp.get("water_mass_g") or 0.0), 0),
                      "particles": p.get("particles"),
                      "still_water_level_cm": round(float(p.get("glass", {}).get("still_water_level_m") or 0.0) * 100, 1),
                      "water_poured_in": bool(val.get("water_poured_in")),
                      "density_recovery_error_pct": round(dens_err, 3),
                      "surface_tension_coeff": round(float(mp.get("surface_tension_coeff") or 0.0), 4),
                      "viscosity_coeff": round(float(mp.get("viscosity_coeff") or 0.0), 4),
                      "nano_coordination": round(float(nano.get("coordination") or 0.0), 3),
                      "nano_hbond_peak_A": round(float(nano.get("hbond_peak_A") or 0.0), 3),
                      "scales_bridged": scales,
                      "peak_wave_roughness_mm": round(float(dyn.get("peak_wave_roughness_m") or 0.0) * 1000, 2),
                      "peak_splash_height_mm": round(float(dyn.get("peak_splash_height_m") or 0.0) * 1000, 2),
                      "max_speed_m_per_s": round(float(dyn.get("max_speed_m_per_s") or 0.0), 3),
                      "waves_present": bool(val.get("waves_present")),
                      "splash_present": bool(val.get("splash_present")),
                      "water_contained": bool(val.get("water_contained")),
                      "stable_no_explosion": bool(val.get("stable_no_explosion")),
                      "cascade_drove_macro": bool(val.get("cascade_drove_macro"))},
            expected="glass_of_water_from_nano (waves + splash + contained + stable, macro params cascaded from nano)",
            references=["liquid water density ~998 kg/m^3 (20 C); recovered by grounded n->rho coarse-graining, not typed",
                        "liquid water O-O g(r) first peak ~2.8 A (hydrogen-bond distance)",
                        "liquid water first-shell coordination ~4.3-4.7"])


class H2oDiffusionTemperatureTrend(ValidationCase):
    name = "h2o_diffusion_temperature_trend"
    description = (
        "Sputnik 'H2O fluid behavior' DYNAMICS, multi-point: a single state "
        "point can be lucky, a trend cannot. The rigid-SPC/E model is swept "
        "across three temperatures (one deterministic anneal: melt, then "
        "equilibrate + measure per block) and the self-diffusion coefficient D "
        "(from the production-phase O-atom MSD, Einstein relation) is measured "
        "at each. Asserts D rises monotonically with T and that the rise over "
        "the measured temperature span tracks the measured water trend "
        "(Holz et al. 2000: D nearly triples 278->318 K), with the rigid "
        "constraints held. D per block is a multi-time-origin MSD average; "
        "absolute values carry constant-density / finite-size caveats and "
        "SPC/E's known slightly-too-steep D(T) (reported, not tuned). Skips when "
        "the slow sweep run is absent."
    )
    category = "fluid"

    def required_runs(self) -> List[str]:
        return [RUN_H2O_DIFFUSION_T]

    def evaluate(self, ctx: "RunContext") -> CaseResult:
        run = _need_run(ctx, RUN_H2O_DIFFUSION_T)
        if run is None:
            return _skip(self.name, self.description, self.category, RUN_H2O_DIFFUSION_T)
        p = _last_emit_payload(run, "diffusion_vs_temperature")
        if not p or "validation" not in p:
            return CaseResult(
                name=self.name, description=self.description, category=self.category,
                status="fail", summary="no diffusion_vs_temperature emit (run incomplete?)")
        val = p["validation"]
        ok = bool(val.get("diffusion_temperature_trend_ok"))
        pts = p.get("points") or []
        dstr = "  ".join(
            f"{pt['mean_temperature_K']:.0f}K:{pt['self_diffusion_m2_per_s']*1e9:.2f}"
            f"(exp{pt['experiment_self_diffusion_m2_per_s']*1e9:.2f})" for pt in pts)
        return CaseResult(
            name=self.name, description=self.description, category=self.category,
            status="pass" if ok else "fail",
            summary=(f"trend_ok={ok} monotonic={bool(val.get('monotonic_increase'))} "
                     f"D[1e-9 m2/s]@T: {dstr}  "
                     f"D-rise TRECH x{p.get('d_ratio_trech', 0):.2f} vs exp x{p.get('d_ratio_experiment', 0):.2f}"),
            measured={"points": [{"T_K": round(pt["mean_temperature_K"], 1),
                                  "D_1e9_m2_per_s": round(pt["self_diffusion_m2_per_s"] * 1e9, 3),
                                  "D_exp_1e9_m2_per_s": round(pt["experiment_self_diffusion_m2_per_s"] * 1e9, 3)}
                                 for pt in pts],
                      "d_ratio_trech": round(float(p.get("d_ratio_trech") or 0.0), 3),
                      "d_ratio_experiment": round(float(p.get("d_ratio_experiment") or 0.0), 3),
                      "monotonic_increase": bool(val.get("monotonic_increase")),
                      "rigid_constraints_held": bool(val.get("rigid_constraints_held"))},
            expected="D monotonically increases with T and the rise tracks the measured water trend",
            references=["liquid water self-diffusion D(T) (Holz, Heil & Sacco, PCCP 2000): "
                        "1.31e-9 (278 K) -> 2.30e-9 (298 K) -> 3.58e-9 (318 K) m^2/s"])


class CntBandStructure(ValidationCase):
    name = "cnt_band_structure"
    description = (
        "Vostok (CNT) milestone: a single-wall carbon nanotube's electronic "
        "character is fixed by its (n,m) chirality. The hook-layer tight-binding "
        "zone-folding model (Geant4 transports electrons through the geometry but "
        "does not compute band structure) must reproduce two textbook results: "
        "(1) the metallicity rule -- metallic iff (n-m) mod 3 == 0 (armchair "
        "always metallic, zigzag (n,0) metallic iff n%3==0); (2) the gap law -- "
        "semiconducting E_g = 2 a_cc gamma0 / d, i.e. E_g * d is constant "
        "(~0.82 eV*nm, measured 0.7-0.9). Asserts the rule holds on known cases, "
        "the primary semiconducting gap is inversely proportional to diameter, "
        "specific tubes match STM-measured gaps within 15%, and nominally "
        "metallic non-armchair tubes acquire the expected curvature secondary "
        "gap proportional to |cos(3 theta)|/d^2 while armchairs remain zero-gap. "
        "Trigonal-warping family split remains a stated residual."
    )
    category = "cnt"

    def required_runs(self) -> List[str]:
        return [RUN_CNT_BAND_STRUCTURE]

    def evaluate(self, ctx: "RunContext") -> CaseResult:
        run = _need_run(ctx, RUN_CNT_BAND_STRUCTURE)
        if run is None:
            return _skip(self.name, self.description, self.category, RUN_CNT_BAND_STRUCTURE)
        p = _last_emit_payload(run, "cnt_panel")
        if not p or "validation" not in p:
            return CaseResult(
                name=self.name, description=self.description, category=self.category,
                status="fail", summary="no cnt_panel emit (run incomplete?)")
        val = p["validation"]
        ok = bool(val.get("cnt_band_structure_ok"))
        return CaseResult(
            name=self.name, description=self.description, category=self.category,
            status="pass" if ok else "fail",
            summary=(f"ok={ok} metallicity_rule={bool(val.get('metallicity_rule_holds'))} "
                     f"primary_gap~1/d={bool(val.get('gap_inverse_diameter_law_holds'))} "
                     f"curvature~cos3theta/d2={bool(val.get('curvature_secondary_gap_law_holds'))} "
                     f"E_g*d={p.get('mean_gap_times_diameter_eV_nm', 0):.3f}eV*nm (meas 0.7-0.9) "
                     f"E_curv*d^2={p.get('mean_zigzag_curvature_gap_times_diameter2_eV_nm2', 0):.3f}eV*nm^2 "
                     f"anchors<={p.get('max_anchor_rel_err', 0)*100:.0f}% "
                     f"{p.get('metallic_count')}nominal-metal/{p.get('semiconducting_count')}semi "
                     f"(gamma0={p.get('gamma0_eV')}eV)"),
            measured={"metallic_count": p.get("metallic_count"),
                      "semiconducting_count": p.get("semiconducting_count"),
                      "quasi_metallic_count": p.get("quasi_metallic_count"),
                      "gap_scaling_eV_nm": round(float(p.get("gap_scaling_eV_nm") or 0.0), 4),
                      "mean_gap_times_diameter_eV_nm": round(float(p.get("mean_gap_times_diameter_eV_nm") or 0.0), 4),
                      "curvature_gap_coeff_eV_nm2": round(float(p.get("curvature_gap_coeff_eV_nm2") or 0.0), 4),
                      "mean_zigzag_curvature_gap_times_diameter2_eV_nm2": round(float(p.get("mean_zigzag_curvature_gap_times_diameter2_eV_nm2") or 0.0), 4),
                      "max_curvature_secondary_gap_eV": round(float(p.get("max_curvature_secondary_gap_eV") or 0.0), 4),
                      "max_anchor_rel_err": round(float(p.get("max_anchor_rel_err") or 0.0), 4),
                      "metallicity_rule_holds": bool(val.get("metallicity_rule_holds")),
                      "gap_inverse_diameter_law_holds": bool(val.get("gap_inverse_diameter_law_holds")),
                      "curvature_secondary_gap_law_holds": bool(val.get("curvature_secondary_gap_law_holds")),
                      "armchair_curvature_gap_zero": bool(val.get("armchair_curvature_gap_zero")),
                      "quasi_metallic_small_gaps": bool(val.get("quasi_metallic_small_gaps")),
                      "measured_anchors_within_15pct": bool(val.get("measured_anchors_within_15pct"))},
            expected="metallicity = (n-m) mod 3 rule; semiconducting primary E_g proportional to 1/d; curvature secondary gap proportional to |cos(3theta)|/d^2",
            references=["SWCNT metallic iff (n-m) mod 3 == 0 (Saito, Dresselhaus & Dresselhaus 1998)",
                        "semiconducting E_g = 2 a_cc gamma0 / d; E_g*d ~ 0.7-0.9 eV*nm (STM, Wildoer/Odom 1998)",
                        "bare curvature gap for nominally metallic tubes ~ (50 meV nm^2 / d^2) cos(3theta)"])


class CntLogicGates(ValidationCase):
    name = "cnt_logic_gates"
    description = (
        "Vostok (CNT) milestone: build carbon-nanotube field-effect transistors "
        "(CNTFETs) from the tight-binding band structure, assemble the full logic-"
        "gate family (NOT/BUFFER/AND/OR/NAND/NOR/XOR/XNOR) as static-CMOS "
        "resistive-divider devices, wire them into circuits (half adder, full "
        "adder, 2-bit ripple-carry adder), and CONFIRM the truth table the "
        "electrons produce at every output. The transistor's on/off ratio is set "
        "by Fermi-Dirac statistics on the band gap (~exp(E_g/2kT)), and the "
        "subthreshold swing recovered from the simulated I_d(V_gs) must land on "
        "the ~60 mV/decade room-temperature Fermi limit (SS = ln(10) kT/q). "
        "Asserts: every gate truth table is correct, the three adder circuits "
        "reproduce binary addition, the working semiconducting tube has healthy "
        "noise margins (outputs near the rails), a METALLIC tube built into the "
        "same topology DESTROYS the logic (outputs collapse to ~Vdd/2 -- the "
        "manufacturing short of docs/CNT/BackToTheCarbon.md), the swing is ~60 "
        "mV/dec, the on/off ratio is gap-controlled (semiconductor >= 1e3 and "
        ">= 1e3x the metallic tube), the on/off ratio falls / swing rises with "
        "temperature (Fermi smearing), and Geant4 transports electrons through "
        "the representative CNT channel each event. Honest scope: Geant4 "
        "transports electrons but does not compute band structure / Fermi level / "
        "device switching -- those are the hook-layer physics for comparison."
    )
    category = "cnt"

    def required_runs(self) -> List[str]:
        return [RUN_CNT_LOGIC_GATES]

    def evaluate(self, ctx: "RunContext") -> CaseResult:
        run = _need_run(ctx, RUN_CNT_LOGIC_GATES)
        if run is None:
            return _skip(self.name, self.description, self.category, RUN_CNT_LOGIC_GATES)
        p = _last_emit_payload(run, "cnt_gates_summary")
        if not p or "validation" not in p:
            return CaseResult(
                name=self.name, description=self.description, category=self.category,
                status="fail", summary="no cnt_gates_summary emit (run incomplete?)")
        val = p["validation"]
        fermi = p.get("fermi") or {}
        transfer = fermi.get("transfer") or {}
        ok = bool(val.get("cnt_logic_gates_ok"))
        return CaseResult(
            name=self.name, description=self.description, category=self.category,
            status="pass" if ok else "fail",
            summary=(f"ok={ok} gates={bool(val.get('all_gate_truth_tables_correct'))} "
                     f"half/full/2bit_adders="
                     f"{bool(val.get('half_adder_correct'))}/"
                     f"{bool(val.get('full_adder_correct'))}/"
                     f"{bool(val.get('ripple_carry_adder_2bit_correct'))} "
                     f"margin_ok={bool(val.get('noise_margin_healthy'))} "
                     f"metallic_breaks={bool(val.get('metallic_tube_breaks_logic'))} "
                     f"SS={transfer.get('subthreshold_swing_mV_per_dec', 0):.1f}mV/dec "
                     f"(ideal {fermi.get('ideal_swing_mV_per_dec', 0):.1f}) "
                     f"on/off semi={fermi.get('semiconducting_on_off_ratio', 0):.3g} "
                     f"vs metal={fermi.get('metallic_on_off_ratio', 0):.3g} "
                     f"g4_drive={bool(val.get('geant4_event_drive_present'))}"),
            measured={
                "all_gate_truth_tables_correct": bool(val.get("all_gate_truth_tables_correct")),
                "half_adder_correct": bool(val.get("half_adder_correct")),
                "full_adder_correct": bool(val.get("full_adder_correct")),
                "ripple_carry_adder_2bit_correct": bool(val.get("ripple_carry_adder_2bit_correct")),
                "noise_margin_healthy": bool(val.get("noise_margin_healthy")),
                "metallic_tube_breaks_logic": bool(val.get("metallic_tube_breaks_logic")),
                "subthreshold_swing_near_60mV": bool(val.get("subthreshold_swing_near_60mV")),
                "on_off_ratio_gap_controlled": bool(val.get("on_off_ratio_gap_controlled")),
                "fermi_temperature_trend": bool(val.get("fermi_temperature_trend")),
                "geant4_event_drive_present": bool(val.get("geant4_event_drive_present")),
                "subthreshold_swing_mV_per_dec": round(float(transfer.get("subthreshold_swing_mV_per_dec") or 0.0), 3),
                "ideal_swing_mV_per_dec": round(float(fermi.get("ideal_swing_mV_per_dec") or 0.0), 3),
                "semiconducting_on_off_ratio": round(float(fermi.get("semiconducting_on_off_ratio") or 0.0), 1),
                "metallic_on_off_ratio": round(float(fermi.get("metallic_on_off_ratio") or 0.0), 3),
                "semiconducting_worst_rail_closeness": round(float(val.get("semiconducting_worst_rail_closeness") or 0.0), 4),
                "gate_count": p.get("gate_count"),
            },
            expected=("every gate + adder truth table matches the canonical boolean function on a "
                      "semiconducting CNTFET; the metallic tube breaks the same logic; "
                      "subthreshold swing ~ 60 mV/dec; on/off ratio gap-controlled"),
            references=["SWCNT metallic iff (n-m) mod 3 == 0 (Saito, Dresselhaus & Dresselhaus 1998)",
                        "static-CMOS logic: pull-up/pull-down complementary FET networks",
                        "subthreshold swing SS = ln(10) kT/q ~ 60 mV/decade at 300 K (Fermi-Dirac limit)",
                        "metallic-tube short / sorting problem (docs/CNT/BackToTheCarbon.md)"])


# ---------- analytic cross-check (classical formula vs Geant4 statistics) ----------

class AnalyticBeerLambertCrossCheck(ValidationCase):
    name = "analytic_beer_lambert_cross_check"
    description = (
        "Complex test scenario with a classical-formula cross-check: a narrow "
        "monochromatic gamma beam crosses a water slab, and the engine compares "
        "two independent answers to 'what fraction crosses without interacting?'. "
        "(1) The CLASSICAL formula T = exp(-mu*x), with the linear attenuation "
        "coefficient mu summed from Geant4's own atomic cross sections "
        "(photoelectric + Compton + Rayleigh + pair) via G4EmCalculator -- the "
        "expected/truth. (2) The GEANT4 MONTE-CARLO STATISTICAL result: the "
        "measured uncollided-primary fraction from transporting N gammas. They "
        "must agree to within the configured relative tolerance (Poisson-limited) "
        "-- a self-consistency validation of the transport + scoring chain against "
        "textbook physics. Asserts every analytic check is within tolerance and "
        "reports the classical-vs-measured gap."
    )
    category = "analytic"

    def required_runs(self) -> List[str]:
        return [RUN_ANALYTIC_BEER_LAMBERT]

    def evaluate(self, ctx: "RunContext") -> CaseResult:
        run = _need_run(ctx, RUN_ANALYTIC_BEER_LAMBERT)
        if run is None or run.scores is None:
            return _skip(self.name, self.description, self.category, RUN_ANALYTIC_BEER_LAMBERT)
        checks = run.scores.get("analytic_checks") or []
        if not checks:
            return CaseResult(
                name=self.name, description=self.description, category=self.category,
                status="fail", summary="no analytic_checks in scores (analytic disabled?)")
        rows: List[str] = []
        worst_rel = 0.0
        all_ok = True
        measured_list: List[Dict[str, Any]] = []
        for c in checks:
            if not c.get("available"):
                all_ok = False
                rows.append(f"{c.get('label')}: UNAVAILABLE ({c.get('note')})")
                continue
            predicted = float(c.get("classical_predicted") or 0.0)
            measured = float(c.get("geant4_measured") or 0.0)
            rel = float(c.get("relative_error") or 0.0)
            within = bool(c.get("within_tolerance"))
            worst_rel = max(worst_rel, rel)
            all_ok = all_ok and within
            rows.append(
                f"{c.get('label')}: classical={predicted:.4f} geant4={measured:.4f} "
                f"rel_err={rel*100:.2f}% (tol {float(c.get('tolerance_rel') or 0.0)*100:.0f}%) "
                f"mu={float(c.get('mu_total_per_mm') or 0.0):.5f}/mm within={within}")
            measured_list.append({
                "label": c.get("label"),
                "classical_predicted": round(predicted, 5),
                "geant4_measured": round(measured, 5),
                "relative_error": round(rel, 5),
                "within_tolerance": within,
            })
        return CaseResult(
            name=self.name, description=self.description, category=self.category,
            status="pass" if all_ok else "fail",
            summary=f"{len(checks)} check(s), worst rel_err={worst_rel*100:.2f}%, all_within_tolerance={all_ok}",
            measured=measured_list,
            expected="classical formula == Geant4 Monte-Carlo result within tolerance",
            references=["Beer-Lambert narrow-beam attenuation T = exp(-mu*x); "
                        "water mu/rho ~ 0.171 cm^2/g at 100 keV (NIST XCOM)"],
            notes=rows)


class CsdaRangeCrossCheck(ValidationCase):
    name = "analytic_csda_range_cross_check"
    description = (
        "Charged-particle CSDA-range cross-check, the companion to Beer-Lambert "
        "and a second fully derived-from-Geant4 test: a proton beam fully stops "
        "inside a water block, and the engine compares two independent answers to "
        "'how far does the proton travel before stopping?'. (1) The CLASSICAL / "
        "Geant4-DERIVED prediction R_CSDA = integral dE/(dE/dx), the continuous-"
        "slowing-down range computed from Geant4's OWN stopping power "
        "(G4EmCalculator::GetCSDARange) -- no externally tuned constant. (2) The "
        "GEANT4 MONTE-CARLO STATISTICAL result: the measured mean primary track "
        "length (a new per-primary path-length tally in SteppingAction), summed "
        "over the proton's steps until it ranges out. A proton is used because it "
        "travels nearly straight and barely backscatters, so its transported track "
        "length equals the CSDA range to high accuracy. Asserts the check is "
        "within tolerance, that every primary is contained (transmitted == 0, so "
        "the measurement is valid), and reports the derived-vs-measured gap."
    )
    category = "analytic"

    def required_runs(self) -> List[str]:
        return [RUN_ANALYTIC_CSDA]

    def evaluate(self, ctx: "RunContext") -> CaseResult:
        run = _need_run(ctx, RUN_ANALYTIC_CSDA)
        if run is None or run.scores is None:
            return _skip(self.name, self.description, self.category, RUN_ANALYTIC_CSDA)
        checks = run.scores.get("analytic_checks") or []
        csda = [c for c in checks if c.get("type") == "csda_range"]
        if not csda:
            return CaseResult(
                name=self.name, description=self.description, category=self.category,
                status="fail", summary="no csda_range analytic check in scores")
        rows: List[str] = []
        worst_rel = 0.0
        all_ok = True
        contained = True
        measured_list: List[Dict[str, Any]] = []
        for c in csda:
            if not c.get("available"):
                all_ok = False
                rows.append(f"{c.get('label')}: UNAVAILABLE ({c.get('note')})")
                continue
            predicted = float(c.get("classical_predicted") or 0.0)
            measured = float(c.get("geant4_measured") or 0.0)
            rel = float(c.get("relative_error") or 0.0)
            within = bool(c.get("within_tolerance"))
            transmitted = int(c.get("primaries_transmitted") or 0)
            emitted = int(c.get("primaries_emitted") or 0)
            if transmitted != 0:
                contained = False
            worst_rel = max(worst_rel, rel)
            all_ok = all_ok and within
            rows.append(
                f"{c.get('label')}: derived(CSDA)={predicted:.4f}mm "
                f"geant4(track len)={measured:.4f}mm rel_err={rel*100:.2f}% "
                f"(tol {float(c.get('tolerance_rel') or 0.0)*100:.0f}%) "
                f"dE/dx={float(c.get('stopping_power_mev_per_mm') or 0.0):.3f}MeV/mm "
                f"contained={transmitted}/{emitted} transmitted within={within}")
            measured_list.append({
                "label": c.get("label"),
                "particle": c.get("particle"),
                "energy_mev": c.get("energy_mev"),
                "csda_range_mm_derived": round(predicted, 4),
                "mean_track_length_mm_measured": round(measured, 4),
                "relative_error": round(rel, 5),
                "stopping_power_mev_per_mm": round(float(c.get("stopping_power_mev_per_mm") or 0.0), 4),
                "primaries_transmitted": transmitted,
                "within_tolerance": within,
            })
        ok = all_ok and contained
        return CaseResult(
            name=self.name, description=self.description, category=self.category,
            status="pass" if ok else "fail",
            summary=(f"{len(csda)} check(s), worst rel_err={worst_rel*100:.2f}%, "
                     f"contained={contained}, all_within_tolerance={all_ok}"),
            measured=measured_list,
            expected="Geant4-derived CSDA range == measured mean primary track length within tolerance (and primaries contained)",
            references=["CSDA range R = integral_0^E dE'/(dE'/dx); "
                        "20 MeV proton in water ~ 0.426 g/cm^2 = 4.26 mm (NIST PSTAR)"],
            notes=rows)


class PhotoFractionCrossCheck(ValidationCase):
    name = "analytic_photo_fraction_cross_check"
    description = (
        "Photon process-branching cross-check, the third analytic test and the "
        "companion to Beer-Lambert: a monochromatic gamma beam enters a water "
        "slab, and the engine compares two independent answers to 'OF the gammas "
        "that interact, what fraction interact photoelectrically?'. (1) The "
        "CLASSICAL / Geant4-DERIVED prediction f_photo = sigma_phot / "
        "(phot + compt + Rayl + conv), the photoelectric share of the total "
        "interaction cross section, summed from Geant4's OWN atomic cross sections "
        "(G4EmCalculator) -- no externally tuned constant. (2) The GEANT4 "
        "MONTE-CARLO STATISTICAL result: the measured fraction of primaries whose "
        "FIRST discrete interaction is photoelectric (a new per-primary tally in "
        "SteppingAction that reads the fired sub-process through QBBC's "
        "G4GammaGeneralProcess wrapper by EM subtype, so it is physics-list "
        "robust). Unlike total attenuation, the branching ratio is independent of "
        "slab thickness, so this isolates Geant4's sampling of the process choice. "
        "Asserts the check is within tolerance and reports the derived-vs-measured "
        "gap."
    )
    category = "analytic"

    def required_runs(self) -> List[str]:
        return [RUN_ANALYTIC_PHOTO_FRACTION]

    def evaluate(self, ctx: "RunContext") -> CaseResult:
        run = _need_run(ctx, RUN_ANALYTIC_PHOTO_FRACTION)
        if run is None or run.scores is None:
            return _skip(self.name, self.description, self.category, RUN_ANALYTIC_PHOTO_FRACTION)
        checks = run.scores.get("analytic_checks") or []
        photo = [c for c in checks if c.get("type") == "photo_fraction"]
        if not photo:
            return CaseResult(
                name=self.name, description=self.description, category=self.category,
                status="fail", summary="no photo_fraction analytic check in scores")
        rows: List[str] = []
        worst_rel = 0.0
        all_ok = True
        measured_list: List[Dict[str, Any]] = []
        for c in photo:
            if not c.get("available"):
                all_ok = False
                rows.append(f"{c.get('label')}: UNAVAILABLE ({c.get('note')})")
                continue
            predicted = float(c.get("classical_predicted") or 0.0)
            measured = float(c.get("geant4_measured") or 0.0)
            rel = float(c.get("relative_error") or 0.0)
            within = bool(c.get("within_tolerance"))
            n_first = int(c.get("primaries_first_interaction") or 0)
            n_photo = int(c.get("primaries_photoelectric_first") or 0)
            # The wrapper-detection guard: a positive photoelectric count proves the
            # G4GammaGeneralProcess sub-process classification actually fired (a
            # broken classifier would tally zero photoelectric first-interactions).
            if n_photo <= 0:
                all_ok = False
            worst_rel = max(worst_rel, rel)
            all_ok = all_ok and within
            rows.append(
                f"{c.get('label')}: derived(f_photo)={predicted:.4f} "
                f"geant4(first-interaction)={measured:.4f} rel_err={rel*100:.2f}% "
                f"(tol {float(c.get('tolerance_rel') or 0.0)*100:.0f}%) "
                f"phot/first={n_photo}/{n_first} "
                f"mu_phot={float(c.get('mu_photoelectric_per_mm') or 0.0):.5f}/mm "
                f"mu_total={float(c.get('mu_total_per_mm') or 0.0):.5f}/mm within={within}")
            measured_list.append({
                "label": c.get("label"),
                "energy_mev": c.get("energy_mev"),
                "photo_fraction_derived": round(predicted, 5),
                "photo_fraction_measured": round(measured, 5),
                "relative_error": round(rel, 5),
                "primaries_first_interaction": n_first,
                "primaries_photoelectric_first": n_photo,
                "within_tolerance": within,
            })
        return CaseResult(
            name=self.name, description=self.description, category=self.category,
            status="pass" if all_ok else "fail",
            summary=(f"{len(photo)} check(s), worst rel_err={worst_rel*100:.2f}%, "
                     f"all_within_tolerance={all_ok}"),
            measured=measured_list,
            expected="Geant4-derived photoelectric fraction == measured first-interaction photoelectric fraction within tolerance",
            references=["Photoelectric branching f = sigma_phot / sigma_total; "
                        "30 keV gamma in water is near the photoelectric/Compton crossover (NIST XCOM)"],
            notes=rows)


# ---------- registry ----------

class MagneticResonanceWater(ValidationCase):
    name = "magnetic_resonance_water"
    description = (
        "Stage-1 NMR/MRI of a 5 cm^3 water cube. Geant4 builds the phantom + a "
        "copper receiver coil and -- through the new material-probe surface -- "
        "supplies the 1H (proton) number density that sets the equilibrium "
        "magnetization; the deterministic hook layer runs the Bloch spin "
        "dynamics (RF frequency sweep, FID, T2* decay). The Larmor line is "
        "DISCOVERED from the FID carrier (the magnetization precesses at gamma*B0) "
        "and the proton density from Geant4, with the textbook values used only to "
        "grade the gap. Asserts the discovered Larmor recovers gamma/2pi = 42.5775 "
        "MHz/T, the Geant4 proton density matches literature water, the FID "
        "decays with a recoverable T2*, the spectroscopy sweep shows a real "
        "resonance, the Geant4 per-event drive is present, and the engine holds no "
        "hard-coded spin rule."
    )
    category = "resonance"

    def required_runs(self) -> List[str]:
        return [RUN_MAGNETIC_RESONANCE]

    def evaluate(self, ctx: "RunContext") -> CaseResult:
        run = _need_run(ctx, RUN_MAGNETIC_RESONANCE)
        if run is None:
            return _skip(self.name, self.description, self.category, RUN_MAGNETIC_RESONANCE)
        v = _last_emit_payload(run, "mr_summary")
        if not v or "validation" not in v:
            return CaseResult(
                name=self.name, description=self.description, category=self.category,
                status="fail", summary="no mr_summary emit (run incomplete?)")
        val = v["validation"]
        gap = v.get("gap_to_truth") or {}
        disc = v.get("discovered") or {}
        g4 = v.get("geant4_material") or {}

        # The material_probes score block must independently carry the same
        # Geant4-derived water proton density the hook layer used (cross-check of
        # the ctx.materials surface vs the emitted scores).
        probes = {p.get("name"): p for p in ((run.scores or {}).get("material_probes") or [])}
        water_probe = probes.get("G4_WATER") or {}
        probe_h = ((water_probe.get("numberDensityPerCm3") or {}).get("H")) or 0.0
        hook_h = float(g4.get("water_proton_per_cm3") or 0.0)
        probe_matches_hook = (
            probe_h > 0.0 and hook_h > 0.0 and _approx_equal(probe_h, hook_h, rel=1e-6)
        )

        required = {
            "larmor_discovered": bool(val.get("larmor_discovered")),
            "proton_density_from_geant4": bool(val.get("proton_density_from_geant4")),
            "fid_decays": bool(val.get("fid_decays")),
            "resonance_lorentzian": bool(val.get("resonance_lorentzian")),
            "geant4_drive_present": bool(val.get("geant4_drive_present")),
            "no_engine_spin_rule": bool(val.get("no_engine_spin_rule")),
            "material_probe_matches_hook": probe_matches_hook,
        }
        ok = all(required.values())

        gamma_recovered = float(disc.get("gamma_recovered_mhz_per_t") or 0.0)
        gamma_ref = float(gap.get("gamma_reference_mhz_per_t") or 42.577478518)
        larmor_rel = float(gap.get("larmor_rel_error") or 1.0)
        proton_rel = float(gap.get("proton_density_rel_error") or 1.0)
        t2_rel = float(gap.get("t2_star_rel_error") or 1.0)
        return CaseResult(
            name=self.name, description=self.description, category=self.category,
            status="pass" if ok else "fail",
            summary=(f"checks={sum(1 for p in required.values() if p)}/{len(required)} "
                     f"gamma={gamma_recovered:.4f} MHz/T (ref {gamma_ref:.4f}, "
                     f"{larmor_rel:.2%}) protonH={hook_h:.3e}/cm3 ({proton_rel:.2%}) "
                     f"T2*fit={float(disc.get('t2_star_s_fit') or 0.0)*1e3:.2f}ms "
                     f"RFphotons={float(disc.get('detected_rf_photons') or 0.0):.2e}"),
            measured={
                **required,
                "discovered_larmor_mhz": disc.get("larmor_mhz"),
                "sweep_coarse_peak_mhz": disc.get("sweep_coarse_peak_mhz"),
                "gamma_recovered_mhz_per_t": gamma_recovered,
                "water_proton_per_cm3_hook": hook_h,
                "water_proton_per_cm3_probe": probe_h,
                "t2_star_s_fit": disc.get("t2_star_s_fit"),
                "detected_rf_photons": disc.get("detected_rf_photons"),
                "gap_larmor_rel_error": larmor_rel,
                "gap_proton_rel_error": proton_rel,
                "gap_t2_star_rel_error": t2_rel,
                "tissue_preview": v.get("tissue_preview"),
            },
            expected={
                "gamma_over_2pi": f"{gamma_ref} MHz/T (proton Larmor constant)",
                "larmor_rel_error": "<= 0.02",
                "proton_density": "Geant4 water 1H ~= 6.686e22 /cm3 (rel <= 0.05)",
                "fid_decays": "T2* recoverable from the FID envelope",
                "material_probe_matches_hook": "scores.material_probes == ctx.materials proton density",
            },
            references=["proton gamma/2pi = 42.577478518 MHz/T (CODATA)",
                        "pure water 1H density ~= 6.686e22 /cm3"])


class MagneticResonanceTissueContrast(ValidationCase):
    name = "magnetic_resonance_tissue_contrast"
    description = (
        "Stage-2 NMR/MRI virtual-tissue contrast, with REAL Geant4 photon "
        "emission driven by Geant4's ignorant proton-density predictions "
        "(scripts/run_magnetic_resonance_tissues.py). For each NIST tissue the "
        "engine reads the Geant4-computed 1H number density (material_probes) and "
        "the driver emits a proportional number of excitation primaries; Geant4 "
        "then produces EVERY consequent photon and a NaI detector shell scores the "
        "real deposited energy (receiver_coil volume_edep_mev). Asserts every "
        "tissue produced a real detected signal, the emission count matches the "
        "Geant4 proton prediction, the detected signal tracks proton density, the "
        "tissues give distinct responses, and no engine spin rule was used. "
        "Reports each tissue's real relative signal next to its proton ratio so "
        "the radiographic photon-yield gap (e.g. cortical bone) is visible."
    )
    category = "resonance"

    def required_runs(self) -> List[str]:
        return [RUN_MR_TISSUES]

    def evaluate(self, ctx: "RunContext") -> CaseResult:
        run = _need_run(ctx, RUN_MR_TISSUES)
        if run is None:
            return _skip(self.name, self.description, self.category, RUN_MR_TISSUES)
        v = _last_emit_payload(run, "mr_tissue_contrast")
        if not v or "validation" not in v:
            return CaseResult(
                name=self.name, description=self.description, category=self.category,
                status="fail", summary="no mr_tissue_contrast emit (driver not run?)")
        val = v["validation"]
        rows = v.get("tissues") or []
        required = {
            "real_detection_all_tissues": bool(val.get("real_detection_all_tissues")),
            "emission_from_geant4_proton": bool(val.get("emission_from_geant4_proton")),
            "signal_tracks_proton_density": bool(val.get("signal_tracks_proton_density")),
            "distinct_tissue_responses": bool(val.get("distinct_tissue_responses")),
            "no_engine_spin_rule": bool(val.get("no_engine_spin_rule")),
        }
        ok = all(required.values())
        corr = float(v.get("corr_signal_vs_proton_density") or 0.0)
        bone = next((r for r in rows if "bone" in (r.get("label") or "")), None)
        table = {
            r.get("label"): {
                "proton_ratio": round(float(r.get("proton_ratio") or 0.0), 4),
                "events": r.get("events_emitted"),
                "detected_signal_mev": round(float(r.get("detected_signal_mev") or 0.0), 3),
                "relative_signal": round(float(r.get("relative_signal") or 0.0), 4),
            }
            for r in rows
        }
        bone_txt = (f" bone={float(bone.get('relative_signal') or 0.0):.3f}x "
                    f"(protonR {float(bone.get('proton_ratio') or 0.0):.3f})") if bone else ""
        return CaseResult(
            name=self.name, description=self.description, category=self.category,
            status="pass" if ok else "fail",
            summary=(f"checks={sum(1 for p in required.values() if p)}/{len(required)} "
                     f"tissues={len(rows)} corr(signal,protonH)={corr:.3f}{bone_txt}"),
            measured={**required, "corr_signal_vs_proton_density": corr, "tissues": table},
            expected={
                "real_detection_all_tissues": "every tissue's receiver_coil edep > 0 (real MC tally)",
                "emission_from_geant4_proton": "events(T)/events(water) == Geant4 N_H(T)/N_H(water)",
                "signal_tracks_proton_density": "Pearson corr(detected signal, proton density) >= 0.7",
                "cortical_bone": "proton-poor -> MRI-dark (relative_signal well below 1)",
            },
            references=["MRI proton-density weighting; cortical bone is 1H-poor (~0.58x water)"])


class MagneticResonanceImageLine(ValidationCase):
    name = "magnetic_resonance_image_line"
    description = (
        "Stage-3 1D MRI: a real Geant4 multi-tissue phantom (a row of NIST-tissue "
        "voxels incl. an air gap and cortical bone) is spatially encoded by a field "
        "gradient so each position precesses at its own Larmor frequency; the "
        "hook-layer synthesizes the frequency-encoded readout and DFT-reconstructs "
        "the proton-density profile -- an actual 1D image line. Amplitudes come "
        "from the Geant4-supplied 1H density (ctx.materials), never hard-coded. "
        "Asserts every bright voxel's position is recovered from its peak frequency "
        "(sub-2mm), the recovered amplitudes track proton density, the air gap "
        "reconstructs black and cortical bone reconstructs dark, real Geant4 "
        "transport occurred, and no engine spin rule was used."
    )
    category = "resonance"

    def required_runs(self) -> List[str]:
        return [RUN_MR_IMAGING]

    def evaluate(self, ctx: "RunContext") -> CaseResult:
        run = _need_run(ctx, RUN_MR_IMAGING)
        if run is None:
            return _skip(self.name, self.description, self.category, RUN_MR_IMAGING)
        v = _last_emit_payload(run, "mr_image_line")
        if not v or "validation" not in v:
            return CaseResult(
                name=self.name, description=self.description, category=self.category,
                status="fail", summary="no mr_image_line emit (run incomplete?)")
        val = v["validation"]
        met = v.get("metrics") or {}
        required = {
            "position_recovered": bool(val.get("position_recovered")),
            "amplitude_tracks_proton_density": bool(val.get("amplitude_tracks_proton_density")),
            "air_gap_is_dark": bool(val.get("air_gap_is_dark")),
            "cortical_bone_is_dark": bool(val.get("cortical_bone_is_dark")),
            "geant4_transport_present": bool(val.get("geant4_transport_present")),
            "no_engine_spin_rule": bool(val.get("no_engine_spin_rule")),
        }
        ok = all(required.values())
        max_pos_err = float(met.get("max_position_error_mm") or 0.0)
        amp_corr = float(met.get("amplitude_proton_corr") or 0.0)
        voxels = {p.get("label"): p for p in (v.get("voxels") or [])}
        air = voxels.get("air gap") or {}
        bone = voxels.get("bone") or {}
        return CaseResult(
            name=self.name, description=self.description, category=self.category,
            status="pass" if ok else "fail",
            summary=(f"checks={sum(1 for p in required.values() if p)}/{len(required)} "
                     f"max_pos_err={max_pos_err:.3f}mm amp_corr={amp_corr:.3f} "
                     f"air={float(air.get('recovered_intensity') or 0):.3f} "
                     f"bone={float(bone.get('recovered_intensity') or 0):.3f}"),
            measured={
                **required,
                "max_position_error_mm": max_pos_err,
                "amplitude_proton_corr": amp_corr,
                "voxels": {
                    p.get("label"): {
                        "x_true_mm": p.get("x_true_mm"),
                        "x_recovered_mm": p.get("x_recovered_mm"),
                        "larmor_offset_khz": round(float(p.get("larmor_offset_khz") or 0.0), 2),
                        "recovered_intensity": round(float(p.get("recovered_intensity") or 0.0), 4),
                    }
                    for p in (v.get("voxels") or [])
                },
            },
            expected={
                "position_recovered": "each bright voxel x_recovered within 1.5 mm of x_true",
                "amplitude_tracks_proton_density": "corr(recovered intensity, proton density) >= 0.95",
                "air_gap_is_dark": "air (no 1H) reconstructs < 0.20 of peak",
                "cortical_bone_is_dark": "bone intensity below muscle & brain (proton-poor)",
            },
            references=["MRI frequency encoding: omega(x)=gamma*(B0+Gx*x); image = FT of rho(x)"])


class MagneticResonanceBrainImage(ValidationCase):
    name = "magnetic_resonance_brain_image"
    description = (
        "Stage-4 2D brain MRI: a procedural BrainWeb-inspired axial head phantom is "
        "painted with each tissue's Geant4-computed mobile-¹H (proton) density, and "
        "a k-space acquisition + 2D FFT reconstruct the image "
        "(scripts/run_magnetic_resonance_brain.py). Asserts the reconstructed "
        "per-tissue intensity tracks Geant4 proton density, CSF/ventricles are the "
        "brightest soft tissue, grey matter is brighter than white matter, the "
        "skull is dark, the background is black, the reconstruction is faithful to "
        "the proton-density phantom, and no engine spin rule was used."
    )
    category = "resonance"

    def required_runs(self) -> List[str]:
        return [RUN_MR_BRAIN]

    def evaluate(self, ctx: "RunContext") -> CaseResult:
        run = _need_run(ctx, RUN_MR_BRAIN)
        if run is None:
            return _skip(self.name, self.description, self.category, RUN_MR_BRAIN)
        v = _last_emit_payload(run, "mr_brain_image")
        if not v or "validation" not in v:
            return CaseResult(
                name=self.name, description=self.description, category=self.category,
                status="fail", summary="no mr_brain_image emit (driver not run?)")
        val = v["validation"]
        required = {
            "intensity_tracks_proton_density": bool(val.get("intensity_tracks_proton_density")),
            "csf_brightest_soft_tissue": bool(val.get("csf_brightest_soft_tissue")),
            "grey_brighter_than_white": bool(val.get("grey_brighter_than_white")),
            "skull_dark": bool(val.get("skull_dark")),
            "background_black": bool(val.get("background_black")),
            "reconstruction_faithful": bool(val.get("reconstruction_faithful")),
            "no_engine_spin_rule": bool(val.get("no_engine_spin_rule")),
        }
        ok = all(required.values())
        corr_ip = float(v.get("corr_intensity_proton") or 0.0)
        recon_corr = float(v.get("recon_phantom_corr") or 0.0)
        tissues = v.get("tissues") or {}
        table = {
            k: {"proton_rel": round(float(t.get("proton_rel") or 0.0), 3),
                "mean_intensity": round(float(t.get("mean_intensity") or 0.0), 3)}
            for k, t in tissues.items()
        }
        return CaseResult(
            name=self.name, description=self.description, category=self.category,
            status="pass" if ok else "fail",
            summary=(f"checks={sum(1 for p in required.values() if p)}/{len(required)} "
                     f"intensity↔proton r={corr_ip:.3f} recon r={recon_corr:.3f} "
                     f"grey={table.get('grey', {}).get('mean_intensity')} "
                     f"white={table.get('white', {}).get('mean_intensity')} "
                     f"skull={table.get('skull', {}).get('mean_intensity')}"),
            measured={**required, "corr_intensity_proton": corr_ip,
                      "recon_phantom_corr": recon_corr, "tissues": table},
            expected={
                "intensity_tracks_proton_density": "corr(reconstructed intensity, Geant4 proton density) >= 0.95",
                "csf_brightest_soft_tissue": "CSF/ventricles >= grey, white, muscle",
                "grey_brighter_than_white": "grey-matter intensity > white-matter (proton density)",
                "skull_dark": "skull < 0.5 * grey; background_black: air < 0.12",
                "reconstruction_faithful": "corr(reconstruction, proton-density phantom) >= 0.9",
            },
            references=["BrainWeb MNI anatomical phantom (inspiration); MRI proton-density weighting"])


ALL_CASES: List[ValidationCase] = [
    MagneticResonanceWater(),
    MagneticResonanceTissueContrast(),
    MagneticResonanceImageLine(),
    MagneticResonanceBrainImage(),
    AnalyticBeerLambertCrossCheck(),
    CsdaRangeCrossCheck(),
    PhotoFractionCrossCheck(),
    H2oFluidBrineRunCloses(),
    PascalPrincipleHolds(),
    OsmoticShiftObserved(),
    EffluxFirstOrderKinetics(),
    BeakerWaterPentaneInference(),
    H2oElectrolysisCombustionCycle(),
    OpticsSurrogateTransportApplied(),
    GenericSurrogateInference(),
    SamplingDiversityNonDegenerate(),
    H2oMoleculeBondsStable(),
    H2oClusterFluidStable(),
    H2oBulkWaterStructure(),
    GlassOfWaterShakenWaves(),
    H2oDiffusionTemperatureTrend(),
    CntBandStructure(),
    CntLogicGates(),
    OpticsNWater(),
    OpticsNGlass(),
    OpticsNAir(),
    OpticsIndexOrdering(),
    OpticsIndexAboveOne(),
    OpticsKKWindowSane(),
    NuclearCycleConservation(),
    NuclearCycleQValueClosure(),
    DeterminismReplay(),
    PrimariesAccountingClosure(),
    EventFeatureMeanConsistent(),
    SystemVolumeDensityArithmetic(),
    VizSceneSchemaV1(),
    VizTrajectoriesPointCount(),
    VizTrajectoryMinPoints(),
    MaterialCompositionSumsToOne(),
    EventFeatureStatsTorchBackedFlag(),
]
