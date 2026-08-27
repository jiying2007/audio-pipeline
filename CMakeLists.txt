cmake_minimum_required(VERSION 3.16)
project(audio_pipeline VERSION 0.3.0 LANGUAGES C)

option(AP_BUILD_TESTS "Build unit/contract tests" ON)
option(AP_BUILD_BENCH "Build benchmarks" ON)
option(AP_BUILD_EXAMPLES "Build portable examples" ON)
option(AP_BUILD_ALSA_EXAMPLE "Build optional Linux ALSA examples" OFF)
option(AP_BUILD_FUZZ "Build clang libFuzzer target" OFF)
option(AP_ENABLE_FAST_MATH "Enable explicitly accepted fast-math DSP policy" OFF)
option(AP_STRICT_WARNINGS "Treat warnings as errors" OFF)

if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
    set(_AP_LINUX_RUNTIME_DEFAULT ON)
else()
    set(_AP_LINUX_RUNTIME_DEFAULT OFF)
endif()
option(AP_ENABLE_LINUX_RUNTIME "Build the Linux SPSC worker runtime" ${_AP_LINUX_RUNTIME_DEFAULT})

set(AP_AEC_BACKEND "MDF" CACHE STRING "Compile-time AEC backend: MDF or NLMS")
set_property(CACHE AP_AEC_BACKEND PROPERTY STRINGS MDF NLMS)
string(TOUPPER "${AP_AEC_BACKEND}" AP_AEC_BACKEND)

set(AP_SIMD_BACKEND "SCALAR" CACHE STRING "Compile-time DSP kernel backend: SCALAR or NEON")
set_property(CACHE AP_SIMD_BACKEND PROPERTY STRINGS SCALAR NEON)
string(TOUPPER "${AP_SIMD_BACKEND}" AP_SIMD_BACKEND)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

set(AP_CORE_SOURCES
    src/core/ap_pipeline.c
    src/frontend/ap_resampler.c
    src/frontend/ap_frontend.c
    src/sync/ap_sync.c
    src/enhance/ap_enhance.c
    src/dsp/ap_fft.c
)

if(AP_AEC_BACKEND STREQUAL "MDF")
    list(APPEND AP_CORE_SOURCES src/aec/ap_aec_mdf.c)
    set(AP_AEC_DEFINE AP_BUILD_AEC_MDF=1)
elseif(AP_AEC_BACKEND STREQUAL "NLMS")
    list(APPEND AP_CORE_SOURCES src/aec/ap_aec_nlms.c)
    set(AP_AEC_DEFINE AP_BUILD_AEC_NLMS=1)
else()
    message(FATAL_ERROR "AP_AEC_BACKEND must be MDF or NLMS")
endif()

if(AP_SIMD_BACKEND STREQUAL "SCALAR")
    list(APPEND AP_CORE_SOURCES src/arch/scalar/ap_kernels_scalar.c)
elseif(AP_SIMD_BACKEND STREQUAL "NEON")
    list(APPEND AP_CORE_SOURCES src/arch/arm_neon/ap_kernels_neon.c)
else()
    message(FATAL_ERROR "AP_SIMD_BACKEND must be SCALAR or NEON")
endif()

add_library(audio_pipeline STATIC ${AP_CORE_SOURCES})
# Keep physical source ownership/module boundaries without paying cross-TU call
# overhead in the tiny real-time graph. CMake 3.16 unity compilation lets the
# optimizer see the selected core/backend/kernel modules as one optimization
# unit while the repository remains split and architecture-linted.
set_target_properties(audio_pipeline PROPERTIES UNITY_BUILD ON UNITY_BUILD_BATCH_SIZE 32)
target_include_directories(audio_pipeline
    PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include
    PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src)
