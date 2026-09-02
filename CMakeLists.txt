cmake_minimum_required(VERSION 3.16)
project(audio_pipeline VERSION 2.3.0 LANGUAGES C)

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

if(CMAKE_SYSTEM_NAME STREQUAL "Linux" AND AP_BUILD_PIPELINE)
    set(_AP_LINUX_RUNTIME_DEFAULT ON)
else()
    set(_AP_LINUX_RUNTIME_DEFAULT OFF)
endif()
option(AP_ENABLE_LINUX_RUNTIME "Build the Linux SPSC worker runtime" ${_AP_LINUX_RUNTIME_DEFAULT})
if(AP_ENABLE_LINUX_RUNTIME AND NOT AP_BUILD_PIPELINE)
    message(FATAL_ERROR "AP_ENABLE_LINUX_RUNTIME requires AP_BUILD_PIPELINE=ON")
endif()
if(AP_ENABLE_LINUX_RUNTIME)
    set(AP_HAVE_LINUX_RUNTIME 1)
else()
    set(AP_HAVE_LINUX_RUNTIME 0)
endif()
if(AP_ENABLE_FAST_MATH)
    set(AP_HAVE_FAST_MATH 1)
else()
    set(AP_HAVE_FAST_MATH 0)
endif()
if(AP_HAVE_BF AND AP_ENABLE_BF_DIRECTION_TRACKING)
    set(AP_HAVE_BF_DIRECTION_TRACKING 1)
else()
    set(AP_HAVE_BF_DIRECTION_TRACKING 0)
endif()

set(AP_AEC_BACKEND "MDF" CACHE STRING "Compile-time AEC backend: MDF or NLMS")
set_property(CACHE AP_AEC_BACKEND PROPERTY STRINGS MDF NLMS)
string(TOUPPER "${AP_AEC_BACKEND}" AP_AEC_BACKEND)
set(AP_NS_ESTIMATOR "EMA" CACHE STRING "Compile-time NS estimator: EMA or MCRA")
set_property(CACHE AP_NS_ESTIMATOR PROPERTY STRINGS EMA MCRA)
string(TOUPPER "${AP_NS_ESTIMATOR}" AP_NS_ESTIMATOR)
set(AP_SIMD_BACKEND "SCALAR" CACHE STRING "Compile-time kernel backend: SCALAR or NEON")
set_property(CACHE AP_SIMD_BACKEND PROPERTY STRINGS SCALAR NEON)
string(TOUPPER "${AP_SIMD_BACKEND}" AP_SIMD_BACKEND)
set(AP_RESAMPLER_MODE "BANDLIMITED" CACHE STRING "Boundary resampler: BANDLIMITED or FAST")
set_property(CACHE AP_RESAMPLER_MODE PROPERTY STRINGS BANDLIMITED FAST)
string(TOUPPER "${AP_RESAMPLER_MODE}" AP_RESAMPLER_MODE)

set(AP_BUILD_SOURCE_REVISION "" CACHE STRING
    "Exact source revision embedded into additive build identity")
if(AP_BUILD_SOURCE_REVISION STREQUAL "")
    execute_process(
        COMMAND git rev-parse --verify HEAD
        WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
        OUTPUT_VARIABLE AP_BUILD_SOURCE_REVISION
        OUTPUT_STRIP_TRAILING_WHITESPACE
        ERROR_QUIET
        RESULT_VARIABLE _AP_GIT_REVISION_RESULT)
    if(NOT _AP_GIT_REVISION_RESULT EQUAL 0 OR AP_BUILD_SOURCE_REVISION STREQUAL "")
        set(AP_BUILD_SOURCE_REVISION "unknown")
    else()
        execute_process(
            COMMAND git status --porcelain
            WORKING_DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}
            OUTPUT_VARIABLE _AP_GIT_DIRTY
            OUTPUT_STRIP_TRAILING_WHITESPACE)
        if(NOT _AP_GIT_DIRTY STREQUAL "")
            string(APPEND AP_BUILD_SOURCE_REVISION "-dirty")
        endif()
    endif()
