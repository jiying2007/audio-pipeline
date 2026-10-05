# FE01 libfvad reference / 首个实际外部 VAD 基准

This is reference integration and D0 adapter qualification, not a shipping VAD replacement.
The approved plan and historical research remain immutable. Full work stays in #657.

## Source and execution admission

The minimal libfvad core is pinned to `532ab666c20d3cfda38bca63abbb0f152706c369`.
`libfvad-source-lock.json` records 24 exact upstream Git blobs: C/header inputs plus
LICENSE, PATENTS and AUTHORS. Source preflight verifies each actual byte sequence
before copying ONLY those files into a fresh build directory. Upstream build scripts,
examples, models and audio data are not executed or copied into the build.

`libfvad-admission.json` retains the independently downloaded preflight receipt and
actual SHA256 manifest. Its digest and the materialized-source manifest digest are
bound by `sources.json`. Every run rechecks both admission and source bytes. The
source receipt's `SOURCE_BYTES_VERIFIED_NOT_EXECUTED` is its pre-execution snapshot,
not the final experiment status. No source/model/data rights for other references
are inferred from this one admission. This is a scoped engineering review, not a
blanket legal determination.

The external source is fetched in the existing Quality job at a full commit and is
compiled by an explicit first-party source list, with inherited credential/preload
variables excluded. Neither upstream source nor binaries become a shipping library
or a new repository-vendored implementation. Research evidence retains upstream
notices with the separately built source/binary files. A pinned source and sanitized
environment are provenance controls, not a general network/process sandbox.

## Frozen comparison and metric boundary

The machine experiment contract is `libfvad-reference-v1.json`. It was preregistered
in #658 before VAD mode scores were inspected.

- B0 is `37a1792861a89c815bec462f819f3deac7d29b09`; its entire unpacked source tree
  must recompute to `5ce9b907c9e915284a4c99da3f20b81e9df9ef3e` before compilation.
- Both arms receive identical raw mono S16LE at 16 kHz, 160 samples per call.
  B0 uses `vad-isolated`, not the full NS-assisted production chain. Neither arm
  silently adds HPF, NS, AGC, normalisation, resampling or tail padding.
- The first-party C adapter emits exactly one binary decision per complete frame,
  copies PCM unchanged, rejects empty/partial inputs and existing output paths,
  and reapplies the frozen rate/mode after upstream reset.
- Decisions are available only after the entire 10 ms frame. Prefix checks compare
  complete frames; no sample-level zero-lookahead claim is made.
- Five fixed canonical cases are used. `clean-capture` is omitted because it
  duplicates the clean near-end input. Calibration replay uses seed 1307 and modes
  0/1/2/3. Select minimum FPR among modes whose pooled recall is at least B0 recall;
  break ties by lower mode. No tolerance or unmatched-recall fallback exists.
- Freeze selection before executing seeds 2307/3307. Only B0 and the selected mode
  are executed there. A missing recall match retains B0-only evaluation and an
  explicit `NO_RECALL_MATCH_NO_SELECTION` decision.

The canonical generator and `run_validation_engine.vad_stats` remain authoritative.
The adapter checks exact input/label/trace/output cardinality before the existing
metric (which otherwise uses the shorter trace). It never changes that metric or
an existing acoustic acceptance threshold. This is a **recall-floor constrained**
comparison of discrete modes, not exact equal-recall matching.

All inputs are **D0 historical synthetic regression replay**. Calibration replay
is not an independent public-development experiment; evaluation seeds are not an
independent speaker/room/source holdout or blind set. A higher F1 does not authorize
promotion, especially when false positives increase. Frame FPR is not KWS FAR/hour.
No CPU, target latency or four-microphone support is inferred.

## Reproducible execution and evidence

The existing `quality.yml` / `frontend-reference` job builds the reference, runs
native and ASan/UBSan adapter/reset/negative/prefix checks, executes the paired
comparison, independently recomputes the retained metrics, and verifies semantic
negative cases even after their checksum envelopes are regenerated. It uses the
pinned project CI image. Evidence and failures are uploaded under
`frontend-reference-<run-id>`; unsuccessful execution does not produce valid PASS
evidence. No standalone/scheduled workflow or second evaluator was introduced.

A local reproduction accepts an unpacked B0 Git archive and pinned libfvad checkout:

```sh
python3 tests/validation/frontend_evolution/test_libfvad_reference.py
python3 tests/validation/frontend_evolution/libfvad_reference.py compare \
  --source /path/to/libfvad --baseline /path/to/unpacked-b0 --output /path/to/new-output
python3 tests/validation/frontend_evolution/libfvad_reference.py verify \
  --output /path/to/new-output
python3 tests/validation/frontend_evolution/test_libfvad_reference.py \
  --evidence /path/to/new-output
```

The baseline directory must contain only the exact archived tree (no `.git`, build
outputs or byte changes). Output must not already exist. CI additionally binds the
actual checkout SHA with `--execution-source`; local reproductions without that
argument are explicitly marked uncommitted, with effective control-file hashes.

Retained evidence contains source/notice hashes, first-party control hashes,
compiler/build configuration, actual binaries, selected input/label files, every
frame trace, transparent output bytes, per-case identity receipts, frozen selection,
aggregate metrics, manifest and checksums. `verify` checks the exact file set,
upstream and binary identities, strict trace counts, per-case receipts, recomputed
canonical metrics, calibration selection and evaluation arm/case sets. Retained
binaries are reference programs, not an SSC305 SDK or authenticated target build.

## 中文进度与后续

本轮已从来源清单推进到实际源码准入、编译、适配与配对执行。原版库与第一方
适配器分别记录身份；只接入最小 core，保留 LICENSE/PATENTS/AUTHORS。B0 是固定
旧版本的 VAD-isolated，同一原始输入，不代表整条生产 NS/VAD 链的表现。

数据仍是旧的合成回归，因此无论分数多高都保持 REFERENCE_ONLY，不替换默认 VAD。
离散 mode 只能满足召回下限，不能宣称精确同召回优势。真实语音开发集、跨说话人/
房间验证、事件误报、起音释放和固定 KWS/ASR 下游测试仍需后续独立完成。

FE00/FE01 继续推进其他来源与适配器；FE02–FE09 未因这个基准完成而自动关闭。
原生四麦、BF/DOA、其他算法效果和板端资源资格仍各自需要实际实现与证据。
