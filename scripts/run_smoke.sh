#!/usr/bin/env sh
set -eu

BUILD_PRESET="${BUILD_PRESET:-dev}"

if ! command -v cmake >/dev/null 2>&1; then
  echo "Missing cmake. Install CMake before running the smoke test." 1>&2
  exit 1
fi

if ! command -v ninja >/dev/null 2>&1; then
  echo "Missing ninja. Install Ninja or adjust the CMake preset generator." 1>&2
  exit 1
fi

if ! command -v c++ >/dev/null 2>&1 && \
   ! command -v clang++ >/dev/null 2>&1 && \
   ! command -v g++ >/dev/null 2>&1; then
  echo "Missing C++ compiler. Install clang++ or g++ before running the smoke test." 1>&2
  exit 1
fi

cmake --preset "${BUILD_PRESET}"
cmake --build --preset "${BUILD_PRESET}"
ctest --test-dir "build/${BUILD_PRESET}"

"./build/${BUILD_PRESET}/trech" run examples/experiments/hello_world.js
