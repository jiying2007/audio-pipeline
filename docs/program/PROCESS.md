# 迭代与闭环执行规范

来源：用户确认的《audio-pipeline 终版迭代方案与闭环流程》，于 2026-09-05 归档规范化。
本次范围覆盖更新优先：真实产品采集、DUT/HIL、Extended Real 的产品资格部分及正式认证
**DEFERRED_BY_SCOPE**，不作为当前软件/开放数据研究的启动依赖；不改写其实际执行状态。
开放数据 Extended 验证可在许可、资源与 runner 条件齐备后开展，不能据名称变成产品认证。

## 闭环层级与变更通道

研究闭环：假设支持/拒绝/证据不足，有可复現材料。KEEP_BASELINE 不关闭仍存在的缺陷。
软件工程闭环：指定源码、构建组合与范围通过正确性、接口、资源、实时性及适用回归。
软件发行闭环：exact source/main Verify、版本、annotated tag、可复现资产、SBOM、provenance
和 immutable Release。真实产品认证是独立层级，本阶段不开展，不能由前三者推导。

四类通道：工程、声学行为、测量权威、治理/文档。混合变更取门禁并集；无法分类时从严。
性能优化若不能证明行为等价，按声学变更；CI/权限/发布/裁判变更按高风险治理审查。

## S0—S11 主线

| 阶段 | 必要产物与出口 |
| --- | --- |
| S0 接入与快照 | live main SHA、open PR/refs、支持范围、既有证据；先冻结现场 |
| S1 复现与根因 | 最小复现、影响范围；分类 algorithm/integration/runtime/resource/corpus/metric/evaluator |
| S2 实验契约 | exact base、假设、目标/非目标场景、数据角色、约束、收益量、候选/确认/运行预算 |
| S3 Development | 有界实现/搜索、淘汰原因、资源预检；无合格候选则保留 baseline |
| S4 Validation | 先冻结候选集合，再按预注册规则一次性选唯一候选；不得临时增加候选 |
| S5 工程预验收 | 构建、测试、资源、性能、文档与调用方迁移、源码清理完成；冻结唯一候选 |
| S6 Shadow | 已知场景 exact-base/行为等价/指标反退化；不能据此改选 |
| S7 Independent Confirmation | 候选冻结后使用未曝光数据，只确认固定假设；失败退役，预算不清零 |
| S8 Hosted Real Promotion | 适用时单向晋级；重复使用的公开 microset 只能叫 Hosted Real Regression |
| S9 最终 PR | 完整 gate plan、审查与 exact-head CI；缺失、旧 SHA、取消或跳过的必需门禁均不通过 |
| S10 合并/交付 | expected head 与有效 base、main exact SHA 复验；必要时受治理发布 |
| S11 封存/再审查 | 可重现证据先封存，再清理 refs/artifacts；明确下一问题与进入点 |

Draft PR 可在 S2/S3 建立以执行 CI，但不得自动消耗确认集。最终两次冻结分别是
候选集合冻结、唯一晋级候选冻结。工程预检与源码清理在确认前完成。

## 数据角色、独立性与曝光

来源 Level 0—5、使用角色、证明范围、曝光状态分开维护。新 seed 不自动等于新数据域。
Development 可调参；Validation 可选冻结集合；Shadow 只检查反退化；Confirmation 只确认；
Hosted Real Regression 可重复；Hosted Real Promotion 只做单向门禁。DUT 证据本阶段不生成。

拆分必须检查 speaker/session/原始录音/RIR/设备/时间段/派生关系；裁剪、增益、重采样、
加噪继承原始 source-group。重复运行标为 replay。确认反馈导致算法变化后，该集合退役。
预注册每个 root-cause 的最大候选数、确认次数和停止规则；改 branch/iteration 不重置历史。
预算耗尽输出 KEEP_BASELINE/INSUFFICIENT_EVIDENCE，不继续抽 holdout 直到碰到 PASS。

已有 ES2003a/ES2004a 与已曝光 synthetic seeds 不自动成为未来 VAD 的独立确认集。
现有 Hosted Real Audio/AEC 日常工作流是 regression；本程序不通过重命名赋予其新 holdout 权限。

## 测量工具链独立验证

