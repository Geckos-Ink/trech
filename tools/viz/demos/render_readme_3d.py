#!/usr/bin/env python3
"""Regenerate every README scenario animation as a faithful classic TRECH 3D replay.

Each entry runs a real scenario and renders its OWN output through ``trech-viz`` (the classic
PyVista viewer) -- nothing here synthesizes motion:

* Geant4-transport scenarios are captured with ``trech run --viz``/``--viz-all`` and replayed from
  ``trech_viz_trajectories.jsonl`` on the recorded Geant4 clock, with the engine's own
  predicted-vs-measured checks in the HUD (``trech_scores.jsonl``).
* Hook-layer scenarios emit ``material_frame`` (atoms, bonds, parcels, membranes, apparatus,
  vectors) straight from their solver state and are replayed held-frame.

Camera orbit, lighting, palette, ground grid and text are the only rendering choices.

Usage (from the repo root, render venv active or via its python)::

    build/render-venv/bin/python tools/viz/demos/render_readme_3d.py            # everything
    build/render-venv/bin/python tools/viz/demos/render_readme_3d.py --only beer_lambert csda
    build/render-venv/bin/python tools/viz/demos/render_readme_3d.py --list

Runs land in ``build/dev/out_readme_3d/<key>`` (derived data, gitignored); GIFs are written to
``tools/viz/demos/`` (committed README media).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

REPO = Path(__file__).resolve().parents[3]
DEMOS = REPO / "tools" / "viz" / "demos"
EXP = REPO / "examples" / "scenarios"
PUBCHEM_NAMES = ["benzene", "D-glucose", "water", "n-pentane", "hydrogen", "oxygen", "glycerol",
                 "toluene 2,4-diisocyanate", "hydrogen peroxide", "potassium iodide"]


@dataclass
class Capture:
    key: str
    gif: str
    title: str
    runs: List[List[str]] = field(default_factory=list)   # [run_subdir, scenario, *args]
    render: List[str] = field(default_factory=list)        # trech_viz args ({run} expands)
    custom: Optional[Callable[["Context", "Capture"], None]] = None
    slow: bool = False
    studio: bool = False  # scalar-grid renderer; classic points cannot display volume fields


@dataclass
class Context:
    trech: Path
    python: str
    runs_dir: Path
    pubchem_cache: Path
    skip_run: bool


def _run(cmd: List[str], env: Optional[Dict[str, str]] = None, log: Optional[Path] = None) -> None:
    started = time.time()
    with open(log, "w") if log else open(os.devnull, "w") as sink:
        proc = subprocess.run(cmd, cwd=REPO, env=env, stdout=sink, stderr=subprocess.STDOUT)
    if proc.returncode != 0:
        raise SystemExit(f"command failed ({proc.returncode}): {' '.join(cmd)}"
                         + (f"\n  see {log}" if log else ""))
    print(f"    ok ({time.time() - started:.0f}s): {' '.join(Path(c).name if '/' in c else c for c in cmd[:3])}")


def run_scenario(ctx: Context, subdir: str, scenario: str, args: List[str]) -> Path:
    out = ctx.runs_dir / subdir
    scores_path = out / "trech_scores.jsonl"
    if ctx.skip_run and scores_path.is_file():
        try:
            scores = [json.loads(line) for line in scores_path.read_text().splitlines() if line.strip()]
            if any(row.get("phase") == "run_end" for row in scores) and not scores[-1].get("hook_emit_dropped_count", 0):
                return out
        except (ValueError, OSError):
            pass  # An interrupted/incomplete output must be rerun, not replayed.
    shutil.rmtree(out, ignore_errors=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, TRECH_PUBCHEM_CACHE_DIR=str(ctx.pubchem_cache))
    script = scenario if scenario.startswith("/") else str(EXP / Path(scenario).stem / scenario)
    _run([str(ctx.trech), "run", script, *args, "--output", str(out)], env=env,
         log=ctx.runs_dir / f"{subdir}.log")
    if scores_path.is_file():
        score = json.loads(scores_path.read_text().splitlines()[-1])
        if score.get("hook_emit_dropped_count", 0):
            raise RuntimeError(f"{scenario}: dropped emits; refusing incomplete media")
    return out


def render(ctx: Context, cap: Capture, args: List[str]) -> None:
    gif = DEMOS / cap.gif
    if cap.studio:
        python = os.environ.get('STUDIO_PY',str(REPO/'build/studio-venv/bin/python'))
        _run([python,'-m','trech_studio.capture','--run',str(ctx.runs_dir/cap.runs[0][0]),
              '--out',str(gif.with_suffix('')),'--width','360','--height','240','--seconds','4',
              '--fps','10','--orbit','0','--annotations','--supersample','1'],
             env=dict(os.environ,PYTHONPATH=str(REPO/'studio')),
             log=ctx.runs_dir/f'{cap.key}.render.log')
        return
    _run([ctx.python, "-m", "trech_viz", *args, "--gif", str(gif), "--title", cap.title],
         env=dict(os.environ, PYTHONPATH=str(REPO / "tools" / "viz")),
         log=ctx.runs_dir / f"{cap.key}.render.log")
    print(f"    wrote {gif.relative_to(REPO)} ({gif.stat().st_size / 1e6:.2f} MB)")


def expand(args: List[str], ctx: Context) -> List[str]:
    return [a.replace("{runs}", str(ctx.runs_dir)) for a in args]


W, H = "1280", "720"   # README resolution (3D view + side chart panel)


def trajectory_args(run: str, *extra: str) -> List[str]:
    return ["--scene", f"{{runs}}/{run}/trech_viz_scene.json",
            "--trajectories", f"{{runs}}/{run}/trech_viz_trajectories.jsonl",
            "--scores", f"{{runs}}/{run}/trech_scores.jsonl",
            "--width", W, "--height", H, *extra]


def frame_args(run: str, *extra: str, scene: bool = False) -> List[str]:
    base = ["--emits", f"{{runs}}/{run}/trech_hook_emits.jsonl", "--width", W, "--height", H]
    if scene:
        base += ["--scene", f"{{runs}}/{run}/trech_viz_scene.json"]
    return base + list(extra)


def caption(*lines: str) -> List[str]:
    return ["--caption", "|".join(lines)]


def mr_tissues(ctx: Context, cap: Capture) -> None:
    """Stage-2 MRI: excitation count per tissue proportional to its Geant4 1H density (the
    multi-run driver's scheme: water 150, cortical bone 90), real photons detected in NaI."""
    work = ctx.runs_dir / "mr_tissues"
    work.mkdir(parents=True, exist_ok=True)
    for tissue, label, events in (("G4_WATER", "water", 150),
                                  ("G4_BONE_CORTICAL_ICRP", "cortical bone", 90)):
        slug = label.replace(" ", "_")
        wrapper = work / f"mr_{slug}.js"
        wrapper.write_text(
            f'globalThis.MR_TISSUE = "{tissue}";\nglobalThis.MR_LABEL = "{label}";\n'
            f'TRECH_INCLUDE("{EXP / "testscenario_magnetic_resonance_tissues" / "testscenario_magnetic_resonance_tissues.js"}");\n')
        run_scenario(ctx, f"mr_tissues/{slug}", str(wrapper),
                     ["--events", str(events), "--viz-all", "--viz-max-trajectories", "2000"])
    render(ctx, cap, expand([
        "--scene", "{runs}/mr_tissues/water/trech_viz_scene.json",
        "--trajectories", "{runs}/mr_tissues/water/trech_viz_trajectories.jsonl",
        "--compare-trajectories", "{runs}/mr_tissues/cortical_bone/trech_viz_trajectories.jsonl",
        "--compare-scene", "{runs}/mr_tissues/cortical_bone/trech_viz_scene.json",
        "--labels", "water (150 packets)|cortical bone (90 packets)",
        "--scores", "{runs}/mr_tissues/water/trech_scores.jsonl",
        "--compare-scores", "{runs}/mr_tissues/cortical_bone/trech_scores.jsonl",
        "--edep", "receiver_coil", "--split", "--charts", "tissues",
        "--tissues", "G4_WATER,G4_BONE_CORTICAL_ICRP",
        "--width", W, "--height", H, "--seconds", "8", "--fps", "12", "--orbit", "40",
        *caption("Geant4 cannot make spins radiate RF, so each 200 keV photon stands in for one "
                 "signal packet;",
                 "the packets per tissue follow Geant4's own proton density, and the NaI shell "
                 "scores what arrives."),
    ], ctx))


def mr_brain(ctx: Context, cap: Capture) -> None:
    """Stage-4 MRI: volumetric acquisition + reconstruction in the brain driver."""
    _run([ctx.python, str(REPO / "scripts" / "run_magnetic_resonance_brain.py"),
          "--binary", str(ctx.trech), "--runs-dir", str(ctx.runs_dir),
          "--out-png", str(ctx.runs_dir / "mr_brain_2d.png"), "--out-gif", str(DEMOS / cap.gif)],
         log=ctx.runs_dir / "mr_brain.log")
    print(f"    wrote {(DEMOS / cap.gif).relative_to(REPO)}")


def optics_pair(ctx: Context, cap: Capture) -> None:
    for flag in ("true", "false"):
        run_scenario(ctx, f"optics_surrogate_{flag}", "optics_surrogate_demo.js",
                     ["--param", "beam_tilt_deg=35", "--param", f"use_surrogate={flag}",
                      "--events", "200", "--viz", "--viz-max-trajectories", "200"])
    render(ctx, cap, expand([
        "--scene", "{runs}/optics_surrogate_true/trech_viz_scene.json",
        "--trajectories", "{runs}/optics_surrogate_true/trech_viz_trajectories.jsonl",
        "--compare-trajectories", "{runs}/optics_surrogate_false/trech_viz_trajectories.jsonl",
        "--compare-scene", "{runs}/optics_surrogate_false/trech_viz_scene.json",
        "--labels", "learned ridge surrogate|pure f-sum extractor", "--derived-n", "nai",
        "--split", "--bundle", "--charts", "refraction", "--incidence-deg", "35",
        "--frame", "scene", "--width", W, "--height", H, "--seconds", "7", "--fps", "12",
        "--orbit", "30",
        *caption("Same beam, same NaI block, two ways for the engine to derive n from Geant4 data.",
                 "The learned surrogate predicts n = 1.77 (close to NaI's measured ~1.77); the "
                 "pure f-sum extractor gives 1.33.",
                 "The higher index bends the light more at the entry face."),
    ], ctx))


def beaker(ctx: Context, cap: Capture) -> None:
    """The beaker's two liquids are both colourless (Geant4 optics); a display-only tint
    through the scenario's own representation override tells them apart."""
    work = ctx.runs_dir / "beaker_wrapper"
    work.mkdir(parents=True, exist_ok=True)
    wrapper = work / "beaker_tinted.js"
    wrapper.write_text(
        "globalThis.TRECH_BEAKER_VIZ_OVERRIDE = { waterTint: [0.55, 0.78, 1.0], "
        "pentaneTint: [1.0, 0.82, 0.42], waterAlpha: 0.75, pentaneAlpha: 0.75, "
        "vaporAlpha: 0.3 };\n"
        f'TRECH_INCLUDE("{EXP / "beaker_water_n_pentane" / "beaker_water_n_pentane.js"}");\n')
    run_scenario(ctx, "beaker", str(wrapper), ["--viz"])
    render(ctx, cap, expand(frame_args(
        "beaker", "--seconds", "12", "--fps", "10", "--orbit", "30", scene=True,
    ) + caption("Geant4 supplies both liquids' composition and density; the cascade predicts "
                "that they do not mix,",
                "that pentane floats, and how much evaporates in an hour at 30 °C. Tints are "
                "display-only."), ctx))


CAPTURES: List[Capture] = [
    Capture("lava_lamp", "lava_lamp_trech_viz.gif", "Lava lamp: recorded inferred parcel state",
            runs=[["lava_lamp", "lava_lamp.js", "--param", "duration_s=600", "--param", "simulation_ticks=100"]],
            render=frame_args("lava_lamp", "--seconds", "10", "--fps", "10", "--orbit", "20", scene=True)),
    Capture("polyurethane", "polyurethane_foam.gif", "Polyurethane: recorded comparison mechanics",
            runs=[["polyurethane", "polyurethane_foam.js"]],
            render=frame_args("polyurethane", "--seconds", "10", "--fps", "10", "--orbit", "20", scene=True), slow=True),
    Capture("toothpaste", "elephants_toothpaste.gif", "Catalytic foam: recorded comparison state",
            runs=[["toothpaste", "elephants_toothpaste.js"]],
            render=frame_args("toothpaste", "--seconds", "10", "--fps", "10", "--orbit", "20", scene=True)),
    Capture("aerodynamics", "aerodynamics.gif", "Independent 3D Euler comparison; not a learned aerodynamic prediction",
            runs=[["aerodynamics", "aerodynamics_reference.js"]],
            render=frame_args("aerodynamics", "--seconds", "4", "--fps", "10", "--orbit", "0"), studio=True),
    *[Capture("molecular_" + name, "molecular_" + name + ".gif",
              name.capitalize() + ": partial-charge polarization and rigid torsion scan",
              runs=[["molecular_" + name, f"molecular_0{i}_{name}.js"]],
              render=frame_args("molecular_" + name, "--seconds", "8", "--fps", "12",
                  "--orbit", "35", "--elevation", "0.25",
                  *caption("RHF/STO-3G learned response; Geant4 supplies elemental consistency and transport.",
                           "Bubbles = atom-integrated partial-charge glyphs, not orbitals. Imposed scan, not dynamics.")))
      for i, name in enumerate(("ethane", "ethanol", "formamide"), 1)],
    *[Capture("molecular_" + name, "molecular_" + name + ".gif",
              name.replace("_", " ").capitalize() + ": polarization and torsion",
              runs=[["molecular_" + name, f"molecular_0{i}_{name}.js"]],
              render=frame_args("molecular_" + name, "--stream", "torsion", "--seconds", "8", "--fps", "12",
                  "--orbit", "35", "--elevation", "0.25",
                  *caption("Red/blue: QM partial charge. Purple: Geant4-trained particle → atom → molecule response.",
                           "Gold: selected torsion axis. Imposed rigid scan; not molecular dynamics.")))
      for i, name in enumerate(("butane", "dimethyl_ether", "acetamide"), 4)],
    *[Capture("molecular_particle_" + name, "molecular_particle_" + name + ".gif",
              name.replace("_", " ").capitalize() + ": particle → atom → molecule",
              runs=[["molecular_" + name, f"molecular_0{i}_{name}.js"]],
              render=frame_args("molecular_" + name, "--stream", "particle_response", "--seconds", "8", "--fps", "12",
                  "--orbit", "25", "--elevation", "0.25",
                  *caption("Purple halo volume follows learned atomic photoelectric response; fixed display scale.",
                           "Particle energy is scanned, scaffold is held. Ground-state QM charge is shown separately.")))
      for i, name in enumerate(("butane", "dimethyl_ether", "acetamide"), 4)],
    Capture("hero_spectral", "glass_of_water_beam.gif",
            "White light through a glass of water (Geant4 optical transport)",
            runs=[["spectral", "glass_of_water_spectral.js", "--viz"]],
            render=trajectory_args(
                "spectral", "--derived-n", "water,glass", "--bundle", "--charts", "optical",
                "--trail", "0.25", "--seconds", "8", "--fps", "12",
                *caption("3000 photons, bundled by wavelength band and recorded surface history;",
                         "dots mark recorded reflections. The chart recovers each photon's "
                         "refractive index from its bend",
                         "and finds the engine's Geant4-derived n(λ): blue bends more."))),
    Capture("beer_lambert", "beer_lambert.gif",
            "Beer-Lambert: 100 keV gamma photons through 50 mm of water",
            runs=[["beer_lambert", "analytic_beer_lambert.js", "--viz-all",
                   "--viz-max-trajectories", "3000"]],
            render=trajectory_args(
                "beer_lambert", "--charts", "attenuation", "--display-events", "70", "--glyphs",
                "--frame", "scene", "--seconds", "8", "--fps", "12",
                *caption("Each line is one photon tracked by Geant4 (70 of 20000 drawn). Bright: "
                         "not yet interacted;",
                         "orange: after a Compton scatter. The chart counts photons still "
                         "untouched at each depth",
                         "against exp(−μx), with μ the engine computes from Geant4 cross "
                         "sections."))),
    Capture("csda", "csda_bragg.gif", "CSDA range: 20 MeV protons stopping in water",
            runs=[["csda", "analytic_csda_range.js", "--viz-all", "--viz-max-trajectories",
                   "3000"]],
            render=trajectory_args(
                "csda", "--charts", "bragg", "--display-events", "50", "--color-by", "energy",
                "--trail", "0.8", "--seconds", "8", "--fps", "12",
                *caption("Each line is one proton; colour is its recorded kinetic energy.",
                         "Protons lose energy fastest just before they stop (the Bragg peak), at "
                         "the range the engine predicts."))),
    Capture("photo_fraction", "photo_fraction.gif",
            "Photoelectric fraction: 30 keV gamma photons in water",
            runs=[["photo_fraction", "analytic_photo_fraction.js", "--viz-all",
                   "--viz-max-trajectories", "3000"]],
            render=trajectory_args(
                "photo_fraction", "--charts", "attenuation", "--display-events", "60",
                "--glyphs", "--frame", "scene", "--seconds", "8", "--fps", "12",
                *caption("At 30 keV a photon's first interaction is photoelectric absorption "
                         "(red) ~39% of the time,",
                         "Compton (white) or Rayleigh (blue) otherwise; scattered photons "
                         "(orange) fade as they leave."))),
    Capture("nuclear", "nuclear_cycle.gif",
            "Nitrogen-carbon cycle: thermal neutrons in N2 gas (Geant4 neutron-HP)",
            runs=[["nuclear", "config_nitrogen_carbon_cycle.js", "--viz-all",
                   "--viz-max-trajectories", "200000", "--events", "20000"]],
            render=trajectory_args(
                "nuclear", "--events-with", "C14", "--context-events", "25", "--nuclides",
                "--glyphs", "--charts", "nuclear", "--seconds", "10", "--fps", "12",
                *caption("Neutrons (grey) scatter off the carbon block; rarely a ¹⁴N nucleus "
                         "absorbs one, becomes ¹⁴C",
                         "and emits a proton. Thousands of years later on the Geant4 clock the "
                         "¹⁴C β⁻-decays back",
                         "to ¹⁴N, emitting an electron and an antineutrino. Both legs are "
                         "Geant4-sampled."))),
    Capture("optics_surrogate", "optics_surrogate.gif",
            "NaI block: which refractive index did the engine derive?", custom=optics_pair),
    Capture("sampling", "sampling_diversity.gif",
            "Beam sampling: spot, divergence and spectrum drawn per photon",
            runs=[["sampling", "glass_of_water_varied.js", "--viz", "--viz-max-trajectories",
                   "1500"]],
            render=trajectory_args(
                "sampling", "--charts", "sampling", "--display-events", "250", "--trail", "0.3",
                "--seconds", "7", "--fps", "12",
                *caption("Every photon gets its own start point, direction and wavelength from "
                         "the declared beam",
                         "distributions (seeded, reproducible); the charts are histograms of "
                         "what Geant4 emitted."))),
    Capture("brine", "brine_deposit.gif", "2 MeV gamma photons through brine and a salt crystal",
            runs=[["brine", "h2o_fluid.js", "--viz-all", "--viz-max-trajectories", "4000"]],
            render=trajectory_args(
                "brine", "--charts", "deposit", "--display-events", "60", "--glyphs",
                "--frame", "scene", "--seconds", "8", "--fps", "12",
                *caption("Brine (3% NaCl in water) and the salt cube are built from elements "
                         "(Geant4 has no NaCl compound).",
                         "Photons Compton-scatter and free electrons (cyan) that deposit their "
                         "energy in the liquid."))),
    Capture("mr_water", "magnetic_resonance.gif",
            "NMR of 5 cm³ of water: discovering the Larmor line",
            runs=[["mr_water", "testscenario_magnetic_resonance.js", "--viz"]],
            render=frame_args(
                "mr_water", "--seconds", "14", "--fps", "10", "--orbit", "40", "--elevation",
                "0.3", *caption(
                    "Protons in water (density from Geant4) align with the magnet's field B0 "
                    "into a net magnetization M.",
                    "Each RF pulse tips M about B_eff; only near resonance does it tip fully. "
                    "After the pulse the spins",
                    "precess at slightly different rates, fan out, and the detected signal "
                    "decays (FID)."), scene=True)),
    Capture("mr_tissues", "magnetic_resonance_tissues.gif",
            "MRI tissue contrast from real Geant4 photons", custom=mr_tissues),
    Capture("mr_imaging", "magnetic_resonance_imaging.gif",
            "1D MRI: a magnetic gradient turns frequency into position",
            runs=[["mr_imaging", "testscenario_magnetic_resonance_imaging.js"]],
            render=frame_args(
                "mr_imaging", "--seconds", "12", "--fps", "10", "--orbit", "30", "--elevation",
                "0.5", *caption(
                    "A field gradient makes each voxel's protons precess at a rate set by its "
                    "position.",
                    "The coil only hears the sum; a Fourier transform separates the "
                    "frequencies back into positions,",
                    "and each voxel's brightness is its Geant4-computed proton density."))),
    Capture("mr_brain", "magnetic_resonance_brain.gif", "Volumetric brain MRI", custom=mr_brain),
    Capture("h2o_molecule", "h2o_molecule.gif", "One H2O molecule: classical MD nuclei",
            runs=[["h2o_molecule", "h2o_molecule_stability.js"]],
            render=frame_args(
                "h2o_molecule", "--physical-duration", "1.0e-13", "--seconds", "8", "--fps",
                "12", "--orbit", "90", *caption(
                    "Velocity-Verlet integration of a flexible water molecule: the bonds "
                    "stretch and the angle bends",
                    "around the force field's rest geometry while total energy stays "
                    "constant."))),
    Capture("h2o_cluster", "h2o_cluster.gif", "8-molecule water droplet (flexible SPC-like MD)",
            runs=[["h2o_cluster", "h2o_cluster_fluid.js"]],
            render=frame_args(
                "h2o_cluster", "--seconds", "9", "--fps", "8", "--orbit", "90", "--colors", "48",
                *caption(
                    "Eight molecules held at 300 K: cyan links are O–O contacts under 3.5 Å "
                    "(the solver's",
                    "hydrogen-bond criterion). The droplet neither evaporates nor "
                    "collapses."))),
    Capture("h2o_bulk", "h2o_bulk_water.gif",
            "Bulk water: 108 rigid SPC/E molecules in a periodic cell",
            runs=[["h2o_bulk", "h2o_bulk_water.js"]],
            render=frame_args(
                "h2o_bulk", "--seconds", "10", "--fps", "8", "--orbit", "50", "--colors", "48",
                *caption("Classical molecular dynamics (hook layer; Geant4 is the clock). The "
                         "O–O g(r) on the right is",
                         "accumulated from these very frames: its first peak is the "
                         "hydrogen-bond distance.")),
            slow=True),
    Capture("diffusion", "diffusion_temperature.gif",
            "Water self-diffusion vs temperature (rigid SPC/E)",
            runs=[["diffusion", "h2o_diffusion_temperature.js"]],
            render=frame_args(
                "diffusion", "--seconds", "13", "--fps", "8", "--orbit", "40", "--colors", "48",
                *caption("The same box is held at 278, 298, then 318 K. Trails show each O "
                         "atom's real path over 480 fs;",
                         "D is the slope of the mean-square displacement, compared with measured "
                         "water.")),
            slow=True),
    Capture("glass_shaken", "glass_of_water_shaken.gif",
            "Glass of water poured and shaken (PBF, cascade-inferred)",
            runs=[["glass_shaken", "glass_of_water_shaken.js"]],
            render=frame_args(
                "glass_shaken", "--seconds", "10", "--fps", "10", "--orbit", "30",
                "--elevation", "0.35", *caption(
                    "Position-based-fluid particles whose rest density, viscosity and surface "
                    "tension are inferred",
                    "by the cascade from Geant4 facts. The glass follows the prescribed shake; "
                    "the waves are the solver's.")),
            slow=True),
    Capture("pascal", "pascal_press.gif", "Pascal's principle: rigid vs deformable vessels",
            runs=[["pascal", "testscenario_pascal.js"]],
            render=frame_args(
                "pascal", "--seconds", "12", "--fps", "8", "--orbit", "24", "--elevation", "0.3",
                "--colors", "48", *caption(
                    "A piston pushes a 3D water bath in three vessels. The pressure it adds "
                    "reaches the far wall",
                    "undiminished; a rigid wall holds, a Hookean wall bulges and keeps a "
                    "permanent set."))),
    Capture("osmotic", "osmotic_dehydration.gif",
            "Osmotic dehydration of a 3D cell in a hypertonic bath",
            runs=[["osmotic", "testscenario_osmotic.js"]],
            render=frame_args(
                "osmotic", "--seconds", "12", "--fps", "8", "--orbit", "40", "--elevation",
                "0.3", "--colors", "48", *caption(
                    "Water crosses the membrane's channels; glucose and ions cannot. With more "
                    "solute outside,",
                    "water leaves faster than it enters, the outside pushes harder, and the "
                    "membrane crenates.")),
            slow=True),
    Capture("efflux", "efflux_clearance.gif",
            "Membrane efflux from a 3D cell (learned transport + crossing operators)",
            runs=[["efflux", "testscenario_efflux.js"]],
            render=frame_args(
                "efflux", "--seconds", "16", "--fps", "8", "--orbit", "30", "--elevation", "0.3",
                "--colors", "48",
                *caption("Lipophilic benzene crosses the lipid membrane and is carried away; "
                         "polar glucose stays.",
                         "Both move by the same learned operators; only their PubChem XLogP "
                         "differs."))),
    Capture("electrolysis", "electrolysis.gif",
            "Electrolysis, then the reverse: combustion (ctx.react)",
            runs=[["electrolysis", "testscenario_h2o_electrolysis_combustion.js"]],
            render=frame_args(
                "electrolysis", "--seconds", "14", "--fps", "10", "--orbit", "40",
                "--elevation", "0.25", *caption(
                    "Current splits water into H₂ bubbles (cathodes) and O₂ (anode) that rise "
                    "into the headspace;",
                    "a spark then burns them back to water, which condenses and falls into the "
                    "bath.",
                    "Molecule counts are ctx.react output; bubble paths are representation."))),
    Capture("briggs_rauscher", "briggs_rauscher.gif",
            "Briggs-Rauscher oscillator (well-mixed, stirred beaker)",
            runs=[["briggs_rauscher", "briggs_rauscher_oscillator.js"]],
            render=frame_args(
                "briggs_rauscher", "--seconds", "12", "--fps", "10", "--orbit", "30",
                "--elevation", "0.35", *caption(
                    "The colour is read off concentrations the engine's learned kinetics "
                    "produce; nothing schedules",
                    "the changes. Amber = free iodine, blue-black = triiodide-starch. The stir "
                    "bar's spin is representation."), scene=True)),
    Capture("glass_from_sand", "glass_from_sand.gif",
            "Glass from sand: soda-lime glass forming in a heated crucible",
            runs=[["glass_from_sand", "glass_from_sand.js", "--viz"]],
            render=frame_args(
                "glass_from_sand", "--seconds", "12", "--fps", "8", "--orbit", "40",
                "--elevation", "0.3", "--colors", "48", *caption(
                    "Sand + soda ash + limestone (grains) heat from the furnace floor, release "
                    "CO₂, melt, and fuse",
                    "into glass. Each cell's material class comes from the learned operators; "
                    "surfaces are drawn",
                    "around the solver's cells."), scene=True)),
    Capture("beaker", "beaker_water_n_pentane.gif",
            "Water + n-pentane: layering and evaporation predicted by the cascade",
            custom=beaker),
    Capture("cnt_band", "cnt_band_structure.gif",
            "CNT band structure: 26 chiralities rolled from (n,m)",
            runs=[["cnt_band", "cnt_band_structure.js"]],
            render=frame_args("cnt_band", "--seconds", "8", "--fps", "8", "--orbit", "50",
                              "--elevation", "0.45", "--colors", "48")),
    Capture("cnt_sweep", "cnt_structure.gif",
            "CNT transistors: semiconducting (16,0) vs metallic (5,5) and (9,0)",
            runs=[["cnt_logic", "cnt_logic_gates.js"]],
            render=frame_args(
                "cnt_logic", "--stream", "cnt_transfer_sweep", "--seconds", "10", "--fps", "10",
                "--orbit", "60", *caption(
                    "The rolling angle (n,m) sets the band gap. Raising the gate voltage turns "
                    "the semiconducting tube on",
                    "(electrons flow source → drain); the metallic tubes conduct at any gate "
                    "voltage, so they cannot switch.",
                    "Currents come from the tight-binding + Fermi-Dirac model."))),
    Capture("cnt_gates", "cnt_circuit.gif", "CNTFET static-CMOS gates, one truth row at a time",
            runs=[["cnt_logic", "cnt_logic_gates.js"]],
            render=frame_args("cnt_logic", "--stream", "cnt_cmos_gates", "--reframe",
                              "--seconds", "14", "--fps", "8", "--orbit", "40")),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--trech", type=Path, default=None,
                        help="trech binary (default: build/rel/trech, else build/dev/trech)")
    parser.add_argument("--runs-dir", type=Path, default=REPO / "build" / "dev" / "out_readme_3d")
    parser.add_argument("--only", nargs="*", default=None, help="capture keys to (re)generate")
    parser.add_argument("--skip-slow", action="store_true",
                        help="skip the multi-minute MD / PBF / osmotic captures")
    parser.add_argument("--skip-run", action="store_true",
                        help="reuse existing run directories; only re-render")
    parser.add_argument("--list", action="store_true", help="list capture keys and exit")
    args = parser.parse_args()
    if args.list:
        for cap in CAPTURES:
            print(f"{cap.key:18s} -> tools/viz/demos/{cap.gif}{'  (slow)' if cap.slow else ''}")
        return 0
    trech = args.trech or next((p for p in (REPO / "build" / "rel" / "trech",
                                            REPO / "build" / "dev" / "trech") if p.exists()), None)
    if trech is None or not trech.exists():
        raise SystemExit("trech binary not found; build it or pass --trech")
    runs_dir = args.runs_dir.resolve()
    runs_dir.mkdir(parents=True, exist_ok=True)
    wanted = set(args.only) if args.only else None
    unknown = (wanted or set()) - {cap.key for cap in CAPTURES}
    if unknown:
        raise SystemExit(f"unknown capture keys: {sorted(unknown)} (see --list)")
    cache = REPO / "build" / "pubchem_cache"
    # Molecular comparisons ship pinned fixtures; rendering them is fully
    # offline and must not refresh unrelated chemistry property caches.
    molecular_only = wanted and all(key.startswith("molecular_") for key in wanted)
    if not molecular_only and not all((cache / f"{n.lower().replace(' ', '-').replace(',', '-')}.json").exists()
               for n in ("benzene", "water")):
        _run([sys.executable, "-m", "trech_pubchem", "fetch", "--cache-dir", str(cache),
              "--no-png", *PUBCHEM_NAMES],
             env=dict(os.environ, PYTHONPATH=str(REPO / "tools" / "pubchem")))
    ctx = Context(trech=trech.resolve(), python=sys.executable, runs_dir=runs_dir,
                  pubchem_cache=cache, skip_run=args.skip_run)
    done_runs: set = set()
    for cap in CAPTURES:
        if wanted is not None and cap.key not in wanted:
            continue
        if args.skip_slow and cap.slow and wanted is None:
            print(f"- {cap.key}: skipped (slow)")
            continue
        print(f"- {cap.key} -> {cap.gif}")
        if cap.custom is not None:
            cap.custom(ctx, cap)
            continue
        for run in cap.runs:
            if run[0] not in done_runs:
                run_scenario(ctx, run[0], run[1], run[2:])
                done_runs.add(run[0])
        render(ctx, cap, expand(cap.render, ctx))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
