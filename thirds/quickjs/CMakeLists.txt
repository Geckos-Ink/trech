if (NOT EXISTS "${CMAKE_CURRENT_LIST_DIR}/quickjs/quickjs.c")
  message(FATAL_ERROR "QuickJS sources not found in thirds/quickjs/quickjs.")
endif()

set(quickjs_sources
  quickjs/quickjs.c
  quickjs/dtoa.c
  quickjs/libregexp.c
  quickjs/libunicode.c
  quickjs/cutils.c
)

if (EXISTS "${CMAKE_CURRENT_LIST_DIR}/quickjs/libbf.c")
  list(APPEND quickjs_sources quickjs/libbf.c)
endif()

add_library(quickjs STATIC ${quickjs_sources})
target_include_directories(quickjs PRIVATE ${CMAKE_CURRENT_LIST_DIR}/quickjs)
if (EXISTS "${CMAKE_CURRENT_LIST_DIR}/quickjs/libbf.c")
  target_compile_definitions(quickjs PUBLIC CONFIG_BIGNUM)
endif()

if (EXISTS "${CMAKE_CURRENT_LIST_DIR}/quickjs/VERSION")
  file(STRINGS "${CMAKE_CURRENT_LIST_DIR}/quickjs/VERSION" quickjs_version LIMIT_COUNT 1)
else()
  set(quickjs_version "unknown")
endif()
target_compile_definitions(quickjs PRIVATE CONFIG_VERSION="${quickjs_version}")

if (UNIX AND NOT APPLE)
  target_link_libraries(quickjs PUBLIC m dl pthread)
endif()
