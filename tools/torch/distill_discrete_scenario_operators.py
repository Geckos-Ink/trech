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
    rng = random.Random(seed)
    rows: List[Row] = []
    for row_index in range(count):
        cleared = 1.0 if rng.random() < 0.20 else 0.0
        radius = rng.uniform(0.0, 65.0 if cleared else 30.0)
        angle = rng.uniform(-math.pi, math.pi)
        x = radius * math.cos(angle)
        y = radius * math.sin(angle)
        rvx = rng.uniform(-3.0, 3.0)
        rvy = rng.uniform(-3.0, 3.0)
        permeant = 1.0 if rng.random() < 0.55 else 0.0
        mass = rng.uniform(70.0, 190.0)
        noise_x = (-3.5 if row_index == 0 else 3.5 if row_index == 1 else
                   max(-3.5, min(3.5, rng.gauss(0.0, 1.0))))
        noise_y = (3.5 if row_index == 0 else -3.5 if row_index == 1 else
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
        norm = max(radius, 1e-9)
        nx = x / norm if radius > 1e-9 else 0.0
        ny = y / norm if radius > 1e-9 else 0.0
        if cleared:
            flow_x = nx * cleared_drift
            flow_y = ny * cleared_drift
        else:
            flow_x = -omega * y
            flow_y = omega * x
            if permeant:
                flow_x += efflux_drift * nx
                flow_y += efflux_drift * ny
        rows.append({
            "x": x, "y": y, "rvx": rvx, "rvy": rvy,
            "mass_u": mass, "permeant": permeant, "cleared": cleared,
            "noise_x": noise_x, "noise_y": noise_y,
            "waste_mean_speed": waste_speed, "waste_mass_u": waste_mass,
            "noise_scale": noise_scale, "thermostat_coupling": coupling,
            "circulation_omega": omega, "efflux_drift_speed": efflux_drift,
            "cleared_drift_speed": cleared_drift, "dt": dt,
            "set_rvx": next_rvx,
            "set_rvy": next_rvy,
            "d_x_dt": next_rvx + flow_x,
            "d_y_dt": next_rvy + flow_y,
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


def _train(name: str, tag: str, inputs: List[str], outputs: List[str],
           root: Path, model_root: Path, rows: Callable[[int, int], List[Row]],
           scale_mm: float, seed: int, hidden: int, epochs: int,
           teacher: str, description: str) -> None:
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
        "--note", description,
    ])
    if rc != 0:
        raise SystemExit(rc)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--work-root",
                        default="build/dev/discrete_operator_teachers")
    parser.add_argument("--model-root", default="data/discrete_operators")
    parser.add_argument("--epochs", type=int, default=900)
    args = parser.parse_args()
    work_root = Path(args.work_root).resolve()
    model_root = Path(args.model_root).resolve()
    shutil.rmtree(work_root, ignore_errors=True)
    model_root.mkdir(parents=True, exist_ok=True)

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

    _train(
        "efflux_transport_operator", "efflux_transport_teacher",
        ["x", "y", "rvx", "rvy", "mass_u", "permeant", "cleared",
         "noise_x", "noise_y", "waste_mean_speed", "waste_mass_u",
         "noise_scale", "thermostat_coupling", "circulation_omega",
         "efflux_drift_speed", "cleared_drift_speed", "dt"],
        ["set_rvx", "set_rvy", "d_x_dt", "d_y_dt"],
        work_root, model_root, _efflux_transport_rows, 0.10, 2026072602,
        40, args.epochs,
        "validation-only efflux OU/advection/drift reference",
        "Micro per-particle membrane-efflux transport operator distilled from "
        "the retired JS normal-path OU/advection/drift law. Boundary projection "
        "and seeded noise generation remain numerical machinery; targets are "
        "not measurements.")

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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
