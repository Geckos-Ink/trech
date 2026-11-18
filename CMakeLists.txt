cmake_minimum_required(VERSION 3.21)
project(TRECH LANGUAGES C CXX)

include(cmake/TrechOptions.cmake)
include(cmake/TrechWarnings.cmake)
include(cmake/TrechFindOrFetch.cmake)

trech_require_nlohmann_json()
trech_require_quickjs()

add_library(trech_core
  src/core/Config.cpp
  src/core/ScalarField.cpp
  src/core/LabSession.cpp
  src/core/SimulationBudget.cpp
  src/core/Provenance.cpp
  src/core/Sha256.cpp
  src/core/RunOptions.cpp
)
target_include_directories(trech_core PUBLIC ${PROJECT_SOURCE_DIR}/include)
target_link_libraries(trech_core PUBLIC nlohmann_json::nlohmann_json)
trech_apply_warnings(trech_core)

# Deterministic host math: one fdlibm-derived implementation of every JavaScript Math
# transcendental, so hook-layer numerics do not depend on the platform libm. Contraction is
# pinned OFF: a fused multiply-add rounds differently, which is exactly the cross-host drift
# this library exists to remove. (MSVC's default /fp:precise already forbids contraction.)
add_library(trech_dmath STATIC src/js/DeterministicMath.c)
target_include_directories(trech_dmath PUBLIC ${PROJECT_SOURCE_DIR}/include)
trech_apply_warnings(trech_dmath)
if (CMAKE_C_COMPILER_ID MATCHES "Clang|GNU|IntelLLVM")
  target_compile_options(trech_dmath PRIVATE -ffp-contract=off -fno-fast-math)
endif()
if (UNIX AND NOT APPLE)
  target_link_libraries(trech_dmath PUBLIC m)
endif()

# Route the vendored QuickJS engine's Math.* and `**` through trech_dmath without patching the
# submodule: force-include a header that renames the libm transcendentals in quickjs.c only.
get_target_property(_trech_qjs_dir quickjs SOURCE_DIR)
get_target_property(_trech_qjs_sources quickjs SOURCES)
set(_trech_qjs_main "")
foreach(_trech_qjs_src IN LISTS _trech_qjs_sources)
  get_filename_component(_trech_qjs_name "${_trech_qjs_src}" NAME)
  if (_trech_qjs_name STREQUAL "quickjs.c")
    if (IS_ABSOLUTE "${_trech_qjs_src}")
      set(_trech_qjs_main "${_trech_qjs_src}")
    else()
      set(_trech_qjs_main "${_trech_qjs_dir}/${_trech_qjs_src}")
    endif()
  endif()
endforeach()
if (NOT _trech_qjs_main)
  message(FATAL_ERROR "quickjs.c not found among the quickjs target sources; "
                      "deterministic host math cannot be routed into the engine.")
endif()
set(_trech_qjs_redirect "${PROJECT_SOURCE_DIR}/src/js/QuickJsMathRedirect.h")
if (MSVC)
  set(_trech_qjs_force_include "/FI${_trech_qjs_redirect}")
else()
  set(_trech_qjs_force_include -include "${_trech_qjs_redirect}")
endif()
set_source_files_properties("${_trech_qjs_main}" DIRECTORY "${_trech_qjs_dir}"
  PROPERTIES COMPILE_OPTIONS "${_trech_qjs_force_include}"
             OBJECT_DEPENDS "${_trech_qjs_redirect}")
target_link_libraries(quickjs PRIVATE trech_dmath)
if (CMAKE_C_COMPILER_ID MATCHES "Clang|GNU|IntelLLVM")
  target_compile_options(quickjs PRIVATE -ffp-contract=off)
endif()

add_library(trech_js
  src/js/JsRuntime.cpp
)
target_include_directories(trech_js PUBLIC ${PROJECT_SOURCE_DIR}/include)
# trech_ml provides GenericSurrogate for the hook layer's ctx.predict.
target_link_libraries(trech_js PUBLIC quickjs nlohmann_json::nlohmann_json trech_ml trech_dmath)
if (CMAKE_CXX_COMPILER_ID MATCHES "Clang|GNU|IntelLLVM")
  # Host-side hook numerics (ctx.rng.normal) must not fuse multiply-add either.
  set_source_files_properties(src/js/JsRuntime.cpp PROPERTIES COMPILE_OPTIONS "-ffp-contract=off")
endif()
if (TRECH_QUICKJS_INCLUDE_DIR)
  if (CMAKE_CXX_COMPILER_ID MATCHES "Clang|GNU")
    target_compile_options(trech_js PRIVATE "-iquote${TRECH_QUICKJS_INCLUDE_DIR}")
  else()
    target_include_directories(trech_js PRIVATE ${TRECH_QUICKJS_INCLUDE_DIR})
  endif()
