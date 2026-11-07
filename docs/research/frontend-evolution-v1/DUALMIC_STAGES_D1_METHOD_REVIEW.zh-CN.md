# 双麦 D1 实施前方法复审

日期：2026-11-07（Asia/Shanghai）。[执行前合同](DUALMIC_STAGES_D1_PLAN.zh-CN.md)
冻结于 `22e9ff695ee8b2cb552673cfe4d4d9ad8ba211e3`，登记 [#922](https://github.com/jiying2007/audio-pipeline/issues/922)。
本页补充测量措辞与实现边界，不修改冻结合同字节、原数据、门槛或预算。

## 独立原件回读

独立审查者从原 main 的完整 A/C ZIP 检查了 SHA-256、795/78 个成员、解包字节、
A 的 649 项 result manifest、C 的 35 项 prepared/16 项 result bindings、60 条原
命令、连续 35,916 帧和最终 PCM 长度。153,843 项检查完成，实际 1.267442 秒。
这只是已经存在的原件回读，没有运行本身份 DSP 或模型。

两原件的实际来源都是 `4daa7e239eebda11f6c7066df2e851269021112f`，GNU 13.3.0 / Release，
SCALAR / MDF / EMA / BANDLIMITED / fast_math=0。共用原 processor SHA-256
`3464c7e89ec26367e018eb8ed3f02857f243764b0b2a5c9e4108186030648f1a`，
config_digest `569d92f450c5a431aee273fcfe0f61df252ec6ba4924b2c87bdfa5421bf3b2ec`。
它们不同于早先首次本地报告的源码与 GNU 14.2 身份，不能混记。

原件审查脚本 SHA-256：`3805d55ad43a2bf46df5e678d635a4ad6589891fe90559903d87f67f70480e1b`。
后续 D1 执行的独立验收必须另有真实原件和回执，这一结果不提前批准新 observer。

## 定位能力的准确含义

第一条音频 tap 是 post-HPF/BF 的 AEC input，capture-only 则为实际 NS input。
所以合同中“BF 前/先于 AEC”的问题，D1 能定位的最细范围为 **raw 到 HPF/BF 联合
上游**；D1 不能区分 HPF 与 BF 各自贡献，更不能证明 BF 之前的单独根因。
此外依次观察 AEC、NS/频域 RES 联合级、AGC。不存在假造的单模块残差分解。

0/160 样点是固定处理坐标；不宣称 HPF/BF 无相位响应，也不沿用旧 ±3 ms 搜索来
逐级消除差异。新增阶段 SI-SDR 与原全链路 alignment score 的定义不同，不能直接
相减后冒称同一指标收益。固定每秒窗不是人工语音活动标签。

C 的 `duplex_mono.pcm` 是混合视图，不能当 clean-near 真值；全部 C processed
视图仅进行原 PCM 中性校验、阶段能量和 gate 观察，复用相同 PCM 对应的旧模型输出。
单句话和六个相关视图仍不支持泛化 CER、KWS FRR/FAR 或触发时延结论。

## Primary-source 机制核查

以下仅用于形成假设，没有复制第三方实现或把它们视为本仓已验证方案：

- WebRTC [dominant_nearend_detector.cc](https://webrtc.googlesource.com/src/+/0732b802be1229544fc28f8f5f306f9c836859f4/modules/audio_processing/aec3/dominant_nearend_detector.cc)，
  commit `0732b802be1229544fc28f8f5f306f9c836859f4`，blob `d7e01fbaeb57c3aaff8404c04273b812a27d27de`，
  同域 near/residual/noise 证据与迟滞，不能直接套用阈值和帧计数。
- 同 commit 的 [suppression_gain.cc](https://webrtc.googlesource.com/src/+/0732b802be1229544fc28f8f5f306f9c836859f4/modules/audio_processing/aec3/suppression_gain.cc)，
  blob `fe9c46efad467752c467d77bb6672c4f270a6e98`，完整 echo 与 residual echo 保留不同语义，
  近端状态影响抑制边界。该结构支持分开观测量纲，不证明本次损伤原因。
- SpeexDSP [mdf.c](https://github.com/xiph/speexdsp/blob/7a158783df74efe7c2d1c6ee8363c1e695c71226/libspeexdsp/mdf.c)，
  固定 commit `7a158783df74efe7c2d1c6ee8363c1e695c71226`；residual postfilter 估计按泄漏
  缩放完整 echo PSD。`last_y` 附近仍有多通道转换约束，不能把它当可直接移植的双麦
  联合残余估计器。本仓 BF 后 mono 仅可作机制对照。

## 执行入口

唯一新增矩阵入口 `.github/workflows/frontend-research.yml` 在相关研究路径的 PR 与
main push 执行；不修改原 Verify 图或 required summary。当前矩阵只有 D1，后续
前端实验扩展这一入口。输出用实际 run/attempt 命名，保留 90 天；原依赖过期时
明确 source failure，禁止将新来源或再生成数据冒充原 ZIP。

构建器入口：`tools/codex_assets/dualmic_stages_build.py --source <checkout>
--source-revision <exact-40hex-SHA> --output <new-directory>`。从 exact Git archive
构建 baseline-build/ap_process_pcm 与 observer-build/ap_process_pcm_observer。
测量副本唯一函数定义重命名，原函数体逐字节保持并验证；构建的真实变换身份另记。

runner：`dualmic_stages_d1.py run --original-a <A> --original-c <C> --build-dir <build>
--output <new-result>`。随后 `verify --output <result>` 只读回完整数据，不运行 DSP。
该工具自己的读回与独立审查者的原件验收分别记账。

每一原处理命令保留参数与事件，仅以安全路径映射替换输入/输出绝对路径。观测器
额外读取 `AP_D1_STAGE_DIR`，要求新空目录；缺失、非空或链接均拒绝，避免无观测却
声称成功。原 main 返回码、stdout、PCM 和 metrics JSONL 都保留。

## 实施静态审查闭环

核心实现的独立 Spec / Quality 静态审查通过，阻断项为零。已关闭：observer 实验
标识不一致、capture-only frequency_enabled 校验错误、原件清单删项后重新封存
可能绕过 ZIP 绑定、构建末端预算遗漏、PR 默认 synthetic merge 与 actual head
身份混淆、原件和实际构建证明保存不完整。它们均在正式 DSP 执行前发现并修复，
没有以更换原输入、增加容差、延长预算或修改生产 DSP 取得通过。

`test_dualmic_stages_d1_integrity.py` 在 CI 获取原件后执行固定 catalog 正例及三个
负例：删除 binding 后重新封存、删除必需文件及 binding 后重新封存、修改原输出
一个字节并更新散列后重新封存。三者必须仍被原 ZIP 与必需成员闭包拒绝。该 gate
不运行 DSP、模型或声学评分；正式观测和实际原件独立验收另记。
