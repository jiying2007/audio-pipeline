#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding='utf-8')
    if old not in text:
        raise SystemExit(f'anchor not found in {path}: {old[:80]!r}')
    if text.count(old) != 1:
        raise SystemExit(f'anchor not unique in {path}')
    p.write_text(text.replace(old, new), encoding='utf-8')


replace_once(
    'README.md',
    'Pinned public sources include Microsoft AEC Challenge, Microsoft DNS Challenge and OpenSLR SLR28 metadata. Public corpora remain outside Git.\n\nLarge public validation runs only on a trusted `audio-validation` runner after readiness and dataset-seal verification. See [`validation/README.md`](validation/README.md) and [`docs/TRUSTED_RUNNERS.md`](docs/TRUSTED_RUNNERS.md).',
    'Pinned Compact/Full sources include Microsoft AEC Challenge, Microsoft DNS Challenge and OpenSLR SLR28 metadata. v2.1.0 adds a separate **Extended Real** family with license-isolated RealMAN, BUT ReverbDB, MUSAN, Mini LibriSpeech and optional VOiCES/AMI/ICSI plus research-only AISHELL-4/FSD50K/WHAM. Public corpora remain outside Git.\n\nExtended Real adds real far-field/moving-source, measured-room, meeting/overlap and hard-negative stress with per-file SHA-256 provenance, scenario-stratified blind holdout, tail metrics, clipping/DC/VAD error gates and scenario/dimension coverage. It is still public validation, never product certification.\n\nLarge public validation runs only on a trusted `audio-validation` runner after readiness and dataset verification. See [`validation/README.md`](validation/README.md), [`docs/EXTENDED_REAL_VALIDATION.md`](docs/EXTENDED_REAL_VALIDATION.md) and [`docs/TRUSTED_RUNNERS.md`](docs/TRUSTED_RUNNERS.md).'
)
replace_once(
    'README.md',
    '- [`docs/TRUSTED_RUNNERS.md`](docs/TRUSTED_RUNNERS.md) — self-hosted runner readiness\n',
    '- [`docs/TRUSTED_RUNNERS.md`](docs/TRUSTED_RUNNERS.md) — self-hosted runner readiness\n- [`docs/EXTENDED_REAL_VALIDATION.md`](docs/EXTENDED_REAL_VALIDATION.md) — real/public far-field, measured-room, meeting and hard-negative validation\n'
)
replace_once(
    'README.zh-CN.md',
    '公共数据源锁定 Microsoft AEC Challenge、Microsoft DNS Challenge 和 OpenSLR SLR28 元数据，大型 corpus 不进入 Git。\n\n大规模公共验证只在可信 `audio-validation` runner 上执行，并先通过 readiness 和 dataset seal。详见 [`validation/README.md`](validation/README.md) 与 [`docs/TRUSTED_RUNNERS.md`](docs/TRUSTED_RUNNERS.md)。',
    'Compact/Full 继续固定 Microsoft AEC Challenge、Microsoft DNS Challenge 和 OpenSLR SLR28。v2.1.0 新增独立 **Extended Real**：商业验证层使用 RealMAN、BUT ReverbDB、MUSAN、Mini LibriSpeech，并可扩展 VOiCES/AMI/ICSI；AISHELL-4/FSD50K/WHAM 被隔离到 research。大型 corpus 不进入 Git。\n\nExtended Real 增加真实 far-field/moving source、实测房间、meeting/overlap、hard-negative、逐文件 SHA-256、scenario 分层 blind、tail metric、clipping/DC/VAD error 和 scenario/dimension gate，但仍不具备 product certification 权限。\n\n大规模公共验证只在可信 `audio-validation` runner 上执行，并先通过 readiness 和 dataset verify。详见 [`validation/README.md`](validation/README.md)、[`docs/EXTENDED_REAL_VALIDATION.zh-CN.md`](docs/EXTENDED_REAL_VALIDATION.zh-CN.md) 与 [`docs/TRUSTED_RUNNERS.md`](docs/TRUSTED_RUNNERS.md)。'
)
replace_once(
    'README.zh-CN.md',
    '- [`docs/TRUSTED_RUNNERS.md`](docs/TRUSTED_RUNNERS.md) — self-hosted runner readiness\n',
    '- [`docs/TRUSTED_RUNNERS.md`](docs/TRUSTED_RUNNERS.md) — self-hosted runner readiness\n- [`docs/EXTENDED_REAL_VALIDATION.zh-CN.md`](docs/EXTENDED_REAL_VALIDATION.zh-CN.md) — 真实远场/房间/会议/环境负例验证\n'
)
replace_once(
    'docs/TESTING.md',
    'This 81-case generated suite is regression evidence only. Public validation remains separately materialized/sealed on trusted `audio-validation` runners using Compact 100 / Full 160 profiles and optional HMAC blind holdout. Product certification remains a still higher trust tier.',
    'This 81-case generated suite is regression evidence only. Public validation remains separately materialized/sealed on trusted `audio-validation` runners using Compact 100 / Full 160 profiles and optional HMAC blind holdout.\n\n### Extended Real validation\n\nv2.1.0 adds an independent Extended Real family; it does not mutate Compact100/Full160. `commercial-core` covers RealMAN real far-field/moving sources plus measured BUT RIR, MUSAN and Mini LibriSpeech combinations. `commercial-plus` adds VOiCES, AMI and ICSI. AISHELL-4, filtered FSD50K and WHAM are research-only/conditional and cannot satisfy commercial gates. Selected source files are SHA-256 bound before corpus construction.\n\nExtended Real adds p10 tail metrics, clipping/DC/level gates, VAD precision/recall/FPR/FNR, speech/noise attenuation, per-scenario sample/pass-rate requirements and dimension coverage. Blind holdout is scenario-stratified. Published releases automatically request commercial-core and the weekly schedule requests commercial-plus only after `EXTENDED_REAL_ENABLED=true`; otherwise automation fails visibly before allocating a self-hosted runner. See `EXTENDED_REAL_VALIDATION.md`.\n\nProduct certification remains a still higher trust tier.'
)
replace_once(
    'docs/TESTING.zh-CN.md',
    '这 81 case 仅是 regression evidence。公共真实数据在独立 `audio-validation` runner 上按 Compact 100 / Full 160 profile 封存和执行，并可做 HMAC blind holdout；Product Certification 仍是更高一级的真实发货硬件证据。',
    '这 81 case 仅是 regression evidence。公共真实数据在独立 `audio-validation` runner 上按 Compact 100 / Full 160 profile 封存和执行，并可做 HMAC blind holdout。\n\n### Extended Real 验证\n\nv2.1.0 增加独立 Extended Real family，不修改 Compact100/Full160 历史基线。`commercial-core` 使用 RealMAN 真实远场/移动声源以及 BUT measured RIR、MUSAN、Mini LibriSpeech；`commercial-plus` 增加 VOiCES、AMI、ICSI。AISHELL-4、过滤后的 FSD50K、WHAM 只能进入 research/conditional 路径，不能满足 commercial gate。所有实际选择的 source file 在构建 corpus 前逐文件 SHA-256 绑定。\n\nExtended Real 增加 P10 tail、clipping/DC/level、VAD precision/recall/FPR/FNR、speech/noise attenuation、scenario 样本数/通过率和维度覆盖；blind 按 scenario 分层。Release published 自动申请 commercial-core，每周申请 commercial-plus；只有 `EXTENDED_REAL_ENABLED=true` 才进入 self-hosted，否则 hosted availability 必须 fail-visible。详见 `EXTENDED_REAL_VALIDATION.zh-CN.md`。\n\nProduct Certification 仍是更高一级的真实发货硬件证据。'
)
replace_once(
    'docs/TRUSTED_RUNNERS.md',
    '| public validation | `self-hosted, linux, audio-validation` | Python/CMake/C compiler/Git/Git LFS, sealed cache paths | Compact/Full public-data validation |',
    '| public validation | `self-hosted, linux, audio-validation` | Python/CMake/C compiler/Git/Git LFS; either Compact/Full seal or Extended Real catalog/cache | Compact/Full/Extended Real public-data validation |'
)
replace_once(
    'docs/TRUSTED_RUNNERS.md',
    '9. Run Full blind holdout.\n\nDo not enable product/hardware claims from public validation results.',
    '9. Run Full blind holdout.\n10. Materialize the Extended Real `commercial-core` cache, rerun readiness with `--extended-catalog`, then run Extended Real visible + scenario-stratified blind.\n11. Materialize VOiCES/AMI/ICSI and run `commercial-plus`.\n12. Only after the isolated runner/cache is repeatedly healthy set `EXTENDED_REAL_ENABLED=true`; release automation then dispatches core and the weekly schedule dispatches plus.\n\nDo not enable product/hardware claims from public validation results.'
)
replace_once(
    'validation/README.md',
    'The full workflow uses the fixed `validation/policies/validation-full.json`; callers cannot replace it with a weaker policy through workflow inputs.',
    'The full workflow uses the fixed `validation/policies/validation-full.json`; callers cannot replace it with a weaker policy through workflow inputs.\n\n## Extended Real validation\n\nCompact100/Full160 remain frozen historical comparison families. v2.1.0 adds a separate Extended Real catalog and workflow for real far-field/moving-source, measured-room, meeting/overlap and hard-negative stress. Commercial profiles are license-isolated; research-only/conditional sources cannot enter commercial validation. Selected real files are individually SHA-256 bound in a source manifest and verified again before corpus construction.\n\nExtended Real uses scenario-stratified blind holdout plus tail/scenario/dimension gates and remains non-authoritative for shipping. See [`../docs/EXTENDED_REAL_VALIDATION.md`](../docs/EXTENDED_REAL_VALIDATION.md).'
)
# Append runner operations section.
p = Path('validation/RUNNER.md')
text = p.read_text(encoding='utf-8')
if '## Extended Real profile' not in text:
    text += '''\n\n## Extended Real profile\n\nExtended Real uses a separate root, normally `/opt/audio-validation-extended`, and `validation/extended.datasets.lock.json`. It requires `ffmpeg` in addition to the normal audio-validation toolchain. Do not pass the Compact/Full seal at the same time as `--extended-catalog`; runner readiness requires exactly one dataset contract.\n\n```bash\npython3 tools/runner_preflight.py \\\n  --source-revision <40-hex-commit-sha> \\\n  --role audio-validation \\\n  --data-root /opt/audio-validation-extended \\\n  --extended-catalog "$PWD/validation/extended.datasets.lock.json" \\\n  --require-command ffmpeg \\\n  --output /tmp/extended-real-readiness.json\n```\n\nAfter materializing the profile directories, use `prepare_extended_validation.py scan` to create the per-file SHA-256 source manifest, then `verify` it before corpus construction. See `../docs/EXTENDED_REAL_VALIDATION.md`. Release/week automation is intentionally disabled until repository variable `EXTENDED_REAL_ENABLED=true`.\n'''
    p.write_text(text, encoding='utf-8')

