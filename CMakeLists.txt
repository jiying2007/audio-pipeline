cmake_minimum_required(VERSION 3.16)
project(audio_pipeline VERSION 2.3.7 LANGUAGES C)

include(GNUInstallDirs)
include(CMakePackageConfigHelpers)

option(AP_BUILD_PIPELINE "Build the high-level composed pipeline API" ON)
option(AP_BUILD_TESTS "Build unit/contract tests" ON)
option(AP_BUILD_BENCH "Build benchmarks" ON)
option(AP_BUILD_EXAMPLES "Build portable examples" ON)
option(AP_BUILD_ALSA_EXAMPLE "Build optional Linux ALSA examples" OFF)
option(AP_BUILD_FUZZ "Build clang libFuzzer target" OFF)
option(AP_ENABLE_FAST_MATH "Enable explicitly accepted fast-math DSP policy" OFF)
option(AP_ENABLE_BF_DIRECTION_TRACKING "Enable adaptive two-mic direction tracking" ON)
option(AP_STRICT_WARNINGS "Treat warnings as errors" OFF)

set(AP_MODULES "RESAMPLER,HPF,BF,SYNC,ACTIVITY,AEC,RES,NS,AGC,VAD" CACHE STRING
    "Compile-time module set")
set(_AP_VALID_MODULES RESAMPLER HPF BF SYNC ACTIVITY AEC RES NS AGC VAD)
foreach(_m IN LISTS _AP_VALID_MODULES)
    set(AP_HAVE_${_m} 0)
endforeach()
string(TOUPPER "${AP_MODULES}" _AP_MODULES_UPPER)
string(REPLACE "," ";" _AP_MODULE_LIST "${_AP_MODULES_UPPER}")
foreach(_m IN LISTS _AP_MODULE_LIST)
    string(STRIP "${_m}" _m)
    if(_m STREQUAL "")
        continue()
    endif()
    if(NOT _m IN_LIST _AP_VALID_MODULES)
        message(FATAL_ERROR "Unknown AP_MODULES entry: ${_m}")
    endif()
    set(AP_HAVE_${_m} 1)
endforeach()

set(AP_BUILD_MAX_IO_RATE_HZ 48000 CACHE STRING "Maximum device I/O rate compiled into this SKU")
set(AP_BUILD_MAX_INTERNAL_RATE_HZ 16000 CACHE STRING "Maximum internal DSP rate compiled into this SKU")
set(AP_BUILD_MAX_MIC_CHANNELS 2 CACHE STRING "Maximum microphone channels compiled into this SKU")
set(AP_BUILD_MAX_DELAY_MS 300 CACHE STRING "Maximum render-reference delay compiled into this SKU")
set(AP_BUILD_MAX_AEC_TAIL_MS 120 CACHE STRING "Maximum AEC tail compiled into this SKU")
set(AP_RUNTIME_QUEUE_DEPTH 8 CACHE STRING "Linux runtime SPSC queue depth; power of two")

if(NOT AP_BUILD_MAX_IO_RATE_HZ MATCHES "^(8000|16000|24000|32000|48000)$")
    message(FATAL_ERROR "AP_BUILD_MAX_IO_RATE_HZ must be one of 8/16/24/32/48 kHz")
endif()
if(NOT AP_BUILD_MAX_INTERNAL_RATE_HZ MATCHES "^(8000|16000)$")
    message(FATAL_ERROR "AP_BUILD_MAX_INTERNAL_RATE_HZ must be 8000 or 16000")
endif()
if(AP_BUILD_MAX_MIC_CHANNELS LESS 1 OR AP_BUILD_MAX_MIC_CHANNELS GREATER 2)
    message(FATAL_ERROR "AP_BUILD_MAX_MIC_CHANNELS must be 1 or 2")