endif()

if(CMAKE_C_COMPILER_TARGET)
    set(AP_BUILD_TARGET_TRIPLE "${CMAKE_C_COMPILER_TARGET}")
else()
    execute_process(
        COMMAND ${CMAKE_C_COMPILER} -dumpmachine
        OUTPUT_VARIABLE AP_BUILD_TARGET_TRIPLE
        OUTPUT_STRIP_TRAILING_WHITESPACE
        ERROR_QUIET
        RESULT_VARIABLE _AP_TARGET_RESULT)
    if(NOT _AP_TARGET_RESULT EQUAL 0 OR AP_BUILD_TARGET_TRIPLE STREQUAL "")
        set(AP_BUILD_TARGET_TRIPLE "${CMAKE_SYSTEM_NAME}-${CMAKE_SYSTEM_PROCESSOR}")
    endif()
endif()
if(AP_BUILD_TARGET_TRIPLE STREQUAL "-")
    set(AP_BUILD_TARGET_TRIPLE "unknown")
endif()

if(CMAKE_BUILD_TYPE)
    set(AP_BUILD_TYPE_NAME "${CMAKE_BUILD_TYPE}")
else()
    set(AP_BUILD_TYPE_NAME "unspecified")
endif()
string(TOUPPER "${AP_BUILD_TYPE_NAME}" _AP_BUILD_TYPE_UPPER)
set(_AP_BUILD_TYPE_FLAGS_VAR "CMAKE_C_FLAGS_${_AP_BUILD_TYPE_UPPER}")
set(_AP_BUILD_TYPE_FLAGS "${${_AP_BUILD_TYPE_FLAGS_VAR}}")
string(CONCAT _AP_CONFIG_IDENTITY
    "version=${PROJECT_VERSION}\n"
    "modules=${AP_MODULES}\n"
    "pipeline=${AP_BUILD_PIPELINE}\n"
    "linux_runtime=${AP_ENABLE_LINUX_RUNTIME}\n"
    "fast_math=${AP_ENABLE_FAST_MATH}\n"
    "bf_direction_tracking=${AP_HAVE_BF_DIRECTION_TRACKING}\n"
    "max_io_rate=${AP_BUILD_MAX_IO_RATE_HZ}\n"
    "max_internal_rate=${AP_BUILD_MAX_INTERNAL_RATE_HZ}\n"
    "max_mics=${AP_BUILD_MAX_MIC_CHANNELS}\n"
    "max_delay_ms=${AP_BUILD_MAX_DELAY_MS}\n"
    "max_aec_tail_ms=${AP_BUILD_MAX_AEC_TAIL_MS}\n"
    "runtime_queue_depth=${AP_RUNTIME_QUEUE_DEPTH}\n"
    "aec_backend=${AP_AEC_BACKEND}\n"
    "ns_estimator=${AP_NS_ESTIMATOR}\n"
    "simd_backend=${AP_SIMD_BACKEND}\n"
    "resampler_mode=${AP_RESAMPLER_MODE}\n"
    "compiler_id=${CMAKE_C_COMPILER_ID}\n"
    "compiler_version=${CMAKE_C_COMPILER_VERSION}\n"
    "target=${AP_BUILD_TARGET_TRIPLE}\n"
    "build_type=${AP_BUILD_TYPE_NAME}\n"
    "c_flags=${CMAKE_C_FLAGS}\n"
    "build_flags=${_AP_BUILD_TYPE_FLAGS}\n")
string(SHA256 AP_BUILD_CONFIG_DIGEST "${_AP_CONFIG_IDENTITY}")

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

set(AP_SOURCES src/ap_build_info.c)
set(AP_MODULE_SOURCES)
set(AP_NEED_FFT 0)
set(AP_AEC_DEFINE)
set(AP_NS_DEFINE)
set(AP_RESAMPLER_DEFINE)

