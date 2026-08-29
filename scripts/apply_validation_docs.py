#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"marker not found in {path}: {old!r}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


cmake = Path("CMakeLists.txt")
text = cmake.read_text(encoding="utf-8")
text = text.replace("project(audio_pipeline VERSION 1.2.0 LANGUAGES C)",
                    "project(audio_pipeline VERSION 1.3.0 LANGUAGES C)", 1)
if "VERSION 1.3.0" not in text:
    raise SystemExit("failed to bump CMake project version")
cmake.write_text(text, encoding="utf-8")

changelog = Path("CHANGELOG.md")
text = changelog.read_text(encoding="utf-8")
section = """# 1.3.0

- Add a validation-grade self-validation layer with explicit `regression`, `validation-grade`, `validation-grade-blind`, and `product-certified` trust boundaries.
- Pin Microsoft AEC Challenge and DNS Challenge source revisions plus OpenSLR SLR28 metadata; require local SHA-256 sealing/checksum-index verification before public data can contribute to validation-grade evidence.
- Add deterministic multi-scenario regression corpus generation and a dependency-free evaluator for SI-SDR, SI-SDR improvement, AEC render-correlation reduction, ERLE, VAD F1, dynamic echo-path changes, and stream discontinuities.
- Add public AEC/DNS/SLR28 corpus adapters, HMAC blind holdout splitting with repository-external keys, hash-bound validation reports/evidence manifests, and a self-hosted `audio-validation` workflow.
- Extend `ap_process_pcm` with offline per-frame metrics JSONL and deterministic control-event injection without changing the core DSP ABI.
- Gate every PR/main on deterministic self-validation, run independent seeds nightly, and publish a clearly regression-only validation-smoke report alongside release SDK/source/SBOM artifacts.

"""
if not text.startswith("# 1.3.0\n"):
    text = section + text
changelog.write_text(text, encoding="utf-8")

english = """## Validation-grade self-validation

`validation/` is the formal acoustic evidence layer between unit tests and real target-board certification. It intentionally separates trust levels:

- `regression`: deterministic generated fixtures used by PR/main and Nightly CI; never presented as validation-grade evidence.
- `validation-grade`: pinned public real data plus locally sealed public-derived simulation. The current source lock pins Microsoft AEC Challenge, Microsoft DNS Challenge and OpenSLR SLR28 metadata without storing third-party corpora in Git.
- `validation-grade-blind`: the same sealed corpus HMAC-partitioned with a repository-external holdout key; release reports may suppress per-case blind metrics.
- `product-certified`: real shipping hardware/audio route plus performance, thermal, power and soak evidence under `certification/`.

The validation runner emits SI-SDR, SI-SDR improvement, AEC render-correlation reduction, ERLE and VAD F1 where references exist. Every report binds the exact dataset lock, corpus manifest, policy and source revision by SHA-256 and emits an evidence manifest.

```bash
python3 validation/tools/build_validation_corpus.py --output /tmp/ap-validation --seed 1307
cmake -S . -B build-validation -DCMAKE_BUILD_TYPE=Release -DAP_BUILD_BENCH=OFF
cmake --build build-validation --target ap_process_pcm --parallel
python3 validation/tools/run_validation.py \\
  --corpus /tmp/ap-validation/corpus.json \\
  --policy validation/policies/validation-smoke.json \\
  --dataset-lock validation/datasets.lock.json \\
  --processor build-validation/ap_process_pcm \\
  --output /tmp/ap-validation/report.json --enforce
```

Large public corpora remain outside the repository. `Validation Grade` runs only on a self-hosted `audio-validation` runner after dataset revision/checksum/seal verification. See `validation/README.md`.

"""
replace_once("README.md", "## Hardware timestamps, discontinuities and route changes\n", english + "## Hardware timestamps, discontinuities and route changes\n")

chinese = """## 验证级自验证

`validation/` 是 unit/regression test 与真实产品板认证之间的正式声学证据层，并强制区分可信等级：

- `regression`：PR/main 和 Nightly 使用的确定性自生成 fixture，**不得**包装成验证级证据。
- `validation-grade`：锁定 revision 的公共真实数据 + 已本地封存的公共数据派生仿真。当前锁定 Microsoft AEC Challenge、Microsoft DNS Challenge、OpenSLR SLR28；第三方大数据不进入 Git。
- `validation-grade-blind`：使用仓库外 HMAC key 对同一封存 corpus 做 blind holdout，发布报告可隐藏逐 case blind 指标。
- `product-certified`：仍必须使用真实发货硬件/音频 route，加 CPU、时延、thermal、power、soak 等 `certification/` 证据。

验证 runner 在存在 reference 时计算 SI-SDR、SI-SDR improvement、AEC render-correlation reduction、ERLE、VAD F1；每份报告都会用 SHA-256 绑定 dataset lock、corpus manifest、policy 和 source revision，并生成 evidence manifest。

```bash
python3 validation/tools/build_validation_corpus.py --output /tmp/ap-validation --seed 1307
cmake -S . -B build-validation -DCMAKE_BUILD_TYPE=Release -DAP_BUILD_BENCH=OFF
cmake --build build-validation --target ap_process_pcm --parallel
python3 validation/tools/run_validation.py \\
  --corpus /tmp/ap-validation/corpus.json \\
  --policy validation/policies/validation-smoke.json \\
  --dataset-lock validation/datasets.lock.json \\
  --processor build-validation/ap_process_pcm \\
  --output /tmp/ap-validation/report.json --enforce
```

大规模公共 corpus 始终保存在仓库外；`Validation Grade` 只在带 `audio-validation` 标签的 self-hosted runner 上运行，并先验证 revision/checksum/local seal。详见 `validation/README.md`。

"""
replace_once("README.zh-CN.md", "## 时间戳、断流与回声路径变化\n", chinese + "## 时间戳、断流与回声路径变化\n")

third = Path("THIRD_PARTY.md")
text = third.read_text(encoding="utf-8")
notice = """

## External validation datasets

`validation/datasets.lock.json` references Microsoft AEC Challenge, Microsoft DNS Challenge and OpenSLR SLR28 for optional offline validation. Their audio is not vendored, redistributed, sublicensed or installed by this repository. Dataset users are responsible for reviewing and complying with the original upstream dataset terms. The repository only stores source revisions, source URLs, integrity policy and validation adapters.
"""
if "## External validation datasets" not in text:
    text = text.rstrip() + notice + "\n"
third.write_text(text, encoding="utf-8")

Path("scripts/apply_validation_docs.py").unlink()
