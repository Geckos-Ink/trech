# Builds, dependencies and optional backends — context and contracts

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../AGENTS.md) · [Roadmap](ROADMAP.md)

Read the root principles and the parent handbook first; then open only the subcategory relevant to the task. Source paths and shell commands in code spans/blocks are repository-relative unless stated otherwise; Markdown links resolve from this file.

- **Geant4:** check for a local clone at [`thirds/geant4`](../../../thirds/geant4) before asking for it;
  never write absolute Geant4 paths in-repo (use `thirds/geant4-build`/`-install` or
  `build/geant4-build`/`-install`). Keep vendored deps current (see the standing dep-refresh note
  in the [dependency roadmap](ROADMAP.md); rebuilds are heavy — confirm before a bump).
- **Current dependency checkout:** Geant4 `f3d5293d38` (`v11.5.0.beta`), json
  `8617d9c94` (upstream develop), QuickJS `19d6bd8`, Evolvo `ed3f7aa`.
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
  return false on interpreter failures. A `<model>.pt.io.json` sidecar bound by
  `model_sha256` gives a module named IO, units and carried accuracy
  ([inference handbook](../../engine/inference/AGENTS.md)). Platform/model-deployment limits remain in the [dependency roadmap](ROADMAP.md).
- **QuickJS vs Node/V8 differential:** `scripts/js_engine_differential.py` (+ the Node host
  `scripts/js_engine_differential_node.js`) compares a scenario's top-level JS results bit for
  bit; CTest `trech_js_engine_differential` (needs `trech`, Node and Python, builds nothing).
- **Optional V8 foundation:** official `thirds/v8` submodule `06637ec79e4` (15.9.0 candidate),
  not built and not the hook backend. `TRECH_ENABLE_V8_PROBE` defaults OFF; its standalone C++
  compile/code-cache probe is syntax-checked against pinned headers, not linked/run. Normal
  builds retain QuickJS; full host parity and performance are unvalidated. See
  [`docs/v8.md`](../../../docs/v8.md); never trigger a heavy upstream build implicitly.
- **Atomic research V8 host:** `TRECH_ENABLE_ATOMIC_RESEARCH` defaults OFF and requires an
  already-installed Node.js >=18 with V8. It builds only the `trech-atomic` C++ process launcher,
  never upstream V8; numerical research lives in JS. This is separate from the optional native
  V8 probe and the QuickJS simulation host. Configure/runtime/source paths are recorded or
  documented; source-tree relocation and Windows execution remain unvalidated. See
  [`docs/atomic_stability.md`](../../../docs/atomic_stability.md).

#### [`CMakeLists.txt`](../../../CMakeLists.txt) · [`cmake/`](../../../cmake) · [`CMakePresets.json`](../../../CMakePresets.json)

Targets: `trech_core` → `trech_ml`/`trech_chem`/`trech_js` → `trech_sim` (Geant4-gated) → `trech`.
Helpers: [`cmake/TrechOptions.cmake`](../../../cmake/TrechOptions.cmake) (the `TRECH_ENABLE_*` options),
[`cmake/TrechWarnings.cmake`](../../../cmake/TrechWarnings.cmake), [`cmake/TrechFindOrFetch.cmake`](../../../cmake/TrechFindOrFetch.cmake)
(QuickJS/json vendor-or-fetch). Presets `dev` (Debug, `build/dev`) and `rel` (Release,
`build/rel`), both `TRECH_ENABLE_GEANT4=ON` + `TRECH_FETCH_DEPS=ON`.

## Build, run, test, debug, and release

Prerequisites: CMake ≥ 3.21, Ninja, a C++ compiler, Python 3. Geant4 is a required submodule for
simulation (`thirds/geant4`; build/install and set `Geant4_DIR` or `CMAKE_PREFIX_PATH`); LibTorch
is optional. Commands (from repo root):

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
scripts/run_validation.sh            # H2O validation run; updates docs/validation_summary.md
scripts/run_validation_suite.sh      # full regression suite → docs/validation_report.md
```

Python tools install with `pip install -e tools/<pkg>` (`trech-viz`, `trech-train-*`,
`python -m trech_validation`, `python -m trech_pubchem`); Studio: see [desktop build and test commands](../../studio/AGENTS.md#interface-build-and-test).
