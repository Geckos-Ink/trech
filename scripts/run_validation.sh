#!/usr/bin/env sh
set -eu

BUILD_PRESET="${BUILD_PRESET:-dev}"
EVENTS="${EVENTS:-100}"
SCORES_FILE="${SCORES_FILE:-trech_scores.jsonl}"

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
ctest --test-dir "build/${BUILD_PRESET}"

"./build/${BUILD_PRESET}/trech" run examples/experiments/h2o_fluid.js --events "${EVENTS}"

if [ ! -f "${SCORES_FILE}" ]; then
  echo "Missing ${SCORES_FILE}. Validation run did not emit scores." 1>&2
  exit 1
fi

python3 - "${SCORES_FILE}" <<'PY'
import json
import sys

path = sys.argv[1]
lines = []
with open(path, "r", encoding="utf-8") as handle:
  for line in handle:
    line = line.strip()
    if line:
      lines.append(line)

if not lines:
  raise SystemExit(f"{path} is empty.")

data = json.loads(lines[-1])
summary = {
  "phase": data.get("phase"),
  "total_edep_mev": data.get("total_edep_mev"),
  "optics_enabled": data.get("optics_enabled"),
  "optical_photon_tracks": data.get("optical_photon_tracks"),
  "optical_photon_steps": data.get("optical_photon_steps"),
  "optical_photon_track_length_mm": data.get("optical_photon_track_length_mm"),
  "n_events": data.get("n_events"),
  "seed": data.get("seed"),
  "physics_list": data.get("physics_list"),
}

print("trech_scores.jsonl (last entry):")
for key, value in summary.items():
  print(f"{key}={value}")
PY
