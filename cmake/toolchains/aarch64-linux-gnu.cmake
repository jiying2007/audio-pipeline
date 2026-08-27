set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR aarch64)

set(CMAKE_C_COMPILER aarch64-linux-gnu-gcc CACHE FILEPATH "AArch64 C compiler")
set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)

# Architecture tuning intentionally belongs to a preset/product profile.