if(AP_BUILD_PIPELINE)
    list(APPEND AP_SOURCES src/core/ap_pipeline.c src/core/ap_pipeline_query.c)
endif()
if(AP_HAVE_RESAMPLER)
    list(APPEND AP_SOURCES src/frontend/ap_resampler.c)
    list(APPEND AP_MODULE_SOURCES src/modules/ap_resampler_module.c)
    if(AP_RESAMPLER_MODE STREQUAL "BANDLIMITED")
        set(AP_RESAMPLER_DEFINE AP_BUILD_RESAMPLER_BANDLIMITED=1)
    elseif(AP_RESAMPLER_MODE STREQUAL "FAST")
        set(AP_RESAMPLER_DEFINE AP_BUILD_RESAMPLER_FAST=1)
    else()
        message(FATAL_ERROR "AP_RESAMPLER_MODE must be BANDLIMITED or FAST")
    endif()
endif()
if(AP_HAVE_HPF)
    list(APPEND AP_SOURCES src/frontend/ap_hpf.c)
    list(APPEND AP_MODULE_SOURCES src/modules/ap_hpf_module.c)
endif()
if(AP_HAVE_BF)
    list(APPEND AP_SOURCES src/frontend/ap_beamformer.c)
    list(APPEND AP_MODULE_SOURCES src/modules/ap_beamformer_module.c)
endif()
if(AP_HAVE_SYNC)
    list(APPEND AP_SOURCES src/sync/ap_sync.c)
    list(APPEND AP_MODULE_SOURCES src/modules/ap_sync_module.c)
endif()
if(AP_HAVE_ACTIVITY)
    list(APPEND AP_SOURCES src/activity/ap_activity.c)
    list(APPEND AP_MODULE_SOURCES src/modules/ap_activity_module.c)
endif()
if(AP_HAVE_RES)
    list(APPEND AP_SOURCES src/enhance/ap_res.c)
    list(APPEND AP_MODULE_SOURCES src/modules/ap_res_module.c)
endif()
if(AP_HAVE_NS)
    list(APPEND AP_SOURCES src/enhance/ap_ns.c src/enhance/ap_noise_tracker.c src/enhance/ap_window.c)
    list(APPEND AP_MODULE_SOURCES src/modules/ap_ns_module.c)
    set(AP_NEED_FFT 1)
    if(AP_NS_ESTIMATOR STREQUAL "MCRA")
        set(AP_NS_DEFINE AP_BUILD_NS_MCRA=1)
    elseif(AP_NS_ESTIMATOR STREQUAL "EMA")
        set(AP_NS_DEFINE AP_BUILD_NS_EMA=1)
    else()
        message(FATAL_ERROR "AP_NS_ESTIMATOR must be EMA or MCRA")
    endif()
endif()
if(AP_HAVE_AGC)
    list(APPEND AP_SOURCES src/enhance/ap_agc.c)
    list(APPEND AP_MODULE_SOURCES src/modules/ap_agc_module.c)
endif()
if(AP_HAVE_VAD)
    list(APPEND AP_SOURCES src/enhance/ap_vad.c)
    list(APPEND AP_MODULE_SOURCES src/modules/ap_vad_module.c)
endif()
if(AP_HAVE_AEC)
    if(AP_AEC_BACKEND STREQUAL "MDF")
        list(APPEND AP_SOURCES src/aec/ap_aec_mdf.c)
        set(AP_AEC_DEFINE AP_BUILD_AEC_MDF=1)
        set(AP_NEED_FFT 1)
    elseif(AP_AEC_BACKEND STREQUAL "NLMS")
        list(APPEND AP_SOURCES src/aec/ap_aec_nlms.c)
        set(AP_AEC_DEFINE AP_BUILD_AEC_NLMS=1)
    else()
        message(FATAL_ERROR "AP_AEC_BACKEND must be MDF or NLMS")
    endif()
    list(APPEND AP_MODULE_SOURCES src/modules/ap_aec_module.c)
    if(AP_SIMD_BACKEND STREQUAL "SCALAR")
        list(APPEND AP_SOURCES src/arch/scalar/ap_kernels_scalar.c)
    elseif(AP_SIMD_BACKEND STREQUAL "NEON")
        list(APPEND AP_SOURCES src/arch/arm_neon/ap_kernels_neon.c)
    else()
        message(FATAL_ERROR "AP_SIMD_BACKEND must be SCALAR or NEON")
    endif()
