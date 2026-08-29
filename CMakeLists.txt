cmake_minimum_required(VERSION 3.16)
project(audio_pipeline VERSION 1.6.1 LANGUAGES C)

include(GNUInstallDirs)
include(CMakePackageConfigHelpers)

option(AP_BUILD_PIPELINE "Build the high-level composed pipeline API" ON)
option(AP_BUILD_TESTS "Build unit/contract tests" ON)
option(AP_BUILD_BENCH "Build benchmarks" ON)
option(AP_BUILD_EXAMPLES "Build portable examples" ON)
option(AP_BUILD_ALSA_EXAMPLE "Build optional Linux ALSA examples" OFF)
option(AP_BUILD_FUZZ "Build clang libFuzzer target" OFF)
option(AP_ENABLE_FAST_MATH "Enable explicitly accepted fast-math DSP policy" OFF)
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
    if(AP_HAVE_AEC AND NOT AP_HAVE_SYNC)
        message(FATAL_ERROR "high-level AEC requires SYNC in AP_MODULES")
    endif()
else()
    set(AP_HAVE_PIPELINE 0)
endif()

configure_file(
    ${CMAKE_CURRENT_SOURCE_DIR}/cmake/ap_build_config.h.in
    ${CMAKE_CURRENT_BINARY_DIR}/generated/audio_pipeline/ap_build_config.h
    @ONLY
)

configure_file(
    ${CMAKE_CURRENT_SOURCE_DIR}/cmake/ap_config.h.in
    ${CMAKE_CURRENT_BINARY_DIR}/generated/audio_pipeline/ap_config.h
    @ONLY
)

set(AP_LIBRARY_SOURCES
    src/modules/ap_resampler_module.c
    src/modules/ap_hpf_module.c
    src/modules/ap_beamformer_module.c
    src/modules/ap_sync_module.c
    src/modules/ap_activity_module.c
    src/modules/ap_aec_module.c
    src/modules/ap_res_module.c
    src/modules/ap_ns_module.c
    src/modules/ap_agc_module.c
    src/modules/ap_vad_module.c
)
if(AP_BUILD_PIPELINE)
    list(APPEND AP_LIBRARY_SOURCES
        src/core/ap_pipeline.c
        src/core/ap_metrics.c
        src/core/ap_config.c
        src/core/ap_build_info.c
    )
endif()

add_library(audio_pipeline STATIC ${AP_LIBRARY_SOURCES})
target_include_directories(audio_pipeline
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
        $<BUILD_INTERFACE:${CMAKE_CURRENT_BINARY_DIR}/generated>
        $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>
    PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/src
)
target_compile_features(audio_pipeline PUBLIC c_std_11)
target_compile_definitions(audio_pipeline PRIVATE _POSIX_C_SOURCE=200809L)
if(AP_ENABLE_FAST_MATH)
    target_compile_options(audio_pipeline PRIVATE -ffast-math)
endif()
if(AP_STRICT_WARNINGS)
    if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
        target_compile_options(audio_pipeline PRIVATE -Wall -Wextra -Wpedantic -Werror)
    endif()
endif()

find_package(Threads REQUIRED)

if(AP_HAVE_PIPELINE)
    add_library(audio_pipeline_runtime STATIC src/platform/linux/ap_runtime.c)
    target_include_directories(audio_pipeline_runtime
        PUBLIC
            $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
            $<BUILD_INTERFACE:${CMAKE_CURRENT_BINARY_DIR}/generated>
            $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>
        PRIVATE
            ${CMAKE_CURRENT_SOURCE_DIR}/src
    )
    target_compile_features(audio_pipeline_runtime PUBLIC c_std_11)
    target_compile_definitions(audio_pipeline_runtime PRIVATE _GNU_SOURCE)
    target_link_libraries(audio_pipeline_runtime PUBLIC audio_pipeline Threads::Threads m)
    if(AP_STRICT_WARNINGS)
        if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
            target_compile_options(audio_pipeline_runtime PRIVATE -Wall -Wextra -Wpedantic -Werror)
        endif()
    endif()
endif()

