cmake_minimum_required(VERSION 3.20)
project(fe09_b3_f0_private C)
# #837 research-only parent. Do not alter the production project's files.
option(B3_F0_SANITIZE "Build bounded ASan/UBSan research executables" OFF)
if(NOT AP_REPO_ROOT)
  get_filename_component(AP_REPO_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../../.." ABSOLUTE)
endif()
get_filename_component(AP_REPO_ROOT "${AP_REPO_ROOT}" ABSOLUTE)
if(NOT EXISTS "${AP_REPO_ROOT}/src/core/ap_pipeline.c")
  message(FATAL_ERROR "AP_REPO_ROOT must be the original audio-pipeline checkout")
endif()
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)
set(CMAKE_INTERPROCEDURAL_OPTIMIZATION OFF)
if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release CACHE STRING "" FORCE)
endif()
add_compile_options(-ffp-contract=off -fno-fast-math -fno-lto -fstack-usage)
add_link_options(-fno-lto)
if(B3_F0_SANITIZE)
  add_compile_options(-O1 -g -fsanitize=address,undefined -fno-omit-frame-pointer)
  add_link_options(-fsanitize=address,undefined)
else()
  add_compile_options(-O2)
endif()
set(AP_BUILD_PIPELINE ON CACHE BOOL "" FORCE)
set(AP_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(AP_BUILD_BENCH OFF CACHE BOOL "" FORCE)
set(AP_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(AP_ENABLE_LINUX_RUNTIME OFF CACHE BOOL "" FORCE)
set(AP_BUILD_MAX_MIC_CHANNELS 2 CACHE STRING "" FORCE)
set(AP_ENABLE_FAST_MATH OFF CACHE BOOL "" FORCE)
set(AP_AEC_BACKEND MDF CACHE STRING "" FORCE)
set(AP_SIMD_BACKEND SCALAR CACHE STRING "" FORCE)
set(AP_RESAMPLER_MODE BANDLIMITED CACHE STRING "" FORCE)
set(AP_NS_ESTIMATOR EMA CACHE STRING "" FORCE)
set(AP_MODULES "RESAMPLER,HPF,BF,SYNC,ACTIVITY,AEC,RES,NS,AGC,VAD" CACHE STRING "" FORCE)
add_subdirectory("${AP_REPO_ROOT}" "${CMAKE_CURRENT_BINARY_DIR}/public_sdk")
# Root project explicitly sets UNITY_BUILD=ON; global OFF alone is insufficient.
# Separate original translation units make actual internal calls visible to ld.
set_target_properties(audio_pipeline PROPERTIES UNITY_BUILD OFF
  INTERPROCEDURAL_OPTIMIZATION FALSE)
get_target_property(B3_PUBLIC_DEFINITIONS audio_pipeline COMPILE_DEFINITIONS)
if(NOT B3_PUBLIC_DEFINITIONS)
  message(FATAL_ERROR "Actual library compile definitions unavailable")
endif()
set(B3_HERE "${AP_REPO_ROOT}/tests/validation/frontend_evolution")
set(B3_SOURCES
  "${B3_HERE}/array_native.c"
  "${B3_HERE}/fe09_b1b0_src.c"
  "${B3_HERE}/fe09_b2s3_t2b_b0_capture_only.c"
  "${B3_HERE}/fe09_b2s3_t2b_b1s0_owner_spsc.c"
  "${B3_HERE}/fe09_b3_f0_composition.c"
  "${B3_HERE}/fe09_b3_f0_observer.c"
  "${B3_HERE}/fe09_b3_f0_composition_test.c")
# composition.c includes original fe09_b1b1_single_bf.c exactly once.
foreach(B3_VARIANT plain observed)
  set(B3_BINARY "fe09_b3_f0_${B3_VARIANT}")
  add_executable("${B3_BINARY}" ${B3_SOURCES})
  set_target_properties("${B3_BINARY}" PROPERTIES
    UNITY_BUILD OFF INTERPROCEDURAL_OPTIMIZATION FALSE
    RUNTIME_OUTPUT_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}")
  target_include_directories("${B3_BINARY}" PRIVATE "${B3_HERE}"
    "${AP_REPO_ROOT}/src" "${AP_REPO_ROOT}/include"
    "${CMAKE_CURRENT_BINARY_DIR}/public_sdk/generated")
  target_compile_definitions("${B3_BINARY}" PRIVATE ${B3_PUBLIC_DEFINITIONS})
  target_compile_options("${B3_BINARY}" PRIVATE -Wall -Wextra -Wpedantic -Werror)
  target_link_libraries("${B3_BINARY}" PRIVATE audio_pipeline m)
endforeach()
target_compile_definitions(fe09_b3_f0_observed PRIVATE FE_B3_F0_OBSERVED=1)
set(B3_WRAPPED_FUNCTIONS
  ap_hpf_process ap_sync_track_delay ap_sync_get_reference ap_activity_process
  ap_aec_backend_process ap_ns_process ap_agc_process_controlled ap_vad_process
  ap_sync_push_render ap_sync_reset ap_aec_backend_reset ap_res_process
  ap_beamformer_process ap_pipeline_notify_stream_discontinuity)
foreach(B3_SYMBOL IN LISTS B3_WRAPPED_FUNCTIONS)
  target_link_options(fe09_b3_f0_observed PRIVATE "-Wl,--wrap=${B3_SYMBOL}")
endforeach()
