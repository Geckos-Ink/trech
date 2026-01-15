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
    set(TRECH_QUICKJS_INCLUDE_DIR "${PROJECT_SOURCE_DIR}/thirds/quickjs/quickjs" PARENT_SCOPE)
    return()
  endif()

  if (TRECH_FETCH_DEPS)
    FetchContent_Declare(
      quickjs
      GIT_REPOSITORY https://github.com/bellard/quickjs.git
      GIT_TAG f1139494d18a2053630c5ed3384a42bb70db3c53
    )
    FetchContent_GetProperties(quickjs)
    if (NOT quickjs_POPULATED)
      FetchContent_Populate(quickjs)
    endif()

    set(quickjs_sources
      ${quickjs_SOURCE_DIR}/quickjs.c
      ${quickjs_SOURCE_DIR}/dtoa.c
      ${quickjs_SOURCE_DIR}/libregexp.c
      ${quickjs_SOURCE_DIR}/libunicode.c
      ${quickjs_SOURCE_DIR}/cutils.c
    )
    if (EXISTS "${quickjs_SOURCE_DIR}/libbf.c")
      list(APPEND quickjs_sources ${quickjs_SOURCE_DIR}/libbf.c)
    endif()
    add_library(quickjs STATIC ${quickjs_sources})
    target_include_directories(quickjs PRIVATE ${quickjs_SOURCE_DIR})
    if (EXISTS "${quickjs_SOURCE_DIR}/libbf.c")
      target_compile_definitions(quickjs PUBLIC CONFIG_BIGNUM)
    endif()
    if (EXISTS "${quickjs_SOURCE_DIR}/VERSION")
      file(STRINGS "${quickjs_SOURCE_DIR}/VERSION" quickjs_version LIMIT_COUNT 1)
    else()
      set(quickjs_version "unknown")
    endif()
    target_compile_definitions(quickjs PRIVATE CONFIG_VERSION="${quickjs_version}")
    set(TRECH_QUICKJS_INCLUDE_DIR "${quickjs_SOURCE_DIR}" PARENT_SCOPE)
    if (UNIX AND NOT APPLE)
      target_link_libraries(quickjs PUBLIC m dl pthread)
    endif()
  else()
    message(FATAL_ERROR "QuickJS not found. Vendor it under thirds/quickjs/quickjs or set TRECH_FETCH_DEPS=ON.")
  endif()
endfunction()
