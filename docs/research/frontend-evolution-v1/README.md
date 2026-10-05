# Frontend Evolution v1 / 双麦与四麦开放研究

## Authority and immutable proposal

The user approved this new stage on 2026-10-05 and authorized implementation. This is an explicit new integration/research requirement under the root agent contract, not permission to rewrite the completed software/public-data program. Research may change algorithm structures, run bounded preregistered searches, train/finetune models, prototype 1/2/4-mic processing, and evaluate streaming/quantization/SIMD. It does not automatically change shipping defaults, API/ABI, third-party rights, holdout roles or Product Certification authority.

- [Complete approved Chinese plan](PLAN.zh-CN.md): original bytes, not a rolling progress report.
- [Original task dependencies](TASKS.json): preserves `PLAN_ONLY_NOT_EXECUTED` as the proposal's historical state.
- [Original checksums](SHA256SUMS): enforced by executable tests. Amendments require a new reviewed document, not rewriting the proposal.
- Live work and evidence: GitHub issue #657; initial foundation PR #656. Neither an unchecked task nor a passing contract is an acoustic result.
- B0 software baseline: `37a1792861a89c815bec462f819f3deac7d29b09` / v2.3.55.
- E001 physical qualification remains `v2.3.16 / 57e4c64adc1cf06819e46e24e275ecd746d5f17f`; no implicit migration.

## First implementation tranche

FE00/FE01 are **in progress**, not fully qualified. The following foundations are implemented under `tests/validation/frontend_evolution/` and use only Python's standard library:

1. Exact-byte archive and dependency validation, including duplicate/non-finite JSON rejection.
2. A source inventory separating code, dependencies, weights, data and redistribution dispositions. Pinned or review-only references cannot silently become executable. Admission requires explicit review and materialized-source digests; a later runner must verify the actual receipt/bytes before execution. Metadata validation itself is not that runner or a legal determination.
3. Explicit S16LE/normalized Float32LE, interleaved 1/2/4-mic **research input contracts** with render channels counted separately. The current shipping SDK remains single/dual microphone. Planar conversion, channel remapping and resampling must be explicit adapter operations, not hidden inside this primitive.
4. Bounded 10 ms to native-hop reblocking. Native 128/384-sample hops remain their real durations. Output is emitted as soon as a native hop is available; no LCM-period wait, normalization or silent tail padding. Partial final hops fail until the adapter declares an explicit tail policy.
5. Per-case output receipts: exact expected case set, explicit success plus integer zero exit status, source/config/processor/evaluator/input/output hashes, exact mono sample count, safe paths, finite normalized floats, and a predeclared nonzero requirement where appropriate. An `OUTPUT_CONTRACT_PASS` is not a quality score.
6. Finite common-prefix/different-future causality checks with preregistered latency/lookahead. This catches hidden future dependence in tested cases, not every possible input. Never tune latency per case to improve a score.

These are offline Python research tools, not allocation-free DSP or a runtime sandbox. They neither execute nor download upstream code. Actual external adapters, model/data admission, baseline comparisons, array DSP and independent effect studies remain to be implemented. Acoustic metrics continue to use `validation/tools` and `validation/authority.json`; do not build a second evaluator here.

## Reference inventory

Machine inventory: `.github/research/frontend-evolution-v1/sources.json`. The initial list includes 26 reference/data/variant entries. Athena and libfvad commits were resolved live; the approved aispeech-earbuds commit is retained as review-only. Other entries remain explicitly unpinned/PLANNED, not falsely frozen. H-GTCRN noisy/IVA remain distinct entries. No external entry has been admitted for execution in this tranche.

Review code, dependency, model and dataset rights independently. Unknown rights on one resource do not block first-party prototypes or other reviewed references. No upstream source, coefficients, weights or binaries were copied by this change.

## Verify locally

```sh
(cd docs/research/frontend-evolution-v1 && sha256sum -c SHA256SUMS)
python3 tests/validation/frontend_evolution/test_contracts.py
```

The existing `.github/scripts/verify-docs-gate.sh` executes these tests for docs and full Verify paths, so the required aggregate summary includes this foundation without introducing another one-shot or scheduled workflow. Full-main verification and the existing release identity gates remain unchanged. Passing tests do not mean FE00-FE09 are complete.

## 接续顺序与中文边界

完整方案已归档；新研究允许结构改进、有限参数实验和训练，不继承旧阶段的 candidate-zero 限制。旧研究结论、失败与归档保持不变。后续进度只更新 #657 和新的实验记录，不把原方案改成虚假的执行证据。

当前已经实现授权/来源登记、帧契约、有界重组、逐例输出检查和有限因果负例。尚未完成上游最小适配器、实际效果对照、原生四麦 DSP、NN 流式/量化和端侧候选资格。四麦输入契约测试不等于 C SDK 已支持线性或环形四麦；25 项基础测试不等于 25 项音质实验。

下一步先完成首批来源/依赖审查及 B0、WebRTC、SpeexDSP、libfvad、Athena 的最小可复现对照，再推进 FE02/03 的几何、分数延时和固定滤波。经典增强与神经研究各自复用同一评估入口。最多三个研究通道，不新增大量一次性工作流，不用独立验证或 blind 数据调参。改 shipping 默认或公共 ABI 时另行执行版本与资格门禁。

## First executed external reference

See [libfvad reference qualification](LIBFVAD_REFERENCE.md) for the first actual
source-byte admission, C adapter, frozen D0 paired VAD replay and evidence checks.
Only the minimal libfvad core is admitted in the catalog; other entries retain
their prior pending/review-only status. FE00/FE01 and the full #657 program remain
in progress. The initial-tranche description above is historical, not a claim
that no later reference can be admitted. No shipping VAD default is changed.

## Native array research prototype

[Native 1/2/4-mic geometry and fractional-delay BF](ARRAY_NATIVE.md) is the next
FE02/03 executable tranche. It processes actual multichannel PCM in C and checks
analytic answers on native/sanitized and AArch32/QEMU builds. It is not installed
in the 2.x SDK. DOA, smooth live steering, BF/AEC integration, independent speech
quality and the final C4 delivery remain open in #657; no new product claim is
inferred from the engineering checks.

## Controlled live steering continuation

[FE03 controlled steering](ARRAY_STEERING.md) extends the same native research
core with a shared-history two-bank crossfade and a small timestamp/confidence
controller. The existing array qualification retains static tests and adds
transition known answers. This is not recorded-speech or AEC quality validation,
automatic DOA, a C4 SDK, or completion of the full research program.

## Recorded-speech spatial diagnostics

[FE03 recorded-speech probe](SPEECH_SPATIAL.md) admits fixed LibriSpeech bytes and
runs the unchanged native BF against actual speech in explicitly synthetic
free-field scenes. Reference/mean/linear/cubic arms, speaker roles and source
selection are fixed before scores. Component transfer and canonical SI-SDR are
reported together, with co-located negative controls and no automatic promotion.
This is not a room recording, DOA/AEC test, installed C4 SDK or full FE closure.
