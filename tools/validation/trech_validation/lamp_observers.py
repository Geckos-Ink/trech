"""Frame-scale observers of a lava-lamp run, read from its ``material_frame`` emits.

They describe what an observer of the lamp sees over the whole run (how warm the wax is, how
high it sits, how far and how often it moves up and down, how molten it is), so two runs that
diverge parcel by parcel can still be compared as experiments. The validation case
``lava_lamp_domain_learner_deploy_closed_loop`` and ``tools/torch/study_domain_learning.py``
both use them, with the tolerances in ``TOLERANCES``.

No emit field outside ``material_frame`` is read, and nothing here changes a run.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Optional

# Absolute tolerances of the paired gate (deployed minus authored run at one condition),
# fixed before the first deploy run on 2026-11-28. Heights in mm (the liquid column is 180 mm),
# temperatures in K, liquid fraction dimensionless, reversals a count of frames.
TOLERANCES: Dict[str, float] = {
    "time_mean_temperature_k": 1.0,
    "final_mean_temperature_k": 2.0,
    "time_mean_height_mm": 10.0,
    "mean_height_range_mm": 20.0,
    "time_mean_liquid_fraction": 0.10,
    "liquid_fraction_range": 0.10,
}

# Frame-to-frame change of the mean height that counts as a direction (mm).
REVERSAL_STEP_MM = 1.0


def frames_from_emits(emits: Iterable[Dict]) -> List[Dict]:
    """The ``material_frame`` payloads of a run's hook emits, in emit order."""
    return [e.get("payload") or {} for e in emits if e.get("tag") == "material_frame"]


def observe(frames: List[Dict]) -> Optional[Dict[str, float]]:
    """Observers over every emitted frame, or None when the run has no frames."""
    temps, heights, liquid = [], [], []
    for frame in frames:
        physics = frame.get("physics_state") or {}
        positions = frame.get("positions_mm") or []
        if not positions or "mean_temperature_k" not in physics:
            continue
        temps.append(float(physics["mean_temperature_k"]))
        liquid.append(float(physics["mean_liquid_fraction"]))
        heights.append(sum(float(p[2]) for p in positions) / len(positions))
    if not heights:
        return None
    reversals, last_sign = 0, 0
    for a, b in zip(heights, heights[1:]):
        step = b - a
        sign = 1 if step > REVERSAL_STEP_MM else (-1 if step < -REVERSAL_STEP_MM else 0)
        if sign and last_sign and sign != last_sign:
            reversals += 1
        if sign:
            last_sign = sign
    n = len(heights)
    return {
        "frames": n,
        "time_mean_temperature_k": sum(temps) / n,
        "final_mean_temperature_k": temps[-1],
        "time_mean_height_mm": sum(heights) / n,
        "mean_height_range_mm": max(heights) - min(heights),
        "time_mean_liquid_fraction": sum(liquid) / n,
        "liquid_fraction_range": max(liquid) - min(liquid),
        "height_reversals": reversals,
    }


def compare(reference: Optional[Dict[str, float]], candidate: Optional[Dict[str, float]]) -> Dict[str, Dict]:
    """Per observer: both values, the absolute gap and, where gated, the tolerance verdict."""
    out: Dict[str, Dict] = {}
    for name in sorted(set(reference or {}) | set(candidate or {})):
        a = (reference or {}).get(name)
        b = (candidate or {}).get(name)
        gap = abs(b - a) if a is not None and b is not None else None
        entry = {"reference": a, "candidate": b, "gap": gap}
        if name in TOLERANCES:
            entry["tolerance"] = TOLERANCES[name]
            entry["within"] = gap is not None and gap <= TOLERANCES[name]
        out[name] = entry
    return out
