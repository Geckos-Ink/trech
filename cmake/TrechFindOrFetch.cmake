include(FetchContent)

function(trech_require_nlohmann_json)
  if (TARGET nlohmann_json::nlohmann_json)
    return()
  endif()

  if (EXISTS "${PROJECT_SOURCE_DIR}/thirds/json/CMakeLists.txt")
    add_subdirectory(${PROJECT_SOURCE_DIR}/thirds/json ${PROJECT_BINARY_DIR}/thirds/json)
    if (TARGET nlohmann_json::nlohmann_json)
      return()
    endif()
  endif()

  if (TRECH_FETCH_DEPS)
    FetchContent_Declare(
      nlohmann_json
      GIT_REPOSITORY https://github.com/nlohmann/json.git
      GIT_TAG v3.11.3
    )
    FetchContent_MakeAvailable(nlohmann_json)
  else()
    message(FATAL_ERROR "nlohmann/json not found. Vendor it under thirds/json or set TRECH_FETCH_DEPS=ON.")
  endif()
endfunction()

function(trech_require_quickjs)
  if (TARGET quickjs)
    return()
  endif()

  if (EXISTS "${PROJECT_SOURCE_DIR}/thirds/quickjs/quickjs/quickjs.c")
    add_subdirectory(${PROJECT_SOURCE_DIR}/thirds/quickjs ${PROJECT_BINARY_DIR}/thirds/quickjs)
    return()
  endif()

  if (TRECH_FETCH_DEPS)
    FetchContent_Declare(
      quickjs
      GIT_REPOSITORY https://github.com/bellard/quickjs.git
      GIT_TAG 2021-03-27
    )
    FetchContent_GetProperties(quickjs)
    if (NOT quickjs_POPULATED)
      FetchContent_Populate(quickjs)
    endif()

    add_library(quickjs STATIC
      ${quickjs_SOURCE_DIR}/quickjs.c
      ${quickjs_SOURCE_DIR}/libregexp.c
      ${quickjs_SOURCE_DIR}/libunicode.c
      ${quickjs_SOURCE_DIR}/libbf.c
      ${quickjs_SOURCE_DIR}/cutils.c
    )
    target_include_directories(quickjs PUBLIC ${quickjs_SOURCE_DIR})
    target_compile_definitions(quickjs PUBLIC CONFIG_BIGNUM)
    if (UNIX AND NOT APPLE)
      target_link_libraries(quickjs PUBLIC m dl pthread)
    endif()
  else()
    message(FATAL_ERROR "QuickJS not found. Vendor it under thirds/quickjs/quickjs or set TRECH_FETCH_DEPS=ON.")
  endif()
endfunction()
