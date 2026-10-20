# D13 事件回归结果：正常获取与重置抑制必须分别验收

日期：2026-10-10；experiment=`FE_DEVICE_CONTRACT_D13`；kind=`measurement`。
决定 **ENGINEERING_EVENT_CONTRACT_BASELINE_ONLY**；`promotion_allowed=false`、`shipping_approved=false`。
[冻结计划](DEVICE_CONTRACT_D13_PLAN.zh-CN.md) 与 [执行前补充](DEVICE_CONTRACT_D13_AMENDMENT.zh-CN.md) 均保留。
完成两版本各 56 例及各一次新进程复跑，共 **114 次、34,200 capture 帧**。
D11 在新事件契约 **52/52 mandatory PASS**；D8 **36/52 PASS、16 FAIL**；另各四例 pulse3 只作诊断。
D11 原设备数据的 REJECTED 不变，本轮不修改算法或批准部署。

## 实际实现与输入身份

[公共 API 事件 fixture](../../../tests/validation/frontend_evolution/device_contract_d13.c)
直接复用字节不变的 D9 生成器，8/16 kHz、seeds1/2、单麦、每例300帧。
配置为 CALL、SYNC|AEC、tracking/drift启用、max100 ms；没有HPF/BF/NS/AGC阶段。
输入文件为 interleaved render/mic 工程样本对，不代表双麦输入；两版全部 input/config 逐字节相同。
acquire/path-switch 的24种输入分别逐字节匹配各版原D9文件，共48次原输入对照，未改旧生成器或样本。
输出由原公共 pipeline 实际产生，不从shadow代替或合成输出。

| 原库 | 实际SHA256 |
| --- | --- |
| D8 | `a04ca88a75c0fd8538f7eb6d3726dfe906b2dfc284cc77c577f2328eb04b23b1` |
| D11 | `ead75733d45f5b78c086bed9122082d410847eea0ed6b21f8bafab102a1cb0ac` |

使用原库、生成头和已锁源码，没有重编库或使用 D12 测量库。
strict C11/warnings 编译通过；无效第三参数各实际返回2；指定路径切换7 ms的新进程复跑，
input/output/CSV/config全部逐字节匹配同版本首跑。
同库、独立状态的SYNC shadow仅为观测候选/确认，显式S16缩放匹配本组等采样率公共输入。
每帧 delay/jumps/slips 与公共 pipeline 完全一致；本组启用AEC，其reset与jump逐帧一致。
只有 observed 时比较公共误差与shadow事件误差，避免把未发布观察当成公共有效观测。
shadow状态不属于产品内存，不能据此声明产品新增资源或目标板代价。

## 冻结事件矩阵

| 必验家族 | 数量/版 | D8 PASS/FAIL | D11 PASS/FAIL |
| --- | ---: | --- | --- |
| initial40→真实1/7/80 ms获取 | 12 | 4/8 | 12/0 |
| 初始值等于真实1/7/80 ms稳态 | 12 | 12/0 | 12/0 |
| 第120帧真实40→1/7/80 ms持续切换 | 12 | 4/8 | 12/0 |
| 10/20帧短参考相关分量 | 8 | 8/0 | 8/0 |
| 全静音 | 4 | 4/0 | 4/0 |
| 无单一echo lag的独立信号 | 4 | 4/0 | 4/0 |
| 合计 | 52 | **36/16** | **52/0** |

正例未仅以末窗通过代替事件恢复：严格检查首次进入目标不晚于phase+80帧，
exactly一次jump/reset，且**唯一跳变本帧**进入truth±3 ms；切换前120帧每帧保持40±3且无jump/reset。
D11 acquire全部第39帧进入目标；path-switch全部第149帧进入目标，均同时产生一次jump/reset。
对应获取处理起点0.39 s；路径变更后0.29 s；这些是本生成器零基10 ms帧时间，不是产品实测恢复延迟。
D8的80 ms组同样为39/149，1/7 ms各八个acquire与switch组合共16例均未进入目标、未产生jump。
该16例保留四项失败原因：末窗不到目标、首次到达超出窗口、非一次jump/reset、跳变帧不到目标。
它们不等于四倍独立失败事件。

