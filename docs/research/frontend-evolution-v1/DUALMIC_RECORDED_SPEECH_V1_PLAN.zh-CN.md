# 双麦真实录音双用途 V1：执行前冻结

日期：2026-11-06（Asia/Shanghai）。实验身份：`FE-C2-RECORDED-SPEECH-DUAL-USE-V1`。
本文件在本实验数据取得、生成、DSP 执行和评分之前保存。
共同合同为 `494ae5ebb9c5cba4a8c3d0739430259a3649513f` 中的
`DUALMIC_NONDEVICE_V2_PLAN.zh-CN.md`；DSP 基线为
`2d93c9ddf74355c7e5ac0bc18c9a6fe3ae53cbd3`、源码版本 2.3.63。
不改 DSP、公开接口、默认 tuning、旧 runner、旧指标、旧门槛或历史结果。

## 输入与权利

复用原 `speech-admission-v1.json` 与 `speech_spatial.source_check()`，原 source
receipt 和 46 个文件不改字节。原始 LibriSpeech dev-clean archive 为 337926286 B，
SHA256 `76f87d090650617fca0cac8f88b9416e0ebf80350acb97b343a85fa903728ab3`；
已准入摘要 `7c4d711d4cb69121ccbbcb9a596d7ea26ca141a325add2dc8f5ff7421b9154c1`。
CC BY 4.0 的原 LICENSE/README/SPEAKERS 和署名保留；说明裁剪、缩放、补零、
空间/回声合成为本次衍生处理。真实英文朗读不是实际双麦房间录制或中文 KWS。

只允许原数值顺序八说话人各前四条 utterance 拼接后的原 4 秒窗口。
四对 near/far 固定为 `(84,174)`、`(251,422)`、`(652,777)`、`(1272,1462)`。
不按幅度、活跃语音量或结果挑人、裁窗或换源。原来已经查看过的 confirmation
角色只保留在 original_role 字段；本实验所有来源 effective_role=`regression`。

首选已有 `speech_pinned_snapshot.py` 固定 origin artifact 12107574410，run
39052067322，ZIP 204415056 B，SHA256
`1dffd4fc4968a0a214658627f1faf8bf54268f119fda86600a48511f897f30d4`。
只恢复 `effects/data/` 原始源，不消费旧声学结果。若缓存不可用，原官方
`https://www.openslr.org/resources/12/dev-clean.tar.gz` 按原脚本恢复同一来源。
每个固定资产的来源取得总预算 300 秒，从请求/下载前开始，包含落盘、hash 和
source_check。第一次失败单独保存，不重置同一次尝试的计时或改来源身份。

## 固定 56 例

16 kHz、两麦 S16LE、35 mm 合成间距、6 秒；每通道 96000 样点、600 个
10 ms 帧。near 的原 64000 样点固定放在 `[24000,88000)`，即 1.5–5.5 秒；
far 原 64000 样点固定放在 `[0,64000)`，即 0–4 秒，其他位置补零。录音内
原始停顿保留。不把放置范围当作逐帧活动标注，不生成真人 VAD ground truth。

每 pair 的两个原始窗口取最大绝对样点 `pN,pF`，固定共同 gain
`g=0.45*32767/(pN+pF)`；pN 或 pF 为零失败，不能重新选样。两源使用同一 g，
保留原 near/far 相对幅度，round/S16 规则复用原 `scale`。所有场景共享这次
缩放，不做逐场景、逐 profile、输出或听评文件响度归一化。混合前检查数值范围；
若将发生 S16 饱和则失败，不靠隐式 clipping 改输入。记录原峰值、g 和衍生峰值。

near broadside，两麦同相；echo 第二麦用既有 35 mm、60 度物理 TDOA 和
fractional_delay。左麦为固定参考。初始 echo taps 为 `(320,.52),(640,.21),
(1120,.09)`；第二路径为 `(160,.40),(720,.30),(1480,.10)`，单位为样点。
这些是合成传播，不是测得的房间 RIR。

| 场景 | 固定输入与控制 |
| --- | --- |
| near-only | near 双路同相；无 render |
| silent-render | 与 near-only 相同 capture；96000 个零 render |
| far-only | 固定 far 的合成 echo；无 near |
| doubletalk-nominal | near + echo |
| doubletalk-weak | near 固定乘 0.55 后 + 同一 echo |
| path-change | frame 300 起切第二 echo path；同帧通知 path change |
| render-gap | capture echo 不变；render frame 300–303 为零；同帧通知 gap/lost=4 |

4 pair × 7 scene × CALL/ASSISTANT = 56。两个 profile 的输入路径和字节完全
共享，不传 tuning override。使用完整生产 `ap_process_pcm` 与严格完整帧模式。
clean_near/interference/echo 是已知合成成分；不对 nonlinear 整链宣称分路响应
可线性相加。所有 case `expected={}`、quality_decision=`DESCRIPTIVE_ONLY`。

## 实现、测量与验收

新增 builder/runner/test，复用原 canonical quality semantics 与
`dualmic_profile_support`。不放宽原 42 例生成器或其检查。新 verifier 从准入
源和冻结规则重建期望 PCM/元数据，拒绝即使重新封 hash 的数据/角色/场景变更。

执行前提交实现，绑定实际源码 SHA、source tree、processor/build-info 二进制
hash、source/admission/generator/evaluator/adapter/合同 hash 和实际 default tuning。
开始、结束检查这些绑定；保留全部输入、实际命令、stderr、输出 PCM、600 帧 JSONL
和逐例指标。严格拒绝缺样点/帧/非有限数、缺例、重复或错配 profile/source。
canonical SI-SDR、near projection、echo ERLE、interference attenuation、恢复、
clipping、电平按现有定义报告；无标签则 VAD F1/onset/release 为未测。

source、build、targeted tests、formal matrix、independent readback 各阶段分别
计时，上限各 300 秒，单例仍用原处理器 30 秒上限。整个正式矩阵用监督进程限制
300 秒，progress/失败保留；不能因为子进程成功而忽略整个阶段超时。
完成仅为 `RECORDED_SPEECH_REPLAY_COMPLETE`，不代表声学改善或任何 profile 胜出。
原质量门禁保持独立执行。源/工具失败、工程完整性失败和描述性坏指标分别报告。

定向负例至少覆盖：少/重复 case、错 profile/角色/事件、缺/伪造真人 VAD 标签、
截断 PCM、错误源绑定、重新封印后改变衍生 PCM、profile 输入不一致，以及不完整
输出/非有限 telemetry。仅方法测试可用明确标为 test-only 的第一方数组；这些数据
不得通过正式原始源 admission，不作为真人执行结果。

## 听评材料

28 个固定 scene/pair 试次，每试次原 mic0、CALL、ASSISTANT 三项，共 84 个
mono 16k/S16 WAV。确定性 SHA256 排列决定匿名 trial/option 名；独立 key 文件映射
原 case 和处理身份。WAV 数据与对应 PCM 逐字节相同，无归一化或剪裁；引导听者
保持播放器音量固定。源署名和 CC BY 4.0 文本随材料保留。匿名仅为操作便利，
不是安全隔离或已进行的盲听试验。ratings 不造数，human_listening=`NOT_RUN`。

中文 KWS/ASR、真人主观质量、实际房间双麦、真实互联网、SSC305 物理 CPU/时延/
热功耗均不得由本实验代替。新测得 host wall time 不是目标板实时性。
