option(TRECH_ENABLE_GEANT4 "Build Geant4 simulation layer" ON)
# Deep-learning backend for model training and inference. It is required: a
# build without learning would validate the engine against simplistic stand-ins.
# LibTorch ("torch") is the only backend today; this switch is the seam for an
# alternative library later.
set(TRECH_ML_BACKEND "torch" CACHE STRING "Required deep-learning backend (torch = LibTorch)")
set_property(CACHE TRECH_ML_BACKEND PROPERTY STRINGS torch)
# TRECH_ENABLE_TORCH used to make LibTorch optional. Drop it from old caches.
if (DEFINED TRECH_ENABLE_TORCH)
  if (NOT TRECH_ENABLE_TORCH)
    message(WARNING "TRECH_ENABLE_TORCH=OFF is no longer supported and is ignored: LibTorch is required.")
  endif()
  unset(TRECH_ENABLE_TORCH CACHE)
  unset(TRECH_ENABLE_TORCH)
endif()
option(TRECH_ENABLE_DNA_CHEM "Enable Geant4-DNA chemistry wiring (when available)" OFF)
option(TRECH_FETCH_DEPS "Allow CMake to fetch third-party dependencies" OFF)
option(TRECH_ENABLE_V8 "Build the V8 JavaScript backend (needs an already-built V8; see docs/engine/v8.md)" OFF)
# Engine a JsRuntime uses when neither --js-engine nor TRECH_JS_ENGINE selects one.
set(TRECH_DEFAULT_JS_ENGINE "quickjs" CACHE STRING "Default JavaScript engine (quickjs or v8; v8 needs TRECH_ENABLE_V8)")
set_property(CACHE TRECH_DEFAULT_JS_ENGINE PROPERTY STRINGS quickjs v8)
option(TRECH_ENABLE_V8_PROBE "Build the optional standalone V8 compile/code-cache probe" OFF)
# Optional Lean proof check of formal/ (docs/engine/formal_laws.md). OFF: Lean is never needed.
# ON needs an installed `lake` matching formal/lean-toolchain, and building the package compiles
# the imported Mathlib modules unless their cache was fetched (heavy).
option(TRECH_ENABLE_LEAN_CHECK "Register a CTest entry that builds the optional Lean law package (needs lake)" OFF)
option(TRECH_ENABLE_ATOMIC_RESEARCH "Build the standalone atomic research JS launcher using an installed Node/V8 runtime" OFF)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
