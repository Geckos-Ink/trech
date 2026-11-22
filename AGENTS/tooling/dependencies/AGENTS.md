# Builds, dependencies and optional backends — context and contracts

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

- **Geant4:** check for a local clone at [`thirds/geant4`](../../../thirds/geant4) before asking for it;
  never write absolute Geant4 paths in-repo (use `thirds/geant4-build`/`-install` or
  `build/geant4-build`/`-install`). Keep vendored deps current (see the standing dep-refresh note
  in the [dependency roadmap](ROADMAP.md); rebuilds are heavy — confirm before a bump).
- **Current dependency checkout:** Geant4 `f3d5293d38` (`v11.5.0.beta`), json
  `8617d9c94` (upstream develop), QuickJS `19d6bd8`. The Evolvo pin is recorded in the TRECH git tree.
  These upstream revisions have not yet been rebuilt or validated together; existing build
  outputs and validation reports do not establish compatibility with this checkout.
- **Evolvo workflow:** `thirds/evolvo` ([Geckos-Ink/evolvo](https://github.com/Geckos-Ink/evolvo)) is
  first-party pure Python, so it is exempt from the confirm-before-bump rule. This workflow applies
  whenever a task touches Evolvo, whether for Torch tooling, V8 or Geant4 work.
  1. **Pull first:** `git -C thirds/evolvo pull --ff-only` before reading or calling it. A pull
     that does not fast-forward (local Evolvo commits not yet upstream) is resolved by rebasing
     those commits, never by discarding them.
  2. **Edit Evolvo, not a TRECH copy:** a general-purpose capability or fix (language, search,
     statistics, torch building, packaging) is implemented in `thirds/evolvo/src/evolvo`. Follow
     its `AGENTS.md`, update its README/AGENTS and add tests under `thirds/evolvo/tests`.
     TRECH-specific glue (run harvesting, scalers, GenericSurrogate/TorchScript export,
     provenance) stays in `tools/torch/trech_torch`.
  3. **Commit there, then here:** commit on Evolvo's `main` with no co-author trailer, then
     commit the new submodule pointer in TRECH and update the checkout line above. Push Evolvo
     before (or with) any push of a TRECH commit that points at it, so the pointer resolves for
     other clones. Push only when asked.
- **Lean 4 and Mathlib (optional, reference checkouts):** `thirds/lean4`
  ([leanprover/lean4](https://github.com/leanprover/lean4)) and `thirds/mathlib4`
  ([leanprover-community/mathlib4](https://github.com/leanprover-community/mathlib4)) are
  shallow submodules tracking `master`. Pull both before every use with
  [`scripts/pull_lean.sh`](../../../scripts/pull_lean.sh) (fast-forward, heads, toolchain check),
  and commit moved pointers with the work that needed them. Current checkout (2026-11-22): lean4
  `5730ab5`, mathlib4 `6ebcce3733`, whose `lean-toolchain` is `v4.37.0-rc1`. CMake and CTest
  never use them; building Lean from source or Mathlib without its cache is heavy and gated. Installed
  2026-11-22 on macOS arm64: Homebrew `elan-init` 4.4.0 with toolchain `v4.37.0-rc1` and the Mathlib
  cache (6.9 GB, ignored). The opt-in `TRECH_ENABLE_LEAN_CHECK` uses them. Contract and rules:
  [formal-laws handbook](../../engine/formal/AGENTS.md).
- **LibTorch (required):** the deep-learning backend is mandatory (`TRECH_ML_BACKEND`, only
  `torch` today; the switch is the seam for a future alternative library). There is no
  learning-free build and no `TRECH_ENABLE_TORCH` option: an old cache's `OFF` is ignored with
  a warning. Gitignored `thirds/torch` is the official macOS ARM64 CPU package 2.14.1. It is
  not a submodule and CMake never downloads it. `./install_torch.sh` installs it, and a missing
  install stops configure with that instruction. `Torch_DIR` defaults to
  `thirds/torch/share/cmake/Torch` (made absolute). `trech_ml` and its consumers compile as
  C++20. The required `TRECH_ML_PYTHON` (default `build/render-venv/bin/python`, migrated from
  `TRECH_ARCH_PYTHON`) must import torch + NumPy at configure time. It trains models, runs the
  Evolvo worker and runs the torch/NumPy Python tests, which fail rather than skip.
  `TorchScriptStub` construction, destruction and moves are defined with the complete Module
  type. The `test_torch_backends` gate creates real synthetic TorchScript modules in C++, covering all
  three loaders, strict stratification, failed reloads and positional snapshot inference.
  GenericSurrogate's two positional APIs validate full finite tensors before publishing and
  return false on interpreter failures. Engine trace (`torch` category,
  [`src/ml/MlTrace.cpp`](../../../src/ml/MlTrace.cpp)): each `load` is `load` → private
  `loadImpl` plus `mltrace::modelLoaded` (backend, `describe(Module)`, `torchRuntime()`), each
  forward (`predictInto`'s JSON path, `predictTorchVector` → `predictTorchVectorImpl`,
  `OpticsSurrogate::predict` → `predictImpl`, `PredictLabel` → `PredictLabelImpl`) reports
  `mltrace::forward`; `DomainLearner`'s residual `Mlp::train` reports a `trainBurst` with the
  loss before/after (read only while tracing). `test_torch_backends` checks the records. A `<model>.pt.io.json` sidecar bound by
  `model_sha256` gives a module named IO, units, measured coverage and carried accuracy
  ([inference handbook](../../engine/inference/AGENTS.md)). Platform/model-deployment limits remain in the [dependency roadmap](ROADMAP.md).
- **QuickJS vs Node/V8 differential:** `scripts/js_engine_differential.py` (+ the Node host
  `scripts/js_engine_differential_node.js`) compares a scenario's top-level JS results bit for
  bit; CTest `trech_js_engine_differential` (needs `trech`, Node and Python, builds nothing).
  `--dmath` installs [`js/trech_dmath_v8.js`](../../../js/trech_dmath_v8.js) first and
  `trech_js_engine_differential_dmath` requires full bit identity.
- **`trech_dmath` WebAssembly module:** `js/trech_dmath_wasm_data.js` is generated and committed.
  Regenerate it with `scripts/build_dmath_wasm.py`, which needs an installed Emscripten `emcc`
  (optional, never fetched; Homebrew 6.0.13 recorded). CMake does not build it. CTest
  `trech_dmath_wasm` needs only Node and fails on a stale module (C source/header SHA-256).
- **V8 JavaScript backend:** `TRECH_ENABLE_V8` (default OFF) needs an already-built V8 and never
  builds one. [`cmake/TrechV8.cmake`](../../../cmake/TrechV8.cmake) accepts an installed prefix
  (`TRECH_V8_ROOT`; Homebrew's `brew --prefix v8` is tried automatically) or a from-source
  monolith (`TRECH_V8_BUILD_DIR/obj/libv8_monolith.a` with `thirds/v8/include`), and probes the
  ABI definitions (`TRECH_V8_DEFINITIONS=AUTO`). Validated source: Homebrew V8 15.9.128.11 on
  macOS arm64 (installed 2026-11-21; component build, pointer compression on, sandbox off, ICU
  data in `libexec/icudtl.dat`). The official `thirds/v8` submodule `06637ec79e4` (15.9.0
  candidate) is the from-source pin: [`scripts/build_v8.sh`](../../../scripts/build_v8.sh)
  fetches depot_tools into `build/depot_tools`, syncs with `thirds/.gclient` (both ignored) and
  builds `v8_monolith` without pointer compression, sandbox or ICU. That script is heavy and has
  not been run; never run it implicitly. `TRECH_ENABLE_V8_PROBE` reuses the same V8 target.
  Engine contract: [runtime handbook](../../engine/runtime/AGENTS.md#engine-backends--quickjs-and-v8-2026-11-21),
  [`docs/engine/v8.md`](../../../docs/engine/v8.md).
- **Atomic research V8 host:** `TRECH_ENABLE_ATOMIC_RESEARCH` defaults OFF and requires an
  already-installed Node.js >=18 with V8. It builds only the `trech-atomic` C++ process launcher,
  never upstream V8; numerical research lives in JS. This is separate from the optional native
  V8 probe and the QuickJS simulation host. Configure/runtime/source paths are recorded or
  documented; source-tree relocation and Windows execution remain unvalidated. See
  [`docs/research/atomic_stability.md`](../../../docs/research/atomic_stability.md).

#### [`CMakeLists.txt`](../../../CMakeLists.txt) · [`cmake/`](../../../cmake) · [`CMakePresets.json`](../../../CMakePresets.json)

Targets: `trech_core` → `trech_ml`/`trech_chem`/`trech_js` → `trech_sim` (Geant4-gated) → `trech`.
Helpers: [`cmake/TrechOptions.cmake`](../../../cmake/TrechOptions.cmake) (the `TRECH_ENABLE_*` options),
[`cmake/TrechWarnings.cmake`](../../../cmake/TrechWarnings.cmake), [`cmake/TrechFindOrFetch.cmake`](../../../cmake/TrechFindOrFetch.cmake)
(QuickJS/json vendor-or-fetch). Presets `dev` (Debug, `build/dev`) and `rel` (Release,
`build/rel`), both `TRECH_ENABLE_GEANT4=ON` + `TRECH_FETCH_DEPS=ON`.

## Build, run, test, debug, and release

Prerequisites: CMake ≥ 3.21, Ninja, a C++ compiler, Python 3. Geant4 is a required submodule for
simulation (`thirds/geant4`; build/install and set `Geant4_DIR` or `CMAKE_PREFIX_PATH`).
LibTorch and the Torch/NumPy Python environment are required by CMake. See the
[user build guide](../../../docs/build.md) for setup. Commands (from repo root):

```bash
# Geant4 from the submodule (once): configure thirds/geant4 into build/geant4-build with
#   -DCMAKE_INSTALL_PREFIX=build/geant4-install -DGEANT4_INSTALL_DATA=ON, build + install
cmake --preset dev -DCMAKE_PREFIX_PATH="$PWD/build/geant4-install"
cmake --build --preset dev
./build/dev/trech run examples/scenarios/hello_world/hello_world.js --output build/dev/out_hello
ctest --preset dev            # 36 CTest entries with Geant4, including Python gates
# the rel preset is ~3-5x faster for MD/PBF/osmotic runs and the README media driver
```

CMake options: `TRECH_ENABLE_GEANT4`, `TRECH_ENABLE_DNA_CHEM`, `TRECH_FETCH_DEPS`; required
cache values `TRECH_ML_BACKEND` (`torch`), `Torch_DIR` and `TRECH_ML_PYTHON`. Validation & smoke (need Geant4 for physics runs; the full suite is slow and
mutates `build/dev/out_*` + the committed validation report — has `SKIP_*` gates):

```bash
scripts/run_smoke.sh                 # build + ctest
scripts/run_validation.sh            # H2O validation run; updates docs/validation/validation_summary.md
scripts/run_validation_suite.sh      # full regression suite → docs/validation/validation_report.md
```

Python tools install with `pip install -e tools/<pkg>` (`trech-viz`, `trech-train-*`,
`python -m trech_validation`, `python -m trech_pubchem`); Studio: see [desktop build and test commands](../../studio/AGENTS.md#interface-build-and-test).
