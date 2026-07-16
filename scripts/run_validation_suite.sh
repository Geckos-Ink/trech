#!/usr/bin/env bash
# Validation suite orchestrator.
#
# Builds the engine if needed, runs the scenarios the validation cases consume,
# then invokes the Python validation runner, which writes
# docs/validation_report.{md,json}.
#
# Env overrides:
#   BUILD_PRESET    (default: dev)            CMake preset to use
#   RUNS_DIR        (default: build/${BUILD_PRESET})
#   N_EVENTS_VIZ    (default: 60)             events for the viz refraction demo
#   N_EVENTS_CYCLE  (default: 5)              events for the nuclear cycle scenario
#   N_EVENTS_GOW    (default: 4000)           events for the glass-of-water optics validation
#   N_EVENTS_VARIED (default: 800)            events for the anti-degeneration varied-beam run
#   N_EVENTS_H2O    (default: 50)             events for the h2o_fluid brine regression run
#   N_EVENTS_PASCAL (default: 2400)           ticks for the Pascal's-principle scenario
#   N_EVENTS_OSMOTIC(default: 6000)           ticks for the osmosis scenario
#   N_EVENTS_EFFLUX (default: 6000)           ticks for the membrane-efflux scenario
#   beaker_water_n_pentane always uses 60 one-minute observer ticks
#   lava_lamp owns its duration/tick parameters; validation runs default, horizon, cool-control, and README cadences
#   N_EVENTS_H2O_CYCLE(default: 3000)         ticks for H2O electrolysis + inverse combustion
#   N_EVENTS_MOLECULE(default: 2000)          ticks for the H2O single-molecule MD
#   N_EVENTS_CLUSTER(default: 4000)           ticks for the H2O cluster-fluid MD
#   N_EVENTS_BULK   (default: 2500)           ticks for the H2O bulk-water MD (slow)
#   N_EVENTS_DIFFUSION_T (default: 8100)      ticks for the H2O D(T) temperature sweep (slow)
#   N_EVENTS_ANALYTIC (default: 20000)        events for the Beer-Lambert analytic cross-check
#   N_EVENTS_CSDA   (default: 5000)           protons for the CSDA-range analytic cross-check
#   N_EVENTS_PHOTO_FRACTION (default: 20000)  gammas for the photo-fraction analytic cross-check
#   REPORT_MD       (default: docs/validation_report.md)
#   REPORT_JSON     (default: docs/validation_report.json)
#   REPORT_GOW_MD   (default: docs/validation_glass_of_water.md)
#   REPORT_GOW_JSON (default: docs/validation_glass_of_water.json)
#   REPORT_GOW_TXT  (default: docs/benchmarks/validation_glass_of_water.txt)
#   SKIP_BUILD      (default: 0)              set to 1 to skip the build step
#   SKIP_SCENARIOS  (default: 0)              set to 1 to skip running scenarios
#   SKIP_GOW        (default: 0)              set to 1 to skip the glass-of-water validator
#   SKIP_H2O        (default: 0)              set to 1 to skip the h2o_fluid regression run
#   SKIP_FLUID      (default: 0)              set to 1 to skip the pascal/osmotic fluid runs
#   SKIP_BULK       (default: 0)              set to 1 to skip the slow bulk-water MD (~4.3 min)
#   SKIP_DIFFUSION_T(default: 0)              set to 1 to skip the slow D(T) sweep (~20 min)
#   SKIP_MR         (default: 0)              set to 1 to skip the magnetic-resonance run
#   N_EVENTS_MR     (default: 236)            ticks for the magnetic-resonance sweep+FID
#   SKIP_MR_TISSUES (default: 0)              set to 1 to skip the Stage-2 tissue-contrast driver
#   N_EVENTS_MR_TISSUES (default: 4000)       water-reference excitation events (others scale by N_H)
#   SKIP_MR_IMAGING (default: 0)              set to 1 to skip the Stage-3 1D imaging run
#   N_EVENTS_MR_IMAGING (default: 200)        clock events for the imaging phantom
#   SKIP_MR_BRAIN   (default: 0)              set to 1 to skip the Stage-4 2D brain-image driver (needs numpy)
#   SKIP_SURROGATE  (default: 0)              set to 1 to skip ridge re-export + surrogate demo
#   RIDGE_MODEL     (default: data/optics_surrogate_ridge.json)  ridge model export path
#   PUBCHEM_CACHE   (default: ${RUNS_DIR}/pubchem_cache) build-local PubChem cache

