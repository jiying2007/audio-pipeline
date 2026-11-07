# 双麦 D1：真人固定输入的同状态阶段诊断

冻结日期：2026-11-07（Asia/Shanghai）。父任务为 #657；这是 PR #920 完成后的
新诊断身份 `FE-DUALMIC-STAGES-D1`，不是历史 D19/D39 的重跑或算法晋升。
本合同必须先提交，再进行任何本身份的音频实验。允许静态实现与独立方法审查。

## 问题、假设与边界

精确基线为 main `4daa7e239eebda11f6c7066df2e851269021112f`，tree
`605d5660d73ffb47c9d7bc5f4c2fd82e56cdeb36`，版本 2.3.63。原 A 的 nominal/weak
doubletalk 近端 SI-SDR 出现退化，原 C 同一 duplex 输入的处理后中文 CER 也变差。
最终 PCM 不能区分退化始于 BF 前、AEC 内、NS/频域 RES 联合级还是 AGC。

待证假设：Activity 未置 DT 时，NS 内频域 RES 可能依据完整 estimated-echo
功率过度抑制 AEC 后残差中的近端。它与普通 NS 的影响尚未分离。D1 只定位阶段，
不修改生产 DSP、API、默认参数、时序或算法状态；不扫描 mu、DT ratio、NS floor、
AGC/limiter 或 release alpha。没有 shadow、oracle、模块关闭或候选算法处理臂。

旧 NS-off 会同时切换 RES 实现并改变延迟，不能作单模块因果证据。频域 RES 在
DT 为真时当前局部乘子已为 1，历史 gain release 常数不能被直接称为当前帧损伤根因。
AEC outer gate 仅称 `adaptation_gate_eligible`，不冒称 MDF 实际更新次数。

## 固定原件与数据角色

唯一输入来自已完成 main Verify `42243575152` / attempt 1：

| 原件 | Artifact ID | ZIP 字节 | SHA-256 |
|---|---:|---:|---|
| A recorded speech | 13519768471 | 45182392 | `17c52894802a32b9a25bb343a8e9e509459935a73985a7d997ac923665a697d8` |
| C Mandarin | 13517113710 | 1368132 | `22f00bcd52b8bd938c655924e2a4e4b0acf1fa061b5bbcf345bc8f5b52b903d1` |

可执行来源锁见 `dualmic-stages-d1-source-lock.json`。整包下载、长度/hash、成员路径、
重复/符号链接/解压总量验证后才使用；不存在时失败并保留原因，不重新生成或换来源。
获取的完整 ZIP、获取回执和原成员一同保留于本轮证据。不得记录临时下载 URL/token。
原 A/C 都是 disclosed regression，旧 A 字段 split=validation 不改变其数据角色。
不是新 holdout、真人双麦实录、听评、ASR/KWS 泛化或物理设备证据。

固定 A 全部 56 例（4 pairs × 7 scenes × CALL/ASSISTANT）及 C 的 call、assistant、
call_duplex、assistant_duplex，共 60 例；两个 C raw 视图原样绑定、不跑 DSP。
保留全流、原 argv 配置和 frame-300 path-change / render-gap 事件。仅对输入和输出
绝对路径作可核验映射。不得裁段重置或挑选最差样本代替全矩阵。

固定计数：35,916 帧，5,746,560 mono 样点。Activity/NS/AGC 各 35,916 次；AEC
30,058 次；capture-only 5,858 帧无 AEC。独立时域 RES 0 次。AEC 的 ref tap 是实际
同步参考，不新增 SYNC 行为。A 8 个 near-only、C 2 个 clean 维持 capture-only，
AEC 相关 lane 标为 absent，不能人为开启或填零冒充实际观察。

## 测量实现及中性验收

复用 D19 的唯一定义重命名模式。在 exact Git archive 的独立测量副本中，只改被
观测函数定义名称，反变换后逐字节匹配原文件；不改函数体。普通处理器从同一真实
提交构建，生产目录与基线逐文件比对。observer 诚实标记 `<SHA>-D1-observer`，
原始提交、变换清单/源 hash、AP_BUILD 宏、编译器/参数、库/程序 hash 全部保存。
委托原 `examples/process_pcm.c` main；新增环境变量只指定只读 taps 的输出目录。

