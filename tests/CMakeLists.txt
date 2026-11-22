add_executable(test_config_roundtrip
  test_config_roundtrip.cpp
)
target_link_libraries(test_config_roundtrip PRIVATE trech_core)

add_test(NAME trech_config_roundtrip COMMAND test_config_roundtrip)

add_executable(test_cli_parse
  test_cli_parse.cpp
)
target_link_libraries(test_cli_parse PRIVATE trech_core)
add_test(NAME trech_cli_parse COMMAND test_cli_parse)

add_executable(test_lab_session
  test_lab_session.cpp
)
target_link_libraries(test_lab_session PRIVATE trech_core)
add_test(NAME trech_lab_session COMMAND test_lab_session)

add_executable(test_provenance_writer
  test_provenance_writer.cpp
)
target_link_libraries(test_provenance_writer PRIVATE trech_core)
add_test(NAME trech_provenance_writer COMMAND test_provenance_writer)

add_executable(test_js_runtime
  test_js_runtime.cpp
)
target_link_libraries(test_js_runtime PRIVATE trech_js)
target_compile_definitions(test_js_runtime PRIVATE TRECH_SOURCE_DIR="${PROJECT_SOURCE_DIR}")
add_test(NAME trech_js_runtime COMMAND test_js_runtime)

# Observation-only engine trace: attribution, scenario reports, summary, no physics change.
add_executable(test_engine_trace test_engine_trace.cpp)
target_link_libraries(test_engine_trace PRIVATE trech_js)
add_test(NAME trech_engine_trace COMMAND test_engine_trace)

# Scenario-backed live lab: transactional script re-evaluation (Geant4-free).
add_executable(test_lab_script_host test_lab_script_host.cpp)
target_link_libraries(test_lab_script_host PRIVATE trech_js)
add_test(NAME trech_lab_script_host COMMAND test_lab_script_host)

# Deterministic host math: golden cross-host digests, IEEE special cases and QuickJS routing.
# Contraction off so the test's own input generation is the same on every host.
add_executable(test_deterministic_math test_deterministic_math.cpp)
target_link_libraries(test_deterministic_math PRIVATE trech_js)
if (CMAKE_CXX_COMPILER_ID MATCHES "Clang|GNU|IntelLLVM")
  target_compile_options(test_deterministic_math PRIVATE -ffp-contract=off)
endif()
add_test(NAME trech_deterministic_math COMMAND test_deterministic_math)

add_executable(test_scenario_bundle test_scenario_bundle.cpp)
target_link_libraries(test_scenario_bundle PRIVATE trech_js)
add_test(NAME trech_scenario_bundle COMMAND test_scenario_bundle)

add_executable(test_scenario_helpers test_scenario_helpers.cpp)
target_link_libraries(test_scenario_helpers PRIVATE trech_js)
target_compile_definitions(test_scenario_helpers PRIVATE TRECH_SOURCE_DIR="${PROJECT_SOURCE_DIR}")
add_test(NAME trech_scenario_helpers COMMAND test_scenario_helpers)

add_executable(test_geometry_generators test_geometry_generators.cpp)
target_link_libraries(test_geometry_generators PRIVATE trech_js)
target_compile_definitions(test_geometry_generators PRIVATE TRECH_SOURCE_DIR="${PROJECT_SOURCE_DIR}")
add_test(NAME trech_geometry_generators COMMAND test_geometry_generators)

add_executable(test_process_references test_process_references.cpp)
target_link_libraries(test_process_references PRIVATE trech_js)
target_compile_definitions(test_process_references PRIVATE TRECH_SOURCE_DIR="${PROJECT_SOURCE_DIR}")
add_test(NAME trech_process_references COMMAND test_process_references)

add_executable(test_euler3d_accuracy test_euler3d_accuracy.cpp)
target_link_libraries(test_euler3d_accuracy PRIVATE trech_js)
target_compile_definitions(test_euler3d_accuracy PRIVATE TRECH_SOURCE_DIR="${PROJECT_SOURCE_DIR}")
add_test(NAME trech_euler3d_accuracy COMMAND test_euler3d_accuracy)

add_executable(test_lattice_continuum test_lattice_continuum.cpp)
target_link_libraries(test_lattice_continuum PRIVATE trech_core)
add_test(NAME trech_lattice_continuum COMMAND test_lattice_continuum)

