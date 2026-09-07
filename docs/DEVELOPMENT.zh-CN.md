# 开发与代码规范（中文）

本页是中文贡献者的开发规则主入口。低层英文规范以 [`DEVELOPMENT.md`](DEVELOPMENT.md) 为 canonical reference；本页重点说明长期必须遵守的工程边界。

## 当前开发姿态

仓库当前处于 **software-commercial-ready 的稳定维护阶段**。软件/public-data program 已无 READY 任务；E001 仍是 external/deferred。

因此默认原则是：

- 有明确缺陷、回归、集成问题或真实外部基础设施失败，再改代码；
- 不为了“看起来更终态”主动堆 DSP heuristic、线程、缓存、workflow 或治理层；
- 不利用缺少真机证据作为理由降低 gate；
- 不把公开数据/QEMU/Hosted CI 写成真实 SKU 性能或 PQ 证据。

## v2 API/ABI

- 2.x 公共结构、函数和导出符号属于兼容契约；
- 不重新引入 1.x alias、wrapper、过渡 API 或重复 certification schema；
- 需要扩展的结构使用 `struct_size`、`api_version` 与 reserved space；
- 破坏性 public change 需要下一 major version；
- public float 参数先检查 finite，再做范围检查。

状态码保持精确：

- `AP_EINVAL`：输入/参数非法；
- `AP_ENOMEM`：调用方提供的存储不足；
- `AP_ESTATE`：当前 build feature 或 lifecycle state 不允许操作。

## C 代码约定

仓库当前不以 `.clang-format` 作为强制真相源；不要为纯格式目的大规模重排既有源码。修改代码时遵循所在文件的现有风格，并满足 strict compiler gate。

通用要求：

- 函数和局部变量使用清晰的 `snake_case` 风格；
- public API 保持 `ap_` 前缀；
- enum/status 名称保持项目已有大写风格；
- 不引入未说明的 magic number；产品/算法阈值应有命名、单位和测试；
- 显式处理整数宽度、符号和溢出边界；
- 公共浮点输入处理 NaN/±Inf；
- 不使用隐藏全局 mutable state 模拟实例状态；
- 不复制 stage 算法实现给 standalone wrapper，wrapper 应复用 stage implementation；
- architecture intrinsic 只放 `src/arch`；CPU/SOC 名称不能进入通用算法判断。

## Realtime 数据面

同步 stage/core/module：

**禁止**：

- heap allocation/free；
- mutex/condition wait；
- 文件、网络、RPC；
- printf/JSON/格式化日志；
- 无界循环或无界队列；
- runtime backend/plugin discovery。

必须：

- state/工作区有界；
- 10 ms 数据契约可推导；
- failure 可观测但不能在 realtime path 做重 I/O；
- 任何新增状态都计入 state-size/resource gate。

## 线程与所有权

- Runtime start 前 Pipeline 由 caller 拥有；
- start 后 live Pipeline 只允许单 DSP worker 访问；
- control plane 通过 Runtime API/受控队列/atomic telemetry 交互；
- output backpressure 不得让已接受的 DSP frame 被跳过；
- ownership、counter、queue publication、lifecycle 改动必须跑 TSan；
- ASan/UBSan 不能替代 TSan。

## 模块与依赖方向

允许：

```text
core -> frontend / sync / activity / aec / enhance
modules -> frontend / sync / activity / aec / enhance
frontend/sync/activity/aec/enhance -> dsp/arch（按需）
platform/linux -> public pipeline API
```

禁止 stage 反向依赖 core、`src/modules` 或 Linux Runtime。跨 stage 影响通过 event/result 由 core 解释。

## Backend 与 Build Envelope

互斥能力使用单 selector：

```text
AP_AEC_BACKEND=MDF|NLMS
AP_NS_ESTIMATOR=EMA|MCRA
AP_SIMD_BACKEND=SCALAR|NEON
AP_RESAMPLER_MODE=BANDLIMITED|FAST
```

新增 build dimension 时必须同时提供：

1. CMake/public validation；
2. generated build-info；
3. 至少一个 CI boundary product；
4. state/ELF pruning 证明（适用时）；
5. 安装后 SDK consumer。

## 算法复杂度准入

任何新的声学复杂度都需要先有**冻结的失败证据**：

1. 明确 evaluation scope；
2. 冻结接受阈值、数据角色和预算；
3. 证明失败不是测量/renderer/decoder/route contract 假象；
4. 单次只改一个根因方向；
5. candidate 与 measurement change 不能互相批准；
6. independent confirmation 后才能讨论 shipping behavior；
7. 无有效提升则 KEEP BASELINE。

validation-grade/blind 数据不能反馈给 optimizer。

## 测试要求

按变更类型选择 targeted tests，但合并前服从仓库 exact-head gate。典型要求：

- API/参数：boundary + invalid + NaN/Inf；
- 内存：state-size、SKU pruning、consumer ELF；
- Runtime：TSan + lifecycle + queue/backpressure；
- DSP：unit/property + backend/composition + acoustic regression；
- Arm：cross-build + QEMU；
- SDK：clean install + CMake/pkg-config consumer；
- 性能：same-runner paired base vs candidate；
- 数据搜索：固定 seed/hash/roles + independent validation；
- Release/certification：negative/fail-closed contract。

禁止通过修改 acceptance threshold、删测试、allow-failure 或 mock product evidence 获取绿色结果。

## 文档要求

以下变化必须同步文档：

- public API/ABI/lifecycle；
- build option/product preset；
- stage/ownership/data flow；
- validation authority；
- Release/Certification authority；
- 操作命令或路径；
- 诊断/隐私边界。

关键中文商用入口必须同步；低层协议仍保持一个 canonical truth，避免双语文档互相成为独立标准。

## Commit / PR

- 一个 PR 尽量只解决一个可说明的问题；
- PR 描述写清 scope、non-goals、authority boundary；
- 不直接 push `main`；
- 不 force-update tag；
- required `summary` 未成功不合并；
- exact head 改变后旧 CI 不再作为 merge evidence；
- squash merge 后再验证 exact main；
- release-neutral 变化不得为了“配版本”制造新 release；
- release-bearing 变化必须遵循 SemVer/CHANGELOG/immutable Release 流程。

## Definition of Done

软件变更至少需要：

- 根因/需求明确；
- scope 与 non-goals 明确；
- targeted + negative test；
- exact-head required gates PASS；
- 文档/中文入口（适用时）同步；
- protected merge；
- exact-main 再验证；
- release/provenance 行为符合变更类别；
- 不留下未分类 branch/ref/evidence 债务。