target_link_libraries(audio_pipeline PUBLIC m)
target_compile_definitions(audio_pipeline PRIVATE ${AP_AEC_DEFINE})
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
        message(FATAL_ERROR "AP_ENABLE_LINUX_RUNTIME requires CMAKE_SYSTEM_NAME=Linux")
    endif()
    add_library(audio_pipeline_runtime STATIC src/platform/linux/ap_runtime.c)
    target_include_directories(audio_pipeline_runtime PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
    target_link_libraries(audio_pipeline_runtime PUBLIC audio_pipeline pthread)
    target_compile_options(audio_pipeline_runtime PRIVATE -Wall -Wextra -Wpedantic)
    if(AP_STRICT_WARNINGS)
        target_compile_options(audio_pipeline_runtime PRIVATE -Werror)
    endif()
endif()

if(AP_BUILD_EXAMPLES)
    add_executable(ap_process_pcm examples/process_pcm.c)
    target_link_libraries(ap_process_pcm PRIVATE audio_pipeline)
endif()

if(AP_BUILD_ALSA_EXAMPLE)
    if(NOT CMAKE_SYSTEM_NAME STREQUAL "Linux")
        message(FATAL_ERROR "AP_BUILD_ALSA_EXAMPLE requires Linux")
    endif()
    if(NOT AP_ENABLE_LINUX_RUNTIME)
        message(FATAL_ERROR "AP_BUILD_ALSA_EXAMPLE requires AP_ENABLE_LINUX_RUNTIME=ON")
    endif()
    find_package(ALSA REQUIRED)
    add_executable(ap_alsa_duplex examples/alsa_duplex.c)
    target_include_directories(ap_alsa_duplex PRIVATE ${ALSA_INCLUDE_DIRS})
    target_link_libraries(ap_alsa_duplex PRIVATE audio_pipeline ${ALSA_LIBRARIES})
    target_compile_options(ap_alsa_duplex PRIVATE -Wall -Wextra -Wpedantic)
    add_executable(ap_alsa_runtime_duplex examples/alsa_runtime_duplex.c)
    target_include_directories(ap_alsa_runtime_duplex PRIVATE ${ALSA_INCLUDE_DIRS})
    target_link_libraries(ap_alsa_runtime_duplex PRIVATE audio_pipeline_runtime ${ALSA_LIBRARIES})
    target_compile_options(ap_alsa_runtime_duplex PRIVATE -Wall -Wextra -Wpedantic)
    if(AP_STRICT_WARNINGS)
        target_compile_options(ap_alsa_duplex PRIVATE -Werror)
        target_compile_options(ap_alsa_runtime_duplex PRIVATE -Werror)
    endif()
endif()

if(AP_BUILD_TESTS)
    enable_testing()
    add_executable(ap_tests tests/test_pipeline.c)
    target_link_libraries(ap_tests PRIVATE audio_pipeline)
    add_test(NAME ap_tests COMMAND ap_tests)

    add_executable(ap_fft_tests tests/test_fft.c)
    target_include_directories(ap_fft_tests PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/src)
    # test_fft.c intentionally includes the private DSP header. Keep the AEC
    # layout selector private to this white-box target rather than exporting it
    # from the library as a public compile definition.
    target_compile_definitions(ap_fft_tests PRIVATE ${AP_AEC_DEFINE})
    target_link_libraries(ap_fft_tests PRIVATE audio_pipeline)
    add_test(NAME ap_fft_tests COMMAND ap_fft_tests)

    add_executable(ap_resampler_tests tests/test_resampler.c)
    target_link_libraries(ap_resampler_tests PRIVATE audio_pipeline)
    add_test(NAME ap_resampler_tests COMMAND ap_resampler_tests)

    add_executable(ap_contract_tests tests/test_contracts.c)
    target_link_libraries(ap_contract_tests PRIVATE audio_pipeline)
    add_test(NAME ap_contract_tests COMMAND ap_contract_tests)

    add_executable(ap_realtime_tests tests/test_realtime.c)
    target_link_libraries(ap_realtime_tests PRIVATE audio_pipeline)
    add_test(NAME ap_realtime_tests COMMAND ap_realtime_tests)

    add_executable(ap_drift_res_tests tests/test_drift_res.c)
    target_link_libraries(ap_drift_res_tests PRIVATE audio_pipeline)
    add_test(NAME ap_drift_res_tests COMMAND ap_drift_res_tests)

    if(AP_ENABLE_LINUX_RUNTIME)
        add_executable(ap_runtime_tests tests/test_runtime.c)
        target_link_libraries(ap_runtime_tests PRIVATE audio_pipeline_runtime)
        add_test(NAME ap_runtime_tests COMMAND ap_runtime_tests)
    endif()

    if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
        foreach(_t ap_tests ap_fft_tests ap_resampler_tests ap_contract_tests ap_realtime_tests ap_drift_res_tests)
            target_compile_options(${_t} PRIVATE -UNDEBUG)
        endforeach()
        if(TARGET ap_runtime_tests)
            target_compile_options(ap_runtime_tests PRIVATE -UNDEBUG)
        endif()
    endif()
endif()

if(AP_BUILD_BENCH)
    add_executable(ap_bench bench/bench_pipeline.c)
    target_link_libraries(ap_bench PRIVATE audio_pipeline)
    if(AP_ENABLE_LINUX_RUNTIME)
        add_executable(ap_runtime_bench bench/bench_runtime.c)
        target_link_libraries(ap_runtime_bench PRIVATE audio_pipeline_runtime)
    endif()
endif()

if(AP_BUILD_FUZZ)
    if(NOT CMAKE_C_COMPILER_ID MATCHES "Clang")
        message(FATAL_ERROR "AP_BUILD_FUZZ requires Clang/libFuzzer")
    endif()
    add_executable(ap_fuzz fuzz/fuzz_pipeline.c)
    target_link_libraries(ap_fuzz PRIVATE audio_pipeline)
    target_compile_options(ap_fuzz PRIVATE -fsanitize=fuzzer,address,undefined -fno-omit-frame-pointer)
    target_link_options(ap_fuzz PRIVATE -fsanitize=fuzzer,address,undefined)
endif()

install(TARGETS audio_pipeline ARCHIVE DESTINATION lib)
if(TARGET audio_pipeline_runtime)
    install(TARGETS audio_pipeline_runtime ARCHIVE DESTINATION lib)
endif()
install(DIRECTORY include/ DESTINATION include)
