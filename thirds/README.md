# Third-party dependencies

This directory is for large or optional dependencies that are vendored or cloned locally.

- QuickJS: place sources under `thirds/quickjs/quickjs` (quickjs.c, quickjs.h, etc.)
- Geant4: required submodule at `thirds/geant4` (init with `git submodule update --init --recursive`)
- nlohmann/json: optional vendor under `thirds/json` (with its CMakeLists.txt)
- Lean 4 and Mathlib: optional shallow submodules `thirds/lean4` and `thirds/mathlib4` (reference sources for the formal-laws route; the build never uses them). Pull before use with `scripts/pull_lean.sh`; see `docs/engine/formal_laws.md`.