endif()
trech_apply_warnings(trech_js)
if (CMAKE_CXX_COMPILER_ID MATCHES "Clang|GNU")
  # Keep QuickJS headers quiet in C++ builds without muting other targets.
  target_compile_options(trech_js PRIVATE -Wno-unused-parameter -Wno-c99-extensions)
endif()

add_library(trech_ml
  src/ml/FeaturePipeline.cpp
  src/ml/Stratifier.cpp
  src/ml/TorchScriptStub.cpp
  src/ml/OnlineEventStats.cpp
  src/ml/OpticsSurrogate.cpp
  src/ml/GenericSurrogate.cpp
  src/ml/ScaleCascade.cpp
  src/ml/StateEvolution.cpp
  src/ml/DiscreteTransition.cpp
  src/ml/PairInteraction.cpp
  src/ml/GroupHierarchy.cpp
  src/ml/DomainDiscovery.cpp
  src/ml/DomainRouting.cpp
  src/ml/DomainLearner.cpp
  src/ml/ComputeBudget.cpp
  src/ml/ArchitectureGenerator.cpp
)
target_include_directories(trech_ml PUBLIC ${PROJECT_SOURCE_DIR}/include)
target_link_libraries(trech_ml PUBLIC trech_core trech_dmath)
# The ML Python trains models (tools/torch, the Evolvo architecture worker) and
# runs the torch-dependent Python tests. Like LibTorch it is required: configure
# fails unless it imports torch and numpy. Architecture generation launches the
# worker (trech_torch.arch_worker) as a subprocess; the interpreter is resolved
# at run time (job "python", $TRECH_PYTHON) and this is the default. The
# repository root locates tools/torch and thirds/evolvo ($TRECH_ROOT overrides).
if (NOT DEFINED TRECH_ML_PYTHON)
  if (DEFINED TRECH_ARCH_PYTHON)  # the variable's former name
    set(_trech_ml_python "${TRECH_ARCH_PYTHON}")
  elseif (EXISTS "${PROJECT_SOURCE_DIR}/build/render-venv/bin/python")
    set(_trech_ml_python "${PROJECT_SOURCE_DIR}/build/render-venv/bin/python")
  else()
    find_package(Python3 COMPONENTS Interpreter QUIET)
    set(_trech_ml_python "${Python3_EXECUTABLE}")
  endif()
  set(TRECH_ML_PYTHON "${_trech_ml_python}" CACHE FILEPATH
      "Required Python with torch + numpy (model training, Evolvo worker, torch tests)")
endif()
unset(TRECH_ARCH_PYTHON CACHE)
execute_process(
  COMMAND "${TRECH_ML_PYTHON}" -c "import torch, numpy; print(torch.__version__)"
  RESULT_VARIABLE _trech_ml_python_rc OUTPUT_VARIABLE _trech_ml_python_torch
  ERROR_QUIET OUTPUT_STRIP_TRAILING_WHITESPACE)
if (NOT _trech_ml_python_rc EQUAL 0)
  message(FATAL_ERROR
    "TRECH_ML_PYTHON='${TRECH_ML_PYTHON}' cannot import torch and numpy. Model training "
    "is required: create the venv (python3 -m venv build/render-venv && "
    "build/render-venv/bin/pip install -e tools/torch) or pass -DTRECH_ML_PYTHON=<python>.")
endif()
message(STATUS "TRECH ML Python: ${TRECH_ML_PYTHON} (torch ${_trech_ml_python_torch})")
set_property(SOURCE src/ml/ArchitectureGenerator.cpp APPEND PROPERTY COMPILE_DEFINITIONS
  TRECH_DEFAULT_PYTHON="${TRECH_ML_PYTHON}"
  TRECH_REPOSITORY_ROOT="${PROJECT_SOURCE_DIR}")
# The surrogate evaluation loop accumulates every neuron in declared input
# order so a vectorised evaluation stays bit-identical to a scalar one.  That
# equality only holds when the compiler is not free to fuse multiply-add in one
# form and not the other, so contraction is pinned OFF for this one translation
# unit -- it makes learned inference reproducible across compilers/flags rather
# than dependent on an optimiser's FMA choice.  (MSVC's default /fp:precise
# already forbids the contraction.)
if (CMAKE_CXX_COMPILER_ID MATCHES "Clang|GNU|IntelLLVM")
  # GroupHierarchy accumulates member centroids that feed the rel_* inputs; the
  # Python trainer (trech_torch/hierarchy.py) replays the same sums, so pin it
  # to the same no-contraction rule.
  # The native classic trainer (ArchitectureGenerator) must export the same
  # weights for the same job on every compiler, so it is pinned too.
  set_source_files_properties(src/ml/GenericSurrogate.cpp src/ml/GroupHierarchy.cpp
    src/ml/ArchitectureGenerator.cpp
    PROPERTIES COMPILE_OPTIONS "-ffp-contract=off")