endif()
if(AP_BUILD_MAX_DELAY_MS LESS 20 OR AP_BUILD_MAX_DELAY_MS GREATER 300)
    message(FATAL_ERROR "AP_BUILD_MAX_DELAY_MS must be 20..300")
endif()
if(AP_BUILD_MAX_AEC_TAIL_MS LESS 20 OR AP_BUILD_MAX_AEC_TAIL_MS GREATER 120)
    message(FATAL_ERROR "AP_BUILD_MAX_AEC_TAIL_MS must be 20..120")
endif()
math(EXPR _ap_depth_minus_one "${AP_RUNTIME_QUEUE_DEPTH} - 1")
math(EXPR _ap_depth_and "${AP_RUNTIME_QUEUE_DEPTH} & ${_ap_depth_minus_one}")
if(AP_RUNTIME_QUEUE_DEPTH LESS 2 OR AP_RUNTIME_QUEUE_DEPTH GREATER 32 OR NOT _ap_depth_and EQUAL 0)
    message(FATAL_ERROR "AP_RUNTIME_QUEUE_DEPTH must be a power of two in 2..32")
endif()

math(EXPR AP_BUILD_IO_FRAME_MAX "${AP_BUILD_MAX_IO_RATE_HZ} / 100")
math(EXPR AP_BUILD_INTERNAL_FRAME_MAX "${AP_BUILD_MAX_INTERNAL_RATE_HZ} / 100")
math(EXPR AP_BUILD_AEC_CAP "${AP_BUILD_MAX_AEC_TAIL_MS} * ${AP_BUILD_MAX_INTERNAL_RATE_HZ} / 1000")
math(EXPR AP_BUILD_AEC_PARTITIONS_MAX "(${AP_BUILD_MAX_AEC_TAIL_MS} + 1) / 2")
math(EXPR _AP_RENDER_NEEDED "${AP_BUILD_MAX_DELAY_MS} * ${AP_BUILD_MAX_INTERNAL_RATE_HZ} / 1000 + ${AP_BUILD_INTERNAL_FRAME_MAX}")
set(AP_BUILD_RENDER_CAP 1)
while(AP_BUILD_RENDER_CAP LESS _AP_RENDER_NEEDED)
    math(EXPR AP_BUILD_RENDER_CAP "${AP_BUILD_RENDER_CAP} * 2")
endwhile()

if(AP_BUILD_PIPELINE)
    set(AP_HAVE_PIPELINE 1)
    if(NOT AP_HAVE_RESAMPLER)
        message(FATAL_ERROR "AP_BUILD_PIPELINE=ON requires RESAMPLER in AP_MODULES")
    endif()
    if(AP_HAVE_AEC AND NOT AP_HAVE_ACTIVITY)
        message(FATAL_ERROR "high-level AEC requires ACTIVITY in AP_MODULES")
    endif()
else()
    set(AP_HAVE_PIPELINE 0)
endif()

foreach(_m IN LISTS _AP_VALID_MODULES)
    set(AP_BUILD_STAGE_${_m} ${AP_HAVE_${_m}})
endforeach()

configure_file(config/ap_limits.h.in ${CMAKE_CURRENT_BINARY_DIR}/generated/ap_limits.h @ONLY)
configure_file(config/audio_pipeline_build.h.in ${CMAKE_CURRENT_BINARY_DIR}/generated/audio_pipeline/audio_pipeline_build.h @ONLY)

set(AP_CORE_SOURCES
    src/core/ap_build_info.c
    src/core/ap_pipeline.c
    src/core/ap_pipeline_query.c
    src/core/ap_modules.c
    src/dsp/ap_fft.c
    src/dsp/ap_resampler.c
    src/dsp/ap_simd.c
    src/enhance/ap_agc.c
    src/enhance/ap_noise_tracker.c
    src/enhance/ap_ns.c
    src/enhance/ap_res.c
    src/enhance/ap_vad.c
    src/enhance/ap_window.c
    src/frontend/ap_beamformer.c
    src/frontend/ap_hpf.c
    src/aec/ap_activity.c
    src/aec/ap_aec_backend.c
    src/aec/ap_mdf.c
    src/aec/ap_nlms.c
    src/aec/ap_sync.c
)

