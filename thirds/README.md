# Third-party dependencies

This directory is for large or optional dependencies that are vendored or cloned locally.

- QuickJS: place sources under `thirds/quickjs/quickjs` (quickjs.c, quickjs.h, etc.)
- Geant4: required submodule at `thirds/geant4` (init with `git submodule update --init --recursive`)
- nlohmann/json: optional vendor under `thirds/json` (with its CMakeLists.txt)
