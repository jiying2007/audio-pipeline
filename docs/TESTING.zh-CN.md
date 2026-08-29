# 测试智能化与 HIL 策略

本文是 `audio-pipeline` 的正式测试路由和真机验证规范。

## Fast Gate 与 Full Gate

PR 先经过强制 Fast Gate，再展开高成本矩阵。Fast Gate 执行架构边界检查、Python 测试工具自测、Clang strict build、unit/contract/property tests，以及在公开/runtime ABI 被影响时执行 additive ABI gate。

纯文档变更只执行 diff/impact 检查，不编译 DSP。任何未知路径、公开头文件、构建系统、workflow、测试基础设施或无法精确归类的核心源码都会保守回退到 FULL。`main` push 无条件强制完整 Verify，impact analyzer 只用于优化 PR 成本，不能削弱发布门禁。

Full Gate 的诊断矩阵保持 `fail-fast: false`，避免一个失败遮蔽其它架构/组合问题；最终 `summary` 是统一 merge/release 状态，既验证应该运行的域全部成功，也验证未选择的域确实是 skipped。

## 变更感知测试选择

`scripts/ci_impact.py` 维护显式依赖映射，可动态选择：

- AEC、NS、resampler、Activity/VAD 对应 composition；
- DSP/runtime 对应 Arm cross profiles；
- NLMS/MCRA alternate backend；
- perf、ALSA、ABI、sanitizer、QEMU、resource gates；
- validation/certification 相关声学验证。

无法识别的输入直接扩展到 FULL，不允许“为了省 CI 而猜测跳过”。

## 可复现 CI 工具链

ARM/QEMU/ALSA/static-analysis 等重任务统一使用 GHCR toolchain image，并按 immutable digest 固定。镜像包含 GCC/Clang、CMake/Ninja、ccache、ARM/AArch64 cross compiler 与 cross libc headers、QEMU、ALSA、gcovr、scan-build 等。

`.github/workflows/ci-toolchain-image.yml` 是永久镜像重建入口：先 build + smoke，再发布 SHA tag 与 `ci-latest`，输出新的 digest；普通 workflow 只接受经过 review 后写入仓库的 digest，不使用 mutable tag。

`ccache` 通过 GitHub cache 保存编译对象，key 绑定 runner OS、compiler/target namespace 与 CMake/header hash。build 目录、测试结果、secret、认证记录和产品 evidence 不进入 cache。

## 失败分类与可复现包

`scripts/ci_failure.py` 输出稳定机器分类，包括 build、ABI、unit、sanitizer、DSP quality、performance、resource、QEMU、HIL、XRUN、infra、evidence、security 等。

声学 validation 会先写 report 再 enforce。失败时 `scripts/validation_reproducer.py` 自动保存对应 mic/render/clean 输入、case JSON、metrics/failure 数据和 `reproduce.sh`，不依赖长日志人工还原。

## Flaky 与历史回归

Nightly `flaky-sentinel` 只构建一次，然后把确定性测试套件重放 100 次；出现“有时成功、有时失败”记为 `FLAKY_SUSPECT`，当前 hard budget 为 2%，不会通过静默 retry 把红灯洗成绿灯。

Nightly `historical-trend` 保存与 revision 绑定的 benchmark/validation 点。`scripts/test_history.py` 使用 median/MAD robust statistics 加相对变化阈值比较最近成功 main 历史，用于发现单次仍未越过绝对门槛、但长期持续恶化的 CPU/时延/声学趋势。

## Metamorphic / Property Contracts

`tests/test_metamorphic.c` 验证不依赖 golden waveform 的不变量，包括 reset 后 deterministic replay、silence 稳定性、单麦/拓扑约束等。它进入普通 CTest，因此会同时覆盖 Fast Gate、sanitizer 及其它适用构建。

## HIL 板卡合同

真实产品板统一使用 `[self-hosted, linux, audio-target]` runner labels，并在板卡本地保存 `/etc/audio-pipeline/board.json`（或显式指定其它路径），格式遵循 `hil/board.schema.json`。manifest 绑定稳定 board/revision/SoC/codec/麦板/扬声器版本、thermal/power sensor、可选 power-cycle/cleanup hook 和默认产品音频 route。

`tools/hil_board.py preflight` 在 DSP 测量前记录板卡身份、kernel/machine、磁盘、温度、CPU governor、NTP、ALSA inventory。实验室/环境故障统一归为 `INFRA_FAILURE`，不污染产品回归统计；测试结束始终 cleanup，最终 evidence 使用 SHA-256 封存。

## 分层 Soak 与故障注入

`.github/workflows/hil-soak.yml` 定义：

| Tier | 时长 | Fault profile | 用途 |
| --- | ---: | --- | --- |
| accelerated-pr | 10 分钟 | accelerated | 可信 PR/复现；route restart、render gap、CPU stall |
| nightly-1h | 1 小时 | none | 产品 route 日常健康 |
| release-8h | 8 小时 | none | 发布后 exact-SHA 产品 route 验证 |
| weekly-24h | 24 小时 | none | 长时稳定性趋势 |
| certification-72h | 72 小时 | none | 扩展 SKU/发布证据 |

仓库是 public，因此外部 PR **不会**自动进入 self-hosted 产品板；`accelerated-pr` 必须由维护者对已 review 的 SHA 手动触发。

Nightly/Weekly 以及 Release 后 HIL 由仓库变量 `HIL_ENABLED=true` 显式打开。未设置或为 false 时自动 skip，不会因为当前没有真实板卡而长期排队或制造假失败。board farm 上线后，每个 runner 直接读取自己的 local manifest；增加新板不需要复制 workflow。

故障注入仅用于 accelerated 测试；正式 certification/nominal performance evidence 不注入人工 fault。

## 证据边界

Hosted x86、cross-build、QEMU 只属于 software correctness/regression evidence，不能包装成 Cortex-A32 真机性能或产品声学认证。正式 `product-certified` 仍必须来自真实发货硬件、shipping compiler/sysroot、真实 audio route、声学 corpus/result、thermal/power 以及要求的 soak evidence。
