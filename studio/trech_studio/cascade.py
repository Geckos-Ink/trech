"""The scale ladder: the multi-scale inference cascade, made legible.

The engine lifts a Geant4 particle/nano base up the dimension ladder
(atomic → nano → micro → meso → macro) through scale-tagged learned stages, and records what it
did on the reserved ``__cascade`` object (and on each ``ctx.evolve``/``ctx.react``/``ctx.interact``
operator report) inside ``trech_hook_emits.jsonl``. Until now that lived only in raw JSON. This
module turns it into the ladder a human can read: which stages ran, at which band, what seeded the
bottom of the ladder from Geant4, and — the honesty half — which stages were **extrapolating past
their trained domain**, sitting in a **starved** (unpopulated) region of it, applied **off the band
they learned**, or carrying **no measured accuracy at all**.

Studio derives no physics here. Every value is a straight read of a field the engine emitted; the
only thing this module adds is *labels* for booleans the engine already decided (badges) and the
count of how many times a pass was emitted. Anything the engine did not record is reported as
**not reported** — never as a zero, and never as a pass.

Pure (no Qt, no engine IO): it consumes an already-parsed ``engine.outputs.RunResult`` and returns
data the panel renders, so it is unit-testable headless.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

# Ascending dimension bands, mirroring trech::ml::DimensionScale. Used only to *sort passes for
# display when the engine's own order is unavailable* — a pass's stages are always shown in the
# order the engine ran them.
BAND_ORDER: Tuple[str, ...] = ("atomic", "nano", "micro", "meso", "macro", "unscaled")

# Badge labels. These name a flag the ENGINE set; Studio never invents one.
BADGE_EXTRAPOLATING = "EXTRAPOLATING"
BADGE_STARVED = "STARVED REGION"
BADGE_JOINT_STARVED = "STARVED REGION (JOINT)"
BADGE_OFF_BAND = "OFF TRAINED BAND"
BADGE_HEURISTIC_DOMAIN = "HEURISTIC DOMAIN"
BADGE_NO_HOLDOUT = "NO MEASURED ACCURACY"
BADGE_DID_NOT_RUN = "DID NOT RUN"


@dataclass
class OutputAccuracy:
    """One predicted quantity's MEASURED held-out error, as carried by the model."""

    name: str
    r2: Optional[float] = None
    mae: Optional[float] = None
    rmse: Optional[float] = None  # measured 1-sigma residual, in the output's own units

    def describe(self) -> str:
        parts: List[str] = []
        if self.r2 is not None:
            parts.append(f"R²={_num(self.r2)}")
        if self.rmse is not None:
            parts.append(f"σ={_num(self.rmse)}")
        elif self.mae is not None:
            parts.append(f"MAE={_num(self.mae)}")
        return f"{self.name}: " + (", ".join(parts) if parts else "no measured error")


