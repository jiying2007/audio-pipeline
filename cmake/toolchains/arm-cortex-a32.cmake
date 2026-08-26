set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR arm)

set(CMAKE_C_COMPILER arm-linux-gnueabihf-gcc CACHE FILEPATH "C compiler")
set(CMAKE_C_FLAGS_INIT "-O3 -mcpu=cortex-a32 -mfpu=neon-fp-armv8 -mfloat-abi=hard -ffast-math -fno-math-errno -fdata-sections -ffunction-sections")
set(CMAKE_EXE_LINKER_FLAGS_INIT "-Wl,--gc-sections")
set(CMAKE_SHARED_LINKER_FLAGS_INIT "-Wl,--gc-sections")

set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)