add_executable(test_field_evolution test_field_evolution.cpp)
target_link_libraries(test_field_evolution PRIVATE trech_ml)
add_test(NAME trech_field_evolution COMMAND test_field_evolution)

add_executable(test_formal_laws test_formal_laws.cpp)
target_link_libraries(test_formal_laws PRIVATE trech_js)
target_compile_definitions(test_formal_laws PRIVATE TRECH_SOURCE_DIR="${PROJECT_SOURCE_DIR}")
if (CMAKE_CXX_COMPILER_ID MATCHES "Clang|GNU|IntelLLVM")
  # C++ and JavaScript classic laws are compared bit for bit: no fused multiply-add here.
  target_compile_options(test_formal_laws PRIVATE -ffp-contract=off)
endif()
add_test(NAME trech_formal_laws COMMAND test_formal_laws)
if (TRECH_ENABLE_LEAN_CHECK)
  # lake build of formal/, then an axiom audit of every theorem listed in formal/laws.json.
  find_program(TRECH_LAKE_EXECUTABLE NAMES lake REQUIRED)
  find_package(Python3 COMPONENTS Interpreter REQUIRED)
  add_test(NAME trech_formal_lean_build
           COMMAND "${Python3_EXECUTABLE}" "${PROJECT_SOURCE_DIR}/scripts/check_lean_laws.py"
                   --lake "${TRECH_LAKE_EXECUTABLE}")
else()
  message(STATUS "Lean law proofs not checked (TRECH_ENABLE_LEAN_CHECK=OFF); classic checks still run")
endif()

add_executable(test_klein_nishina test_klein_nishina.cpp)
target_include_directories(test_klein_nishina PRIVATE ${PROJECT_SOURCE_DIR}/include)
add_test(NAME trech_klein_nishina COMMAND test_klein_nishina)

add_executable(test_event_moments test_event_moments.cpp)
target_include_directories(test_event_moments PRIVATE ${PROJECT_SOURCE_DIR}/include)
add_test(NAME trech_event_moments COMMAND test_event_moments)

add_executable(test_exact_sum test_exact_sum.cpp)
target_include_directories(test_exact_sum PRIVATE ${PROJECT_SOURCE_DIR}/include)
add_test(NAME trech_exact_sum COMMAND test_exact_sum)

add_executable(test_geometry_resolution test_geometry_resolution.cpp)
target_include_directories(test_geometry_resolution PRIVATE ${PROJECT_SOURCE_DIR}/include)
target_link_libraries(test_geometry_resolution PRIVATE trech_core)
add_test(NAME trech_geometry_resolution COMMAND test_geometry_resolution)

add_executable(test_photonuclear_kinematics test_photonuclear_kinematics.cpp)
target_include_directories(test_photonuclear_kinematics PRIVATE ${PROJECT_SOURCE_DIR}/include)
add_test(NAME trech_photonuclear_kinematics COMMAND test_photonuclear_kinematics)

add_executable(test_process_operators test_process_operators.cpp)
target_link_libraries(test_process_operators PRIVATE trech_js)
target_compile_definitions(test_process_operators PRIVATE TRECH_SOURCE_DIR="${PROJECT_SOURCE_DIR}")
add_test(NAME trech_process_operators COMMAND test_process_operators)

add_executable(test_process_materials test_process_materials.cpp)
target_link_libraries(test_process_materials PRIVATE trech_js)
target_compile_definitions(test_process_materials PRIVATE TRECH_SOURCE_DIR="${PROJECT_SOURCE_DIR}")
add_test(NAME trech_process_materials COMMAND test_process_materials)

add_executable(test_process_spatial test_process_spatial.cpp)
target_link_libraries(test_process_spatial PRIVATE trech_js)
target_compile_definitions(test_process_spatial PRIVATE TRECH_SOURCE_DIR="${PROJECT_SOURCE_DIR}")
add_test(NAME trech_process_spatial COMMAND test_process_spatial)

add_executable(test_process_empty_population test_process_empty_population.cpp)
target_link_libraries(test_process_empty_population PRIVATE trech_js)
target_compile_definitions(test_process_empty_population PRIVATE TRECH_SOURCE_DIR="${PROJECT_SOURCE_DIR}")
add_test(NAME trech_process_empty_population COMMAND test_process_empty_population)