@dataclass
class LadderStage:
    """One executed (or skipped) inference stage, exactly as the engine reported it."""

    model: str
    scale: str = ""
    ran: bool = False
    outputs: List[str] = field(default_factory=list)          # cascade stages
    integrated_fields: List[str] = field(default_factory=list)  # operator: d_<field>_dt
    assigned_fields: List[str] = field(default_factory=list)    # operator: set_<field>
    missing_inputs: List[str] = field(default_factory=list)
    element_kind: str = ""
    # Trust profile (all optional: absent means the emit did not carry it).
    in_domain: Optional[bool] = None
    domain_measured: Optional[bool] = None
    extrapolation: Optional[float] = None
    out_of_domain_inputs: List[str] = field(default_factory=list)
    starved_inputs: List[str] = field(default_factory=list)
    # Joint (multivariate) starvation: in range on every axis yet far from any
    # training point. `joint_measured` False means the model carries no joint
    # reference and the check was NOT performed -- unknown, not a pass.
    joint_measured: Optional[bool] = None
    joint_starved: Optional[bool] = None
    joint_distance: Optional[float] = None
    joint_radius: Optional[float] = None
    elements_joint_starved: Optional[int] = None
    scale_mismatch: Optional[bool] = None
    trained_scale: str = ""
    holdout_r2: Optional[float] = None
    holdout_samples: Optional[int] = None
    output_accuracy: List[OutputAccuracy] = field(default_factory=list)
    # Batched operator stages report how much they actually touched.
    elements_matched: Optional[int] = None
    elements_out_of_domain: Optional[int] = None

    @property
    def predicts(self) -> List[str]:
        """What this stage produced, whichever shape the engine reported it in."""
        if self.outputs:
            return list(self.outputs)
        return list(self.integrated_fields) + list(self.assigned_fields)

    @property
    def badges(self) -> List[str]:
        """Display labels for flags the ENGINE set (no Studio judgement)."""
        out: List[str] = []
        if not self.ran:
            out.append(BADGE_DID_NOT_RUN)
            return out
        if self.in_domain is False or (self.elements_out_of_domain or 0) > 0:
            out.append(BADGE_EXTRAPOLATING)
        if self.starved_inputs:
            out.append(BADGE_STARVED)
        if self.joint_starved or (self.elements_joint_starved or 0) > 0:
            out.append(BADGE_JOINT_STARVED)
        if self.scale_mismatch:
            out.append(BADGE_OFF_BAND)
        if self.domain_measured is False:
            out.append(BADGE_HEURISTIC_DOMAIN)
        if self.holdout_r2 is None:
            out.append(BADGE_NO_HOLDOUT)
        return out

    def joint_note(self) -> str:
        """What the multivariate density check found -- or that nobody ran it."""
        if not self.joint_measured:
            return (
                "no joint training reference travels with this model: whether "
                "this point is in a region training actually covered was not "
                "checked (the per-feature range checks cannot answer it)"
            )
        distance = f"{self.joint_distance:.4g}" if self.joint_distance is not None else "?"
        radius = f"{self.joint_radius:.4g}" if self.joint_radius is not None else "?"
        if self.joint_starved or (self.elements_joint_starved or 0) > 0:
            return (
                f"in range on every axis, but {distance} from the nearest region "
                f"training covered (radius {radius}) — an interpolation across "
                f"untrained space"
            )
        return f"inside a region training covered ({distance} ≤ radius {radius})"

    def accuracy_note(self) -> str:
        """How well this stage is known to predict — or that nobody measured it."""
        if self.holdout_r2 is None and not self.output_accuracy:
            return (
                "no held-out accuracy travels with this model — an illustrative map, "
                "not a trained-and-validated stage"
            )
        parts: List[str] = []
        if self.holdout_r2 is not None:
            samples = f" on {self.holdout_samples} held-out rows" if self.holdout_samples else ""
            parts.append(f"worst output R²={_num(self.holdout_r2)}{samples}")
        if self.output_accuracy:
            parts.append("per output — " + "; ".join(a.describe() for a in self.output_accuracy))
        return "; ".join(parts)


@dataclass
class LadderPass:
    """One recorded inference pass: a cascade (properties) or an operator (state change)."""

    kind: str  # "cascade" | "operator"
    tag: str  # the emit tag the pass was found under
    path: str = ""  # where inside that payload the trace sat (scenarios choose the key)
    stages: List[LadderStage] = field(default_factory=list)
    seed_keys: List[str] = field(default_factory=list)
    stages_run: Optional[int] = None
    stages_extrapolating: Optional[int] = None
    stages_scale_mismatched: Optional[int] = None
    stages_starved: Optional[int] = None
    inference_count: Optional[int] = None
    out_of_domain_inferences: Optional[int] = None
    selection_status: str = ""
    occurrences: int = 1  # how many emits carried this pass (the last one is shown)

    @property
    def bands(self) -> List[str]:
        """The distinct scale bands this pass bridged, in the engine's execution order."""
        seen: List[str] = []
        for stage in self.stages:
            if stage.ran and stage.scale and stage.scale not in seen:
                seen.append(stage.scale)
        return seen

    @property
    def geant4_seed_keys(self) -> List[str]:
        """Seed keys that came from the Geant4 base (event tallies / material probes).

        The engine names ambient material facts ``material.<name>.<fact>`` and per-event tallies
        with its own fixed vocabulary; anything else in ``seedKeys`` was supplied by the scenario.
        """
        return [k for k in self.seed_keys if k.startswith("material.") or k in _EVENT_SEED_KEYS]

    def headline(self) -> str:
        bands = self.bands
        span = " → ".join(bands) if bands else "no band recorded"
        ran = self.stages_run if self.stages_run is not None else sum(1 for s in self.stages if s.ran)
        where = f" · {self.path}" if self.path else ""
        return f"{self.tag}{where} · {ran} stage(s) · {span}"


