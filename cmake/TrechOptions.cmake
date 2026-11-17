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
option(TRECH_ENABLE_V8_PROBE "Build the optional standalone V8 compile/code-cache probe (not the hook runtime)" OFF)
option(TRECH_ENABLE_ATOMIC_RESEARCH "Build the standalone atomic research JS launcher using an installed Node/V8 runtime" OFF)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)