add_library(audio_pipeline STATIC ${AP_CORE_SOURCES})
add_library(audio_pipeline::audio_pipeline ALIAS audio_pipeline)
target_compile_features(audio_pipeline PUBLIC c_std_11)
target_include_directories(audio_pipeline
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
        $<BUILD_INTERFACE:${CMAKE_CURRENT_BINARY_DIR}/generated>
        $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>
    PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src ${CMAKE_CURRENT_BINARY_DIR}/generated)
target_link_libraries(audio_pipeline PUBLIC m)

if(AP_ENABLE_FAST_MATH)
    if(MSVC)
        target_compile_options(audio_pipeline PRIVATE /fp:fast)
    else()
        target_compile_options(audio_pipeline PRIVATE -ffast-math)
    endif()
endif()
if(AP_STRICT_WARNINGS)
    if(MSVC)
        target_compile_options(audio_pipeline PRIVATE /W4 /WX)
    else()
        target_compile_options(audio_pipeline PRIVATE -Wall -Wextra -Wpedantic -Werror)
    endif()
endif()

if(AP_BUILD_EXAMPLES)
    add_executable(ap_process_pcm examples/process_pcm.c)
    target_link_libraries(ap_process_pcm PRIVATE audio_pipeline)
    if(AP_STRICT_WARNINGS AND NOT MSVC)
        target_compile_options(ap_process_pcm PRIVATE -Wall -Wextra -Wpedantic -Werror)
    endif()
endif()

if(AP_BUILD_TESTS)
    enable_testing()
    add_executable(ap_test_pipeline tests/test_pipeline.c)
    target_link_libraries(ap_test_pipeline PRIVATE audio_pipeline)
    add_test(NAME pipeline COMMAND ap_test_pipeline)

    add_executable(ap_test_modules tests/test_modules.c)
    target_link_libraries(ap_test_modules PRIVATE audio_pipeline)
    add_test(NAME modules COMMAND ap_test_modules)

    add_executable(ap_test_dsp tests/test_dsp.c)
    target_link_libraries(ap_test_dsp PRIVATE audio_pipeline)
    add_test(NAME dsp COMMAND ap_test_dsp)
endif()

if(AP_BUILD_BENCH)
    add_executable(ap_bench bench/bench_pipeline.c)
    target_link_libraries(ap_bench PRIVATE audio_pipeline)
endif()

include(CMakePackageConfigHelpers)
write_basic_package_version_file(
    "${CMAKE_CURRENT_BINARY_DIR}/audio_pipeline-config-version.cmake"
    VERSION ${PROJECT_VERSION}
    COMPATIBILITY SameMajorVersion)
configure_package_config_file(
    "${CMAKE_CURRENT_SOURCE_DIR}/cmake/audio_pipeline-config.cmake.in"
    "${CMAKE_CURRENT_BINARY_DIR}/audio_pipeline-config.cmake"
    INSTALL_DESTINATION "${CMAKE_INSTALL_LIBDIR}/cmake/audio_pipeline")

install(TARGETS audio_pipeline EXPORT audio_pipeline-targets
        ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR})
install(DIRECTORY include/audio_pipeline DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/generated/audio_pipeline/audio_pipeline_build.h
        DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/audio_pipeline)
install(EXPORT audio_pipeline-targets
        FILE audio_pipeline-targets.cmake
        NAMESPACE audio_pipeline::
        DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/audio_pipeline)
install(FILES
        ${CMAKE_CURRENT_BINARY_DIR}/audio_pipeline-config.cmake
        ${CMAKE_CURRENT_BINARY_DIR}/audio_pipeline-config-version.cmake
        DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/audio_pipeline)