add_executable(test_process_units test_process_units.cpp)
target_link_libraries(test_process_units PRIVATE trech_js)
target_compile_definitions(test_process_units PRIVATE TRECH_SOURCE_DIR="${PROJECT_SOURCE_DIR}")
add_test(NAME trech_process_units COMMAND test_process_units)

add_executable(test_stratifier
  test_stratifier.cpp
)
target_link_libraries(test_stratifier PRIVATE trech_ml)
add_test(NAME trech_stratifier COMMAND test_stratifier)

add_executable(test_model_loader_snapshots test_model_loader_snapshots.cpp)
target_link_libraries(test_model_loader_snapshots PRIVATE trech_ml)
add_test(NAME trech_model_loader_snapshots COMMAND test_model_loader_snapshots)

add_executable(test_optics_surrogate
  test_optics_surrogate.cpp
)
target_link_libraries(test_optics_surrogate PRIVATE trech_ml)
add_test(NAME trech_optics_surrogate COMMAND test_optics_surrogate)

add_executable(test_generic_surrogate
  test_generic_surrogate.cpp
)
target_link_libraries(test_generic_surrogate PRIVATE trech_ml)
target_compile_definitions(test_generic_surrogate PRIVATE TRECH_SOURCE_DIR="${PROJECT_SOURCE_DIR}")
add_test(NAME trech_generic_surrogate COMMAND test_generic_surrogate)

add_executable(test_torch_backends test_torch_backends.cpp)
target_link_libraries(test_torch_backends PRIVATE trech_ml)
target_include_directories(test_torch_backends SYSTEM PRIVATE ${TORCH_INCLUDE_DIRS})
add_test(NAME trech_torch_backends COMMAND test_torch_backends)

add_executable(test_scale_cascade
  test_scale_cascade.cpp
)
target_link_libraries(test_scale_cascade PRIVATE trech_ml)
add_test(NAME trech_scale_cascade COMMAND test_scale_cascade)

add_executable(test_group_hierarchy
  test_group_hierarchy.cpp
)
target_link_libraries(test_group_hierarchy PRIVATE trech_ml)
target_compile_definitions(test_group_hierarchy PRIVATE
  TRECH_SOURCE_DIR="${PROJECT_SOURCE_DIR}" TRECH_BINARY_DIR="${CMAKE_CURRENT_BINARY_DIR}")
add_test(NAME trech_group_hierarchy COMMAND test_group_hierarchy)

# Engine architecture generation: classic native family + Evolvo worker bridge.
add_executable(test_architecture_generator test_architecture_generator.cpp)
target_link_libraries(test_architecture_generator PRIVATE trech_ml)
target_compile_definitions(test_architecture_generator PRIVATE
  TRECH_SOURCE_DIR="${PROJECT_SOURCE_DIR}" TRECH_BINARY_DIR="${CMAKE_CURRENT_BINARY_DIR}")
target_compile_definitions(test_architecture_generator PRIVATE TRECH_TEST_PYTHON="${TRECH_ML_PYTHON}")
add_test(NAME trech_architecture_generator COMMAND test_architecture_generator)
set_tests_properties(trech_architecture_generator PROPERTIES TIMEOUT 300)
# The real Evolvo worker through TRECH_ML_PYTHON; an unavailable worker is a failure.
add_test(NAME trech_architecture_evolvo_live COMMAND test_architecture_generator --live)
set_tests_properties(trech_architecture_evolvo_live PROPERTIES TIMEOUT 600)

add_executable(test_state_evolution
  test_state_evolution.cpp
)
target_link_libraries(test_state_evolution PRIVATE trech_ml)
add_test(NAME trech_state_evolution COMMAND test_state_evolution)

add_executable(test_domain_learner
  test_domain_learner.cpp
)
target_link_libraries(test_domain_learner PRIVATE trech_ml)
add_test(NAME trech_domain_learner COMMAND test_domain_learner)
set_tests_properties(trech_domain_learner PROPERTIES TIMEOUT 300)

