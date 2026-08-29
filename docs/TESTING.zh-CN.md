# 测试智能化与 HIL 策略

本文是 `audio-pipeline` 的正式测试路由、历史回归和真机验证规范。Hosted/QEMU 与真实产品板证据严格分层，不允许把未执行的 HIL 或认证包装成 PASS。

## Fast Gate 与 Full Gate

PR 先经过强制 Fast Gate，再展开高成本矩阵。Fast Gate 执行架构边界检查、Python assurance/validation 工具自测、Clang strict build、unit/contract/property tests，并在公开/runtime ABI 被影响时执行 additive ABI gate。

纯文档变更可只执行 diff/impact 检查；未知路径、公开头文件、构建系统、workflow、测试基础设施或无法精确归类的核心源码一律保守扩展为 FULL。`main` push 无条件执行完整 Verify。

性能比较具有明确基线：

- PR：`origin/main -> candidate`；
- main push：精确 `github.event.before -> HEAD`。

最终 `summary` 是唯一 merge/release 聚合状态，同时验证应运行域全部成功、未选择域确实 skipped。

## 变更感知测试选择

`scripts/ci_impact.py` 维护显式依赖映射，可选择 AEC/NS/resampler/Activity/VAD composition、Arm cross profile、alternate backend、perf、ALSA、ABI、sanitizer、QEMU、resource 与 validation/certification 域。无法识别的输入直接回退 FULL，不允许为了节省 CI 猜测跳过。

## 可复现 CI 与资源单一真相源

ARM/QEMU/ALSA/static-analysis 等重任务使用按 immutable digest 固定的 GHCR toolchain image。`ccache` 只保存编译对象；build 目录、测试结论、secret、认证记录和产品 evidence 不缓存。

Hosted resource 数字不在文档中重复维护。机器真相源是 `ci/resource-baseline.json`，人类可读视图由 `docs/generated/RESOURCE_BASELINE.md` 生成；Resource Gate 会重新测量并 diff 两者，防止文档漂移。

## 失败分类与可复现包

`scripts/ci_failure.py` 输出稳定机器分类，包括 build、ABI、unit、sanitizer、DSP quality、performance、resource、QEMU、HIL、XRUN、infra、evidence、security。

声学 validation 失败时，`scripts/validation_reproducer.py` 保存 mic/render/clean 输入、case JSON、metrics/failure 数据与 `reproduce.sh`，避免依赖长日志人工还原。

## Deterministic regression、Flaky 与历史成熟度

PR 与 Nightly 都执行 deterministic regression seeds `1307/2307/3307`，每个 seed 必须 8/8 case、`pass_rate=1.0`。regression corpus manifest 当前 generator version 为 v2，并做字节级 deterministic regeneration 检查。

Nightly `flaky-sentinel` 将确定性测试套件重放 100 次，hard budget 为 2%，不允许通过静默 retry 洗绿。

Nightly `historical-trend` 使用 median/MAD 与相对变化阈值。`PASS/FAIL` 与统计成熟度分离：历史不足时可为 `PASS + WARMING_UP`，只有所有当前指标都至少拥有 30 个可比历史样本后才可标记 `MATURE`。因此短历史不能被描述为“成熟趋势门禁”。

## Metamorphic / Property Contracts

`tests/test_metamorphic.c` 验证 reset 后 deterministic replay、silence 稳定性、单麦/拓扑约束等不依赖 golden waveform 的不变量，并进入普通 CTest、sanitizer 及适用构建。

## HIL 板卡合同

真实产品板使用 `[self-hosted, linux, audio-target]` runner labels，并在板卡本地保存 `/etc/audio-pipeline/board.json`（或显式其它路径），格式遵循 `hil/board.schema.json`。manifest 绑定 board/revision/SoC/codec/麦板/扬声器版本、thermal/power sensor、可选 power-cycle/cleanup hook 和默认产品 audio route。

`tools/hil_board.py preflight` 在测量前记录板卡身份、kernel/machine、磁盘、温度、CPU governor、NTP、ALSA inventory。实验室/环境故障归类为 `INFRA_FAILURE`；测试结束始终 cleanup，最终 evidence 使用 SHA-256 封存。

## 分层 Soak 与故障注入

`.github/workflows/hil-soak.yml` 定义：

| Tier | 时长 | Fault profile | 用途 |
| --- | ---: | --- | --- |
| accelerated-pr | 10 分钟 | accelerated | 可信 PR/复现；route restart、render gap、CPU stall |
| nightly-1h | 1 小时 | none | 产品 route 日常健康 |
| release-8h | 8 小时 | none | 新 immutable Release 后 exact-SHA route 验证 |
| weekly-24h | 24 小时 | none | 长时稳定性趋势 |
| certification-72h | 72 小时 | none | 正式 shipping certification 最低 soak |

外部 PR 不自动进入 self-hosted 产品板；`accelerated-pr` 必须由维护者针对已 review SHA 手动触发。

Scheduled/Release HIL 是 **fail-visible** 的：当它们按策略应执行但 `HIL_ENABLED!=true` 时，availability gate 失败，而不是静默 skip 或伪造 PASS。只有真实 target runner、板卡与 route 已在线后才应设置 `HIL_ENABLED=true`。

Release 后 8 h HIL 仅由真正新建并确认 immutable 的 Release 显式 `repository_dispatch` 触发，并绑定该 Release 的 exact SHA；已有 Release 不会重复制造 HIL 历史。Scheduled HIL 固定到调度事件 SHA，避免排队期间 main 前进导致证据漂移。

故障注入仅用于 accelerated 测试；正式 certification/nominal performance evidence 不注入人工 fault。

## Product Certification 拓扑

正式 shipping certification 使用三段可信拓扑：

`audio-builder -> audio-target -> certification-archive`

- `audio-builder` 使用明确的 shipping compiler、sysroot、toolchain root、CFLAGS/CMake args 构建；
- `audio-target` 只部署并执行该构建产物，记录 real route benchmark/soak/thermal/power/acoustic evidence；
- build/deployed/executed binary SHA-256 必须一致，builder 与 DUT runner 必须分离；
- `certification-archive` 验证 bundle digest，并返回 immutable `product-lifecycle` archive receipt；
- certification record v4、deployment provenance、bundle 与 archive receipt 均进入 attestation/semantic validation。

正式 shipping policy `certification/policies/cortex-a32-low-shipping.json` 要求最少 72 小时 soak。1 h / 8 h / 24 h HIL 是运营健康与发布历史，不替代 72 h shipping certification。

## 证据边界

Hosted x86、cross-build、QEMU 只属于 software correctness/regression evidence，不能包装成 Cortex-A32 真机性能或产品声学认证。正式 `product-certified` 仍必须来自真实发货硬件、exact shipping toolchain、真实 audio route、声学 corpus/result、thermal/power 与 72 h soak evidence。
