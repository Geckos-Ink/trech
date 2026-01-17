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

add_executable(test_provenance_writer
  test_provenance_writer.cpp
)
target_link_libraries(test_provenance_writer PRIVATE trech_core)
add_test(NAME trech_provenance_writer COMMAND test_provenance_writer)

add_executable(test_js_runtime
  test_js_runtime.cpp
)
target_link_libraries(test_js_runtime PRIVATE trech_js)
add_test(NAME trech_js_runtime COMMAND test_js_runtime)

add_executable(test_stratifier
  test_stratifier.cpp
)
target_link_libraries(test_stratifier PRIVATE trech_ml)
add_test(NAME trech_stratifier COMMAND test_stratifier)

add_executable(test_dna_chemistry_bridge
  test_dna_chemistry_bridge.cpp
)
target_link_libraries(test_dna_chemistry_bridge PRIVATE trech_chem)
add_test(NAME trech_dna_chemistry_bridge COMMAND test_dna_chemistry_bridge)
