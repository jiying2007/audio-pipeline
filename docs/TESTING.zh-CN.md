# 测试智能化与 HIL 策略

本文是 `audio-pipeline` 的正式测试路由、历史回归和真机验证规范。Hosted/QEMU 与真实产品板证据严格分层，不允许把未执行的 HIL 或认证包装成 PASS。

## Fast Gate 与 Full Gate

PR 先经过强制 Fast Gate，再展开高成本矩阵。Fast Gate 执行架构/硬切边界检查、Python assurance/validation 工具自测、Clang strict build、unit/contract/property tests，并在公开/runtime ABI 被影响时执行 v2 ABI gate。

纯文档变更可只执行 diff/impact 检查；未知路径、公开头文件、构建系统、workflow、测试基础设施或无法精确归类的核心源码一律保守扩展为 FULL。`main` push 无条件执行完整 Verify。

性能比较基线：PR 使用 `origin/main -> candidate`，main push 使用精确 `github.event.before -> HEAD`。最终 `summary` 是唯一 merge/release 聚合状态。

## v2 API/ABI 硬切门禁

2.0.0 首版不再对 1.x 做 additive compatibility。门禁要求当前 `ap_build_info()`、`ap_runtime_open()`、`ap_runtime_submit_frame()`、`ap_runtime_read_metrics()` 等 v2 symbol 存在，同时明确禁止被移除的 1.x runtime/build-info symbol、类型和兼容 shadow header 回流；Certification 当前只接受 schema v4。

`v2.0.0` immutable tag 发布后，后续 2.x ABI 检查自动以 v2.0.0 为正式同 major baseline，从而同时做到“旧兼容残留不回流”和“2.x 稳定 ABI”。

## 变更感知测试选择

`scripts/ci_impact.py` 维护 composition、Arm profile、alternate backend、performance、ALSA、ABI、sanitizer、QEMU、resource 与 validation/certification 的显式依赖。无法识别的输入直接回退 FULL，不允许为了节省 CI 猜测跳过。

## 可复现 CI 与资源单一真相源

ARM/QEMU/ALSA/static-analysis 等重任务使用 immutable digest 固定的 GHCR toolchain image。`ccache` 只保存编译对象；build 目录、测试结论、secret、认证记录和产品 evidence 不缓存。

Hosted resource 数字只维护在 `ci/resource-baseline.json`；`docs/generated/RESOURCE_BASELINE.md` 由它生成，Resource Gate 会重新测量并 diff 两者。

## Deterministic regression 与公共数据验证

PR/main 音频 regression 使用 generator **v3** 与 seeds `1307 / 2307 / 3307`。每个 seed 生成 **27 个 case**，必须 27/27 PASS，并对同 seed 重生成结果做 hash 级 deterministic 检查；因此 hosted generated regression 总计 81 case。

这 81 case 仅是 regression evidence。公共真实数据在独立 `audio-validation` runner 上按 Compact 100 / Full 160 profile 封存和执行，并可做 HMAC blind holdout。

### Extended Real 验证

v2.1.0 增加独立 Extended Real family，不修改 Compact100/Full160 历史基线。`commercial-core` 使用 RealMAN 真实远场/移动声源以及 BUT measured RIR、MUSAN、Mini LibriSpeech；`commercial-plus` 增加 VOiCES、AMI、ICSI。AISHELL-4、过滤后的 FSD50K、WHAM 只能进入 research/conditional 路径，不能满足 commercial gate。所有实际选择的 source file 在构建 corpus 前逐文件 SHA-256 绑定。

Extended Real 增加 P10 tail、clipping/DC/level、VAD precision/recall/FPR/FNR、speech/noise attenuation、scenario 样本数/通过率和维度覆盖；blind 按 scenario 分层。Release published 自动申请 commercial-core，每周申请 commercial-plus；只有 `EXTENDED_REAL_ENABLED=true` 才进入 self-hosted，否则 hosted availability 必须 fail-visible。详见 `EXTENDED_REAL_VALIDATION.zh-CN.md`。

Product Certification 仍是更高一级的真实发货硬件证据。

## 失败分类与可复现包