endif()
if(AP_NEED_FFT)
    list(APPEND AP_SOURCES src/dsp/ap_fft.c)
endif()
list(APPEND AP_SOURCES ${AP_MODULE_SOURCES})
if(NOT AP_SOURCES)
    message(FATAL_ERROR "AP_MODULES/AP_BUILD_PIPELINE selected no buildable source")
endif()

configure_file(${CMAKE_CURRENT_SOURCE_DIR}/cmake/audio_pipeline_build.h.in
               ${CMAKE_CURRENT_BINARY_DIR}/generated/audio_pipeline/audio_pipeline_build.h @ONLY)

set(AP_STAGE_DEFINES
    AP_BUILD_STAGE_HPF=${AP_HAVE_HPF}
    AP_BUILD_STAGE_BF=${AP_HAVE_BF}
    AP_BUILD_BF_DIRECTION_TRACKING=${AP_HAVE_BF_DIRECTION_TRACKING}
    AP_BUILD_STAGE_SYNC=${AP_HAVE_SYNC}
    AP_BUILD_ACTIVITY=${AP_HAVE_ACTIVITY}
    AP_BUILD_STAGE_AEC=${AP_HAVE_AEC}
    AP_BUILD_STAGE_RES=${AP_HAVE_RES}
    AP_BUILD_STAGE_NS=${AP_HAVE_NS}
    AP_BUILD_STAGE_AGC=${AP_HAVE_AGC}
    AP_BUILD_STAGE_VAD=${AP_HAVE_VAD})

add_library(audio_pipeline STATIC ${AP_SOURCES})
set_target_properties(audio_pipeline PROPERTIES EXPORT_NAME core)
if(AP_BUILD_PIPELINE)
    set_target_properties(audio_pipeline PROPERTIES UNITY_BUILD ON UNITY_BUILD_BATCH_SIZE 32)
    if(AP_MODULE_SOURCES)
        set_source_files_properties(${AP_MODULE_SOURCES} PROPERTIES SKIP_UNITY_BUILD_INCLUSION ON)
    endif()
endif()
target_include_directories(audio_pipeline
    PUBLIC $<BUILD_INTERFACE:${CMAKE_CURRENT_BINARY_DIR}/generated>
           $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
           $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>
    PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src)
target_link_libraries(audio_pipeline PUBLIC m)
target_compile_definitions(audio_pipeline PRIVATE
    ${AP_STAGE_DEFINES} ${AP_AEC_DEFINE} ${AP_NS_DEFINE} ${AP_RESAMPLER_DEFINE})
target_compile_options(audio_pipeline PRIVATE -Wall -Wextra -Wpedantic)
if(AP_STRICT_WARNINGS)
    target_compile_options(audio_pipeline PRIVATE -Werror)
endif()
if(AP_ENABLE_FAST_MATH)
    if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
        target_compile_options(audio_pipeline PRIVATE -ffast-math -fno-math-errno)
    else()
        message(FATAL_ERROR "AP_ENABLE_FAST_MATH currently supports GNU/Clang only")
    endif()
endif()

if(AP_ENABLE_LINUX_RUNTIME)
    if(NOT CMAKE_SYSTEM_NAME STREQUAL "Linux")
        message(FATAL_ERROR "AP_ENABLE_LINUX_RUNTIME requires Linux")
    endif()
    find_package(Threads REQUIRED)
    add_library(audio_pipeline_runtime STATIC src/platform/linux/ap_runtime.c)
    set_target_properties(audio_pipeline_runtime PROPERTIES EXPORT_NAME runtime)
    target_include_directories(audio_pipeline_runtime PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_BINARY_DIR}/generated>
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
        $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>)
    target_link_libraries(audio_pipeline_runtime PUBLIC audio_pipeline Threads::Threads)
    target_compile_options(audio_pipeline_runtime PRIVATE -Wall -Wextra -Wpedantic)
    if(AP_STRICT_WARNINGS)
        target_compile_options(audio_pipeline_runtime PRIVATE -Werror)
    endif()