add_executable(test_discrete_transition
  test_discrete_transition.cpp
)
target_link_libraries(test_discrete_transition PRIVATE trech_ml)
add_test(NAME trech_discrete_transition COMMAND test_discrete_transition)

add_executable(test_pair_interaction
  test_pair_interaction.cpp
)
target_link_libraries(test_pair_interaction PRIVATE trech_ml)
add_test(NAME trech_pair_interaction COMMAND test_pair_interaction)

add_executable(test_dna_chemistry_bridge
  test_dna_chemistry_bridge.cpp
)
target_link_libraries(test_dna_chemistry_bridge PRIVATE trech_chem)
add_test(NAME trech_dna_chemistry_bridge COMMAND test_dna_chemistry_bridge)

find_package(Python3 COMPONENTS Interpreter QUIET)
# fdlibm constants: decimal literal vs IEEE words in the deterministic math source.
if (Python3_Interpreter_FOUND)
  add_test(NAME trech_dmath_constants
    COMMAND "${Python3_EXECUTABLE}" "${PROJECT_SOURCE_DIR}/scripts/check_dmath_constants.py")
endif()
if(Python3_Interpreter_FOUND)
  add_test(NAME trech_scenario_contracts
    COMMAND ${Python3_EXECUTABLE} ${PROJECT_SOURCE_DIR}/tests/test_scenario_contracts.py)
endif()
if (Python3_Interpreter_FOUND)
  add_test(NAME trech_chemistry_probability COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/test_chemistry_probability.py)
  add_test(
    NAME trech_molecular_series
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/test_molecular_series.py
  )
  add_test(
    NAME trech_particle_molecule
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/test_particle_molecule.py
  )
  add_test(
    NAME trech_particle_observer
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/test_particle_observer.py
  )
  add_test(
    NAME trech_validation_pairs
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/test_validation_pairs.py
  )
  add_test(
    NAME trech_validation_offline
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/test_validation_offline.py
  )
  add_test(
    NAME trech_formal_law_pairs
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/test_formal_law_pairs.py
  )
  add_test(
    NAME trech_js_law_audit
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/test_js_law_audit.py
  )
  add_test(
    NAME trech_scenario_purity_report
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/test_scenario_purity_report.py
  )
  add_test(
    NAME trech_surrogate_output_links
    COMMAND ${TRECH_ML_PYTHON} ${CMAKE_CURRENT_SOURCE_DIR}/test_surrogate_output_links.py
  )
  add_test(
    NAME trech_joint_domain
    COMMAND ${TRECH_ML_PYTHON} ${CMAKE_CURRENT_SOURCE_DIR}/test_joint_domain.py
  )
  # Measured routing_domain blocks for domain routing (trech-measure-routing-domain).
  add_test(
    NAME trech_routing_domain
    COMMAND ${TRECH_ML_PYTHON} ${CMAKE_CURRENT_SOURCE_DIR}/test_routing_domain.py
  )
  # Online domain learner: NumPy twin of frozen routing and prediction.
  add_test(
    NAME trech_domain_learner_numpy
    COMMAND ${TRECH_ML_PYTHON} ${CMAKE_CURRENT_SOURCE_DIR}/test_domain_learner.py $<TARGET_FILE:test_domain_learner>
  )
  # Recursive group lifting: plan validation, engine-identical partition and the
  # NumPy reference evaluator.
  add_test(
    NAME trech_group_hierarchy_py
    COMMAND ${TRECH_ML_PYTHON} ${CMAKE_CURRENT_SOURCE_DIR}/test_group_hierarchy.py
  )
  # Evolvo GFSL-NN adapter: language validity, export, worker contract and CLI (torch required).
  add_test(
    NAME trech_evolvo_arch
    COMMAND ${TRECH_ML_PYTHON} ${CMAKE_CURRENT_SOURCE_DIR}/test_evolvo_arch.py
  )
  add_test(
    NAME trech_media_coverage
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/test_media_coverage.py
  )
  # Committed-model audit staleness + static/run-based ML validation gates
  # (NumPy and torch required, through TRECH_ML_PYTHON).
  add_test(
    NAME trech_ml_model_audit
    COMMAND ${TRECH_ML_PYTHON} ${CMAKE_CURRENT_SOURCE_DIR}/test_ml_model_validation.py
  )
  # Python side of the engine trace (trech_torch.trace): API, numpy/torch records, and trained
  # weights byte-identical with the trace on and off.
  add_test(
    NAME trech_python_trace
    COMMAND ${TRECH_ML_PYTHON} ${CMAKE_CURRENT_SOURCE_DIR}/test_python_trace.py
  )
  # Fresh-run re-check report staleness: fails when a re-checked committed model or its
  # recipe changed since docs/validation/ml_model_recheck.json was produced (no NumPy needed).
  add_test(
    NAME trech_ml_model_recheck
    COMMAND ${CMAKE_COMMAND} -E env PYTHONPATH=${PROJECT_SOURCE_DIR}/tools/torch
            ${TRECH_ML_PYTHON} -m trech_torch.recheck_models --root ${PROJECT_SOURCE_DIR}
            --recipes data/ml_recheck_recipes.json --json docs/validation/ml_model_recheck.json --check
  )
