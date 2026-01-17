#!/usr/bin/env sh
set -eu

BUILD_PRESET="${BUILD_PRESET:-dev}"
EVENTS="${EVENTS:-100}"
SCORES_FILE="${SCORES_FILE:-trech_scores.jsonl}"
PROVENANCE_FILE="${PROVENANCE_FILE:-trech_provenance.jsonl}"
SUMMARY_FILE="${SUMMARY_FILE:-docs/validation_summary.md}"

if ! command -v cmake >/dev/null 2>&1; then
  echo "Missing cmake. Install CMake before running validation." 1>&2
  exit 1
fi

if ! command -v ninja >/dev/null 2>&1; then
  echo "Missing ninja. Install Ninja or adjust the CMake preset generator." 1>&2
  exit 1
fi

if ! command -v c++ >/dev/null 2>&1 && \
   ! command -v clang++ >/dev/null 2>&1 && \
   ! command -v g++ >/dev/null 2>&1; then
  echo "Missing C++ compiler. Install clang++ or g++ before running validation." 1>&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "Missing python3. Install Python 3 for score summarization." 1>&2
  exit 1
fi

cmake --preset "${BUILD_PRESET}"
cmake --build --preset "${BUILD_PRESET}"
if ctest --help 2>/dev/null | grep -q -- "--preset"; then
  ctest --preset "${BUILD_PRESET}"
else
  ctest --test-dir "build/${BUILD_PRESET}"
fi

trech_output=$("./build/${BUILD_PRESET}/trech" run examples/experiments/h2o_fluid.js --events "${EVENTS}" 2>&1)
echo "${trech_output}"
if echo "${trech_output}" | grep -q "Geant4 disabled"; then
  if [ -d "thirds/geant4" ]; then
    echo "TRECH built without Geant4; submodule at thirds/geant4 is present. Build/install it and set Geant4_DIR or CMAKE_PREFIX_PATH, then rebuild." 1>&2
  else
    echo "TRECH built without Geant4; install Geant4 and rebuild for H2O validation." 1>&2
  fi
  exit 1
fi

if [ ! -f "${SCORES_FILE}" ]; then
  echo "Missing ${SCORES_FILE}. Validation run did not emit scores." 1>&2
  exit 1
fi

python3 scripts/update_validation_summary.py \
  --scores "${SCORES_FILE}" \
  --provenance "${PROVENANCE_FILE}" \
  --output "${SUMMARY_FILE}"
