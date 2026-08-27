#!/bin/sh
set -eu

fail() {
  echo "architecture contract failed: $1" >&2
  exit 1
}

# Removed hard-cut build switches must not reappear. Exclude this policy file
# because it necessarily names the forbidden tokens it is looking for.
if grep -R -n -E 'AP_ENABLE_RUNTIME|AP_ENABLE_MDF_AEC|AP_ENABLE_NEON' \
    --exclude='check-architecture.sh' \
    CMakeLists.txt CMakePresets.json cmake src include scripts .github docs README.md README.zh-CN.md 2>/dev/null; then
  fail "legacy build switch found"
fi

# SIMD intrinsics belong exclusively to the architecture backend.
if grep -R -n 'arm_neon.h' src --exclude='ap_kernels_neon.c' 2>/dev/null; then
  fail "Arm NEON include escaped src/arch/arm_neon"
fi

# POSIX thread/semaphore policy belongs exclusively to the Linux adapter.
if grep -R -n -E '#include <(pthread|semaphore)\.h>' src \
    --exclude='ap_runtime.c' 2>/dev/null; then
  fail "Linux runtime dependency escaped platform/linux"
fi

# CPU model names belong to build/certification policy, never DSP algorithms.
if grep -R -n -E 'cortex-a7|cortex-a32|cortex-a53' src 2>/dev/null; then
  fail "CPU model name leaked into DSP source"
fi

# Synchronous DSP modules remain allocation-free.
if grep -R -n -E '\b(malloc|calloc|realloc|free)[[:space:]]*\(' \
    src/core src/frontend src/sync src/aec src/enhance src/dsp src/arch 2>/dev/null; then
  fail "heap allocation found in synchronous DSP modules"
fi

echo "architecture contracts: OK"