set -euo pipefail

BUILD_PRESET="${BUILD_PRESET:-dev}"
RUNS_DIR="${RUNS_DIR:-build/${BUILD_PRESET}}"
N_EVENTS_VIZ="${N_EVENTS_VIZ:-60}"
N_EVENTS_CYCLE="${N_EVENTS_CYCLE:-5}"
N_EVENTS_GOW="${N_EVENTS_GOW:-4000}"
N_EVENTS_VARIED="${N_EVENTS_VARIED:-800}"
N_EVENTS_H2O="${N_EVENTS_H2O:-50}"
N_EVENTS_PASCAL="${N_EVENTS_PASCAL:-2400}"
N_EVENTS_OSMOTIC="${N_EVENTS_OSMOTIC:-6000}"
N_EVENTS_EFFLUX="${N_EVENTS_EFFLUX:-6000}"
N_EVENTS_H2O_CYCLE="${N_EVENTS_H2O_CYCLE:-3000}"
N_EVENTS_MOLECULE="${N_EVENTS_MOLECULE:-2000}"
N_EVENTS_CLUSTER="${N_EVENTS_CLUSTER:-4000}"
N_EVENTS_BULK="${N_EVENTS_BULK:-2500}"
N_EVENTS_GLASS="${N_EVENTS_GLASS:-641}"
N_EVENTS_DIFFUSION_T="${N_EVENTS_DIFFUSION_T:-8100}"
N_EVENTS_ANALYTIC="${N_EVENTS_ANALYTIC:-20000}"
N_EVENTS_CSDA="${N_EVENTS_CSDA:-5000}"
N_EVENTS_PHOTO_FRACTION="${N_EVENTS_PHOTO_FRACTION:-20000}"
REPORT_MD="${REPORT_MD:-docs/validation_report.md}"
REPORT_JSON="${REPORT_JSON:-docs/validation_report.json}"
REPORT_GOW_MD="${REPORT_GOW_MD:-docs/validation_glass_of_water.md}"
REPORT_GOW_JSON="${REPORT_GOW_JSON:-docs/validation_glass_of_water.json}"
REPORT_GOW_TXT="${REPORT_GOW_TXT:-docs/benchmarks/validation_glass_of_water.txt}"
SKIP_BUILD="${SKIP_BUILD:-0}"
SKIP_SCENARIOS="${SKIP_SCENARIOS:-0}"
SKIP_GOW="${SKIP_GOW:-0}"
SKIP_H2O="${SKIP_H2O:-0}"
SKIP_FLUID="${SKIP_FLUID:-0}"
SKIP_BULK="${SKIP_BULK:-0}"
SKIP_GLASS="${SKIP_GLASS:-0}"
SKIP_DIFFUSION_T="${SKIP_DIFFUSION_T:-0}"
SKIP_SURROGATE="${SKIP_SURROGATE:-0}"
RIDGE_MODEL="${RIDGE_MODEL:-data/optics_surrogate_ridge.json}"
PUBCHEM_CACHE="${PUBCHEM_CACHE:-${RUNS_DIR}/pubchem_cache}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"

if [[ "${SKIP_BUILD}" != "1" ]]; then
  echo "==> Building (preset=${BUILD_PRESET})"
  cmake --build --preset "${BUILD_PRESET}" --target trech >/dev/null
fi

TRECH_BIN="${RUNS_DIR}/trech"
if [[ ! -x "${TRECH_BIN}" ]]; then
  echo "error: trech binary not found at ${TRECH_BIN}; build the project first." >&2
  exit 2
fi

