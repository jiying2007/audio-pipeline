# 双麦识别交互与语音对讲：首轮实施合同

状态：实施前冻结，尚无本合同候选执行结果。日期：2026-11-06。

用户明确要求“聚焦双麦，前处理不仅用于识别交互，也会用于语音对讲，全面闭环落地”。本合同承接现有 frontend-evolution-v1 授权，首轮只处理已经定位的正确性缺陷与双用途评测接入。四麦既有源码、科学记录和回归保留，不新增四麦候选。本合同不重新开放 I025–I040、已关闭的 AGC 参数研究或已拒绝的固定神经后置配置。

## 基线与共同约束

- 精确基线：`438fe09d79ff768306c00573849517bcd91cbc6e`；主线 Verify `42166460584` 已成功。
- 输入：第一方可重建合成工程信号；已有公开语料仅按既定来源锁和数据角色执行。旧曝光数据是回归，不能变成独立效果确认。
- 使用现有 `AP_PROFILE_CALL` 与 `AP_PROFILE_ASSISTANT`、同一公共双麦管线及 canonical evaluator。默认 API/CLI 行为保持 CALL；不新增平行 DSP、公开结构或版本后缀接口。
- 每项因果变更在独立工作树实施、定向验证后集成；两个算法修复不得用彼此的变化掩盖失败。评测方法接入与效果优胜判定分开。
- 实时路径不分配、不阻塞、不做 I/O；新增常驻内部状态总上限 64 B。保留现有 50,000 B 保守目标 arena 上限及各资源门槛，不通过提高阈值获得通过。
- 本地单次构建/定向测试预算各 300 秒；完整现有验证按原工作流预算。没有新定时任务、无界搜索、训练或付费执行任务。
- 对源码行为变更按当前源版本治理使用 2.3.62，并同步 CHANGELOG；不创建发布/tag。冻结历史实验不改字节；必要的后继源码准入须另立身份、独立审查，保持原输入、判据和执行预算。

## A：FE-C2-SYNC-OBSERVATION-TIME-V1

根因：`ap_sync_apply_drift` 将相邻成功延迟观测之间的差值固定按 100 ms 换算 ppm；相关性拒绝可以延长实际间隔。先前公开 API 诊断已经观察到 16k 下 +1 样点/100 ms 与 +1 样点/1 s 均产生一次 EMA 后 31.25 ppm。

唯一算法变化：按捕获样点计数保存成功观测的时间坐标，用 `1e6 * delta_delay / elapsed_capture_samples` 归一化。保持现有 0.95/0.05 EMA、ppm clamp、搜索阈值、路由确认、整数 slip、分数插值与误差反馈公式。关闭跟踪/补偿、reset、timestamp 和路由切换须明确使时间基准无效或重新建立，避免旧 epoch 的差值进入新 epoch；不顺带改造成 ASRC。

实施前固定验收：

1. 8k/16k、100 ms 与 1 s 有效间隔；相同采样率下 raw ppm 按实际间隔成比例。16k、从零开始、一次更新的 +1/100 ms 为 31.25 ppm，+1/1 s 为 3.125 ppm，误差不超过 1e-4 ppm。
2. 连续有效观测维持既有 EMA 暂态与正常 100 ms 行为；拒绝观测不得凭空产生 delay-observed 或路由事件。
3. 相同端点斜率、不同拒绝间隙不应触发由错误时间分母造成的 ppm clamp；不要求不同有效更新次数的 EMA 输出立即相等。
4. reset、timestamp、route jump、关闭再开启及计数边界不产生过期 rate 观测；公开非法输入保持原子拒绝。
5. 现有 SYNC/AEC/RES、runtime、8/16k、CALL/ASSISTANT、backend/ABI/资源回归保持；遇到真正行为回归保留失败并审查，不能修改原声学阈值。

## B：FE-C2-FIXED-DIRECTION-HEALTH-V1

根因：`track_direction=false` 无条件清除 BF fallback；SSC305-low 与 LITE 因而失去已有的狭义 hard-contamination 保护。现有 hard signature 是能量比与 roughness 的联合规则，不是通用坏麦分类。

唯一算法变化：保留 `track_direction=true` 原搜索、阈值与节拍；固定方向时每四帧在当前固定 lag 上进行 O(n) 观察，仅对既有 hard-contamination signature 做持续确认与恢复。不得更改 lag、lag_score、score_updates，不引入全 lag 搜索，也不把低相关/轻微失配直接升级为 soft fallback。可复用已有内部状态；模式切换的已确认 hard 状态须有明确生命周期。

实施前固定验收：

1. 8k/16k、左右污染互换的既有 hard signature 在持续确认后选择对应干净通道；固定方向 lag 与方向估计状态保持不动。
2. 安静、双路零、同相同幅、轻微增益失配、合法弱通道、离轴时延和普通非相关噪声负例不因新固定方向分支误触发；原健康输出保持等权/既定 lag 行为。
3. FULL→LITE、LITE→FULL、跟踪开/关、故障恢复与 reset 均覆盖；有限输入始终产生完整、有限的连续帧。
4. 既有 track=true 的全部健康/故障回归保持。单独报告恢复阶段的电平和边界变化，不从“有限/无丢帧”宣称无点击或真人音质改善。
5. 数字断流、单路精确零、卡死/rail、极性颠倒不新增分类或凭空宣称已解决；若未匹配现有 hard signature，保留原行为并记录覆盖边界。

## C：FE-C2-DUAL-USE-PROFILE-REPLAY-V1

集成缺口：公共 SDK 有 CALL/ASSISTANT，但现有离线处理入口固定创建 CALL，无法直接测量完整 ASSISTANT 默认配置。

改动：给现有 PCM 入口增加显式 `--profile call|assistant`，默认 call；canonical evaluator 可显式透传配置并记录有效 profile。没有指定 tuning override 时必须保留该 profile 的默认参数；显式 override 继续生效。历史源锁定 runner 不改字节。

实施前固定验收：

1. 未给 `--profile` 与显式 call 的输出和既有参数语义一致；非法、缺失 profile 值失败并保留原错误处理边界。
2. 两 profile 的实际配置和构建身份可回读；CALL 的 tail/mu/floor/AGC 与 ASSISTANT 的差异不被评测器默认参数悄悄覆盖。
3. 同一已冻结工程语料分别运行两个 profile，报告各自结果；capture-only、render/duplex、有限连续流和输出长度均实际验证。
4. 公共 canonical 指标与原门槛保持。新 profile 接入不产生质量优胜结论，不把本地合成测试称为 KWS FAR/FRR、对讲主观质量或物理 SSC305 结果。

## 双用途完成标准与后续效果研究

本轮软件完成要求独立代码复审、上述定向/负例验证、精确 PR head 的所有适用门禁及 required summary 成功、受保护 squash 合并和新 main 再验证。结果记录分别报告三个工作包、源码身份、失败与资源变化。

交互用途后续必须固定中文 KWS 模型、事件规则与阈值角色，评价漏唤醒、误唤醒、播放打断和延迟。对讲用途独立评价近端单讲保真、远端残余回声、双讲起音/尾音、路径恢复、背景噪声、pumping/clipping 和连续流时延；不以 KWS 分数代替对讲质量。

双讲近端/回声控制结构、独立真实语音确认、实际 KWS 模型评价、SSC305 I/O/CPU/热功耗属于后续效果证据。已有 D30–D49 负结果保留；新结构研究另行固定观测、候选与验收，不由本轮代码修复自动批准。缺少物理设备或相关语料时如实标记 NOT_RUN/BLOCKED，公共数据与离线研究继续按自身条件推进。
