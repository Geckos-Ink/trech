#!/usr/bin/env python3
"""Distil validation-only JS reference laws into portable TRECH operators.

This tool intentionally owns the remaining closed-form teachers for the
electrolysis/combustion and membrane-efflux migrations. Runtime scenarios use
the generated GenericSurrogate artefacts through ``ctx.react``/``ctx.evolve``;
the formulas below are training/validation references and never run on the
normal operator path.

The generated run-shaped datasets live under ``build/`` and are not source.
The portable JSON models and manifests under ``data/discrete_operators`` are
committed source-of-truth inference artefacts.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import shutil
from pathlib import Path
from typing import Callable, Dict, Iterable, List

from trech_torch.train_surrogate import main as train_surrogate


Row = Dict[str, float]


def _write_jsonl(path: Path, records: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for record in records:
            stream.write(json.dumps(record, separators=(",", ":")) + "\n")


def _make_run(path: Path, rows: List[Row], tag: str,
              characteristic_mm: float, seed: int) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _write_jsonl(path / "trech_scores.jsonl", [{
        "phase": "run_summary",
        "n_events": len(rows),
        "system_volume_mm3": characteristic_mm ** 3,
    }])
    config = {
        "run": {"nEvents": len(rows), "seed": seed},
        "detector": {"worldSizeMm": characteristic_mm},
        "determinism": {"mode": "strict"},
    }
    _write_jsonl(path / "trech_provenance.jsonl", [{
        "seed": seed,
        "n_events": len(rows),
        "determinism_mode": "strict",
        "config_json": json.dumps(config, separators=(",", ":")),
    }])
    chunk = 512
    records = []
    for begin in range(0, len(rows), chunk):
        records.append({
            "phase": "hook_emit",
            "event_id": begin,
            "hook": "validation_only_teacher",
            "tag": tag,
            "payload": {"samples": rows[begin:begin + chunk]},
        })
    _write_jsonl(path / "trech_hook_emits.jsonl", records)


def _event_activation(edep: float, track_length: float, steps: float,
                      energy_scale: float) -> float:
    edep_scale = math.log1p(edep / max(energy_scale, 1e-9))
    track_scale = math.log1p(track_length / 12.0)
    step_scale = math.log1p(steps) / 4.0
    return max(0.15, min(
        2.8, 0.40 + 0.55 * edep_scale + 0.20 * track_scale +
        0.15 * step_scale))


def _h2o_rows(seed: int, count: int) -> List[Row]:
    rng = random.Random(seed)
    rows: List[Row] = []
    for row_index in range(count):
        electrolysis = 1.0 if rng.random() < 0.5 else 0.0
        progress = (0.0 if row_index == 0 else
                    1.0 if row_index == 1 else rng.random())
        edep = rng.uniform(0.0, 0.025)
        track = rng.uniform(0.0, 45.0)
        steps = float(rng.randint(0, 24))
        field = rng.uniform(0.65, 1.35)
        water_mu = rng.uniform(0.030, 0.045)
        hydrogen_mu = rng.uniform(2.4e-6, 3.8e-6)
        oxygen_mu = rng.uniform(4.3e-5, 6.8e-5)
        cathode_energy = rng.uniform(0.006, 0.012)
        spark_energy = rng.uniform(0.022, 0.040)
        probe_energy = rng.uniform(0.025, 0.036)
        base_split = rng.uniform(0.007, 0.014)
        base_burn = rng.uniform(0.13, 0.24)
        activation = _event_activation(edep, track, steps, cathode_energy)
        gas_mean = 0.5 * (hydrogen_mu + oxygen_mu)
        interaction_scale = max(
            0.2, min(2.4, water_mu / max(gas_mean * 200.0, 1e-9)))
        ramp = min(1.0, progress * 7.0)
        p_molecule = min(
            0.45, base_split * field * interaction_scale * activation * ramp)
        # Each runtime element carries two H2O packets; this is the probability
        # that at least one of the teacher's two molecule trials fires.
        p_split_pair = 1.0 - (1.0 - p_molecule) ** 2
        spark_ramp = min(1.0, progress * 7.5)
        interaction_mix = max(
            0.1, min(2.0, spark_energy / max(probe_energy, 1e-9)))
        p_burn = min(
            0.80, base_burn * interaction_mix * activation * spark_ramp)
        rows.append({
            "water": float(rng.choice([0, 2])),
            "hydrogen": float(rng.choice([0, 2])),
            "oxygen": float(rng.choice([0, 1])),
            "phase_electrolysis": electrolysis,
            "phase_combustion": 1.0 - electrolysis,
            "phase_progress": progress,
            "event_edep_mev": edep,
            "event_track_length_mm": track,
            "event_step_count": steps,
            "field_strength": field,
            "water_mu_per_mm": water_mu,
            "hydrogen_mu_per_mm": hydrogen_mu,
            "oxygen_mu_per_mm": oxygen_mu,
            "cathode_energy_mev": cathode_energy,
            "spark_energy_mev": spark_energy,
            "probe_energy_mev": probe_energy,
            "base_dissociation_probability": base_split,
            "base_combustion_probability": base_burn,
            "dt": rng.uniform(0.75, 1.25),
            "hazard_electrolysis": p_split_pair if electrolysis else 0.0,
            "hazard_combustion": p_burn if not electrolysis else 0.0,
        })
    return rows


def _efflux_transport_rows(seed: int, count: int) -> List[Row]:
    """3D spherical-cell teacher: OU random velocity, rigid streaming rotation
    about z, and a radial efflux/clearance drift along the 3D outward normal."""
    rng = random.Random(seed)
    rows: List[Row] = []
    for row_index in range(count):
        cleared = 1.0 if rng.random() < 0.20 else 0.0
        radius = rng.uniform(0.0, 65.0 if cleared else 30.0)
        # Uniform direction on the sphere.
        cos_theta = rng.uniform(-1.0, 1.0)
        sin_theta = math.sqrt(max(0.0, 1.0 - cos_theta * cos_theta))
        phi = rng.uniform(-math.pi, math.pi)
        x = radius * sin_theta * math.cos(phi)
        y = radius * sin_theta * math.sin(phi)
        z = radius * cos_theta
        rvx = rng.uniform(-3.0, 3.0)
        rvy = rng.uniform(-3.0, 3.0)
        rvz = rng.uniform(-3.0, 3.0)
        permeant = 1.0 if rng.random() < 0.55 else 0.0
        mass = rng.uniform(70.0, 190.0)
        noise_x = (-3.5 if row_index == 0 else 3.5 if row_index == 1 else
                   max(-3.5, min(3.5, rng.gauss(0.0, 1.0))))
        noise_y = (3.5 if row_index == 0 else -3.5 if row_index == 1 else
                   max(-3.5, min(3.5, rng.gauss(0.0, 1.0))))
        noise_z = (-3.5 if row_index == 2 else 3.5 if row_index == 3 else
                   max(-3.5, min(3.5, rng.gauss(0.0, 1.0))))
        waste_speed = rng.uniform(0.75, 1.15)
        waste_mass = rng.uniform(72.0, 84.0)
        noise_scale = rng.uniform(0.38, 0.58)
        coupling = rng.uniform(0.012, 0.028)
        omega = rng.uniform(0.016, 0.032)
        efflux_drift = rng.uniform(0.018, 0.040)
        cleared_drift = rng.uniform(0.45, 0.75)
        dt = rng.uniform(0.75, 1.25)

        gamma = max(0.0, min(0.999, 1.0 - coupling))
        sigma = waste_speed * math.sqrt(waste_mass / max(mass, 1e-9))
        sigma *= noise_scale
        noise = sigma * math.sqrt(max(0.0, 1.0 - gamma * gamma))
        next_rvx = gamma * rvx + noise_x * noise
        next_rvy = gamma * rvy + noise_y * noise
        next_rvz = gamma * rvz + noise_z * noise
        norm = max(radius, 1e-9)
        nx = x / norm if radius > 1e-9 else 0.0
        ny = y / norm if radius > 1e-9 else 0.0
        nz = z / norm if radius > 1e-9 else 0.0
        if cleared:
            flow_x = nx * cleared_drift
            flow_y = ny * cleared_drift
            flow_z = nz * cleared_drift
        else:
            flow_x = -omega * y
            flow_y = omega * x
            flow_z = 0.0
            if permeant:
                flow_x += efflux_drift * nx
                flow_y += efflux_drift * ny
                flow_z += efflux_drift * nz
        rows.append({
            "x": x, "y": y, "z": z, "rvx": rvx, "rvy": rvy, "rvz": rvz,
            "mass_u": mass, "permeant": permeant, "cleared": cleared,
            "noise_x": noise_x, "noise_y": noise_y, "noise_z": noise_z,
            "waste_mean_speed": waste_speed, "waste_mass_u": waste_mass,
            "noise_scale": noise_scale, "thermostat_coupling": coupling,
            "circulation_omega": omega, "efflux_drift_speed": efflux_drift,
            "cleared_drift_speed": cleared_drift, "dt": dt,
            "set_rvx": next_rvx,
            "set_rvy": next_rvy,
            "set_rvz": next_rvz,
            "d_x_dt": next_rvx + flow_x,
            "d_y_dt": next_rvy + flow_y,
            "d_z_dt": next_rvz + flow_z,
        })
    return rows


def _efflux_crossing_rows(seed: int, count: int) -> List[Row]:
    rng = random.Random(seed)
    rows: List[Row] = []
    for row_index in range(count):
        permeant = 1.0 if rng.random() < 0.55 else 0.0
        at_boundary = 1.0 if rng.random() < 0.55 else 0.0
        xlogp = rng.uniform(-4.0, 3.5)
        p_ref = rng.uniform(0.012, 0.024)
        mu_membrane = rng.uniform(0.024, 0.035)
        mu_cytosol = rng.uniform(0.032, 0.044)
        edep = 0.0 if row_index == 0 else rng.uniform(0.0, 0.035)
        track = 0.0 if row_index == 0 else rng.uniform(0.0, 24.0)
        steps = 0.0 if row_index == 0 else float(rng.randint(0, 18))
        activation = max(0.75, min(
            1.35, 0.88 + 0.04 * math.log1p(steps) +
            0.012 * math.log1p(track) + 0.20 * edep))
        interaction_ratio = mu_cytosol / max(mu_membrane, 1e-12)
        hazard = min(0.95, p_ref * interaction_ratio * activation)
        eligible = permeant > 0.5 and at_boundary > 0.5 and xlogp > 0.0
        rows.append({
            "inside": 1.0,
            "cleared": 0.0,
            "permeant": permeant,
            "at_boundary": at_boundary,
            "xlogp": xlogp,
            "event_edep_mev": edep,
            "event_track_length_mm": track,
            "event_step_count": steps,
            "p_cross_reference": p_ref,
            "mu_membrane_per_mm": mu_membrane,
            "mu_cytosol_per_mm": mu_cytosol,
            "dt": rng.uniform(0.75, 1.25),
            "hazard_cross": hazard if eligible else 0.0,
        })
    return rows


# --- Osmotic cell (testscenario_osmotic) -------------------------------------------------------
# Certain passage/blocking is encoded as a margin target this far past the engine's [0,1] hazard
# bound: any prediction beyond the bound is clamped by ctx.react to exactly 1 (always crosses) or 0
# (never crosses). A target of exactly 0 would leave a small positive prediction, and with
# thousands of wall strikes per run that leaks blocked solute across the membrane.
OSMOTIC_CERTAINTY_MARGIN = 0.25


def _bounded_gaussian(rng: random.Random, limit: float = 3.5) -> float:
    return max(-limit, min(limit, rng.gauss(0.0, 1.0)))


def _osmotic_thermostat_rows(seed: int, count: int) -> List[Row]:
    """Per-particle Ornstein-Uhlenbeck velocity refresh of the osmotic bath.

    gamma = 1 - coupling; sigma = mean_speed * sqrt(m_ref / m); the refreshed velocity is
    gamma*v + noise*sigma*sqrt(1 - gamma^2). The rule has no position dependence, so positions
    are not inputs; free flight (x += v dt) is kinematics the scenario integrates.

    Targets are the per-tick velocity change d_v*_dt (small, so the fit's absolute error is
    small). A constant velocity bias b is amplified
    by the velocity memory to a drift b/(1-gamma) (25x at coupling 0.04), which pins slow
    solute to a bath wall, so rows come in mirrored (-v, -noise) pairs: the law is odd in them
    and the training set then carries no net bias. Velocities are drawn on each mass's own
    thermal scale (+-4.5 sigma), so heavy, slow solute is covered as densely as water."""
    rng = random.Random(seed)
    rows: List[Row] = []
    for row_index in range(0, count, 2):
        # Log-uniform mass covers water (1), the ion (1.2) and glucose (10) evenly.
        mass = math.exp(rng.uniform(math.log(0.8), math.log(12.5)))
        mean_speed = rng.uniform(0.7, 1.1)
        mass_ref = rng.uniform(0.8, 1.2)
        coupling = rng.uniform(0.02, 0.07)
        sigma = mean_speed * math.sqrt(mass_ref / max(mass, 1e-9))
        velocity = [sigma * rng.uniform(-4.5, 4.5) for _ in range(3)]
        # Corner rows pin the bounded-noise extremes into the measured input domain.
        noise = [_bounded_gaussian(rng) for _ in range(3)]
        if row_index < 6:
            noise[row_index // 2] = -3.5
        gamma = max(0.0, min(0.999, 1.0 - coupling))
        scale = sigma * math.sqrt(max(0.0, 1.0 - gamma * gamma))
        for sign in (1.0, -1.0):
            v = [sign * c for c in velocity]
            n = [sign * c for c in noise]
            nv = [gamma * v[k] + n[k] * scale for k in range(3)]
            rows.append({
                "vx": v[0], "vy": v[1], "vz": v[2], "mass_u": mass,
                "noise_x": n[0], "noise_y": n[1], "noise_z": n[2],
                "water_mean_speed": mean_speed, "water_mass_u": mass_ref,
                "thermostat_coupling": coupling,
                "d_vx_dt": nv[0] - v[0], "d_vy_dt": nv[1] - v[1], "d_vz_dt": nv[2] - v[2],
            })
    return rows[:count]


def _osmotic_crossing_rows(seed: int, count: int) -> List[Row]:
    """Channel passage of a particle that reached the membrane.

    A particle passes when it meets a pore (`in_pore`), fits the channel
    (radius <= channel radius) and carries the channel's polarity; otherwise the
    wall reflects it. The hazard of the direction the particle is on (inside ->
    out, outside -> in) is certain passage or certain blocking."""
    rng = random.Random(seed)
    rows: List[Row] = []
    for _ in range(count):
        inside = 1.0 if rng.random() < 0.5 else 0.0
        in_pore = 1.0 if rng.random() < 0.5 else 0.0
        channel_radius = rng.uniform(0.40, 1.20)
        # Half the rows sit within 0.3 of the channel radius, where the size verdict flips.
        if rng.random() < 0.5:
            radius = max(0.2, channel_radius + rng.uniform(-0.3, 0.3))
        else:
            radius = rng.uniform(0.2, 2.4)
        polarity = 1.0 if rng.random() < 0.5 else -1.0
        channel_polarity = 1.0 if rng.random() < 0.5 else -1.0
        passes = (in_pore > 0.5 and radius <= channel_radius and
                  polarity * channel_polarity > 0.0)
        certain = 1.0 + OSMOTIC_CERTAINTY_MARGIN
        blocked = -OSMOTIC_CERTAINTY_MARGIN
        rows.append({
            "inside": inside, "outside": 1.0 - inside, "in_pore": in_pore,
            "particle_radius": radius, "polarity": polarity,
            "channel_radius": channel_radius, "channel_polarity": channel_polarity,
            "hazard_cross_out": certain if passes and inside > 0.5 else blocked,
            "hazard_cross_in": certain if passes and inside < 0.5 else blocked,
        })
    return rows


# name -> (row generator, hook tag, characteristic size in mm). Used by `fresh_run` so committed
# operators can be re-checked on runs they never saw (trech_torch.recheck_models).
FRESH_RUN_PRODUCERS = {
    "h2o_cycle_transition_operator": (lambda seed, n: _h2o_rows(seed, n), "h2o_cycle_transition_teacher", 120.0),
    "efflux_transport_operator": (lambda seed, n: _efflux_transport_rows(seed, n), "efflux_transport_teacher", 0.10),
    "efflux_crossing_operator": (lambda seed, n: _efflux_crossing_rows(seed, n), "efflux_crossing_teacher", 0.10),
    "osmotic_thermostat_operator": (lambda seed, n: _osmotic_thermostat_rows(seed, n), "osmotic_thermostat_teacher", 0.10),
    "osmotic_crossing_operator": (lambda seed, n: _osmotic_crossing_rows(seed, n), "osmotic_crossing_teacher", 0.10),
}


def fresh_run(out_dir: str, seed: int, rows: int, name: str) -> None:
    """Write one run-shaped teacher dataset for `name` under `out_dir` (same layout as training).

    The seed selects the operating points; a seed the model was trained or held out on replays
    those exact rows, so callers must pass seeds outside the recorded training/holdout seeds.
    """
    generator, tag, scale_mm = FRESH_RUN_PRODUCERS[name]
    _make_run(Path(out_dir), generator(int(seed), int(rows)), tag, scale_mm, int(seed))


def _train(name: str, tag: str, inputs: List[str], outputs: List[str],
           root: Path, model_root: Path, rows: Callable[[int, int], List[Row]],
           scale_mm: float, seed: int, hidden: int, epochs: int,
           teacher: str, description: str, extra: Iterable[str] = ()) -> None:
    train_dir = root / name / "train"
    holdout_dir = root / name / "holdout"
    _make_run(train_dir, rows(seed, 24000), tag, scale_mm, seed)
    _make_run(holdout_dir, rows(seed + 100003, 6000), tag, scale_mm, seed + 100003)
    out_json = model_root / f"{name}.json"
    manifest = model_root / f"{name}.manifest.json"
    rc = train_surrogate([
        "--runs", str(train_dir),
        "--validation-runs", str(holdout_dir),
        "--source", "hook_emits", "--tag", tag, "--expand", "samples",
        "--inputs", ",".join(inputs), "--outputs", ",".join(outputs),
        "--out-json", str(out_json), "--manifest", str(manifest),
        "--hidden", str(hidden), "--epochs", str(epochs), "--lr", "0.004",
        "--seed", str(seed), "--teacher", teacher, "--measured", "false",
        "--note", description, *extra,
    ])
    if rc != 0:
        raise SystemExit(rc)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--work-root",
                        default="build/dev/discrete_operator_teachers")
    parser.add_argument("--model-root", default="data/discrete_operators")
    parser.add_argument("--epochs", type=int, default=900)
    parser.add_argument("--only", action="append", default=None,
                        help="retrain only the named operator(s) (repeatable); "
                             "default retrains all")
    args = parser.parse_args()
    work_root = Path(args.work_root).resolve()
    model_root = Path(args.model_root).resolve()
    model_root.mkdir(parents=True, exist_ok=True)
    selected = set(args.only or [])

    def wanted(name: str) -> bool:
        if selected and name not in selected:
            return False
        shutil.rmtree(work_root / name, ignore_errors=True)
        return True

    if wanted("h2o_cycle_transition_operator"):
        _train(
          "h2o_cycle_transition_operator", "h2o_cycle_transition_teacher",
          ["phase_electrolysis", "phase_combustion", "phase_progress", "event_edep_mev",
           "event_track_length_mm", "event_step_count", "field_strength",
           "water_mu_per_mm", "hydrogen_mu_per_mm", "oxygen_mu_per_mm",
           "cathode_energy_mev", "spark_energy_mev", "probe_energy_mev",
           "base_dissociation_probability", "base_combustion_probability", "dt"],
          ["hazard_electrolysis", "hazard_combustion"],
          work_root, model_root, _h2o_rows, 120.0, 2026072601, 32, args.epochs,
          "validation-only electrolysisProbability/combustionProbability reference",
          "Meso discrete H2O cycle hazards distilled from the retired JS normal-path "
          "reaction law over independent operating points. Atom conservation and "
          "seeded transitions remain engine-owned; targets are not measurements.")

    if wanted("efflux_transport_operator"):
        _train(
          "efflux_transport_operator", "efflux_transport_teacher",
          ["x", "y", "z", "rvx", "rvy", "rvz", "mass_u", "permeant", "cleared",
           "noise_x", "noise_y", "noise_z", "waste_mean_speed", "waste_mass_u",
           "noise_scale", "thermostat_coupling", "circulation_omega",
           "efflux_drift_speed", "cleared_drift_speed", "dt"],
          ["set_rvx", "set_rvy", "set_rvz", "d_x_dt", "d_y_dt", "d_z_dt"],
          # 64 hidden units / >=2400 epochs: the velocity-memory product
        # gamma(coupling) * rv sets the 3D diffusion (and so the clearance)
        # rate; a smaller fit learned gamma ~0.987 vs the teacher's 0.982,
        # a ~35% longer velocity memory that doubled the 3D clearance rate.
        work_root, model_root, _efflux_transport_rows, 0.10, 2026072602,
          64, max(args.epochs, 2400),
          "validation-only efflux OU/advection/drift reference",
          "Micro per-particle 3D membrane-efflux transport operator (spherical "
          "cell) distilled from the retired JS normal-path OU/advection/drift "
          "law. Boundary projection "
          "and seeded noise generation remain numerical machinery; targets are "
          "not measurements.")

    if wanted("efflux_crossing_operator"):
        _train(
          "efflux_crossing_operator", "efflux_crossing_teacher",
          ["inside", "cleared", "permeant", "at_boundary", "xlogp",
           "event_edep_mev", "event_track_length_mm", "event_step_count",
           "p_cross_reference", "mu_membrane_per_mm", "mu_cytosol_per_mm", "dt"],
          ["hazard_cross"],
          work_root, model_root, _efflux_crossing_rows, 0.10, 2026072603,
          32, args.epochs,
          "validation-only Overton/Geant4-scaled crossing reference",
          "Micro membrane-crossing hazard distilled from the retired JS "
          "normal-path selectivity/rate mapping. Packet identity, availability "
          "and seeded stochastic acceptance are engine-owned; targets are not "
          "measurements.")

    if wanted("osmotic_thermostat_operator"):
        _train(
          "osmotic_thermostat_operator", "osmotic_thermostat_teacher",
          ["vx", "vy", "vz", "mass_u", "noise_x", "noise_y", "noise_z",
           "water_mean_speed", "water_mass_u", "thermostat_coupling"],
          ["d_vx_dt", "d_vy_dt", "d_vz_dt"],
          # As for efflux transport: the velocity memory gamma sets the bath's kinetic energy
          # (variance sigma^2 (1-gamma^2)/(1-gamma'^2)) and amplifies any velocity bias into a
          # drift, so the fit gets width and epochs.
          work_root, model_root, _osmotic_thermostat_rows, 0.10, 2026112601,
          64, max(args.epochs, 4000),
          "validation-only osmotic Langevin (OU) velocity refresh reference",
          "Micro per-particle 3D velocity response (Langevin refresh) of the osmotic bath, "
          "distilled from the retired JS applyLangevinThermostat. Free flight, bath walls, "
          "membrane reflection and seeded noise generation remain numerical machinery; targets are "
          "not measurements.",
          # Anneal the step: the residual bias, not the variance, is what the bath amplifies.
          extra=("--lr-final-factor", "0.05"))

    if wanted("osmotic_crossing_operator"):
        _train(
          "osmotic_crossing_operator", "osmotic_crossing_teacher",
          ["inside", "outside", "in_pore", "particle_radius", "polarity",
           "channel_radius", "channel_polarity"],
          ["hazard_cross_out", "hazard_cross_in"],
          work_root, model_root, _osmotic_crossing_rows, 0.10, 2026112602,
          64, max(args.epochs, 2400),
          "validation-only osmotic channel size/polarity passage reference",
          "Micro membrane-channel passage hazards distilled from the retired JS stepParticle "
          "crossing rule (pore alignment, size and polarity). Certain passage/blocking is a target "
          f"{OSMOTIC_CERTAINTY_MARGIN} past the [0,1] bound so the engine clamp returns exact 1/0. "
          "Pore placement, inside/outside identity and seeded acceptance are engine/topology; "
          "targets are not measurements.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