# Extend the architecture contract after the existing extended-real Python block.
p = Path('scripts/check-architecture.sh')
text = p.read_text(encoding='utf-8')
marker = "print('extended-real validation contracts: OK')\nPY\n"
addition = r'''print('extended-real validation contracts: OK')
PY
python3 - <<'PY_AUTO'
from pathlib import Path
canonical = Path('.github/workflows/validation-extended-real.yml').read_text(encoding='utf-8')
auto = Path('.github/workflows/extended-real-automation.yml').read_text(encoding='utf-8')
for token in ('source_sha:', 'commercial-core', 'commercial-plus', '--stratify scenario', '--source-manifest extended-out/source-manifest.json'):
    assert token in canonical, token
assert "options: [commercial-core, commercial-plus, research]" in canonical
assert "release:" in auto and "schedule:" in auto
assert 'EXTENDED_REAL_ENABLED' in auto
assert 'EXTENDED_REAL_REQUIRED_BUT_DISABLED' in auto
assert 'gh workflow run validation-extended-real.yml' in auto
assert '-f "source_sha=$SOURCE_SHA"' in auto
assert 'profile=commercial-core' in auto and 'profile=commercial-plus' in auto
assert 'research' not in auto, 'research profile must never be automated'
print('extended-real automation contracts: OK')
PY_AUTO
'''
if 'extended-real automation contracts: OK' not in text:
    if marker not in text:
        raise SystemExit('architecture extended-real marker not found')
    text = text.replace(marker, addition, 1)
    p.write_text(text, encoding='utf-8')

replace_once(
    'CHANGELOG.md',
    '- Keep extended-real validation non-authoritative for product shipping: real DUT HIL, product acoustic/thermal/power evidence and 72 h certification remain separate mandatory gates.',
    '- Automate exact-SHA Extended Real commercial-core validation on published releases and commercial-plus weekly through one canonical workflow; automation remains fail-visible until `EXTENDED_REAL_ENABLED=true`.\n- Keep extended-real validation non-authoritative for product shipping: real DUT HIL, product acoustic/thermal/power evidence and 72 h certification remain separate mandatory gates.'
)
print('extended-real docs/architecture migration: OK')
