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
RUN_OPTICS_SURROGATE = "out_optics_surrogate"
RUN_GOW_VARIED = "out_gow_varied"
RUN_H2O_MOLECULE = "out_h2o_molecule"
RUN_H2O_CLUSTER = "out_h2o_cluster"
RUN_H2O_BULK = "out_h2o_bulk"
RUN_H2O_DIFFUSION_T = "out_h2o_diffusion_T"
RUN_CNT_BAND_STRUCTURE = "out_cnt_band_structure"


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
        "Hookean-deformable vessel the wall expands and damps the pressure. "
        "Asserts the scenario's own validation booleans plus rigid << deformable "
        "wall displacement -- guards the fluid/pressure hook path."
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
                      "deformable_wall_displacement": deform})


class OsmoticShiftObserved(ValidationCase):
    name = "osmotic_shift_observed"
    description = (
        "Osmosis scenario: a semipermeable membrane passes water but excludes "
        "the larger solute. Asserts the scenario's validation booleans "
        "(dimensional exclusion of the solute holds; a net osmotic water shift "
        "toward the solute side is observed) -- guards the membrane/diffusion "
        "hook path."
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
        exclusion = bool(val.get("dimensional_exclusion_holds"))
        shift = bool(val.get("osmotic_shift_observed"))
        ok = exclusion and shift
        return CaseResult(
            name=self.name, description=self.description, category=self.category,
            status="pass" if ok else "fail",
            summary=(f"dimensional_exclusion_holds={exclusion} "
                     f"osmotic_shift_observed={shift} "
                     f"net_water_flux_out={v.get('net_water_flux_out')}"),
            measured={"dimensional_exclusion_holds": exclusion,
                      "osmotic_shift_observed": shift})


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
        "the gap is inversely proportional to diameter, and specific tubes match "
        "STM-measured gaps within 15%. Leading-order zone-folding; curvature "
        "secondary gaps and the trigonal-warping family split are stated residuals."
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
                     f"gap~1/d={bool(val.get('gap_inverse_diameter_law_holds'))} "
                     f"E_g*d={p.get('mean_gap_times_diameter_eV_nm', 0):.3f}eV*nm (meas 0.7-0.9) "
                     f"anchors<={p.get('max_anchor_rel_err', 0)*100:.0f}% "
                     f"{p.get('metallic_count')}metal/{p.get('semiconducting_count')}semi "
                     f"(gamma0={p.get('gamma0_eV')}eV)"),
            measured={"metallic_count": p.get("metallic_count"),
                      "semiconducting_count": p.get("semiconducting_count"),
                      "gap_scaling_eV_nm": round(float(p.get("gap_scaling_eV_nm") or 0.0), 4),
                      "mean_gap_times_diameter_eV_nm": round(float(p.get("mean_gap_times_diameter_eV_nm") or 0.0), 4),
                      "max_anchor_rel_err": round(float(p.get("max_anchor_rel_err") or 0.0), 4),
                      "metallicity_rule_holds": bool(val.get("metallicity_rule_holds")),
                      "gap_inverse_diameter_law_holds": bool(val.get("gap_inverse_diameter_law_holds")),
                      "measured_anchors_within_15pct": bool(val.get("measured_anchors_within_15pct"))},
            expected="metallicity = (n-m) mod 3 rule; semiconducting E_g proportional to 1/d on measured gaps",
            references=["SWCNT metallic iff (n-m) mod 3 == 0 (Saito, Dresselhaus & Dresselhaus 1998)",
                        "semiconducting E_g = 2 a_cc gamma0 / d; E_g*d ~ 0.7-0.9 eV*nm (STM, Wildoer/Odom 1998)"])


# ---------- registry ----------

ALL_CASES: List[ValidationCase] = [
    H2oFluidBrineRunCloses(),
    PascalPrincipleHolds(),
    OsmoticShiftObserved(),
    OpticsSurrogateTransportApplied(),
    SamplingDiversityNonDegenerate(),
    H2oMoleculeBondsStable(),
    H2oClusterFluidStable(),
    H2oBulkWaterStructure(),
    H2oDiffusionTemperatureTrend(),
    CntBandStructure(),
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
