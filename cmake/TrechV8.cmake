# Locate an already-built V8 for TRECH_ENABLE_V8 (the V8 JavaScript backend) and
# TRECH_ENABLE_V8_PROBE. Configuring TRECH never builds or downloads V8 (docs/engine/v8.md).
#
# Two layouts are accepted, checked in this order:
#   1. From-source monolith (scripts/build_v8.sh builds the pinned thirds/v8 submodule):
#      TRECH_V8_BUILD_DIR/obj/libv8_monolith.a, headers from thirds/v8/include.
#   2. Installed prefix (Homebrew `brew install v8`, a distribution package, a custom
#      install): TRECH_V8_ROOT/include/v8.h plus libv8, libv8_libplatform and libv8_libbase.
#      When TRECH_V8_ROOT is empty, `brew --prefix v8` and the default search paths are tried.
#
# The embedder must compile with the same ABI definitions as the V8 library (pointer
# compression, 31-bit Smis, sandbox). TRECH_V8_DEFINITIONS=AUTO (the default) finds them by
# building and running cmake/v8_abi_probe.cpp against each known combination; set the list
# explicitly when cross-compiling.
#
# Result: the INTERFACE target trech_v8 and TRECH_V8_VERSION / TRECH_V8_LAYOUT variables.

function(trech_find_v8)
  if (TARGET trech_v8)
    return()
  endif()
  set(TRECH_V8_BUILD_DIR "" CACHE PATH "From-source V8 build directory containing obj/libv8_monolith.a (scripts/build_v8.sh)")
  set(TRECH_V8_ROOT "" CACHE PATH "Installed V8 prefix with include/v8.h and lib/libv8 (e.g. Homebrew's)")
  set(TRECH_V8_DEFINITIONS "AUTO" CACHE STRING "V8 ABI definitions (semicolon-separated), or AUTO to detect them")

  set(_include "")
  set(_libs "")
  set(_rpath "")
  set(_icu "")
  set(_layout "")
  set(_build_dir "${TRECH_V8_BUILD_DIR}")
  if (NOT _build_dir AND EXISTS "${PROJECT_SOURCE_DIR}/thirds/v8/out.gn/trech/obj/libv8_monolith.a")
    set(_build_dir "${PROJECT_SOURCE_DIR}/thirds/v8/out.gn/trech")
  endif()
  if (_build_dir)
    find_library(TRECH_V8_MONOLITH NAMES v8_monolith PATHS "${_build_dir}/obj" NO_DEFAULT_PATH)
    if (NOT TRECH_V8_MONOLITH)
      message(FATAL_ERROR "TRECH_V8_BUILD_DIR=${_build_dir} has no obj/libv8_monolith.a. "
                          "Build it with scripts/build_v8.sh or point TRECH_V8_ROOT at an installed V8.")
    endif()
    set(_layout "monolith")
    set(_include "${PROJECT_SOURCE_DIR}/thirds/v8/include")
    find_package(Threads REQUIRED)
    set(_libs "${TRECH_V8_MONOLITH}" Threads::Threads ${CMAKE_DL_LIBS})
    if (EXISTS "${_build_dir}/icudtl.dat")
      set(_icu "${_build_dir}/icudtl.dat")
    endif()
  else()
    set(_root "${TRECH_V8_ROOT}")
    if (NOT _root)
      find_program(TRECH_BREW_EXECUTABLE brew)
      if (TRECH_BREW_EXECUTABLE)
        execute_process(COMMAND "${TRECH_BREW_EXECUTABLE}" --prefix v8
                        OUTPUT_VARIABLE _brew_prefix OUTPUT_STRIP_TRAILING_WHITESPACE
                        RESULT_VARIABLE _brew_status ERROR_QUIET)
        if (_brew_status EQUAL 0 AND EXISTS "${_brew_prefix}/include/v8.h")
          set(_root "${_brew_prefix}")
        endif()
      endif()
    endif()
    if (_root)
      find_path(TRECH_V8_INCLUDE_DIR v8.h PATHS "${_root}/include" NO_DEFAULT_PATH)
      set(_hints PATHS "${_root}/lib" "${_root}/libexec" NO_DEFAULT_PATH)
    else()
      find_path(TRECH_V8_INCLUDE_DIR v8.h PATH_SUFFIXES v8)
      set(_hints "")
    endif()
    find_library(TRECH_V8_LIBRARY NAMES v8 ${_hints})
    find_library(TRECH_V8_PLATFORM_LIBRARY NAMES v8_libplatform ${_hints})
    find_library(TRECH_V8_BASE_LIBRARY NAMES v8_libbase ${_hints})
    if (NOT TRECH_V8_INCLUDE_DIR OR NOT TRECH_V8_LIBRARY OR NOT TRECH_V8_PLATFORM_LIBRARY OR NOT TRECH_V8_BASE_LIBRARY)
      message(FATAL_ERROR
        "TRECH_ENABLE_V8 needs a built V8. Install one (macOS: `brew install v8`) and set "
        "TRECH_V8_ROOT to its prefix, or build the pinned submodule with scripts/build_v8.sh "
        "and set TRECH_V8_BUILD_DIR. Found: include=${TRECH_V8_INCLUDE_DIR} v8=${TRECH_V8_LIBRARY} "
        "platform=${TRECH_V8_PLATFORM_LIBRARY} base=${TRECH_V8_BASE_LIBRARY}")
    endif()
    set(_layout "prefix")
    set(_include "${TRECH_V8_INCLUDE_DIR}")
    set(_libs "${TRECH_V8_LIBRARY}" "${TRECH_V8_PLATFORM_LIBRARY}" "${TRECH_V8_BASE_LIBRARY}")
    get_filename_component(_libdir "${TRECH_V8_LIBRARY}" DIRECTORY)
    get_filename_component(_prefix "${_libdir}" DIRECTORY)
    # Homebrew's component build keeps the real dylibs and their @rpath dependencies in libexec.
    foreach(_dir "${_libdir}" "${_prefix}/libexec")
      if (EXISTS "${_dir}")
        list(APPEND _rpath "${_dir}")
      endif()
      if (NOT _icu AND EXISTS "${_dir}/icudtl.dat")
        set(_icu "${_dir}/icudtl.dat")
      endif()
    endforeach()
  endif()

  # ABI definitions.
  set(_definitions "${TRECH_V8_DEFINITIONS}")
  set(_version "")
  if (_definitions STREQUAL "AUTO")
    set(_definitions "")
    set(_found FALSE)
    set(_index 0)
    # Plain, pointer compression (V8's default on 64-bit targets), pointer compression + sandbox.
    foreach(_candidate NONE COMPRESSED SANDBOXED)
      set(_defs "")
      if (NOT _candidate STREQUAL "NONE")
        set(_defs V8_COMPRESS_POINTERS V8_31BIT_SMIS_ON_64BIT_ARCH)
      endif()
      if (_candidate STREQUAL "SANDBOXED")
        list(APPEND _defs V8_ENABLE_SANDBOX)
      endif()
      set(_flags "")
      foreach(_d IN LISTS _defs)
        list(APPEND _flags "-D${_d}")
      endforeach()
      set(_link_rpath "")
      foreach(_dir IN LISTS _rpath)
        list(APPEND _link_rpath "-Wl,-rpath,${_dir}")
      endforeach()
      try_run(_run_status _compile_ok
        "${CMAKE_BINARY_DIR}/trech_v8_abi_probe_${_index}"
        "${PROJECT_SOURCE_DIR}/cmake/v8_abi_probe.cpp"
        CMAKE_FLAGS "-DINCLUDE_DIRECTORIES=${_include}"
        COMPILE_DEFINITIONS ${_flags}
        LINK_LIBRARIES ${_libs}
        LINK_OPTIONS ${_link_rpath}
        CXX_STANDARD 20
        CXX_STANDARD_REQUIRED ON
        COMPILE_OUTPUT_VARIABLE _compile_log
        RUN_OUTPUT_VARIABLE _run_output)
      math(EXPR _index "${_index} + 1")
      if (_compile_ok AND _run_status EQUAL 0)
        set(_definitions "${_defs}")
        string(STRIP "${_run_output}" _version)
        set(_found TRUE)
        break()
      endif()
    endforeach()
    if (NOT _found)
      message(FATAL_ERROR "No known ABI definitions run against this V8 (${_layout}: ${_libs}). "
                          "Set TRECH_V8_DEFINITIONS to the definitions the library was built with. "
                          "Last compile log:\n${_compile_log}")
    endif()
  endif()

  add_library(trech_v8 INTERFACE)
  target_include_directories(trech_v8 SYSTEM INTERFACE "${_include}")
  target_link_libraries(trech_v8 INTERFACE ${_libs})
  target_compile_definitions(trech_v8 INTERFACE ${_definitions})
  if (_icu)
    target_compile_definitions(trech_v8 INTERFACE TRECH_V8_ICU_DATA="${_icu}")
  endif()
  foreach(_dir IN LISTS _rpath)
    target_link_options(trech_v8 INTERFACE "LINKER:-rpath,${_dir}")
  endforeach()
  set(TRECH_V8_VERSION "${_version}" PARENT_SCOPE)
  set(TRECH_V8_LAYOUT "${_layout}" PARENT_SCOPE)
  message(STATUS "V8 ${_version} (${_layout}): ${_libs}; ABI definitions: ${_definitions}")
endfunction()