endif()

if (TRECH_ENABLE_GEANT4)
  add_executable(test_nuclear_spatial test_nuclear_spatial.cpp)
  target_link_libraries(test_nuclear_spatial PRIVATE trech_sim)
  add_test(NAME trech_nuclear_spatial COMMAND test_nuclear_spatial)
  add_executable(test_material_isotopes test_material_isotopes.cpp)
  target_link_libraries(test_material_isotopes PRIVATE trech_sim)
  add_test(NAME trech_material_isotopes COMMAND test_material_isotopes)
  add_executable(test_nuclear_cycle_analyzer
    test_nuclear_cycle_analyzer.cpp
  )
  target_link_libraries(test_nuclear_cycle_analyzer PRIVATE trech_sim)
  add_test(NAME trech_nuclear_cycle_analyzer COMMAND test_nuclear_cycle_analyzer)
endif()

add_executable(test_adaptive_precision test_adaptive_precision.cpp)
target_link_libraries(test_adaptive_precision PRIVATE trech_js)
target_compile_definitions(test_adaptive_precision PRIVATE TRECH_SOURCE_DIR="${PROJECT_SOURCE_DIR}")
add_test(NAME trech_adaptive_precision COMMAND test_adaptive_precision)

add_executable(test_chemistry_authoring test_chemistry_authoring.cpp)
target_link_libraries(test_chemistry_authoring PRIVATE trech_js)
target_compile_definitions(test_chemistry_authoring PRIVATE TRECH_SOURCE_DIR="${PROJECT_SOURCE_DIR}")
add_test(NAME trech_chemistry_authoring COMMAND test_chemistry_authoring)
add_executable(test_chemistry_scene test_chemistry_scene.cpp)
target_link_libraries(test_chemistry_scene PRIVATE trech_js)
target_compile_definitions(test_chemistry_scene PRIVATE TRECH_SOURCE_DIR="${PROJECT_SOURCE_DIR}")
add_test(NAME trech_chemistry_scene COMMAND test_chemistry_scene)

add_executable(test_scalar_field test_scalar_field.cpp)
target_link_libraries(test_scalar_field PRIVATE trech_core)
add_test(NAME trech_scalar_field COMMAND test_scalar_field)

# Spectrum-prediction JavaScript subproject (projects/spectrum_prediction). Its library/training
# tests need only an installed Node.js >= 18; nothing is built or downloaded.
find_program(TRECH_SPECTRA_NODE_EXECUTABLE NAMES node nodejs)
if (TRECH_SPECTRA_NODE_EXECUTABLE)
  file(GLOB TRECH_SPECTRA_JS_TESTS CONFIGURE_DEPENDS
    "${PROJECT_SOURCE_DIR}/projects/spectrum_prediction/test/*.test.js")
  add_test(NAME trech_spectrum_prediction_js
    COMMAND "${TRECH_SPECTRA_NODE_EXECUTABLE}" --test ${TRECH_SPECTRA_JS_TESTS})
  set_tests_properties(trech_spectrum_prediction_js PROPERTIES TIMEOUT 300)
endif()
# trech_dmath compiled to WebAssembly for V8 hosts (js/trech_dmath_v8.js): the C golden
# digests, staleness against the C source, and the QuickJS-compatible Math wrappers.
if (TRECH_SPECTRA_NODE_EXECUTABLE)
  add_test(NAME trech_dmath_wasm
    COMMAND "${TRECH_SPECTRA_NODE_EXECUTABLE}" "${PROJECT_SOURCE_DIR}/tests/test_dmath_wasm.cjs")