if(AP_BUILD_TESTS)
    enable_testing()
    add_executable(ap_module_tests tests/test_modules.c)
    target_link_libraries(ap_module_tests PRIVATE audio_pipeline m)
    add_test(NAME ap_module_tests COMMAND ap_module_tests)

    if(AP_HAVE_PIPELINE)
        add_executable(ap_build_info_tests tests/test_build_info.c)
        target_link_libraries(ap_build_info_tests PRIVATE audio_pipeline)
        add_test(NAME ap_build_info_tests COMMAND ap_build_info_tests)

        add_executable(ap_tests tests/test_pipeline.c)
        target_link_libraries(ap_tests PRIVATE audio_pipeline m)
        add_test(NAME ap_tests COMMAND ap_tests)

        add_executable(ap_contract_tests tests/test_contracts.c)
        target_link_libraries(ap_contract_tests PRIVATE audio_pipeline m)
        add_test(NAME ap_contract_tests COMMAND ap_contract_tests)

        add_executable(ap_metamorphic_tests tests/test_metamorphic.c)
        target_link_libraries(ap_metamorphic_tests PRIVATE audio_pipeline m)
        add_test(NAME ap_metamorphic_tests COMMAND ap_metamorphic_tests)

        add_executable(ap_realtime_tests tests/test_realtime.c)
        target_link_libraries(ap_realtime_tests PRIVATE audio_pipeline m)
        add_test(NAME ap_realtime_tests COMMAND ap_realtime_tests)

        add_executable(ap_fft_tests tests/test_fft.c)
        target_link_libraries(ap_fft_tests PRIVATE audio_pipeline m)
        add_test(NAME ap_fft_tests COMMAND ap_fft_tests)

        add_executable(ap_noise_tracker_tests tests/test_noise_tracker.c)
        target_link_libraries(ap_noise_tracker_tests PRIVATE audio_pipeline m)
        add_test(NAME ap_noise_tracker_tests COMMAND ap_noise_tracker_tests)

        add_executable(ap_resampler_tests tests/test_resampler.c)
        target_link_libraries(ap_resampler_tests PRIVATE audio_pipeline m)
        add_test(NAME ap_resampler_tests COMMAND ap_resampler_tests)

        add_executable(ap_drift_res_tests tests/test_drift_res.c)
        target_link_libraries(ap_drift_res_tests PRIVATE audio_pipeline m)
        add_test(NAME ap_drift_res_tests COMMAND ap_drift_res_tests)

        add_executable(ap_runtime_tests tests/test_runtime.c)
        target_link_libraries(ap_runtime_tests PRIVATE audio_pipeline_runtime m)
        add_test(NAME ap_runtime_tests COMMAND ap_runtime_tests)
    endif()
endif()

if(AP_BUILD_BENCH AND AP_HAVE_PIPELINE)
    add_executable(ap_bench bench/bench_pipeline.c)
    target_link_libraries(ap_bench PRIVATE audio_pipeline m)

    add_executable(ap_runtime_bench bench/bench_runtime.c)
    target_link_libraries(ap_runtime_bench PRIVATE audio_pipeline_runtime m)
endif()

if(AP_BUILD_EXAMPLES)
    if(AP_HAVE_PIPELINE)
        add_executable(ap_build_info_dump examples/build_info.c)
        target_link_libraries(ap_build_info_dump PRIVATE audio_pipeline)

        add_executable(ap_process_pcm examples/process_pcm.c)
        target_link_libraries(ap_process_pcm PRIVATE audio_pipeline m)
    endif()
endif()

if(AP_BUILD_ALSA_EXAMPLE AND AP_HAVE_PIPELINE)
    find_package(ALSA REQUIRED)
    add_executable(ap_alsa_runtime_duplex examples/alsa_runtime_duplex.c)
    target_link_libraries(ap_alsa_runtime_duplex PRIVATE audio_pipeline_runtime ALSA::ALSA m)
endif()

if(AP_BUILD_FUZZ AND AP_HAVE_PIPELINE)
    if(NOT CMAKE_C_COMPILER_ID MATCHES "Clang")
        message(FATAL_ERROR "AP_BUILD_FUZZ requires Clang/libFuzzer")
    endif()
    foreach(_target ap_fuzz_pipeline ap_fuzz_runtime_commands ap_fuzz_flight_recorder ap_fuzz_apd)
        add_executable(${_target} fuzz/${_target}.c)
        target_compile_options(${_target} PRIVATE -fsanitize=fuzzer,address,undefined)
        target_link_options(${_target} PRIVATE -fsanitize=fuzzer,address,undefined)
        target_link_libraries(${_target} PRIVATE audio_pipeline_runtime m)
    endforeach()
endif()

install(TARGETS audio_pipeline
    EXPORT audio_pipelineTargets
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
)
if(AP_HAVE_PIPELINE)
    install(TARGETS audio_pipeline_runtime
        EXPORT audio_pipelineTargets
        ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
    )
endif()
install(DIRECTORY include/audio_pipeline DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
install(DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}/generated/audio_pipeline DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})

configure_package_config_file(
    ${CMAKE_CURRENT_SOURCE_DIR}/cmake/audio_pipelineConfig.cmake.in
    ${CMAKE_CURRENT_BINARY_DIR}/audio_pipelineConfig.cmake
    INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/audio_pipeline
)
write_basic_package_version_file(
    ${CMAKE_CURRENT_BINARY_DIR}/audio_pipelineConfigVersion.cmake
    VERSION ${PROJECT_VERSION}
    COMPATIBILITY SameMajorVersion
)
install(FILES
    ${CMAKE_CURRENT_BINARY_DIR}/audio_pipelineConfig.cmake
    ${CMAKE_CURRENT_BINARY_DIR}/audio_pipelineConfigVersion.cmake
    DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/audio_pipeline
)
install(EXPORT audio_pipelineTargets
    FILE audio_pipelineTargets.cmake
    NAMESPACE audio_pipeline::
    DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/audio_pipeline
)

configure_file(audio_pipeline.pc.in audio_pipeline.pc @ONLY)
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/audio_pipeline.pc DESTINATION ${CMAKE_INSTALL_LIBDIR}/pkgconfig)
install(FILES LICENSE THIRD_PARTY_NOTICES.md README.md CHANGELOG.md DESTINATION ${CMAKE_INSTALL_DATADIR}/audio_pipeline)