endif()

if(AP_BUILD_EXAMPLES)
    add_executable(ap_build_info_dump examples/build_info.c)
    target_link_libraries(ap_build_info_dump PRIVATE audio_pipeline)
endif()
if(AP_BUILD_EXAMPLES AND AP_BUILD_PIPELINE)
    add_executable(ap_process_pcm examples/process_pcm.c)
    target_link_libraries(ap_process_pcm PRIVATE audio_pipeline)
endif()
if(AP_BUILD_ALSA_EXAMPLE)
    if(NOT CMAKE_SYSTEM_NAME STREQUAL "Linux" OR NOT AP_ENABLE_LINUX_RUNTIME OR NOT AP_HAVE_SYNC)
        message(FATAL_ERROR "ALSA duplex examples require Linux runtime and SYNC")
    endif()
    find_package(ALSA REQUIRED)
    add_executable(ap_alsa_duplex examples/alsa_duplex.c)
    target_include_directories(ap_alsa_duplex PRIVATE ${ALSA_INCLUDE_DIRS})
    target_link_libraries(ap_alsa_duplex PRIVATE audio_pipeline ${ALSA_LIBRARIES})
    add_executable(ap_alsa_runtime_duplex examples/alsa_runtime_duplex.c)
    target_include_directories(ap_alsa_runtime_duplex PRIVATE ${ALSA_INCLUDE_DIRS})
    target_link_libraries(ap_alsa_runtime_duplex PRIVATE audio_pipeline_runtime ${ALSA_LIBRARIES})
    target_compile_options(ap_alsa_duplex PRIVATE -Wall -Wextra -Wpedantic)
    target_compile_options(ap_alsa_runtime_duplex PRIVATE -Wall -Wextra -Wpedantic)
    if(AP_STRICT_WARNINGS)
        target_compile_options(ap_alsa_duplex PRIVATE -Werror)
        target_compile_options(ap_alsa_runtime_duplex PRIVATE -Werror)
    endif()
endif()

