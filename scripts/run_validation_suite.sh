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
#   REPORT_MD       (default: docs/validation_report.md)
#   REPORT_JSON     (default: docs/validation_report.json)
#   SKIP_BUILD      (default: 0)              set to 1 to skip the build step
#   SKIP_SCENARIOS  (default: 0)              set to 1 to skip running scenarios

set -euo pipefail

BUILD_PRESET="${BUILD_PRESET:-dev}"
RUNS_DIR="${RUNS_DIR:-build/${BUILD_PRESET}}"
N_EVENTS_VIZ="${N_EVENTS_VIZ:-60}"
N_EVENTS_CYCLE="${N_EVENTS_CYCLE:-5}"
REPORT_MD="${REPORT_MD:-docs/validation_report.md}"
REPORT_JSON="${REPORT_JSON:-docs/validation_report.json}"
SKIP_BUILD="${SKIP_BUILD:-0}"
SKIP_SCENARIOS="${SKIP_SCENARIOS:-0}"

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
fi

echo "==> Running validation"
PYTHONPATH="${ROOT}/tools/validation:${PYTHONPATH:-}" python3 -m trech_validation \
  --runs-dir "${RUNS_DIR}" \
  --report "${REPORT_MD}" \
  --json "${REPORT_JSON}"

echo "==> Report: ${REPORT_MD}"
echo "==> Sidecar: ${REPORT_JSON}"
