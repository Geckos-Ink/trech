#!/usr/bin/env bash
# Explicit experimental promotion gate. A failed candidate exits non-zero.
# Run from any directory; use an existing build and cached PubChem inputs.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "${ROOT}"
TRECH_BIN="${TRECH_BIN:-build/rel/trech}"
RUNS_DIR="${RUNS_DIR:-build/rel/foam_mechanics_candidate}"
PUBCHEM_CACHE="${PUBCHEM_CACHE:-build/pubchem_cache}"
if [[ ! -x "${TRECH_BIN}" ]]; then
  echo "error: build TRECH first or set TRECH_BIN" >&2
  exit 2
fi
mkdir -p "${RUNS_DIR}"
for CONTROL in nominal zero_g hot; do
  CONTROL_PARAMS=(--param gravity_scale=1)
  CONTROL_SUFFIX=""
  if [[ "${CONTROL}" == "zero_g" ]]; then
    CONTROL_PARAMS=(--param gravity_scale=0)
    CONTROL_SUFFIX="_zero_g"
  elif [[ "${CONTROL}" == "hot" ]]; then
    CONTROL_PARAMS=(--param initial_temperature_k=305)
    CONTROL_SUFFIX="_hot"
  fi
  for SOURCE in reference operator; do
    OUT="${RUNS_DIR}/out_polyurethane_mechanics_${SOURCE}${CONTROL_SUFFIX}"
    # The engine appends JSONL; require fresh output without deleting earlier evidence.
    if [[ -e "${OUT}" ]]; then
      echo "error: output already exists: ${OUT}; set RUNS_DIR to a fresh directory" >&2
      exit 2
    fi
    echo "foam mechanics: ${CONTROL} / ${SOURCE}"
    TRECH_PUBCHEM_CACHE_DIR="${PUBCHEM_CACHE}" "${TRECH_BIN}" run \
      examples/scenarios/polyurethane_foam/polyurethane_foam.js \
      --param "mechanics_source=\"${SOURCE}\"" "${CONTROL_PARAMS[@]}" \
      --output "${OUT}" >"${OUT}.log" 2>&1
  done
done
PYTHONPATH="${ROOT}/tools/validation:${PYTHONPATH:-}" python3 -m trech_validation \
  --suite foam-mechanics-candidate --runs-dir "${RUNS_DIR}" \
  --report "${RUNS_DIR}/promotion_report.md" --json "${RUNS_DIR}/promotion_report.json"