if(AP_BUILD_TESTS)
    enable_testing()
    add_executable(ap_module_tests tests/test_modules.c)
    target_link_libraries(ap_module_tests PRIVATE audio_pipeline)
    add_test(NAME ap_module_tests COMMAND ap_module_tests)
    add_executable(ap_build_info_tests tests/test_build_info.c)
    target_link_libraries(ap_build_info_tests PRIVATE audio_pipeline)
    add_test(NAME ap_build_info_tests COMMAND ap_build_info_tests)

    if(AP_BUILD_PIPELINE)
        add_executable(ap_tests tests/test_pipeline.c)
        target_link_libraries(ap_tests PRIVATE audio_pipeline)
        add_test(NAME ap_tests COMMAND ap_tests)
        add_executable(ap_contract_tests tests/test_contracts.c)
        target_link_libraries(ap_contract_tests PRIVATE audio_pipeline)
        add_test(NAME ap_contract_tests COMMAND ap_contract_tests)
        add_executable(ap_pipeline_control_tests tests/test_pipeline_controls.c)
        target_link_libraries(ap_pipeline_control_tests PRIVATE audio_pipeline)
        add_test(NAME ap_pipeline_control_tests COMMAND ap_pipeline_control_tests)
        if(AP_HAVE_BF AND AP_HAVE_NS AND AP_HAVE_VAD)
            add_executable(ap_metamorphic_tests tests/test_metamorphic.c)
            target_link_libraries(ap_metamorphic_tests PRIVATE audio_pipeline)
            add_test(NAME ap_metamorphic_tests COMMAND ap_metamorphic_tests)
        endif()
        add_executable(ap_state_size tests/print_pipeline_state.c)
        target_link_libraries(ap_state_size PRIVATE audio_pipeline)
        add_executable(ap_consumer_smoke tests/consumer_smoke.c)
        target_link_libraries(ap_consumer_smoke PRIVATE audio_pipeline)
        if(AP_HAVE_SYNC AND AP_HAVE_AEC)
            add_executable(ap_realtime_tests tests/test_realtime.c)
            target_link_libraries(ap_realtime_tests PRIVATE audio_pipeline)
            add_test(NAME ap_realtime_tests COMMAND ap_realtime_tests)
        endif()
    endif()

    if(AP_NEED_FFT)
        add_executable(ap_fft_tests tests/test_fft.c)
        target_include_directories(ap_fft_tests PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src)
        target_link_libraries(ap_fft_tests PRIVATE audio_pipeline)
        add_test(NAME ap_fft_tests COMMAND ap_fft_tests)
    endif()
    if(AP_HAVE_NS)
        add_executable(ap_noise_tracker_tests tests/test_noise_tracker.c)
        target_include_directories(ap_noise_tracker_tests PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src)
        target_compile_definitions(ap_noise_tracker_tests PRIVATE
            ${AP_NS_DEFINE} AP_BUILD_STAGE_RES=${AP_HAVE_RES})
        target_link_libraries(ap_noise_tracker_tests PRIVATE audio_pipeline)
        add_test(NAME ap_noise_tracker_tests COMMAND ap_noise_tracker_tests)
    endif()
    if(AP_HAVE_RESAMPLER)
        add_executable(ap_resampler_tests tests/test_resampler.c)
        target_link_libraries(ap_resampler_tests PRIVATE audio_pipeline)
        add_test(NAME ap_resampler_tests COMMAND ap_resampler_tests)
    endif()
    if(AP_BUILD_PIPELINE AND AP_HAVE_SYNC AND AP_HAVE_AEC AND AP_HAVE_RES AND AP_HAVE_NS)
        add_executable(ap_drift_res_tests tests/test_drift_res.c)
        target_link_libraries(ap_drift_res_tests PRIVATE audio_pipeline)
        add_test(NAME ap_drift_res_tests COMMAND ap_drift_res_tests)
    endif()
    if(AP_ENABLE_LINUX_RUNTIME)
        add_executable(ap_runtime_tests tests/test_runtime.c)
        target_link_libraries(ap_runtime_tests PRIVATE audio_pipeline_runtime)
        add_test(NAME ap_runtime_tests COMMAND ap_runtime_tests)
        add_executable(ap_runtime_extended_tests tests/test_runtime_extended.c)
        target_link_libraries(ap_runtime_extended_tests PRIVATE audio_pipeline_runtime)
        add_test(NAME ap_runtime_extended_tests COMMAND ap_runtime_extended_tests)
        add_executable(ap_runtime_state_size tests/print_runtime_state.c)
        target_link_libraries(ap_runtime_state_size PRIVATE audio_pipeline_runtime)
    endif()

    if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
        get_property(_targets DIRECTORY PROPERTY BUILDSYSTEM_TARGETS)
        foreach(_t IN LISTS _targets)
            if(_t MATCHES "^ap_.*tests$")
                target_compile_options(${_t} PRIVATE -UNDEBUG)
            endif()
        endforeach()
    endif()
endif()

if(AP_BUILD_BENCH AND AP_BUILD_PIPELINE)
    add_executable(ap_bench bench/bench_pipeline.c)
    target_link_libraries(ap_bench PRIVATE audio_pipeline)
    if(AP_ENABLE_LINUX_RUNTIME)
        add_executable(ap_runtime_bench bench/bench_runtime.c)
        target_link_libraries(ap_runtime_bench PRIVATE audio_pipeline_runtime)
    endif()
endif()