观察点：Activity 的输入能量、EMA、阈值、hangover 与真实 far/DT；AEC 的输入、
实际 reference、estimated echo、residual；NS 的输入、联合输出、mode/floor、
frequency enabled/active、真实 RES gain；AGC 输出和 gain before/after/allow；
独立时域 RES 调用数。保存未经归一化的原始 Float32LE，检查有限值、160 样点帧、
调用次序与上下游 memcmp。AEC 输入与 echo+residual 的最大绝对误差不得超过 1e-6。

每例必须满足两项独立字节相等：

1. 同一提交 fresh plain 与 observer 的最终 PCM 和原 metrics JSONL 相同。
2. fresh plain 与锁定原 A/C 工件的 PCM 和 metrics JSONL 相同。

任何不相等均为 `MEASUREMENT_INVALID`；不增加浮点容差、不改变原输出格式或旧
证据以取得通过。旧与新构建身份分别保存，不将旧结果重标为新执行。中性验证前
不解释 stage 结果。原模型输出直接绑定相同 PCM，不重复跑 ASR/KWS。

## 固定测量轴与解释

16 kHz / 160 样点，S16 到 float 使用除以 32768。AEC input/echo/residual/NS input
的时间偏移为 0，NS output/AGC output 为 160 样点。这个偏移不代表 HPF/BF 无相位
变化，也不是 40 ms render 初始参考延迟。禁止逐 stage 搜索最佳相关性 lag。

所有 lane 比较同一物理公共跨度 `[0,N-160)`；post-NS lane 使用 `[160,N)`。
另完整输出固定每秒窗口，最后一窗截于 N-160，不依观察结果筛选。可另报 native
whole-buffer 能量，但不得混为同物理跨度。RMS/peak 沿用 D19 公式，不做响度归一化
或 S16 往返量化。A 阶段 SI-SDR 只调用 canonical
`validation/tools/run_validation_engine.py::si_sdr_span`，near reference 除以 32768，
采用上述固定偏移；零能量参考返回 null。它是新诊断量，不替代旧全链路 ±3 ms
对齐的 canonical 指标或重新解释其阈值。C 不把 mixed duplex_mono 当 clean truth，
只报能量、gate 和原模型观察绑定。源放置区间不称人工 VAD 真值。

原 report、canonical summary、ASR/KWS 输出及其 hash 保留；无新 acoustic pass、
CER/WER/FRR/FAR 晋升。estimated echo 不是声学真值，AEC residual 仍含语音/噪声/
回声，NS+频域 RES 只称联合阶段，gate 覆盖不证明漏检或损伤因果。

## 预算、执行与停止

实际 DSP 执行在 GitHub Actions；不启动额外 Codex/ChatGPT Work 云任务。复用前端
研究的单一矩阵入口 `frontend-research.yml`，后续研究扩展矩阵而非每实验新建 workflow。
仅涉及明确研究路径的 branch/PR/main 触发，不把有期限的旧 artifact 变为所有普通
main 更新的永久依赖。所有正常 Verify/required summary 仍完整执行。

本新身份预算预先固定：source acquire 全阶段 300 秒；plain configure+build 300 秒；
observer configure+build 300 秒；60 例执行总阶段 300 秒；分析 300 秒；verify 300 秒；
独立原件复核 300 秒；Actions job 总计 20 分钟。单子进程也不得超过剩余总阶段预算。
失败退出、计时和已有文件原样保留。旧实验的失败和预算不变。

先冻结本合同，再提交实现并独立静态审查，才启动正式执行。完整原件通过独立
读回后记录结论；新 head 的结果不接受旧 head CI。合并走 protected squash，合并前
核对实际 head/base、全部适用 checks 和 required summary，合并后新 main 重新验证。
无发布/tag，无硬件、真实 WAN、MOS 或物理资源结论。

若损伤主要先于 NS，优先假设削弱，转向另立 upstream 诊断。若同状态结果支持
NS/频域 RES 联合阶段为主要增量，下一身份才冻结：固定真实 pre-NS/echo/gate 流，
连续比较同 NS 的 frequency on/off，原臂必须精确重放且 noise tracker 同态。
关闭 frequency 只是因果诊断，不自动成为产品候选。无法区分就保留不足以定位。
