set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR arm)

set(CMAKE_C_COMPILER arm-linux-gnueabihf-gcc CACHE FILEPATH "ARM hard-float C compiler")
set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)

# CPU/FPU/SIMD tuning intentionally lives in CMake presets or product build
# configuration, not in this generic ABI/toolchain description.