@dataclass
class ScaleLadder:
    output_dir: str = ""
    passes: List[LadderPass] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.passes

    def pass_for(self, tag: str) -> Optional[LadderPass]:
        for p in self.passes:
            if p.tag == tag:
                return p
        return None

    @property
    def bands_bridged(self) -> List[str]:
        """Every distinct band any pass in this run touched, in ladder order.

        The headline cascade metric from the root ROADMAP: a narrow point-predictor bridges one.
        """
        seen = {b for p in self.passes for b in p.bands}
        return [b for b in BAND_ORDER if b in seen]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "output_dir": self.output_dir,
            "bands_bridged": self.bands_bridged,
            "passes": [
                {
                    "kind": p.kind,
                    "tag": p.tag,
                    "bands": p.bands,
                    "seed_keys": list(p.seed_keys),
                    "stages": [
                        {"model": s.model, "scale": s.scale, "ran": s.ran, "badges": s.badges}
                        for s in p.stages
                    ],
                }
                for p in self.passes
            ],
        }


# The per-event Geant4 tallies `buildAmbientGeant4Seed` puts in the seed (docs/scenario_hooks.md).
_EVENT_SEED_KEYS = frozenset(
    {
        "edep_mev",
        "track_length_mm",
        "step_count",
        "track_count",
        "optical_photon_steps",
        "optical_photon_tracks",
        "optical_photon_track_length_mm",
    }
)


def _num(value: float) -> str:
    return f"{value:.6g}"


def _as_float(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _as_int(value: Any) -> Optional[int]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value: Any) -> Optional[bool]:
    return value if isinstance(value, bool) else None


def _as_str_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(v) for v in value if isinstance(v, (str, int, float))]


def _parse_output_accuracy(raw: Any) -> List[OutputAccuracy]:
    """Read ``outputAccuracy`` — the model's MEASURED per-output held-out error.

    An output the model never measured is simply absent from the emit; it stays absent here
    rather than being shown as a zero error.
    """
    if not isinstance(raw, dict):
        return []
    out: List[OutputAccuracy] = []
    for name in sorted(raw):
        entry = raw[name]
        if not isinstance(entry, dict):
            continue
        out.append(
            OutputAccuracy(
                name=str(name),
                r2=_as_float(entry.get("r2")),
                mae=_as_float(entry.get("mae")),
                rmse=_as_float(entry.get("rmse")),
            )
        )
    return out


def _parse_stage(raw: Dict[str, Any]) -> LadderStage:
    return LadderStage(
        model=str(raw.get("model") or ""),
        scale=str(raw.get("scale") or ""),
        ran=bool(raw.get("ran", False)),
        outputs=_as_str_list(raw.get("outputs")),
        integrated_fields=_as_str_list(raw.get("integratedFields")),
        assigned_fields=_as_str_list(raw.get("assignedFields")),
        missing_inputs=_as_str_list(raw.get("missingInputs")),
        element_kind=str(raw.get("elementKind") or raw.get("pairKind") or ""),
        in_domain=_as_bool(raw.get("inDomain")),
        domain_measured=_as_bool(raw.get("domainMeasured")),
        extrapolation=_as_float(raw.get("extrapolation") or raw.get("maxExtrapolation")),
        out_of_domain_inputs=_as_str_list(raw.get("outOfDomainInputs")),
        starved_inputs=_as_str_list(raw.get("starvedInputs")),
        joint_measured=_as_bool(raw.get("jointMeasured")),
        joint_starved=_as_bool(raw.get("jointStarved")),
        joint_distance=_as_float(raw.get("jointDistance") or raw.get("maxJointDistance")),
        joint_radius=_as_float(raw.get("jointRadius")),
        elements_joint_starved=_as_int(
            raw.get("elementsJointStarved") or raw.get("pairsJointStarved")
        ),
        scale_mismatch=_as_bool(raw.get("scaleMismatch")),
        trained_scale=str(raw.get("trainedScale") or ""),
        holdout_r2=_as_float(raw.get("holdoutR2")),
        holdout_samples=_as_int(raw.get("holdoutSamples")),
        output_accuracy=_parse_output_accuracy(raw.get("outputAccuracy")),
        elements_matched=_as_int(raw.get("elementsMatched") or raw.get("pairsMatched")),
        elements_out_of_domain=_as_int(
            raw.get("elementsOutOfDomain") or raw.get("pairsOutOfDomain")
        ),
    )


