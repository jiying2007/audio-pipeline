#!/bin/sh
set -eu

fail() {
  echo "architecture contract failed: $1" >&2
  exit 1
}

if grep -R -n -E 'AP_ENABLE_RUNTIME|AP_ENABLE_MDF_AEC|AP_ENABLE_NEON' \
    --exclude='check-architecture.sh' \
    CMakeLists.txt CMakePresets.json cmake src include scripts .github docs README.md README.zh-CN.md 2>/dev/null; then
  fail "legacy build switch found"
fi

# Per-stage runtime composition replaced the old pile of public enable booleans.
if grep -R -n -E '\b(enable_hpf|enable_beamformer|enable_aec|enable_residual_echo_suppression|enable_noise_suppression|enable_agc|enable_vad)\b' \
    --exclude='check-architecture.sh' \
    src include tests bench examples fuzz 2>/dev/null; then
  fail "legacy stage enable field found; use ap_config_t.stages"
fi

# Physical stage split is part of the compile-pruning contract.
if [ -e src/frontend/ap_frontend.c ] || [ -e src/enhance/ap_enhance.c ]; then
  fail "legacy multi-stage translation unit found"
fi

if [ -e src/ap_internal.h ]; then
  fail "repository-wide src/ap_internal.h must not exist"
fi
internal_users=$(grep -R -l '#include "ap_internal.h"' src 2>/dev/null || true)
if [ "$internal_users" != "src/dsp/ap_fft.c" ]; then
  fail "ap_internal.h escaped the DSP-local FFT implementation"
fi

MODULE_DIRS="src/frontend src/sync src/aec src/enhance src/dsp src/arch"
if grep -R -n -E '\b(ap_pipeline_t|ap_metrics_t|ap_config_t)\b' $MODULE_DIRS 2>/dev/null; then
  fail "composite pipeline/config/metrics leaked into a DSP module"
fi
if grep -R -n 'audio_pipeline/audio_pipeline.h' $MODULE_DIRS 2>/dev/null; then
  fail "public pipeline API leaked into an internal DSP module"
fi
if grep -n 'audio_pipeline/audio_pipeline.h' include/audio_pipeline/audio_modules.h 2>/dev/null; then
  fail "standalone module SDK depends on high-level pipeline API"
fi

# Dependency direction is core -> stages -> dsp/arch. The public standalone
# wrapper layer may call stages, but stages must never depend back on wrappers.
if grep -R -n -E '#include "(core|sync|aec|enhance|modules|platform)/' src/frontend 2>/dev/null; then
  fail "frontend has a forbidden stage dependency"
fi
if grep -R -n -E '#include "(core|frontend|aec|enhance|modules|platform)/' src/sync 2>/dev/null; then
  fail "sync has a forbidden stage dependency"
fi
if grep -R -n -E '#include "(core|frontend|sync|enhance|modules|platform)/' src/aec 2>/dev/null; then
  fail "AEC has a forbidden stage dependency"
fi
if grep -R -n -E '#include "(core|frontend|sync|aec|modules|platform)/' src/enhance 2>/dev/null; then
  fail "enhancement has a forbidden stage dependency"
fi
if grep -R -n -E '#include "(core|frontend|sync|aec|enhance|modules|platform|arch)/' src/dsp 2>/dev/null; then
  fail "DSP primitive layer depends upward"
fi
if grep -R -n -E '#include "(core|frontend|sync|aec|enhance|modules|platform)/' src/arch 2>/dev/null; then
  fail "architecture kernel layer depends upward"
fi
if grep -R -n '#include "modules/' src/core 2>/dev/null; then
  fail "core depends on standalone wrapper layer"
fi
if grep -R -n -E '#include "(core|platform)/' src/modules 2>/dev/null; then
  fail "standalone wrapper depends on orchestration/platform layer"
fi

if grep -R -n 'arm_neon.h' src --exclude='ap_kernels_neon.c' 2>/dev/null; then
  fail "Arm NEON include escaped src/arch/arm_neon"
fi

if grep -R -n -E '#include <(pthread|semaphore)\.h>' src \
    --exclude='ap_runtime.c' 2>/dev/null; then
  fail "Linux runtime dependency escaped platform/linux"
fi

if grep -R -n -E 'cortex-a7|cortex-a32|cortex-a53' src 2>/dev/null; then
  fail "CPU model name leaked into DSP source"
fi

if grep -R -n -E '\b(malloc|calloc|realloc|free)[[:space:]]*\(' \
    src/core src/frontend src/sync src/aec src/enhance src/modules src/dsp src/arch 2>/dev/null; then
  fail "heap allocation found in synchronous DSP/modules"
fi

# Public validation workflows are part of the repository assurance boundary.
# Keep their profile-selection and balanced-corpus logic executable in the
# required fast gate instead of relying only on YAML/Python syntax checks.
python3 validation/tools/prepare_public_validation.py self-test
python3 validation/tools/build_compact_public_corpus.py --self-test

echo "architecture contracts: OK"
