if (NOT EXISTS "${CMAKE_CURRENT_LIST_DIR}/quickjs/quickjs.c")
  message(FATAL_ERROR "QuickJS sources not found in thirds/quickjs/quickjs.")
endif()

add_library(quickjs STATIC
  quickjs/quickjs.c
  quickjs/libregexp.c
  quickjs/libunicode.c
  quickjs/libbf.c
  quickjs/cutils.c
)
target_include_directories(quickjs PUBLIC ${CMAKE_CURRENT_LIST_DIR}/quickjs)
target_compile_definitions(quickjs PUBLIC CONFIG_BIGNUM)

if (UNIX AND NOT APPLE)
  target_link_libraries(quickjs PUBLIC m dl pthread)
endif()
