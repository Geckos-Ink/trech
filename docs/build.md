# Build TRECH

[Documentation home](README.md) · [First experiment →](first_run.md) · [Run checks](validation/running_checks.md)

## Prerequisites

- CMake with support for the repository's [version 6 presets](../CMakePresets.json),
  Ninja and a C++20-capable compiler.
- A Geant4 build or installation with the datasets needed by the selected physics list.
  Set `Geant4_DIR` to the directory containing `Geant4Config.cmake`, or set
  `CMAKE_PREFIX_PATH` to the installation prefix. The Geant4 source pin lives in
  `thirds/geant4`. Keep local builds under `build/`. See the
  [Geant4 baseline and capability map](engine/GEANT4_features_and_limits.md).
- A platform-compatible LibTorch installation. TRECH searches `thirds/torch` by default.
  [`install_torch.sh`](../install_torch.sh) downloads a CPU distribution on supported
  hosts. For a separate installation, pass `-DTorch_DIR=<libtorch>/share/cmake/Torch`.
- A Python environment that imports `torch` and `numpy`. Set `TRECH_ML_PYTHON` if
  using an interpreter other than the repository default in `build/render-venv`.
  The [Torch tooling](../tools/torch/README.md) documents training and backend checks.
- QuickJS and nlohmann/json. The development and release presets allow CMake to
  fetch these if local sources are unavailable. V8 is optional (see below).

See the [dependency handbook](../AGENTS/tooling/dependencies/AGENTS.md) for checkout
guidance and [its roadmap](../AGENTS/tooling/dependencies/ROADMAP.md#priority-queue)
for compatibility checks still pending on pinned dependencies. Recorded validation
applies to the builds named by those reports.

## Configure and build

Run from the repository root. Use the actual path to your local Geant4 installation.

```sh
python3 -m venv build/render-venv
build/render-venv/bin/pip install -e tools/torch
cmake --preset dev -DCMAKE_PREFIX_PATH=/path/to/geant4-install
cmake --build --preset dev
```

The `dev` preset creates a debug build in `build/dev`. For an optimized build, configure
and build with `--preset rel` and use the binary under `build/rel`.
Use `-DTRECH_ENABLE_DNA_CHEM=ON` at configure time to include the optional
Geant4-DNA chemistry wiring. See the [Geant4 capability map](engine/GEANT4_features_and_limits.md#3-what-trech-can-count-on-geant4-capability-map)
for applicable models and materials.

## Optional: the V8 JavaScript engine

TRECH always builds QuickJS. Add `-DTRECH_ENABLE_V8=ON` to also build the V8 backend, which
runs the same scenarios and hooks several times faster when they do heavy JavaScript work.
CMake never builds V8 itself; point it at one that is already built:

- macOS: `brew install v8` (a prebuilt download). CMake finds Homebrew's prefix by itself.
- Any platform: build the pinned `thirds/v8` submodule from source with
  [`scripts/build_v8.sh`](../scripts/build_v8.sh), then pass `-DTRECH_V8_BUILD_DIR=<its out dir>`.
  This downloads several GB and compiles for a long time.
- Another installed V8: `-DTRECH_V8_ROOT=<prefix>` with `include/v8.h` and `lib/libv8*`.

```sh
cmake --preset rel -DCMAKE_PREFIX_PATH=/path/to/geant4-install -DTRECH_ENABLE_V8=ON
cmake --build --preset rel
./build/rel/trech inspect examples/scenarios/hello_world/hello_world.js --js-engine v8
```

Add `-DTRECH_DEFAULT_JS_ENGINE=v8` to make V8 the default of that binary. The
[V8 backend guide](engine/v8.md) explains selection, results and limits.

## Optional: Lean and Mathlib sources

`thirds/lean4` and `thirds/mathlib4` hold the sources for the [formal-laws route](engine/formal_laws.md).
The TRECH build never uses them, and a normal clone does not need them. To fetch or update
them, run `scripts/pull_lean.sh`; it clones them shallowly if missing and builds nothing.

Continue with the [first experiment](first_run.md) or
[install the Studio client](../studio/README.md).