endif()
# The deep-learning backend is required (see TRECH_ML_BACKEND). LibTorch is a
# local, gitignored install in thirds/torch (./install_torch.sh); CMake never
# downloads it.
if (NOT TRECH_ML_BACKEND STREQUAL "torch")
  message(FATAL_ERROR "TRECH_ML_BACKEND='${TRECH_ML_BACKEND}' is not supported; the only backend is 'torch' (LibTorch).")
endif()
set(_trech_torch_default "${PROJECT_SOURCE_DIR}/thirds/torch/share/cmake/Torch")
if (Torch_DIR AND NOT IS_ABSOLUTE "${Torch_DIR}")
  get_filename_component(_trech_torch_abs "${Torch_DIR}" ABSOLUTE BASE_DIR "${PROJECT_SOURCE_DIR}")
  set(Torch_DIR "${_trech_torch_abs}" CACHE PATH "LibTorch CMake package directory" FORCE)
endif()
if ((NOT Torch_DIR OR NOT EXISTS "${Torch_DIR}") AND EXISTS "${_trech_torch_default}")
  set(Torch_DIR "${_trech_torch_default}" CACHE PATH "LibTorch CMake package directory" FORCE)
endif()
find_package(Torch QUIET)
if (NOT Torch_FOUND)
  message(FATAL_ERROR
    "LibTorch is required (TRECH_ML_BACKEND=torch) but was not found. Install it into "
    "thirds/torch with ./install_torch.sh, or pass -DTorch_DIR=<libtorch>/share/cmake/Torch.")
endif()
# Modern LibTorch requires C++20; it propagates to trech_ml's consumers.
target_compile_features(trech_ml PUBLIC cxx_std_20)
if (TARGET Torch::Torch)
  target_link_libraries(trech_ml PUBLIC Torch::Torch)
else()
  target_link_libraries(trech_ml PUBLIC ${TORCH_LIBRARIES})
  if (TORCH_INCLUDE_DIRS)
    target_include_directories(trech_ml SYSTEM PUBLIC ${TORCH_INCLUDE_DIRS})
  endif()
endif()
if (TORCH_CXX_FLAGS)
  separate_arguments(TORCH_CXX_FLAGS_LIST NATIVE_COMMAND "${TORCH_CXX_FLAGS}")
  target_compile_options(trech_ml PRIVATE ${TORCH_CXX_FLAGS_LIST})
endif()
trech_apply_warnings(trech_ml)

add_library(trech_chem
  src/chem/DnaChemistry.cpp
)
target_include_directories(trech_chem PUBLIC ${PROJECT_SOURCE_DIR}/include)
target_link_libraries(trech_chem PUBLIC trech_core)
trech_apply_warnings(trech_chem)

if (TRECH_ENABLE_GEANT4)
  find_package(Geant4 QUIET COMPONENTS ui_all vis_all)
  if (Geant4_FOUND)
    include(${Geant4_USE_FILE})

    add_library(trech_sim
      src/sim/GeantRunner.cpp
      src/sim/DetectorConstruction.cpp
      src/sim/ActionInitialization.cpp
      src/sim/PrimaryGeneratorAction.cpp
      src/sim/RunAction.cpp
      src/sim/EventAction.cpp
      src/sim/EventRecords.cpp
      src/sim/SteppingAction.cpp
      src/sim/TrackingAction.cpp
      src/sim/NuclearCycleAnalyzer.cpp
      src/sim/MultiscaleBridge.cpp
      src/sim/MolecularOptics.cpp
      src/sim/AnalyticCrossCheck.cpp
      src/sim/MaterialProbe.cpp
      src/sim/NuclearSpatialProbe.cpp
      src/sim/VizRecorder.cpp
    )
    target_include_directories(trech_sim PUBLIC ${PROJECT_SOURCE_DIR}/include)
    target_link_libraries(trech_sim PUBLIC trech_core trech_ml trech_chem trech_js ${Geant4_LIBRARIES})
    if (TRECH_ENABLE_DNA_CHEM)
      target_compile_definitions(trech_sim PRIVATE TRECH_ENABLE_DNA_CHEM=1)
    endif()
    trech_apply_warnings(trech_sim)
  else()
    message(WARNING "Geant4 not found; disabling TRECH_ENABLE_GEANT4.")
    set(TRECH_ENABLE_GEANT4 OFF)
  endif()
endif()

add_executable(trech apps/trech-cli/main.cpp)
if (TRECH_ENABLE_GEANT4)
  target_link_libraries(trech PRIVATE trech_sim)
  target_compile_definitions(trech PRIVATE TRECH_HAS_GEANT4=1)
else()
  target_link_libraries(trech PRIVATE trech_js)