先固定产品与 PCM → 已知答案/边界/反例 → 修改 corpus/标签/metric/evaluator →
新旧测量差分并解释变化 → 独立审查 → 冻结测量契约 → 重建产品 baseline。
不能在同一声学晋级中修改参赛算法与裁判。故意错位、缺数据、坏输出、错标签必须被检测。

物理审计包括 excitation alias、direct vs reflection、I/O 延时、causal margin、RIR/速度范围、
SNR 定义、样本长度、frontend-equivalent oracle、相同 PCM、fractional-delay 附加延时。
降低物理模型假设的范围可以；不能将粗略仿真声称为完整真实声场。

## 目标、保护场景与资源

先硬约束，再比较收益。目标改善不能抵消非目标失败。记录 pass count、median、低分位、
worst case；CPU 记录 p50/p95/p99/最大观测与绝对预算，不将样本最大值称为已证明 WCET。
允许退化、最低有效改善和重复测量规则必须事前声明。证据不足不默认 PASS。

区分 baseline 已有缺陷、candidate 新退化、candidate 改善；新 oracle 不可随结果改门禁。
同时有 module probe、实际构建组合、端到端证据。host/QEMU/cross-build 不替代 DUT 指标。
复用已有 resource SSOT、canonical metrics、policy 与 CLI，不另造同义 evaluator。

## 证据身份与失效

每轮记录 issue/root-cause/iteration、base/candidate/merged/release SHA、config/组合/编译器/
flags/依赖/runner、数据与 generator/evaluator/policy 指纹、曝光账本、全部尝试与退出原因。
SHA 在提交形成后由运行材料绑定，不通过反复回写候选本身制造身份循环。

DSP/配置/状态/构建行为变化使相关声学证据失效；测量变化先走工具链验证；工具链与组合变化
重验数值/资源；base 移动重新验证集成。可证明纯元数据变化可引用旧声学确认，但最终 CI
必须满足实际 head。fresh execution 不是 fresh independent data。

角色分离：提出候选、执行测量、按冻结规则裁决分别记录。重复调用同上下文模型不自动构成
独立审查。自动器输出候选/证据/拒绝原因，不能改 main/default/version 或自行修改规则后批准。

## CI、失败与发布

验收 gate plan 的完整性，而非绿色 job 数量。必需项存在、完成、通过、身份一致且未失效
才可晋级。不适用必须在规则中事先定义。依赖/编译缓存可用，旧测试结果不可冒充新执行。
治理改动不得完全用候选自己修改后的 classifier 自证安全；最终审查核对可信基线契约。

研究执行 SUCCESS 与 candidate REJECT 可以同时成立；测量完成不是产品晋级。
语料/指标错误回工具链；开发/Validation/Shadow 失败淘汰；确认/holdout 失败登记并退役；
资源失败重新开发；基础设施仅有限重试并保留首次失败；main 失败停止发布。

不是每个 PR 都升级版本。版本已存在只在发布身份/资产契约一致时 no-op；冲突失败，禁止
retag/覆盖。治理 main 不冒充旧 release source。沿用 existing release manifest 与不可变发布。
本程序不弱化已有软件门禁，也不把未执行的真实资格转换成 PASS。

## 清理、归档、停止与流程自测

源码清理在最终验证前；仓库对象清理在合并和封存后。研究 ref 删除必须 terminal、exact SHA、
可重现证据封存、无 open PR、无在途写入/依赖、live SHA 一致；不确定即不删除。
90天 Actions artifact 不是永久归档；GC 前须按现有 registry/lifecycle 流程封存。
无主/失效 TODO 可清理；真实未解决问题进入台账。历史失败保留回归保护。

每轮出口仅 ACCEPT、KEEP_BASELINE、REJECT、INSUFFICIENT_EVIDENCE、BLOCKED。
关闭实验不等于关闭产品问题。范围内无已知交付阻断、适用门禁满足、无无主残留且证据完整
才可称相应软件阶段收敛；不宣称所有可能优化耗尽。

流程自身测试：旧 SHA、缺门禁、缺证据、已曝光确认集、隐藏首次失败、超预算、循环依赖、
无 handler、dispatch-only、release 冲突与 GC SHA 漂移必须拒绝或明确 BLOCKED。
当前程序只自动校验已经实现的子集；计划中其余项不得描述为全部自动强制执行。
