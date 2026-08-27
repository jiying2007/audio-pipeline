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

# The old repository-wide internal header was the main state-coupling surface.
# FFT keeps a module-local private include only to avoid rewriting its large
# read-only twiddle table for a header-only refactor.
if [ -e src/ap_internal.h ]; then
  fail "repository-wide src/ap_internal.h must not exist"
fi
internal_users=$(grep -R -l '#include "ap_internal.h"' src 2>/dev/null || true)
if [ "$internal_users" != "src/dsp/ap_fft.c" ]; then
  fail "ap_internal.h escaped the DSP-local FFT implementation"
fi

# Only core may know the composite pipeline/public config/public telemetry.
MODULE_DIRS="src/frontend src/sync src/aec src/enhance src/dsp src/arch"
if grep -R -n -E '\b(ap_pipeline_t|ap_metrics_t|ap_config_t)\b' $MODULE_DIRS 2>/dev/null; then
  fail "composite pipeline/config/metrics leaked into a DSP module"
fi
if grep -R -n 'audio_pipeline/audio_pipeline.h' $MODULE_DIRS 2>/dev/null; then
  fail "public pipeline API leaked into an internal DSP module"
fi

# Dependency direction is core -> stages -> dsp/arch. Sibling stages do not
# include or call through each other's private contracts.
if grep -R -n -E '#include "(core|sync|aec|enhance|platform)/' src/frontend 2>/dev/null; then
  fail "frontend has a forbidden stage dependency"
fi
if grep -R -n -E '#include "(core|frontend|aec|enhance|platform)/' src/sync 2>/dev/null; then
  fail "sync has a forbidden stage dependency"
fi
if grep -R -n -E '#include "(core|frontend|sync|enhance|platform)/' src/aec 2>/dev/null; then
  fail "AEC has a forbidden stage dependency"
fi
if grep -R -n -E '#include "(core|frontend|sync|aec|platform)/' src/enhance 2>/dev/null; then
  fail "enhancement has a forbidden stage dependency"
fi
if grep -R -n -E '#include "(core|frontend|sync|aec|enhance|platform|arch)/' src/dsp 2>/dev/null; then
  fail "DSP primitive layer depends upward"
fi
if grep -R -n -E '#include "(core|frontend|sync|aec|enhance|platform)/' src/arch 2>/dev/null; then
  fail "architecture kernel layer depends upward"
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