if [[ "${SKIP_SCENARIOS}" != "1" ]]; then
  echo "==> Running scenarios"

  echo "  - viz_refraction_demo (primary run)"
  rm -rf "${RUNS_DIR}/out_viz_refraction"
  "${TRECH_BIN}" run examples/experiments/viz_refraction_demo.js \
    --events "${N_EVENTS_VIZ}" \
    --output "${RUNS_DIR}/out_viz_refraction" >/dev/null 2>&1

  echo "  - viz_refraction_demo (replay run, same seed)"
  rm -rf "${RUNS_DIR}/out_viz_refraction_replay"
  "${TRECH_BIN}" run examples/experiments/viz_refraction_demo.js \
    --events "${N_EVENTS_VIZ}" \
    --output "${RUNS_DIR}/out_viz_refraction_replay" >/dev/null 2>&1

  echo "  - config_nitrogen_carbon_cycle"
  rm -rf "${RUNS_DIR}/out_nitrogen_cycle"
  "${TRECH_BIN}" run examples/experiments/config_nitrogen_carbon_cycle.js \
    --events "${N_EVENTS_CYCLE}" \
    --output "${RUNS_DIR}/out_nitrogen_cycle" >/dev/null 2>&1

  echo "  - cnt_band_structure (Vostok: CNT electronic structure, fast)"
  rm -rf "${RUNS_DIR}/out_cnt_band_structure"
  "${TRECH_BIN}" run examples/experiments/cnt_band_structure.js \
    --events 5 \
    --output "${RUNS_DIR}/out_cnt_band_structure" >/dev/null 2>&1

  echo "  - cnt_logic_gates (Vostok: CNTFET logic gates + circuit truth tables, fast)"
  rm -rf "${RUNS_DIR}/out_cnt_logic_gates"
  "${TRECH_BIN}" run examples/experiments/cnt_logic_gates.js \
    --events 8 \
    --output "${RUNS_DIR}/out_cnt_logic_gates" >/dev/null 2>&1

  if [[ "${SKIP_MR:-0}" != "1" ]]; then
    echo "  - magnetic_resonance (Stage-1 NMR: discovered Larmor + Geant4 proton density, fast)"
    rm -rf "${RUNS_DIR}/out_mr"
    "${TRECH_BIN}" run examples/experiments/testscenario_magnetic_resonance.js \
      --events "${N_EVENTS_MR:-236}" \
      --output "${RUNS_DIR}/out_mr" >/dev/null 2>&1
  fi

  if [[ "${SKIP_MR_TISSUES:-0}" != "1" ]]; then
    echo "  - magnetic_resonance_tissues (Stage-2: REAL per-tissue photon contrast, ~20s)"
    python3 "${ROOT}/scripts/run_magnetic_resonance_tissues.py" \
      --binary "${TRECH_BIN}" --runs-dir "${RUNS_DIR}" \
      --base-events "${N_EVENTS_MR_TISSUES:-4000}" >/dev/null 2>&1
  fi

  if [[ "${SKIP_MR_IMAGING:-0}" != "1" ]]; then
    echo "  - magnetic_resonance_imaging (Stage-3: 1D frequency-encoded image line, fast)"
    rm -rf "${RUNS_DIR}/out_mr_imaging"
    "${TRECH_BIN}" run examples/experiments/testscenario_magnetic_resonance_imaging.js \
      --events "${N_EVENTS_MR_IMAGING:-200}" \
      --output "${RUNS_DIR}/out_mr_imaging" >/dev/null 2>&1
  fi

  if [[ "${SKIP_MR_BRAIN:-0}" != "1" ]]; then
    echo "  - magnetic_resonance_brain (Stage-4: 2D brain MRI image, needs numpy)"
    # Prefer the render venv (numpy + matplotlib for the README figure); fall back
    # to python3 (numpy still required; the figure render is skipped if missing).
    MR_BRAIN_PY="python3"
    if [[ -x "${ROOT}/build/render-venv/bin/python" ]]; then
      MR_BRAIN_PY="${ROOT}/build/render-venv/bin/python"
    fi
    "${MR_BRAIN_PY}" "${ROOT}/scripts/run_magnetic_resonance_brain.py" \
      --binary "${TRECH_BIN}" --runs-dir "${RUNS_DIR}" >/dev/null 2>&1
  fi

  echo "  - analytic_beer_lambert (classical formula vs Geant4 MC, fast)"
  rm -rf "${RUNS_DIR}/out_analytic_beer_lambert"
  "${TRECH_BIN}" run examples/experiments/analytic_beer_lambert.js \
    --events "${N_EVENTS_ANALYTIC}" \
    --output "${RUNS_DIR}/out_analytic_beer_lambert" >/dev/null 2>&1

  echo "  - analytic_csda_range (Geant4 stopping power -> CSDA range vs measured track length, fast)"
  rm -rf "${RUNS_DIR}/out_analytic_csda"
  "${TRECH_BIN}" run examples/experiments/analytic_csda_range.js \
    --events "${N_EVENTS_CSDA}" \
    --output "${RUNS_DIR}/out_analytic_csda" >/dev/null 2>&1

  echo "  - analytic_photo_fraction (Geant4 cross-section branching vs measured first-interaction fraction, fast)"
  rm -rf "${RUNS_DIR}/out_analytic_photo_fraction"
  "${TRECH_BIN}" run examples/experiments/analytic_photo_fraction.js \
    --events "${N_EVENTS_PHOTO_FRACTION}" \
    --output "${RUNS_DIR}/out_analytic_photo_fraction" >/dev/null 2>&1

  if [[ "${SKIP_GOW}" != "1" ]]; then
    echo "  - validation_glass_of_water"
    rm -rf "${RUNS_DIR}/out_validation_gow"
    "${TRECH_BIN}" run examples/experiments/validation_glass_of_water.js \
      --events "${N_EVENTS_GOW}" \
      --output "${RUNS_DIR}/out_validation_gow" >/dev/null 2>&1

    echo "  - glass_of_water_varied (anti-degeneration sampling-diversity guard)"
    rm -rf "${RUNS_DIR}/out_gow_varied"
    "${TRECH_BIN}" run examples/experiments/glass_of_water_varied.js \
      --events "${N_EVENTS_VARIED}" \
      --output "${RUNS_DIR}/out_gow_varied" >/dev/null 2>&1
  fi

  echo "  - surrogate_generic_demo (generic models[]/ctx.predict guard)"
  rm -rf "${RUNS_DIR}/out_surrogate_generic"
  "${TRECH_BIN}" run examples/experiments/surrogate_generic_demo.js \
    --output "${RUNS_DIR}/out_surrogate_generic" >/dev/null 2>&1

  if [[ "${SKIP_H2O}" != "1" ]]; then
    echo "  - h2o_fluid (brine + salt; element-component regression guard)"
    rm -rf "${RUNS_DIR}/out_h2o_fluid"
    "${TRECH_BIN}" run examples/experiments/h2o_fluid.js \
      --events "${N_EVENTS_H2O}" \
      --output "${RUNS_DIR}/out_h2o_fluid" >/dev/null 2>&1
  fi

  if [[ "${SKIP_FLUID}" != "1" ]]; then
    echo "  - testscenario_pascal (Pascal's principle, hook-driven bath)"
    rm -rf "${RUNS_DIR}/out_pascal"
    "${TRECH_BIN}" run examples/experiments/testscenario_pascal.js \
      --events "${N_EVENTS_PASCAL}" \
      --output "${RUNS_DIR}/out_pascal" >/dev/null 2>&1

    echo "  - testscenario_osmotic (osmosis across a semipermeable membrane)"
    rm -rf "${RUNS_DIR}/out_osmotic"
    "${TRECH_BIN}" run examples/experiments/testscenario_osmotic.js \
      --events "${N_EVENTS_OSMOTIC}" \
      --output "${RUNS_DIR}/out_osmotic" >/dev/null 2>&1

    echo "  - testscenario_efflux (passive membrane efflux vs first-order law)"
    echo "    fetching PubChem data -> ${PUBCHEM_CACHE}"
    PYTHONPATH="${ROOT}/tools/pubchem:${PYTHONPATH:-}" python3 -m trech_pubchem fetch \
      --cache-dir "${PUBCHEM_CACHE}" --no-png benzene "D-glucose" >/dev/null
    rm -rf "${RUNS_DIR}/out_efflux"
    TRECH_PUBCHEM_CACHE_DIR="${PUBCHEM_CACHE}" "${TRECH_BIN}" run examples/experiments/testscenario_efflux.js \
      --events "${N_EVENTS_EFFLUX}" \
      --output "${RUNS_DIR}/out_efflux" >/dev/null 2>&1

    echo "  - beaker_water_n_pentane (Geant4+structure cascade -> layers, colour, evaporation)"
    echo "    fetching PubChem structures only -> ${PUBCHEM_CACHE}"
    PYTHONPATH="${ROOT}/tools/pubchem:${PYTHONPATH:-}" python3 -m trech_pubchem fetch \
      --cache-dir "${PUBCHEM_CACHE}" --no-png water n-pentane >/dev/null
    rm -rf "${RUNS_DIR}/out_beaker_water_n_pentane"
    TRECH_PUBCHEM_CACHE_DIR="${PUBCHEM_CACHE}" "${TRECH_BIN}" run \
      examples/experiments/beaker_water_n_pentane.js \
      --output "${RUNS_DIR}/out_beaker_water_n_pentane" >/dev/null 2>&1

    echo "  - lava_lamp (persistent Geant4-seeded inferred thermofluid state)"
    rm -rf "${RUNS_DIR}/out_lava_lamp"
    "${TRECH_BIN}" run examples/experiments/lava_lamp.js \
      --output "${RUNS_DIR}/out_lava_lamp" >/dev/null 2>&1

    echo "  - lava_lamp 60-second horizon identity (same 5 s output cadence as default)"
    rm -rf "${RUNS_DIR}/out_lava_lamp_horizon_60s"
    "${TRECH_BIN}" run examples/experiments/lava_lamp.js \
      --param duration_s=60 --param simulation_ticks=12 \
      --output "${RUNS_DIR}/out_lava_lamp_horizon_60s" >/dev/null 2>&1

    echo "  - lava_lamp 60-second low-heater control (same material/state, different condition)"
    rm -rf "${RUNS_DIR}/out_lava_lamp_cool_heater"
    "${TRECH_BIN}" run examples/experiments/lava_lamp.js \
      --param duration_s=60 --param simulation_ticks=12 \
      --param heater_temperature_k=310 \
      --output "${RUNS_DIR}/out_lava_lamp_cool_heater" >/dev/null 2>&1

    echo "  - lava_lamp README cadence (100 Geant4 ticks -> 101 persistent one-minute states)"
    rm -rf "${RUNS_DIR}/out_lava_lamp_readme_1m"
    "${TRECH_BIN}" run examples/experiments/lava_lamp.js \
      --param duration_s=60 --param playback_duration_s=10 \
      --param simulation_ticks=100 --param heater_temperature_k=340 \
      --output "${RUNS_DIR}/out_lava_lamp_readme_1m" >/dev/null 2>&1

    echo "  - testscenario_h2o_electrolysis_combustion (PubChem+Geant4 reaction cycle)"
    echo "    fetching PubChem data -> ${PUBCHEM_CACHE}"
    PYTHONPATH="${ROOT}/tools/pubchem:${PYTHONPATH:-}" python3 -m trech_pubchem fetch \
      --cache-dir "${PUBCHEM_CACHE}" --no-png water hydrogen oxygen >/dev/null
    rm -rf "${RUNS_DIR}/out_h2o_cycle"
    TRECH_PUBCHEM_CACHE_DIR="${PUBCHEM_CACHE}" "${TRECH_BIN}" run examples/experiments/testscenario_h2o_electrolysis_combustion.js \
      --events "${N_EVENTS_H2O_CYCLE}" \
      --output "${RUNS_DIR}/out_h2o_cycle" >/dev/null 2>&1

    echo "  - h2o_molecule_stability (Sputnik: single-molecule bond stability)"
    rm -rf "${RUNS_DIR}/out_h2o_molecule"
    "${TRECH_BIN}" run examples/experiments/h2o_molecule_stability.js \
      --events "${N_EVENTS_MOLECULE}" \
      --output "${RUNS_DIR}/out_h2o_molecule" >/dev/null 2>&1

    echo "  - h2o_cluster_fluid (Sputnik: multi-molecule fluid behavior)"
    rm -rf "${RUNS_DIR}/out_h2o_cluster"
    "${TRECH_BIN}" run examples/experiments/h2o_cluster_fluid.js \
      --events "${N_EVENTS_CLUSTER}" \
      --output "${RUNS_DIR}/out_h2o_cluster" >/dev/null 2>&1

    if [[ "${SKIP_BULK}" != "1" ]]; then
      # Periodic bulk water with DSF electrostatics + O-O g(r) -- the slowest
      # scenario (~4.3 min at N=108); set SKIP_BULK=1 for a fast suite pass.
      echo "  - h2o_bulk_water (Sputnik: bulk liquid structure, O-O g(r))"
      rm -rf "${RUNS_DIR}/out_h2o_bulk"
      "${TRECH_BIN}" run examples/experiments/h2o_bulk_water.js \
        --events "${N_EVENTS_BULK}" \
        --output "${RUNS_DIR}/out_h2o_bulk" >/dev/null 2>&1
    fi

    if [[ "${SKIP_GLASS}" != "1" ]]; then
      # Multi-scale-cascade canonical demo: ~1 L of water poured into a wide glass
      # and shaken, its macro fluid parameters inferred from a nanoscale MD via
      # ctx.cascade, sloshed with a Position-Based-Fluid solver on a spatial grid
      # (~4300 particles, slow ~15-25 min); set SKIP_GLASS=1 for a faster pass.
      echo "  - glass_of_water_shaken (multi-scale cascade: nano -> macro sloshing, poured)"
      rm -rf "${RUNS_DIR}/out_glass_shaken"
      "${TRECH_BIN}" run examples/experiments/glass_of_water_shaken.js \
        --events "${N_EVENTS_GLASS}" \
        --output "${RUNS_DIR}/out_glass_shaken" >/dev/null 2>&1
    fi

    if [[ "${SKIP_DIFFUSION_T}" != "1" ]]; then
      # Rigid-SPC/E self-diffusion swept across 3 temperatures (D(T) trend vs
      # measured water) -- the slowest scenario (~20 min, N=108 over 3 blocks
      # with multi-ps structural equilibration per block); set
      # SKIP_DIFFUSION_T=1 for a faster suite pass.
      echo "  - h2o_diffusion_temperature (Sputnik: self-diffusion D(T) trend)"
      rm -rf "${RUNS_DIR}/out_h2o_diffusion_T"
      "${TRECH_BIN}" run examples/experiments/h2o_diffusion_temperature.js \
        --events "${N_EVENTS_DIFFUSION_T}" \
        --output "${RUNS_DIR}/out_h2o_diffusion_T" >/dev/null 2>&1
    fi
  fi

  echo "  - optics_training_panel"
  rm -rf "${RUNS_DIR}/out_optics_panel"
  "${TRECH_BIN}" run examples/experiments/optics_training_panel.js \
    --events 1 \
    --output "${RUNS_DIR}/out_optics_panel" >/dev/null 2>&1

  if [[ "${SKIP_SURROGATE}" != "1" && -d "${RUNS_DIR}/out_optics_panel" ]]; then
    # (a) CI retrain/re-export: refit the ridge on the freshly-derived panel and
    # overwrite the committed model, so `git diff ${RIDGE_MODEL}` flags drift
    # whenever the extractor or dataset changes (same pattern as the report).
    echo "  - re-export ridge surrogate model -> ${RIDGE_MODEL}"
    python3 "${ROOT}/scripts/validate_optics_surrogate.py" \
      --run "${RUNS_DIR}/out_optics_panel" --no-write \
      --export "${RIDGE_MODEL}" >/dev/null 2>&1

    # (b) end-to-end transport guard: run the opt-in surrogate demo with the
    # just-exported model so the validation case can confirm the learned n was
    # shifted into transport (RINDEX) for NaI.
    echo "  - optics_surrogate_demo (ridge surrogate -> transport)"
    rm -rf "${RUNS_DIR}/out_optics_surrogate"
    "${TRECH_BIN}" run examples/experiments/optics_surrogate_demo.js \
      --events 1 \
      --output "${RUNS_DIR}/out_optics_surrogate" >/dev/null 2>&1
  fi
fi

echo "==> Running validation"
PYTHONPATH="${ROOT}/tools/validation:${PYTHONPATH:-}" python3 -m trech_validation \
  --runs-dir "${RUNS_DIR}" \
  --report "${REPORT_MD}" \
  --json "${REPORT_JSON}"

echo "==> Report: ${REPORT_MD}"
echo "==> Sidecar: ${REPORT_JSON}"

if [[ "${SKIP_GOW}" != "1" && -d "${RUNS_DIR}/out_validation_gow" ]]; then
  echo "==> Running glass-of-water classical-optics validator"
  python3 "${ROOT}/scripts/validate_glass_of_water.py" \
    --run "${RUNS_DIR}/out_validation_gow" \
    --report "${REPORT_GOW_MD}" \
    --json "${REPORT_GOW_JSON}" \
    --txt "${REPORT_GOW_TXT}"
fi

if [[ -d "${RUNS_DIR}/out_optics_panel" ]]; then
  echo "==> Running optics surrogate held-out validator"
  python3 "${ROOT}/scripts/validate_optics_surrogate.py" \
    --run "${RUNS_DIR}/out_optics_panel"
fi
