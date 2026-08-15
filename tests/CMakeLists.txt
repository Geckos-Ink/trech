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
target_link_libraries(test_js_runtime PRIVATE trech_core)
add_test(NAME trech_js_runtime COMMAND test_js_runtime)

add_executable(test_stratifier
  test_stratifier.cpp
)
target_link_libraries(test_stratifier PRIVATE trech_ml)
add_test(NAME trech_stratifier COMMAND test_stratifier)

add_executable(test_optics_surrogate
  test_optics_surrogate.cpp
)
target_link_libraries(test_optics_surrogate PRIVATE trech_ml)
add_test(NAME trech_optics_surrogate COMMAND test_optics_surrogate)

add_executable(test_generic_surrogate
  test_generic_surrogate.cpp
)
target_link_libraries(test_generic_surrogate PRIVATE trech_ml)
add_test(NAME trech_generic_surrogate COMMAND test_generic_surrogate)

add_executable(test_scale_cascade
  test_scale_cascade.cpp
)
target_link_libraries(test_scale_cascade PRIVATE trech_ml)
add_test(NAME trech_scale_cascade COMMAND test_scale_cascade)

add_executable(test_state_evolution
  test_state_evolution.cpp
)
target_link_libraries(test_state_evolution PRIVATE trech_ml)
add_test(NAME trech_state_evolution COMMAND test_state_evolution)

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
if (Python3_Interpreter_FOUND)
  add_test(
    NAME trech_validation_pairs
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/test_validation_pairs.py
  )
  add_test(
    NAME trech_js_law_audit
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/test_js_law_audit.py
  )
  add_test(
    NAME trech_joint_domain
    COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/test_joint_domain.py
  )
endif()

if (TRECH_ENABLE_GEANT4)
  add_executable(test_nuclear_cycle_analyzer
    test_nuclear_cycle_analyzer.cpp
  )
  target_link_libraries(test_nuclear_cycle_analyzer PRIVATE trech_sim)
  add_test(NAME trech_nuclear_cycle_analyzer COMMAND test_nuclear_cycle_analyzer)
endif()
