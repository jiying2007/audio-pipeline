cmake_minimum_required(VERSION 3.20)
project(fe09_t3s3_f0_private C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
set(CMAKE_INTERPROCEDURAL_OPTIMIZATION OFF)
# The original parent controls its library and reference target unchanged.
add_subdirectory("${CMAKE_CURRENT_LIST_DIR}/../fe09_b3_f0_build" b3)
get_target_property(RESOURCE_SOURCES fe09_b3_f0_plain SOURCES)
get_target_property(RESOURCE_INCLUDES fe09_b3_f0_plain INCLUDE_DIRECTORIES)
get_target_property(RESOURCE_DEFINITIONS fe09_b3_f0_plain COMPILE_DEFINITIONS)
list(FILTER RESOURCE_SOURCES EXCLUDE REGEX "/fe09_b3_f0_composition_test\\.c$")
add_executable(fe09_t3s3_f0_probe ${RESOURCE_SOURCES}
  "${CMAKE_CURRENT_LIST_DIR}/../fe09_t3s3_f0_call_resource_probe.c")
set_target_properties(fe09_t3s3_f0_probe PROPERTIES UNITY_BUILD OFF
  INTERPROCEDURAL_OPTIMIZATION FALSE RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}")
target_include_directories(fe09_t3s3_f0_probe PRIVATE ${RESOURCE_INCLUDES})
target_compile_definitions(fe09_t3s3_f0_probe PRIVATE ${RESOURCE_DEFINITIONS})
target_compile_options(fe09_t3s3_f0_probe PRIVATE
  -ffp-contract=off -fno-fast-math -fno-lto -fstack-usage
  -Wall -Wextra -Wpedantic -Werror)
target_link_options(fe09_t3s3_f0_probe PRIVATE -fno-lto)
if(B3_F0_SANITIZE)
  target_compile_options(fe09_t3s3_f0_probe PRIVATE
    -O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer)
  target_link_options(fe09_t3s3_f0_probe PRIVATE -fsanitize=address,undefined)
else()
  target_compile_options(fe09_t3s3_f0_probe PRIVATE -O2)
endif()
target_link_libraries(fe09_t3s3_f0_probe PRIVATE audio_pipeline m)
foreach(SYMBOL fe_b3_f0_bind fe_b3_f0_process_one fe_b1s0_capture_submit
               fe_b1s0_render_present fe_b1s0_render_absent)
  target_link_options(fe09_t3s3_f0_probe PRIVATE "-Wl,--wrap=${SYMBOL}")
endforeach()