endif()
# JS model definitions / structure searches / checkpoint store (tools/ml, js/trech_ml.js).
# Node-only; training is exercised with a fake trainer, so no Python/torch is needed.
if (TRECH_SPECTRA_NODE_EXECUTABLE)
  file(GLOB TRECH_ML_JS_TESTS CONFIGURE_DEPENDS "${PROJECT_SOURCE_DIR}/tools/ml/test/*.test.js")
  add_test(NAME trech_ml_models_js COMMAND "${TRECH_SPECTRA_NODE_EXECUTABLE}" --test ${TRECH_ML_JS_TESTS})
  set_tests_properties(trech_ml_models_js PROPERTIES TIMEOUT 300)
endif()
# The same library inside the QuickJS host: TRECH_READ_JSON registry resolution + conflict refusal.
if (TRECH_ENABLE_GEANT4)
  add_test(NAME trech_ml_registry_quickjs
    COMMAND "$<TARGET_FILE:trech>" inspect "${PROJECT_SOURCE_DIR}/tests/fixtures/ml_registry/resolve_scenario.js")
  set_tests_properties(trech_ml_registry_quickjs PROPERTIES TIMEOUT 120
    PASS_REGULAR_EXPRESSION "\"conflict\":\"refused\",\"resolved\":\"fixture_model@v1:active\""
    FAIL_REGULAR_EXPRESSION "Error|error:")
endif()
# Same-input QuickJS vs installed Node/V8 differential of the engine-neutral JS numerics. Gates
# only what IEEE-754/the probe guarantee on any host (integer RNG stream, sqrt, CHILL+ phases,
# builtins within 1 ulp); trajectory divergence is reported, not gated. Builds nothing.
if (TARGET trech AND TRECH_SPECTRA_NODE_EXECUTABLE AND Python3_Interpreter_FOUND)
  add_test(NAME trech_js_engine_differential
    COMMAND "${Python3_EXECUTABLE}" "${PROJECT_SOURCE_DIR}/scripts/js_engine_differential.py"
      --trech "$<TARGET_FILE:trech>" --node "${TRECH_SPECTRA_NODE_EXECUTABLE}" --check)
  set_tests_properties(trech_js_engine_differential PROPERTIES TIMEOUT 120)
  # With trech_dmath installed as V8's Math (WebAssembly), the whole probe -- builtins, RNG
  # and the 40-step water trajectory -- must be bit-identical across the two engines.
  add_test(NAME trech_js_engine_differential_dmath
    COMMAND "${Python3_EXECUTABLE}" "${PROJECT_SOURCE_DIR}/scripts/js_engine_differential.py"
      --trech "$<TARGET_FILE:trech>" --node "${TRECH_SPECTRA_NODE_EXECUTABLE}"
      --dmath --check --require-identical)
  set_tests_properties(trech_js_engine_differential_dmath PROPERTIES TIMEOUT 120)
endif()
# Lab-mode geometry refusal through a real Geant4 kernel: refused batches, one
# geometry_refused record, an interactive session that survives, no onInit count.
if (TRECH_ENABLE_GEANT4 AND Python3_Interpreter_FOUND)
  add_test(NAME trech_lab_geometry_refusal
    COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/test_lab_geometry_refusal.py"
      "$<TARGET_FILE:trech>")
  set_tests_properties(trech_lab_geometry_refusal PROPERTIES TIMEOUT 300)
endif()
# Engine trace, Geant4 side: kernel/run/event/track/step records and tallies from a real kernel,
# serial and with two workers, traced vs untraced byte identity, run_end provenance reference.
if (TRECH_ENABLE_GEANT4 AND Python3_Interpreter_FOUND)
  add_test(NAME trech_geant4_trace
    COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/test_geant4_trace.py"
      "$<TARGET_FILE:trech>")
  set_tests_properties(trech_geant4_trace PROPERTIES TIMEOUT 300)
