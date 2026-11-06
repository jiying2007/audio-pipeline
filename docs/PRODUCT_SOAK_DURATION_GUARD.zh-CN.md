# 正式产品认证：实测 Soak 时长双来源守卫

> **历史协议记录，非当前执行入口。** 本页保留退役产品流程的设计背景，不要求或启动商业认证、Release、72 小时测试。当前研究仅遵循 [RESEARCH_ONLY_EXECUTION.md](RESEARCH_ONLY_EXECUTION.md)；保留原始证据，不把旧流程作为科研前提。

本阶段是 **Product Certification 工作流的认证证据加固**，**不**代表已运行 SSC305、72 小时测试或已取得产品认证。预注册与真实原代码证据见 [Issue #58](https://github.com/jiying2007/audio-pipeline/issues/58#issuecomment-6581164729)。

## 风险与来源

固定产品资格候选是不可变 `v2.3.16` / `57e4c64adc1cf06819e46e24e275ecd746d5f17f`。其原始 `tools/target_evidence.py` 的 `route_soak` 写入 `soak.hours = args.seconds / 3600`，即请求时长。真实 ALSA 设备正常可能按实时完成，但原先没有独立单调时钟与 10ms 帧数反证，故绝不能仅凭它推定物理经历了 72 小时。

本改动保持产品 source checkout 与签名二进制不变，只在 **受保护 main 上的 Product Certification 控制平面**引入一个来源独立的持续时间观察者。调用 Product Certification 时应选受保护 main 工作流，在 workflow_dispatch 输入中提供审核确认的独立 `release_tag` 等参数。受保护 `github.sha` 通过第二份 `actions/checkout` 固定到独立目录，不替换产品源码，关闭凭据持久化，精确校验 HEAD 后调用该目录内的观察器。

## 何时允许通过

1. 在真实 `audio-target` 上，发行版自己的 `target_evidence.py route-soak` 开始前与返回后分别读取操作系统 `CLOCK_MONOTONIC`（`time.monotonic_ns()`）。验证真实 elapsed nanoseconds **至少** 请求时长。
2. 原始 `soak.json` 必须是原 collector schema v1/version 2.1 的成功结果。只能存在唯一的 `produced`、`received`，且二者 **精确等于** `soak_seconds * 100` 个 10ms 帧（正常路径）；不得以零帧、提前结束或重复计数蒙混。录音/渲染仍由原实际 ALSA 程序完成，新增观察者不模拟音频。
3. 原始请求时长和原 JSON SHA256 被单独记录；`soak.hours` 更新为**实测**时长，同时保留 `soak.requested_hours`、`soak.requested_seconds` 和独立 `duration_observation`。临时文件必须原子更新、回读一致，已有观察收据不得覆盖。原始原料 SHA 在观察收据中可追溯。
4. 此增强后的 `/tmp/soak.json` 被既有 `ap_certify.py` 复制进 materialized evidence，沿现有完整 v4 record/evidence-manifest SHA、签名与不可变 `product-lifecycle` 路径封存；**不能**只凭一次独立小收据把整体认证宣称 PASS。
5. 任何时钟、源 commit、帧数、JSON、权限、完整性、重复 key、非有限数值或文件写入失败均 **fail closed**；72 小时策略、不允许 XRUN、温升/功耗/声学阈值、CPU/RSS、原产品 SHA 不降低。

## 离线验证（非实机结果）

```sh
python3 .github/program/test_product_soak_observed_duration.py
python3 -O .github/program/test_product_soak_observed_duration.py
python3 -OO .github/program/test_product_soak_observed_duration.py
```

这些单测只有人工构造元数据及虚拟时钟输入，**没有**启动 Linux ALSA 设备、真实 DSP、源程序或计时 72 小时。真实认证仍须 #58 所有四类 Runner、发布治理 #511、实际 PCR02 双麦/时钟/功耗/温度、受信任语料、1/8/24h HIL、72h soak、签名和生命周期归档全部成功。保留所有旧失败与之前证据，不能升级资格状态。

## English contract

Protected main control plane performs a distinct monotonic elapsed-time and 10ms frame-count observation around the immutable release collector, never in place of it. It seals the original collector receipt hash, separate control/release source SHAs and observed elapsed hours inside the existing certification evidence. Offline controls are not physical proof. Any mismatch fails closed and does not change the original shipping binary or the 72h requirement.
