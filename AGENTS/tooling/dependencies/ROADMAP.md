# Builds, dependencies and optional backends — roadmap

[Root principles](../../../AGENTS.md) · [Root roadmap](../../../ROADMAP.md) · [Parent](../ROADMAP.md) · [Handbook](AGENTS.md)

Maintain work in its owning branch. Dated results apply to the recorded checkout; they do not validate subsequent changes.

## Installed Node/V8 atomic research host

- [x] Opt-in `TRECH_ENABLE_ATOMIC_RESEARCH`, installed Node >=18/V8 discovery, shell-free
  C++ launcher, JS numerical/finite-basis tests and direct-vs-launcher CLI/provenance tests.
  No dependency download, bump or upstream V8/Geant4 build is part of this feature.
  Fresh macOS ARM64 Release build with Geant4/fetch disabled passes CTest 38/38; installed
  Node 24.21.0 reports V8 13.6.233.17-node.53. Native submodule V8 remains unbuilt.
- [ ] Installation/relocation and Windows execution remain unvalidated; the launcher currently
  retains configured source/runtime paths. Same-host JSON replay does not establish cross-host
  numerical identity. Full embedded-V8 hook parity/performance is still unimplemented and is
  not implied by using Node's V8. Physics gaps belong to the
  [runtime research roadmap](../../engine/runtime/ROADMAP.md#atomic-stability-research).

## Dependency checkout refresh — 2026-10-27

- Local gitignored LibTorch replaced with the official macOS ARM64 CPU **2.14.1** package
  (`https://download.pytorch.org/libtorch/cpu/libtorch-macos-arm64-2.14.1.zip`), replacing
  x86_64 1.2.0. Archive SHA-256:
  `6ab4e92bed813981cb26434db0ea12aaae7ce7c548d031a5b25032a286de1b58`.
  Old installation retained at `build/torch-update/libtorch-1.2.0-x86_64-backup`.
  Normal presets remain Torch-disabled; isolated verification uses `build/torch-check`.
- **Installation verified:** CMake discovery and a standalone C++20 tensor + scripted-module
  inference check pass (`LibTorch 2.14.1: tensor/TorchScript sum=12`).
- [x] **Torch integration:** enabled ML targets/consumers request C++20, while ordinary builds
  keep C++17. `TorchScriptStub` owns its lifecycle/moves where Module is complete. The conditional
  `test_torch_backends` gate creates real modules in C++ and exercises generic/stratifier/optics
  inference, strict stratification, module replacement, failed reloads and interpreter failures.
  Both GenericSurrogate positional APIs share finite-input/full-tensor validation and publish
  atomically; the previously unchecked vector path could return NaN/Inf. These are synthetic
  numerical tests, not physical-model validation or a promotion of Torch models.
- [ ] Torch deployment extensions: named IO/unit metadata for raw `.pt` registry models remains
  absent, so generic hook/operator use still needs portable named-IO JSON. Cross-platform/accelerator
  validation, production-model parity/performance and the newly checked-out Geant4 revision remain
  separate work. Normal presets keep Torch disabled; no dependency was bumped or rebuilt here.

  Integration verification: local macOS ARM64 CPU LibTorch 2.14.1 builds pass CTest 31/31 with
  Geant4 off and 34/34 with the existing installed Geant4. Ordinary Debug/Release builds pass
  33/33 each. Eight fresh-output Geant4 runs (four repeated cases) cover a real synthetic `.pt`
  event classifier in strict/predictive mode and JSON-model/blocked-recipe parity with the prior
  Torch-disabled outputs; only the recorded `event_feature_stats_torch_backed` flag differs.
  Scores/emits replay exactly and no emits are dropped. Backend fixtures also cover full-tensor
  finite checks, float input overflow, unsupported outputs and interpreter errors without partial
  publication. These tests do not validate the newer Geant4 checkout or promote a physical model.

  Studio source-guard verification: pytest 106 passed, one Metal-adapter check skipped in the
  sandbox. Real-engine/Qt tests cover dormant/visible include drafts, browser and Chemistry
  cancellation, external conflicts, failed target opens, Save/Discard and job-preserving rejected
  close events. Dirty labels and the actual default-Cancel dialog were visually inspected.
- All submodules recursively match their fetched upstream default-branch tips: Geant4
  `f3d5293d38` (`v11.5.0.beta`, previously v11.4.2), nlohmann/json `8617d9c94`
  (develop, previously v3.12.0), QuickJS `19d6bd8` (previously `04be246`), and Evolvo
  `7ca9c66` (unchanged). The parent branch was already current.
- Existing dev-build CTest passes **21/21** without rebuilding; this does not validate the
  updated dependency sources.
- [ ] Rebuild/install Geant4 and rebuild TRECH against these revisions, then run CTest and
  physics regression comparisons. This checkout update alone establishes no compatibility,
  reproducibility or physics-validation claim; existing build outputs/reports predate it.
- Geant4 11.5.0.beta removed `G4EmDNAPhysics_option1/3/5/7`. `GeantRunner.cpp` now includes and
  instantiates them only under `G4VERSION_NUMBER < 1150`. Against 11.5+ a scenario asking for one
  of them fails before any kernel is created; it is never remapped. Verified only by
  `-fsyntax-only` with `TRECH_ENABLE_DNA_CHEM=1` against the installed 11.4.2 headers, plus an
  emulated 11.5 (`-DG4VERSION_NUMBER=1150` with the four headers shadowed by `#error` stubs,
  which breaks the previous code), not by a real 11.5 build.
- [ ] After the 11.5 rebuild: compile and link with `TRECH_ENABLE_DNA_CHEM=ON` for real, and
  install G4EMLOW 9.0 (installed: 8.8). Revalidate `DNA_Opt4` (electrons now to 10 MeV), EM-option-2
  lists (`ApplyCuts` on), DNA chemistry yields (multiple ionisation) and
  `primaries_photoelectric_first_fraction` (`G4GammaGeneralProcess` refactor). Full list:
  [`docs/GEANT4_features_and_limits.md` §6](../../../docs/GEANT4_features_and_limits.md#6-migration-items-for-the-pinned-checkout).

- Third-party dependency refresh landed (2026-06-30): **nlohmann/json v3.12.0** (was 3.11.2; header-only, no source changes), **QuickJS 2026-06-04 release** (`04be246`; internal `quickjs.h` layout only — public C API unchanged, bindings recompiled as-is), **Geant4 v11.4.2** (was 11.4.0; patch series, no public API changes → no call-site migration; incremental rebuild into `build/geant4-install`). trech rebuilt + relinked; `ctest --preset dev` 9/9; `cnt_logic_gates` reproduces byte-identical Geant4 transport against 11.4.2. LibTorch (`thirds/torch`) deferred at 1.2.0 (x86_64, off-by-default, ridge backend covers it; 1.2→2.x is binary-swap-only since our torch API usage is stable).
