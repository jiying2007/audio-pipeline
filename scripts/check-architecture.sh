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

# v2 is a hard cut. Current public headers and current product documentation
# must never restore v1 generational wrappers/types or advertise historical
# certification schemas as accepted input.
if grep -R -n -E '\b(ap_build_info_v2_t|ap_build_info_v2_get|ap_runtime_init_ex|ap_runtime_submit_ex|ap_runtime_metrics_v2_t|ap_runtime_metrics_v3_t|ap_runtime_get_metrics_v2|ap_runtime_get_metrics_v3|AP_RUNTIME_METRICS_V3_API_VERSION|AP_RUNTIME_CONTROL_API_VERSION)\b' \
    include/audio_pipeline README.md README.zh-CN.md docs certification/README.md 2>/dev/null; then
  fail "v2 public compatibility residue found"
fi
if grep -n -E 'schema v2/v3 remain accepted|v2, v3 or v4|\[2, 3, 4\]' \
    certification/README.md certification/validate_record.py certification/record.schema.json 2>/dev/null; then
  fail "historical certification compatibility returned"
fi
python3 - <<'PY'
import json
schema = json.load(open('certification/record.schema.json', encoding='utf-8'))
assert schema['properties']['schema_version'] == {'const': 4}
print('certification schema v4-only contract: OK')
PY

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

if grep -R -n -E '\bmlockall[[:space:]]*\(' src 2>/dev/null; then
  fail "process-global mlockall is forbidden inside the SDK runtime"
fi

if grep -R -n -E 'cortex-a7|cortex-a32|cortex-a53' src 2>/dev/null; then
  fail "CPU model name leaked into DSP source"
fi

if grep -R -n -E '\b(malloc|calloc|realloc|free)[[:space:]]*\(' \
    src/core src/frontend src/sync src/aec src/enhance src/modules src/dsp src/arch 2>/dev/null; then
  fail "heap allocation found in synchronous DSP/modules"
fi

# Public validation and trusted-runner workflows are part of the repository
# assurance boundary. Keep profile selection, holdout budgets and runner-role
# preflight executable in the required fast gate rather than relying only on
# YAML/Python syntax checks.
python3 validation/tools/prepare_public_validation.py self-test
python3 validation/tools/build_compact_public_corpus.py --self-test
python3 validation/tools/build_full_public_corpus.py --self-test
python3 validation/tools/split_holdout.py --self-test
python3 tools/runner_preflight.py --self-test
python3 - <<'PY'
import json
from pathlib import Path

expected = {
    'validation-compact.json': ({'validation-grade'}, 100),
    'validation-compact-partition.json': ({'validation-grade'}, 60),
    'validation-compact-blind.json': ({'validation-grade-blind'}, 10),
    'validation-full.json': ({'validation-grade'}, 160),
    'validation-full-partition.json': ({'validation-grade'}, 100),
    'validation-full-blind.json': ({'validation-grade-blind'}, 16),
}
root = Path('validation/policies')
for name, (tiers, minimum) in expected.items():
    data = json.loads((root / name).read_text())
    assert set(data['allowed_tiers']) == tiers, (name, data['allowed_tiers'])
    assert int(data['minimum_cases']) == minimum, (name, data['minimum_cases'])
    assert float(data['aggregate']['min_pass_rate']) == 0.98
print('public validation policy contracts: OK')
PY

# Formal evidence entrypoints must be immutable and explicitly source-bound.
python3 - <<'PY2'
from pathlib import Path

manual = [
    Path('.github/workflows/trusted-runner-readiness.yml'),
    Path('.github/workflows/validation-compact.yml'),
    Path('.github/workflows/validation-grade.yml'),
    Path('.github/workflows/hil-soak.yml'),
    Path('.github/workflows/product-certification.yml'),
]
for path in manual:
    text = path.read_text(encoding='utf-8')
    assert '      source_sha:' in text, path
    assert 'inputs.ref' not in text, path
    assert '40-character' in text, path
for path in (Path('.github/workflows/validation-compact.yml'), Path('.github/workflows/validation-grade.yml')):
    text = path.read_text(encoding='utf-8')
    assert text.count("--source-revision '${{ needs.resolve.outputs.sha }}'") >= 4, path
product = Path('.github/workflows/product-certification.yml').read_text(encoding='utf-8')
for role in ('audio-builder', 'audio-target', 'certification-archive'):
    assert f'--role {role}' in product, role
assert '--builder-readiness shipping-build/audio-builder-readiness.json' in product
assert '--target-readiness /tmp/audio-target-readiness.json' in product
print('immutable evidence entrypoint contracts: OK')
PY2

echo "architecture contracts: OK"