`scripts/ci_failure.py` 输出稳定机器分类，包括 build、ABI、unit、sanitizer、DSP quality、performance、resource、QEMU、HIL、XRUN、infra、evidence、security。

声学 validation 失败时，`scripts/validation_reproducer.py` 保存精确输入、case JSON、metrics/failure 数据和复现入口，避免依赖人工阅读长日志。

## Flaky 与历史成熟度

Nightly `flaky-sentinel` 重放确定性测试 100 次，不允许静默 retry 洗绿。历史趋势使用 robust median/MAD；`PASS/FAIL` 与 `WARMING_UP/MATURE` 分开。所有当前指标至少有 30 个可比成功样本后才能标为 `MATURE`。

## Metamorphic / Property Contracts

`tests/test_metamorphic.c` 验证 reset 后 deterministic replay、silence 稳定性和拓扑约束，并进入普通 CTest 和适用 sanitizer/build matrix。

## Trusted Runner Readiness

`tools/runner_preflight.py` 对 `audio-validation`、`audio-builder`、`audio-target`、`certification-archive` 提供 fail-closed readiness。**Trusted Runner Readiness** 针对 exact ref 执行；`READY` 只表示基础设施可用，不是 acoustic/HIL/performance/product PASS。

Compact/Full validation 和 HIL 仍会在真实 self-hosted job 内重复 preflight，防止陈旧 readiness 结果被误用。详见 `TRUSTED_RUNNERS.md`。

## HIL 板卡合同

真实产品板使用 `[self-hosted, linux, audio-target]`，并在板卡本地保存符合 `hil/board.schema.json` 的 `/etc/audio-pipeline/board.json`。它绑定 board/revision/SoC/codec/麦板/扬声器、thermal/power sensor、reset/cleanup hook 和默认 route。

`tools/hil_board.py preflight` 在测量前记录板卡身份、kernel/machine、磁盘、温度、CPU governor、NTP、ALSA inventory。实验室/环境故障归类为 `INFRA_FAILURE`；结束始终 cleanup，evidence 使用 SHA-256 封存。

## 分层 Soak 与故障注入

| Tier | 时长 | Fault profile | 用途 |
| --- | ---: | --- | --- |
| accelerated-pr | 10 分钟 | accelerated | 可信 PR/复现 |
| nightly-1h | 1 小时 | none | 产品 route 日常健康 |
| release-8h | 8 小时 | none | immutable Release 后 exact-SHA 验证 |
| weekly-24h | 24 小时 | none | 长时稳定性趋势 |
| certification-72h | 72 小时 | none | 当前 LOW shipping policy 正式最低 soak |

外部 PR 不自动进入 self-hosted 产品板。Scheduled/Release HIL 是 **fail-visible**：当策略要求执行但 `HIL_ENABLED!=true` 时，availability 直接失败，而不是静默 skip 或伪造 PASS。只有真实 target runner、板卡和 route 在线后才应打开该变量。

故障注入仅用于 accelerated 工程测试；正式 certification/nominal evidence 不注入人工 fault。

## Product Certification 拓扑

正式 shipping certification 使用：

`audio-builder -> audio-target -> certification-archive`

- builder 使用精确 shipping compiler/sysroot/toolchain/CFLAGS/CMake args；
- target 只部署并执行该构建产物，采集 real route benchmark/soak/thermal/power/acoustic evidence；
- build/deployed/executed SHA-256 必须一致，builder 与 DUT 必须分离；
- archive 返回 immutable `product-lifecycle` receipt；
- 当前 certification record **只接受 schema v4**。

正式 Cortex-A32 LOW shipping policy 要求最少 72 小时 soak；1 h / 8 h / 24 h HIL 只属于运营健康和发布历史，不能替代正式认证。

## 证据边界

Hosted x86、generated regression、cross-build、QEMU 只属于 software correctness/regression evidence，不能包装成 Cortex-A32 真机性能或产品声学认证。正式 `product-certified` 必须来自真实发货硬件、exact shipping toolchain/deployed binary、真实 route、声学 corpus/result、thermal/power、72 h policy soak、attestation 与 lifecycle archive evidence。
