cmake_minimum_required(VERSION 3.20)
project(fe09_t3s3_f1_private C)
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
set(CMAKE_INTERPROCEDURAL_OPTIMIZATION OFF)

# Preserve every original F0/B3 build/source byte. No target is run by this build.
add_subdirectory("${CMAKE_CURRENT_LIST_DIR}/../fe09_t3s3_f0_build" f0)
foreach(F1_TARGET fe09_b3_f0_plain fe09_t3s3_f0_probe)
  target_sources(${F1_TARGET} PRIVATE
    "${CMAKE_CURRENT_LIST_DIR}/../fe09_t3s3_f1_rss_observer.c")
  target_link_options(${F1_TARGET} PRIVATE "-Wl,--wrap=main")
endforeach()

# The real launcher and engineering image are native-only, built once. The
# Sanitized/ARM compile databases have no helper translation units.
if(NOT B3_F0_SANITIZE AND NOT CMAKE_CROSSCOMPILING)
  foreach(F1_HELPER launcher fixture)
    add_executable(fe09_t3s3_f1_${F1_HELPER}
      "${CMAKE_CURRENT_LIST_DIR}/../fe09_t3s3_f1_rss_${F1_HELPER}.c")
    set_target_properties(fe09_t3s3_f1_${F1_HELPER} PROPERTIES
      UNITY_BUILD OFF INTERPROCEDURAL_OPTIMIZATION FALSE
      RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}")
    target_compile_options(fe09_t3s3_f1_${F1_HELPER} PRIVATE
      -O2 -ffp-contract=off -fno-fast-math -fno-lto -fstack-usage
      -Wall -Wextra -Wpedantic -Werror)
    target_link_options(fe09_t3s3_f1_${F1_HELPER} PRIVATE -fno-lto)
  endforeach()
endif()
