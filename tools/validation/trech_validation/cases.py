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
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .runner import RunContext, RunOutputs


# Run output directory names that cases will look for under --runs-dir.
RUN_VIZ_REFRACTION = "out_viz_refraction"
RUN_VIZ_REFRACTION_REPLAY = "out_viz_refraction_replay"
RUN_NITROGEN_CYCLE = "out_nitrogen_cycle"
RUN_H2O_FLUID = "out_h2o_fluid"


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
            measured={
                "total_edep_mev": edep,
                "fluid_bulk_edep_mev": brine_edep,
                "emitted": e,
                "transmitted": t,
                "absorbed": a,
            },
        )


# ---------- registry ----------

ALL_CASES: List[ValidationCase] = [
    H2oFluidBrineRunCloses(),
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
