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
#   N_EVENTS_MOLECULE(default: 2000)          ticks for the H2O single-molecule MD
#   N_EVENTS_CLUSTER(default: 4000)           ticks for the H2O cluster-fluid MD
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
#   SKIP_SURROGATE  (default: 0)              set to 1 to skip ridge re-export + surrogate demo
#   RIDGE_MODEL     (default: data/optics_surrogate_ridge.json)  ridge model export path

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
N_EVENTS_MOLECULE="${N_EVENTS_MOLECULE:-2000}"
N_EVENTS_CLUSTER="${N_EVENTS_CLUSTER:-4000}"
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
SKIP_SURROGATE="${SKIP_SURROGATE:-0}"
RIDGE_MODEL="${RIDGE_MODEL:-data/optics_surrogate_ridge.json}"

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
    --output "${RUNS_DIR}/out_viz_refraction" >/dev/null 2>&1 || true

  echo "  - viz_refraction_demo (replay run, same seed)"
  rm -rf "${RUNS_DIR}/out_viz_refraction_replay"
  "${TRECH_BIN}" run examples/experiments/viz_refraction_demo.js \
    --events "${N_EVENTS_VIZ}" \
    --output "${RUNS_DIR}/out_viz_refraction_replay" >/dev/null 2>&1 || true

  echo "  - config_nitrogen_carbon_cycle"
  rm -rf "${RUNS_DIR}/out_nitrogen_cycle"
  "${TRECH_BIN}" run examples/experiments/config_nitrogen_carbon_cycle.js \
    --events "${N_EVENTS_CYCLE}" \
    --output "${RUNS_DIR}/out_nitrogen_cycle" >/dev/null 2>&1 || true

  if [[ "${SKIP_GOW}" != "1" ]]; then
    echo "  - validation_glass_of_water"
    rm -rf "${RUNS_DIR}/out_validation_gow"
    "${TRECH_BIN}" run examples/experiments/validation_glass_of_water.js \
      --events "${N_EVENTS_GOW}" \
      --output "${RUNS_DIR}/out_validation_gow" >/dev/null 2>&1 || true

    echo "  - glass_of_water_varied (anti-degeneration sampling-diversity guard)"
    rm -rf "${RUNS_DIR}/out_gow_varied"
    "${TRECH_BIN}" run examples/experiments/glass_of_water_varied.js \
      --events "${N_EVENTS_VARIED}" \
      --output "${RUNS_DIR}/out_gow_varied" >/dev/null 2>&1 || true
  fi

  if [[ "${SKIP_H2O}" != "1" ]]; then
    echo "  - h2o_fluid (brine + salt; element-component regression guard)"
    rm -rf "${RUNS_DIR}/out_h2o_fluid"
    "${TRECH_BIN}" run examples/experiments/h2o_fluid.js \
      --events "${N_EVENTS_H2O}" \
      --output "${RUNS_DIR}/out_h2o_fluid" >/dev/null 2>&1 || true
  fi

  if [[ "${SKIP_FLUID}" != "1" ]]; then
    echo "  - testscenario_pascal (Pascal's principle, hook-driven bath)"
    rm -rf "${RUNS_DIR}/out_pascal"
    "${TRECH_BIN}" run examples/experiments/testscenario_pascal.js \
      --events "${N_EVENTS_PASCAL}" \
      --output "${RUNS_DIR}/out_pascal" >/dev/null 2>&1 || true

    echo "  - testscenario_osmotic (osmosis across a semipermeable membrane)"
    rm -rf "${RUNS_DIR}/out_osmotic"
    "${TRECH_BIN}" run examples/experiments/testscenario_osmotic.js \
      --events "${N_EVENTS_OSMOTIC}" \
      --output "${RUNS_DIR}/out_osmotic" >/dev/null 2>&1 || true

    echo "  - h2o_molecule_stability (Sputnik: single-molecule bond stability)"
    rm -rf "${RUNS_DIR}/out_h2o_molecule"
    "${TRECH_BIN}" run examples/experiments/h2o_molecule_stability.js \
      --events "${N_EVENTS_MOLECULE}" \
      --output "${RUNS_DIR}/out_h2o_molecule" >/dev/null 2>&1 || true

    echo "  - h2o_cluster_fluid (Sputnik: multi-molecule fluid behavior)"
    rm -rf "${RUNS_DIR}/out_h2o_cluster"
    "${TRECH_BIN}" run examples/experiments/h2o_cluster_fluid.js \
      --events "${N_EVENTS_CLUSTER}" \
      --output "${RUNS_DIR}/out_h2o_cluster" >/dev/null 2>&1 || true
  fi

  echo "  - optics_training_panel"
  rm -rf "${RUNS_DIR}/out_optics_panel"
  "${TRECH_BIN}" run examples/experiments/optics_training_panel.js \
    --events 1 \
    --output "${RUNS_DIR}/out_optics_panel" >/dev/null 2>&1 || true

  if [[ "${SKIP_SURROGATE}" != "1" && -d "${RUNS_DIR}/out_optics_panel" ]]; then
    # (a) CI retrain/re-export: refit the ridge on the freshly-derived panel and
    # overwrite the committed model, so `git diff ${RIDGE_MODEL}` flags drift
    # whenever the extractor or dataset changes (same pattern as the report).
    echo "  - re-export ridge surrogate model -> ${RIDGE_MODEL}"
    python3 "${ROOT}/scripts/validate_optics_surrogate.py" \
      --run "${RUNS_DIR}/out_optics_panel" --no-write \
      --export "${RIDGE_MODEL}" >/dev/null 2>&1 || true

    # (b) end-to-end transport guard: run the opt-in surrogate demo with the
    # just-exported model so the validation case can confirm the learned n was
    # shifted into transport (RINDEX) for NaI.
    echo "  - optics_surrogate_demo (ridge surrogate -> transport)"
    rm -rf "${RUNS_DIR}/out_optics_surrogate"
    "${TRECH_BIN}" run examples/experiments/optics_surrogate_demo.js \
      --events 1 \
      --output "${RUNS_DIR}/out_optics_surrogate" >/dev/null 2>&1 || true
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
    --run "${RUNS_DIR}/out_optics_panel" || true
fi
