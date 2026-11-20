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
  fetch these if local sources are unavailable.

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

Continue with the [first experiment](first_run.md) or
[install the Studio client](../studio/README.md).