if(AP_BUILD_FUZZ)
    if(NOT AP_BUILD_PIPELINE OR NOT CMAKE_C_COMPILER_ID MATCHES "Clang")
        message(FATAL_ERROR "AP_BUILD_FUZZ requires pipeline + Clang/libFuzzer")
    endif()
    set(_AP_FUZZ_TARGETS ap_fuzz)
    add_executable(ap_fuzz fuzz/fuzz_pipeline.c)
    target_link_libraries(ap_fuzz PRIVATE audio_pipeline)
    if(AP_ENABLE_LINUX_RUNTIME)
        add_executable(ap_fuzz_runtime_commands fuzz/fuzz_runtime_commands.c)
        target_link_libraries(ap_fuzz_runtime_commands PRIVATE audio_pipeline_runtime)
        add_executable(ap_fuzz_flight_recorder fuzz/fuzz_flight_recorder.c)
        target_link_libraries(ap_fuzz_flight_recorder PRIVATE audio_pipeline_runtime)
        list(APPEND _AP_FUZZ_TARGETS ap_fuzz_runtime_commands ap_fuzz_flight_recorder)
    endif()
    foreach(_f IN LISTS _AP_FUZZ_TARGETS)
        target_compile_options(${_f} PRIVATE
            -fsanitize=fuzzer,address,undefined -fno-omit-frame-pointer)
        target_link_options(${_f} PRIVATE -fsanitize=fuzzer,address,undefined)
    endforeach()
endif()

install(TARGETS audio_pipeline EXPORT AudioPipelineTargets
        ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR})
if(TARGET audio_pipeline_runtime)
    install(TARGETS audio_pipeline_runtime EXPORT AudioPipelineTargets
            ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR})
endif()
install(FILES
    include/audio_pipeline/audio_types.h
    include/audio_pipeline/audio_modules.h
    ${CMAKE_CURRENT_BINARY_DIR}/generated/audio_pipeline/audio_pipeline_build.h
    DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/audio_pipeline)
if(AP_BUILD_PIPELINE)
    install(FILES include/audio_pipeline/audio_pipeline.h
            DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/audio_pipeline)
endif()
if(TARGET audio_pipeline_runtime)
    install(FILES
            include/audio_pipeline/audio_runtime.h
            include/audio_pipeline/audio_diag.h
            DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/audio_pipeline)
endif()
install(FILES LICENSE THIRD_PARTY.md README.md CHANGELOG.md
        DESTINATION ${CMAKE_INSTALL_DOCDIR})
install(EXPORT AudioPipelineTargets
        FILE AudioPipelineTargets.cmake
        NAMESPACE AudioPipeline::
        DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/AudioPipeline)
configure_package_config_file(cmake/AudioPipelineConfig.cmake.in
    ${CMAKE_CURRENT_BINARY_DIR}/AudioPipelineConfig.cmake
    INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/AudioPipeline)
write_basic_package_version_file(
    ${CMAKE_CURRENT_BINARY_DIR}/AudioPipelineConfigVersion.cmake
    VERSION ${PROJECT_VERSION}
    COMPATIBILITY SameMajorVersion)
install(FILES
    ${CMAKE_CURRENT_BINARY_DIR}/AudioPipelineConfig.cmake
    ${CMAKE_CURRENT_BINARY_DIR}/AudioPipelineConfigVersion.cmake
    DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/AudioPipeline)
configure_file(cmake/audio-pipeline.pc.in
               ${CMAKE_CURRENT_BINARY_DIR}/audio-pipeline.pc @ONLY)
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/audio-pipeline.pc
        DESTINATION ${CMAKE_INSTALL_LIBDIR}/pkgconfig)
if(TARGET audio_pipeline_runtime)
    configure_file(cmake/audio-pipeline-runtime.pc.in
                   ${CMAKE_CURRENT_BINARY_DIR}/audio-pipeline-runtime.pc @ONLY)
    install(FILES ${CMAKE_CURRENT_BINARY_DIR}/audio-pipeline-runtime.pc
            DESTINATION ${CMAKE_INSTALL_LIBDIR}/pkgconfig)
endif()