endif()
trech_apply_warnings(trech)

# V8 uses its own GN/Ninja build. Never trigger that heavy build or change the
# deterministic QuickJS hook backend as a side effect of configuring TRECH.
if (TRECH_ENABLE_V8_PROBE)
  set(TRECH_V8_BUILD_DIR "${PROJECT_SOURCE_DIR}/thirds/v8/out.gn/trech" CACHE PATH "Prebuilt V8 monolith directory")
  set(TRECH_V8_DEFINITIONS "" CACHE STRING "ABI definitions matching the V8 build (semicolon-separated)")
  find_library(TRECH_V8_MONOLITH NAMES v8_monolith PATHS "${TRECH_V8_BUILD_DIR}/obj" NO_DEFAULT_PATH REQUIRED)
  find_package(Threads REQUIRED)
  add_executable(trech-v8-probe src/js/V8Probe.cpp)
  target_compile_features(trech-v8-probe PRIVATE cxx_std_20)
  target_include_directories(trech-v8-probe SYSTEM PRIVATE "${PROJECT_SOURCE_DIR}/thirds/v8/include")
  target_compile_definitions(trech-v8-probe PRIVATE ${TRECH_V8_DEFINITIONS})
  target_link_libraries(trech-v8-probe PRIVATE nlohmann_json::nlohmann_json "${TRECH_V8_MONOLITH}" Threads::Threads ${CMAKE_DL_LIBS})
  trech_apply_warnings(trech-v8-probe)
endif()

# Atomic research runs its numerical core in an already-installed Node/V8 host.
# It neither builds the V8 submodule nor changes the simulation's QuickJS host.
if (TRECH_ENABLE_ATOMIC_RESEARCH)
  find_program(TRECH_ATOMIC_NODE_EXECUTABLE NAMES node nodejs REQUIRED)
  execute_process(
    COMMAND "${TRECH_ATOMIC_NODE_EXECUTABLE}" -e
      "if (!process.versions.v8 || Number(process.versions.node.split('.')[0]) < 18) process.exit(1); process.stdout.write('Node ' + process.versions.node + ', V8 ' + process.versions.v8)"
    RESULT_VARIABLE TRECH_ATOMIC_NODE_STATUS
    OUTPUT_VARIABLE TRECH_ATOMIC_RUNTIME_VERSION
    ERROR_VARIABLE TRECH_ATOMIC_NODE_ERROR
    OUTPUT_STRIP_TRAILING_WHITESPACE
    TIMEOUT 10
  )
  if (NOT TRECH_ATOMIC_NODE_STATUS EQUAL 0)
    message(FATAL_ERROR "Atomic research requires Node.js 18 or newer with V8: ${TRECH_ATOMIC_NODE_ERROR}")
  endif()
  message(STATUS "Atomic research host: ${TRECH_ATOMIC_RUNTIME_VERSION}")
  add_executable(trech-atomic src/js/AtomicResearchMain.cpp)
  target_compile_definitions(trech-atomic PRIVATE
    TRECH_ATOMIC_NODE="${TRECH_ATOMIC_NODE_EXECUTABLE}"
    TRECH_ATOMIC_RUNNER="${PROJECT_SOURCE_DIR}/tools/atomic/run.cjs"
  )
  trech_apply_warnings(trech-atomic)
endif()

enable_testing()
if (TRECH_ENABLE_V8_PROBE)
  add_test(NAME trech_v8_code_cache COMMAND trech-v8-probe)
endif()
if (TRECH_ENABLE_ATOMIC_RESEARCH)
  add_test(NAME trech_atomic_stability
    COMMAND "${TRECH_ATOMIC_NODE_EXECUTABLE}" "${PROJECT_SOURCE_DIR}/tests/test_atomic_stability.cjs")
  add_test(NAME trech_atomic_composition
    COMMAND "${TRECH_ATOMIC_NODE_EXECUTABLE}" "${PROJECT_SOURCE_DIR}/tests/test_atomic_composition.cjs")
  add_test(NAME trech_atomic_host_help COMMAND trech-atomic --help)
  add_test(NAME trech_atomic_host_run COMMAND trech-atomic)
  find_package(Python3 COMPONENTS Interpreter QUIET)
  if (Python3_Interpreter_FOUND)
    add_test(NAME trech_atomic_host_contract
      COMMAND "${Python3_EXECUTABLE}" "${PROJECT_SOURCE_DIR}/tests/test_atomic_host.py"
        "$<TARGET_FILE:trech-atomic>" "${TRECH_ATOMIC_NODE_EXECUTABLE}"
        "${PROJECT_SOURCE_DIR}/tools/atomic/run.cjs")
    set_tests_properties(trech_atomic_host_contract PROPERTIES TIMEOUT 60)
  endif()
endif()
add_subdirectory(tests)