steady两版本全部末20帧保持目标且无jump/reset；silence每帧保持40 ms且slips=0。
unrelated只核无jump/reset，不赋予“保持40就是正确对齐”的真值。
这些是固定合成工程结果，不是未知设备场景中的误跳率、双讲保持或正常声学能力。

## 短时分量与三次更新的诊断边界

主40 ms参考相关分量保持存在，第120帧另叠加幅度0.9的80 ms参考相关分量。
持续10帧时两版最大 confirm_after=1；持续20帧时为1或2。
所有这16个短pulse执行均无jump/reset、末20帧回到40±3。
以16 kHz/seed1为例，两版第129帧产生一次确认；20帧pulse在139帧达到两次，149帧当前40 ms候选使确认清零。
确认值在中间非更新帧保留，不把每帧持有一次确认误算为连续多次确认。
这验证了本组短pulse行为，不是从10/20帧时长直接推断所有信号均不足三次确认。

四例/版的30帧pulse3预先声明为diagnostic，未加入mandatory分母：

| 版本 | 有跳变的pulse3输入 | 事件与最终状态 |
| --- | --- | --- |
| D8 | 8 kHz/seed1；16 kHz/seeds1/2，共3/4 | 第149帧跳到79/80 ms，第179帧回40；两次jump/reset，末窗40 |
| D11 | 16 kHz/seeds1/2，共2/4 | 同为149/179帧、79/80→40；两次jump/reset，末窗40 |

其余pulse3输入无jump，全部最终保持40。第三次确认执行后confirm_after会清0，不能因最大after=2否认已完成三次。
前三次强候选出现时，算法无法仅据相同前缀预知该分量随后消失。
不得把本诊断结果重新命名为两版mandatory全通过，也不得以D11的2/4少于D8的3/4推导真实抗干扰优势。

## 决定、下一实验和外部证据

本轮证明：已知真值的正常获取/持续路径恢复可需要jump/reset；更少reset可能伴随获取失败。
因此下一单一算法实验必须同时通过本事件契约、原D9 mandatory、uniqueness证明、资源约束与原设备开发回放稳定性，
不能以减少重置总数替代正确获取，也不能抹去D11现场拒绝来让其晋升。
本轮没有新的算法修改或可部署候选，D8/D9/D10/D11/D12历史结论全部保留。

真实设备的40→1–2 ms迁移仍缺独立真值，不能据这些合成获取例重新分类为现场正常恢复。
下一真实采集应同步保留实际送入AEC的render、原始双麦、处理前后音频、capture/render时间戳与sequence/XRUN，
绑定设备制品、profile/volume/rpm、通道含义与播放/人工说话/运动分段；对齐真值和人声标签分别提供。
新独立数据不得用于本轮参数选择；已查看tests/audio继续保持development角色。
没有设备/HIL/声学或资源资格，不能把Host同库回归推广到AISpeech产品链路或shipping。

## 证据与恢复

实际工件 `/tmp/audio-fe-device-contract-d13-20261010`，临时可用性不代表长期归档。

| 工件 | SHA256 |
| --- | --- |
| 原D9生成器 | `7395752ba53b93e701e607b06760af6bfcddc4b6a0243ab059812d26023663a2` |
| result.json | `c5e9722ab6c68f481517fe603a0a851e3d3fd0d12542f53767de7117d1575804` |
| binding.json | `52ea5a30f534fc6fdfe38c0b41eae4e271bf4f12cd763344ecc262460a78fdb9` |
| 后续补充audit.json | `395846c4970756d8ca66be5e8ee519abd5b0b79cad5fc033cacd6d4bd023ac2b` |

原binding不覆盖后续audit，最终审查快照另绑定该补充与当前文档。
Provider route unresolved，仓内reviewing candidate，未正式归档；无SCM或设备写。
当前主线SHA在读取时为cc887b0ced20a828ed7148b9ac949f639a1e2868，summary/release成功，但不是本地研究资格。
独立复审见 [D13复审](DEVICE_CONTRACT_D13_REVIEW.zh-CN.md)。恢复时先核原库、源、头、全部工件hash，
不从后来main重建库冒充本轮基线；若临时工件缺失，报告证据不可用并按新身份重建，保留原历史决定。
