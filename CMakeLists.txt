cmake_minimum_required(VERSION 3.21)
project(TRECH LANGUAGES C CXX)

include(cmake/TrechOptions.cmake)
include(cmake/TrechWarnings.cmake)
include(cmake/TrechFindOrFetch.cmake)

trech_require_nlohmann_json()
trech_require_quickjs()

add_library(trech_core
  src/core/Config.cpp
  src/core/Provenance.cpp
  src/core/RunOptions.cpp
)
target_include_directories(trech_core PUBLIC ${PROJECT_SOURCE_DIR}/include)
target_link_libraries(trech_core PUBLIC nlohmann_json::nlohmann_json)
trech_apply_warnings(trech_core)

add_library(trech_js
  src/js/JsRuntime.cpp
  src/js/TrechJsApi.cpp
)
target_include_directories(trech_js PUBLIC ${PROJECT_SOURCE_DIR}/include)
target_link_libraries(trech_js PUBLIC trech_core quickjs)
if (TRECH_QUICKJS_INCLUDE_DIR)
  if (CMAKE_CXX_COMPILER_ID MATCHES "Clang|GNU")
    target_compile_options(trech_js PRIVATE "-iquote${TRECH_QUICKJS_INCLUDE_DIR}")
  else()
    target_include_directories(trech_js PRIVATE ${TRECH_QUICKJS_INCLUDE_DIR})
  endif()
endif()
trech_apply_warnings(trech_js)

add_library(trech_ml
  src/ml/FeaturePipeline.cpp
  src/ml/Stratifier.cpp
  src/ml/TorchScriptStub.cpp
)
target_include_directories(trech_ml PUBLIC ${PROJECT_SOURCE_DIR}/include)
target_link_libraries(trech_ml PUBLIC trech_core)
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
      src/sim/SteppingAction.cpp
      src/sim/MultiscaleBridge.cpp
    )
    target_include_directories(trech_sim PUBLIC ${PROJECT_SOURCE_DIR}/include)
    target_link_libraries(trech_sim PUBLIC trech_core trech_ml trech_chem ${Geant4_LIBRARIES})
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
target_link_libraries(trech PRIVATE trech_core trech_js)
if (TRECH_ENABLE_GEANT4)
  target_link_libraries(trech PRIVATE trech_sim)
  target_compile_definitions(trech PRIVATE TRECH_HAS_GEANT4=1)
endif()
trech_apply_warnings(trech)

enable_testing()
add_subdirectory(tests)