endif()
# Scenario-backed lab with --watch: on-disk hook edits reloaded before the next batch, a
# kernel-bound edit refused once while the batches continue on the same kernel.
if (TRECH_ENABLE_GEANT4 AND Python3_Interpreter_FOUND)
  add_test(NAME trech_lab_watch
    COMMAND "${Python3_EXECUTABLE}" "${CMAKE_CURRENT_SOURCE_DIR}/test_lab_watch.py"
      "$<TARGET_FILE:trech>" "${PROJECT_SOURCE_DIR}/examples/lab/live_hook_tuning.js")
  set_tests_properties(trech_lab_watch PROPERTIES TIMEOUT 300)
endif()
# No `**` operator in repository scripts: V8 cannot route it through trech_dmath, so it would
# break QuickJS/V8 bit identity (docs/engine/v8.md). Math.pow is identical in QuickJS.
if (Python3_Interpreter_FOUND)
  add_test(NAME trech_js_pow_operator
    COMMAND "${Python3_EXECUTABLE}" "${PROJECT_SOURCE_DIR}/scripts/check_js_pow_operator.py"
      js examples projects tests/fixtures
    WORKING_DIRECTORY "${PROJECT_SOURCE_DIR}")
endif()
# Engine-level check of the scenario against the committed JS-trained models.
if (TRECH_ENABLE_GEANT4 AND Python3_Interpreter_FOUND)
  add_test(NAME trech_spectrum_prediction_scenario
    COMMAND "${Python3_EXECUTABLE}" "${PROJECT_SOURCE_DIR}/scripts/validate_spectrum_prediction.py"
      --trech "$<TARGET_FILE:trech>" --out "${CMAKE_CURRENT_BINARY_DIR}/spectrum_prediction_validation")
  set_tests_properties(trech_spectrum_prediction_scenario PROPERTIES TIMEOUT 300)
endif()

# JavaScript exponent-operator scan (the V8 backend refuses `**`; scripts/check_js_pow_operator.py
# is its Python twin).
add_executable(test_pow_operator_scan test_pow_operator_scan.cpp)
target_link_libraries(test_pow_operator_scan PRIVATE trech_core)
add_test(NAME trech_pow_operator_scan COMMAND test_pow_operator_scan)

if (TRECH_ENABLE_V8)
  # QuickJS vs V8 on the same scenarios and hook calls, byte for byte.
  add_executable(test_js_engine_parity test_js_engine_parity.cpp)
  target_link_libraries(test_js_engine_parity PRIVATE trech_js)
  target_compile_definitions(test_js_engine_parity PRIVATE TRECH_SOURCE_DIR="${PROJECT_SOURCE_DIR}")
  add_test(NAME trech_js_engine_parity COMMAND test_js_engine_parity)
  # The engine-neutral JavaScript suites again, on V8 (TRECH_JS_ENGINE selects the engine of
  # every default-constructed JsRuntime).
  foreach(_trech_js_suite IN ITEMS js_runtime lab_script_host deterministic_math scenario_bundle
          scenario_helpers geometry_generators)
    add_test(NAME trech_${_trech_js_suite}_v8 COMMAND test_${_trech_js_suite})
    set_tests_properties(trech_${_trech_js_suite}_v8 PROPERTIES ENVIRONMENT "TRECH_JS_ENGINE=v8")
  endforeach()
  if (TRECH_ENABLE_GEANT4 AND Python3_Interpreter_FOUND)
    # Whole `trech run`s on both engines with every output compared (scripts/js_engine_run_parity.py).
    add_test(NAME trech_js_engine_run_parity
      COMMAND "${Python3_EXECUTABLE}" "${PROJECT_SOURCE_DIR}/scripts/js_engine_run_parity.py"
        --trech "$<TARGET_FILE:trech>"
        examples/scenarios/hello_world/hello_world.js
        examples/scenarios/hooks_track_ledger/hooks_track_ledger.js
        examples/scenarios/cascade_multiscale_demo/cascade_multiscale_demo.js
        examples/scenarios/surrogate_generic_demo/surrogate_generic_demo.js
        examples/scenarios/briggs_rauscher_oscillator/briggs_rauscher_oscillator.js
      WORKING_DIRECTORY "${PROJECT_SOURCE_DIR}")
    set_tests_properties(trech_js_engine_run_parity PROPERTIES TIMEOUT 600)
  endif()
endif()
