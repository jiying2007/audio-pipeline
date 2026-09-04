# Render-Correlation 验证

## 范围

自 v2.3.6 起，canonical 离线 AEC render-correlation 指标在既有 +/-100 ms 窗口内检查每一个整数 sample lag。该修复用于消除窄带宽峰值落在历史 sparse grid 点之间造成的漏峰，不修改 metric 定义、dataset lock、policy 阈值、产品 DSP、公开 API/ABI 或 Product Certification 权限边界。

exact 搜索窗口严格为 `max_lag = sample_rate // 10`；input-render 与 output-render 最大相关性使用同一个 backend 和同一组完整整数 lag。

`validation/tools/render_corr_exact.c` 是纯 validation helper，由 `run_validation.py` 在 host 上编译；它不会进入 CMake 安装、不会导出为 SDK 组件，也不会链接进产品 runtime。helper 只使用 canonical stride-4 归一化项寻找全局最强整数 lag。随后 `run_validation.py` 再调用 `run_validation_engine.normalized_corr(..., stride=4)` 重新计算最终上报分数；native 与 canonical 分数不一致时直接 fail-closed。

## 信任与证据

如果 host C11 helper 无法编译或加载，validation 直接失败，不允许回退到历史 sparse scan。每份 report 绑定 evaluator engine、loader 源码、helper 源码、编译后的 helper 二进制、correlation-search 标识以及 compiler identity；evidence manifest 同时包含 evaluator/loader/helper 源文件。

接受策略保持不变。适用策略中的 `max_output_render_corr_ratio` 仍为 1.20。input 与 output 使用完全相同的全整数 lag 搜索，因此发现更高的 input/output 最大相关峰时具有对称语义。

## 准入证据

非 shipping research run `33843998920` 在完全相同的 processor/corpus bytes 上比较 sparse 与 exact search。已知 colored geometry 和另一组独立 fresh colored seeds 均由 28/36 提升到 36/36，消除的都是 ratio-only sparse-grid false failure；fresh tonal 保持 36/36。canonical motion validation/shadow 以及 exact-main/fixed-geometry 的 generic call validation/shadow 均保持全通过且无新增失败。完整 evaluator wall time 由 300.537 s 降为 118.364 s，即 0.394x。

Hosted Real AEC 明确不参与 search 设计和调参，只作为 release candidate 的单向最终准入门禁。真实 holdout 失败意味着拒绝候选，不允许据此调整 lag-search 参数或放宽阈值。

## Host 要求

canonical validation 现在要求 POSIX host，并可通过 `CC` 或 `cc` 使用 C11 compiler。仓库 CI 与 trusted validation runner 均配置该能力。compiler 缺失属于基础设施失败，不能作为继续使用旧 sparse evaluator 的理由。