def _is_stage(node: Any) -> bool:
    """A stage-trace entry, identified by its own shape.

    Scenarios nest their inference reports under whatever key they like and rename the
    surrounding counters (``cascade``, ``cascade_trace``, ``chemistry_inference.stage_trace``,
    ``parcel_step_inferences`` …), so keying on a container name would find some runs and quietly
    miss others. What the engine fixes is the STAGE record: a model name, whether it ran, and its
    band/trust fields.
    """
    if not isinstance(node, dict):
        return False
    return (
        isinstance(node.get("model"), str)
        and isinstance(node.get("ran"), bool)
        and ("scale" in node or "holdoutR2" in node or "domainMeasured" in node)
    )


def _stage_list(node: Any) -> bool:
    return isinstance(node, list) and bool(node) and all(_is_stage(v) for v in node)


def _walk(node: Any, tag: str, path: str, found: List[Tuple[str, str, str, Dict[str, Any], List[Any]]]) -> None:
    """Collect every stage trace anywhere inside an emit payload, with its parent context."""
    if isinstance(node, dict):
        for key, value in node.items():
            child = f"{path}.{key}" if path else str(key)
            if _stage_list(value):
                kind = "cascade" if ("seedKeys" in node or "stagesRun" in node) else "operator"
                found.append((kind, tag, child, node, value))
            else:
                _walk(value, tag, child, found)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _walk(value, tag, f"{path}[{index}]", found)


def _build_pass(
    kind: str, tag: str, path: str, parent: Dict[str, Any], stages: List[Any]
) -> LadderPass:
    selection = parent.get("selection")
    status = ""
    if isinstance(selection, dict):
        status = str(selection.get("status") or "")
    return LadderPass(
        kind=kind,
        tag=tag,
        path=path,
        stages=[_parse_stage(s) for s in stages if isinstance(s, dict)],
        seed_keys=_as_str_list(parent.get("seedKeys")),
        stages_run=_as_int(parent.get("stagesRun")),
        stages_extrapolating=_as_int(parent.get("stagesExtrapolating")),
        stages_scale_mismatched=_as_int(parent.get("stagesScaleMismatched")),
        stages_starved=_as_int(parent.get("stagesStarved")),
        # An operator report carries its batched accounting; a scenario that renamed those
        # counters simply leaves them unreported rather than having Studio guess a total.
        inference_count=_as_int(parent.get("inferenceCount")),
        out_of_domain_inferences=_as_int(parent.get("outOfDomainInferences")),
        selection_status=status,
    )


def build_scale_ladder(result: Any, output_dir: str = "") -> ScaleLadder:
    """Build the ladder view from a run's hook emits.

    ``result`` is an ``engine.outputs.RunResult`` (duck-typed: anything exposing ``.emits`` with
    ``.tag``/``.payload``). Emits are append-mode and a scenario re-emits its cascade every event,
    so identical passes collapse to one entry showing the **last** occurrence, with the number of
    occurrences recorded rather than hidden.
    """
    ladder = ScaleLadder(output_dir=output_dir or getattr(result, "output_dir", "") or "")
    emits: Iterable[Any] = getattr(result, "emits", None) or []
    by_key: Dict[Tuple[str, str, str], LadderPass] = {}
    order: List[Tuple[str, str, str]] = []
    for emit in emits:
        payload = getattr(emit, "payload", None)
        tag = str(getattr(emit, "tag", "") or "")
        found: List[Tuple[str, str, str, Dict[str, Any], List[Any]]] = []
        _walk(payload, tag, "", found)
        for kind, emit_tag, path, parent, stages in found:
            built = _build_pass(kind, emit_tag, path, parent, stages)
            # A pass is identified by where it came from and which models it ran, so the same
            # cascade re-emitted every event collapses instead of flooding the ladder.
            key = (kind, emit_tag, path + "|" + "|".join(s.model for s in built.stages))
            if key in by_key:
                built.occurrences = by_key[key].occurrences + 1
            else:
                order.append(key)
            by_key[key] = built
    ladder.passes = [by_key[k] for k in order]
    return ladder
