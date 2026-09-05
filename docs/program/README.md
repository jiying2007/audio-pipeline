# audio-pipeline 执行总纲

本目录是项目目标、设计决策、研究计划与进度的入口。2026-09-05 当前阶段为
**software-public-data**：使用可复现合成、声学仿真、开源实现研究和许可明确的开放数据，
推进软件、算法验证与发行工程；**不开展真实产品采集、DUT/HIL 或产品认证闭环**。
这是阶段范围，不是 HIL PASS，也不是取消未来产品认证。已有实验室/认证代码保留且不能伪造结果。

## 目标与非目标

目标：可量化改进的端侧音频 SDK；确定的状态与 ownership；可裁剪且资源有界；
故障可重放；测量权威可验证；候选可拒绝；发布可审计；每轮有明确停止条件。

当前不承诺：真实机器人远场识别率、真实电机噪声抑制量、板级 CPU/热/功耗、
目标机 worst-case latency、量产认证或任何仅由公开数据推导的产品性能保证。

不为优化制造新 backend，不保留被替代的入口或兼容 shim。合法破坏性改动应统一迁移
调用方、examples、tests、docs，并按公开版本契约升级主版本；不在 2.x 中悄悄破坏 ABI。
有明确产品约束的 MDF/NLMS、EMA/MCRA、SCALAR/NEON 不是仅凭名称即可删除的冗余。

## 权威入口：不再复制事实

| 内容 | 唯一维护位置/职责 |
| --- | --- |
| 迭代顺序、依赖、状态、预算、下一步 | [plan.json](plan.json)；`scripts/program.py` 校验并生成视图 |
| 执行规则、数据使用权限、冻结与失败回退 | [PROCESS.md](PROCESS.md) |
| 外部实践、开源代码、数据与使用边界 | [REFERENCES.md](REFERENCES.md) |
| 单轮实验预注册与验收 | [iterations/](iterations/)；运行结果留在 SHA-bound artifact，审查后回填索引 |
| 生产依赖与处理路径 | [ARCHITECTURE](../ARCHITECTURE.md)、[DSP_DESIGN](../DSP_DESIGN.md) |
| API/ABI、ownership、线程与 reset 语义 | [API_CONTRACT](../API_CONTRACT.md)、[DEVELOPMENT](../DEVELOPMENT.md) |
| RAM 基准 | `ci/resource-baseline.json`，文档视图由已有工具生成 |
| canonical evaluator / tuning 权限 | `validation/authority.json` 与已有 `run_validation.py` / `tuning_iteration.py` |
| 开放数据身份与许可 | `validation/*datasets.lock.json`、`tests/validation/data/*.lock.json`；不在 plan 复制 hash |
| 研究分支清理 | `.github/research/evidence-index.json` 与 `scripts/research_registry.py` |
| 发行证据 | 现有 release manifest、SBOM、provenance、immutable Release |

`plan.json` 是人工审查后提交的进度索引，不是 CI PASS 权威。自动生成的进度视图明确区分
**已提交状态、此次实测结果、下一步等待审查**，不因为 workflow 绿色就把算法任务改为完成。

## 架构准则与审查矩阵

保留既有单向依赖：core/modules 调用 stage，stage 只依赖必要的 dsp/arch，Linux runtime
通过公开 API 持有 pipeline。控制、诊断、文件和网络操作不进入 DSP 实时路径。

| 工作面 | 核心问题 | 软件阶段验收 |
| --- | --- | --- |
| AEC / Sync | direct I/O geometry、causal headroom、tracker alias、漂移与移动反射 | 先审 corpus/metric；同 PCM exact-base 对照；ERLE 分布、相关、收敛、双讲保护 |
| RES / activity | scalar/frequency 状态交接、远端抑制、近端恢复 | 保留现有快速恢复证据；加入恢复后重入与负例，不重新调已确认数据 |
| NS / VAD | 非平稳风扇/电机噪声、低 SNR、弱语音、音乐与误激活 | speech preservation + noise reduction；帧/事件指标、onset/release、false-active duration |
| AGC | 动态电平、噪声增益、残余回声放大 | target/limiter 之外同时检查 slew、settling、clipping、无 near-end 时的增益 |
| BF / HPF | 麦健康、相位/灵敏度、源移动、混响、双侧故障 | frontend-equivalent oracle；目标改善、非目标 exact-base 保护；不能以能量代替健康 |
| Resampler | 频响、alias、分块等价、时间映射、drift | impulse/tone/broadband、metamorphic、边界与跨平台数值比较 |
| Runtime / API | 生命周期、reset/reconfigure、queue、backpressure、并发 | TSan、故障注入、普通用户运行；callback 无分配/阻塞/格式化日志 |
| 性能 / 裁剪 | FULL/LOW/TINY/RAW/custom、scratch、FFT、ROM | 同 runner 配对 + 绝对预算；host/QEMU 结果不得包装成 DUT 性能 |
| Diagnostics | telemetry → trigger → bounded dump → APD → replay | source/build/config/timing 绑定；隐私默认关闭、限额、确定性故障回归 |
| 治理 / Release | 缺失门禁、旧 SHA、裁判变更、缓存、清理与供应链 | required 集合完整；exact-head/main 复验；证据先封存再删除 |

机器人场景以**仿真假设**登记：静止、平移、旋转、电机启动/匀速/急停、风扇、结构振动、
dock/charger；距离 0.5/1/2/3/5m，角度 0/±30/±60/±90/rear，SNR +20/+10/+5/0/-5dB。
采用分层抽样与高风险交互，而非不加预算地穷举笛卡尔积；没有可执行模型的格子保持 PLANNED。

## 首轮基线与实施范围

接入快照：`2e98354dc54b23c019d30b1c75a6d304d5a09ccb`；main Verify run
`33961870472` 的 `summary` 已成功。最新软件发行 `v2.3.11` 为 immutable；
此处不把 release SHA 与后续治理 main SHA 混同。已合并 BF、VAD、RES 的历史工作不重做。

首轮 `I001` 只验证 AEC motion 测量模型：记录现有五音激励与变化的最早路径；
以固定设备内 speaker/mic 几何、明确 I/O 延时、宽带/语音包络随机激励和一阶墙面反射作对照。
它是固定产品上的诊断，不是新的 shipping generator 或声学改进授权。
现有 canonical v1 回归不在本轮被删除或改写。`I002` 才决定如何一次性迁移 canonical corpus；
诊断 fixture 保留为不同职责的测试，不能发展为第二套生产 evaluator。

## 自动执行边界

`Program Iteration` 在相关 PR/main、手动和定时入口执行机器计划校验与已注册的只读任务。
第一项已实现 handler 为 `aec-model-audit`。它构建 exact base，调用已有 canonical evaluator，
保存所有种子、负面结果、源码快照和命令日志。其 SUCCESS 只说明测量完成且完整性通过。

自动化不写 main、不改 shipping defaults、不改版本、不放宽阈值、不用 holdout 循环选优，
不假装存在无人值守的通用代码生成代理。没有实现 handler 的下一任务报告
`BLOCKED_IMPLEMENTATION`；新实现仍通过 PR。编码代理的持续接力规则见根目录 `AGENTS.md`。

运行证据是阶段性 artifact（90天），不是永久存档。研究关闭/分支删除前必须将必要的
源码、配置、生成器与失败证据转入已有研究归档流程；仅记录 URL/摘要不足以允许 GC。
