# F05 新八说话人双麦整链有限验证合同

**状态：方法与 tiny tests 就绪，真实合成和声学矩阵尚未执行。**

本研究的独立身份是 `F05-DUALMIC-RESERVED-VALIDATION-V1`。它使用 F05 已完成来源准备的
32 个完整语句，描述固定 CALL、ASSISTANT 默认整链相对于原始麦克风 0 的表现。
必须先公开冻结本合同、机器计划和执行源码，再使用同一实际公开 revision 的 CI 构建包执行。
完成状态表示 128 次调用及证据完整，不要求声学收益，也不授权候选晋升或产品发布。

机器合同：[f05-dualmic-validation-v1.json](../../../.github/research/frontend-evolution-v1/f05-dualmic-validation-v1.json)。
实现：[f05_dualmic_validation.py](../../../tests/validation/frontend_evolution/f05_dualmic_validation.py)。
纯 tiny：[test_f05_dualmic_validation.py](../../../tests/validation/frontend_evolution/test_f05_dualmic_validation.py)。
既有来源合同：[F05_SPEECH_SOURCE_V1.zh-CN.md](F05_SPEECH_SOURCE_V1.zh-CN.md)。

## 1. 本次问题与来源边界

本次只问：在预定来源、固定合成传播和相同原句区间下，默认 CALL 与 ASSISTANT 整链相对
原始麦克风 0 的描述性变化是多少？同一组源句各有 near-only 和含双讲场景，全部保存。
不更改旧 56 例语料、旧 source 入口、冻结锁、评分实现或现有 DSP 源码。

| 项目 | 固定内容 |
| --- | --- |
| 原始来源 | OpenSLR 12 LibriSpeech `dev-clean.tar.gz`，337,926,286 B |
| 原归档 SHA-256 | `76f87d090650617fca0cac8f88b9416e0ebf80350acb97b343a85fa903728ab3` |
| 来源准备 revision | `a058b02582962875ac10e6bb42b928c46c405213` |
| 来源准备计划 SHA-256 | `cde46538288219a077927eada139fea62c2bc156fa9bd478626aae139e0db4d3` |
| 原 source receipt SHA-256 | `35fb4797cf67d004ae1646d61b7905a85bf376f7abbd031d4b3d58531ca57e5c` |
| 原始资产 | 32 个原 FLAC 及 32 个完整解码 PCM；5,241,680 样点，即 327.605 s |
| 说话人 | 2412、2428、2803、2902、3000、3081、3170、3536，每人 4 句 |
| 来源角色 | `reserved-validation-visible-scope-separated`；`NOT_BLIND` |
| 本次输入用途 | 完整原句；来源包中的 8 个 4 s 适配片段不参与本研究 |

这 8 人由此前公开的 source-only 合同在已查看范围排除 16 人后按数值排序选择；语句也在
声学评分之前按元数据排序固定。这里保留当时的扫描范围、排除依据和漏查限制。
“可见范围分离”不等于没有任何历史接触，更不建立普遍独立性。来源准备回执中的
`acoustic_execution_allowed_by_this_contract=false` 不作修改；本次新的有限声学授权由本合同给出。

原数据授权依据仍是准确归档保留的 `LICENSE.TXT` 与 CC BY 4.0、原作者和 OpenSLR 归属。
来源包保留原件、完整 PCM、原声明和无损解码记录。本次只生成可追溯的新合成衍生输入，
不修改原 PCM，不增加外部模型、下载权重或解码器调用，也不自动公开音频副本。
既有公开入口为 <https://www.openslr.org/12/>；本次实际 bytes 由上述归档和回执哈希决定。

## 2. 固定设计、时轴和合成传播

相邻说话人配对为 `(2412,2428)`、`(2803,2902)`、`(3000,3081)`、`(3170,3536)`。
每对按同一语句序号 0–3 配对，再交换近端与远端角色。不根据能量、内容、长度是否有利
或结果改变配对，不搜索增益、延迟或其他参数。

32 个完整近端语句 × 2 场景形成 64 个输入；每输入分别执行 CALL 和 ASSISTANT，固定
**128 个输出**。其相关层次为 8 个来源说话人、32 个原句和 4 个说话人对；场景和 profile
是重复测量。128 不能作为 128 个独立来源样本，合成双麦也不是实测双麦房间录音。

| 参数 | 冻结值和规则 |
| --- | --- |
| 数字格式 | 原生 16 kHz、PCM16；mic interleaved 2 通道，render 和参考均 1 通道 |
| 原句增益 | 所有近端和远端统一乘 0.25；不作逐句峰值、RMS 或结果归一化 |
| 近端起点 | 样点 24,000，即 1.5 s；两麦放置相同完整近端波形 |
| near-only | capture-only，默认完整 capture profile；没有 render 或 interference 文件 |
| 含双讲场景 | 从样点 0 放入完整远端 render；完整 near 从样点 24,000 开始 |
| mic0 回声 | 复用原 `echo_from_render`；tap `(320,0.52)`、`(640,0.21)`、`(1120,0.09)` |
| mic1 回声 | 复用原 `fractional_delay`；35 mm、60°、声速 343,000 mm/s，线性插值 |
| 目标方向 | 0°，两麦目标时差 0；合成几何，不是设备物理通道标定 |
| 尾部 | 上下文结束后 8,000 个零样点，再补 0–159 个零达到 160 样点边界 |
| 混合数值 | 复用既有 PCM16 舍入；任何相加超出 PCM16 范围立即失败，不降低增益重做 |

near-only 的长度是 `ceil160(24000 + Nnear + 8000)`；含双讲场景的长度是
`ceil160(max(24000 + Nnear, Nfar) + 8000)`。原始语句全部保留，没有从完整帧边界截去末尾。
32 个原句中 11 个在 160 样点边界上有 80 样点余数；新场景明确记载实际尾补 0 或 80 样点。
128 输出共 **28,277,760 样点，即 1767.36 s**，最长一例 **479,840 样点，即 29.99 s**。
输出时长包含重复 profile、场景和合成上下文，不增加 327.605 s 原始语音覆盖量。

调用前额外要求 `render` 样点数精确等于 mic 的每通道样点数。原 CLI 会对较短 render 补零，
因此这里的拒绝是新 harness 的输入约束，不能声称旧 CLI 原本就会拒绝短 render。
两种 profile 都显式传 `--strict-capture-frames`，不传任何调参、事件或阶段隔离参数。

### 含双讲场景的结构性交集

这些场景保留整句，不保证近端语句期间远端一直存在。对每个原始远端长度 `F`，mic0 的潜在
回声支持包络为 `[320,F+1120)`；固定线性分数延迟约 1.413919 样点使 mic1 的包络成为
`[321,F+1122)`。分别与固定原近端区间 `[24000,24000+Nnear)` 求交，逐例保留起止、样点数
及占原近端长度比例。当前元数据推导的 mic0 比例为约 8.42%–100%；例如 2428/序号 0 为
17920/212880。mic1 逐例单独计算，不用 mic0 数字替代。

这只是由完整文件长度、FIR 和线性插值推导的潜在支持包络，**不是实际发声或 VAD 活动率**。
报告应称“含双讲场景的整句保存表现”，不称“全程双讲压力”。不因交集短而更换语句、缩短
主评分 mask、补选场景或增加门槛。没有人工 VAD 标签，结果不计算或声明 VAD 质量。

## 3. 主评分与辅助评分必须同时保留

### 固定声明延迟的完整近端主评分

主评分直接复用 `run_validation_engine.si_sdr_span_with_identity`，不新增 SI-SDR 正则化或
归一化定义。raw 为 mic0，延迟 0；CALL 与 ASSISTANT 固定补偿 **160 样点 / 10 ms**。
该值来自已有 API 的源码声明：默认 NS 一帧为 10 ms，16→16 kHz 重采样延迟为 0。
CI/本宿主工程 tiny 必须核实每一帧 telemetry 声明 10 ms；不使用目标相关性或冲激峰位置
拟合延迟。它是源码声明的块延迟，不是 HPF/BF 的频率相关相位或物理传播延迟校准。

主参考 mask 固定为 `[24000,24000+Nnear)`。按 raw/CALL/ASSISTANT 的固定延迟计算公共有效
span，要求完整原近端区间都有效；不足即失败，不截断为容易评分的子片段。
`primary_target_lag_searches=0`、`parameter_searches=0`。

逐例保存三种 SI-SDR、三种 `reference_identical` 和两个相对 raw 的差值。
near-only 的 raw 与 clean 精确相同，所以原 canonical 函数可能给出很大的有限 epsilon
正则化分数，同时 `identity=true`。保留这个真实恒等属性和原值；整链输出的负 delta 不
改写为零，也不因基线是恒等而从主汇总中删除。零能量等合法 null 原样保留并计数；非有限
数字则属于方法完整性失败。

汇总按 scene/profile 分开，保留每个说话人的 4 个原句差值、有效和 null 数，计算每人均值
与中位数，再汇总 8 人均值的中位数及范围。说话人等权，避免长句增加话语权。不从 128 个
相关视图编造置信区间、显著性或普遍独立性。

### 原 canonical 完整输出辅助评分

原 `dualmic_profile_support.validation_semantics` 全部保留，使用完整场景输出。其既有
目标对齐包含源码声明延迟附近 **±3 ms** 相关性精修；render/interference 的 maxcorr
诊断还包含 **±100 ms** 搜索。两者都登记为辅助方法，不能据此改变主延迟、来源、profile、
参数或结论选择。因此不能笼统写“所有 lag search 都是 0”。

辅助结果和原辅助汇总的 identity 规则保持不变；主汇总单独保留恒等基线负 delta 和 null。
两组指标的有效区间及对齐约定不同，不保证数值或方向一致，报告必须并列呈现。含双讲场景
的已知 interference 投影衰减是描述性分解，**不是纯远端 ERLE**；不设置 `echo_audio`
来伪装纯回声真值。不根据任一个指标更好而隐藏另一个。

## 4. 二进制、宿主、源码和执行预算

先由独立 AP portable 工程入口在 GitHub Actions 从干净、准确公开 source 构建并封存
`ap_process_pcm`、`ap_build_info_dump`。本次使用其 `AP_CURRENT_PORTABLE_V1` /
`PASS_ENGINEERING_ONLY` 包；该工程状态不代表语音收益、物理 SSC305 或真实房间评测。
bundle revision 必须与本次实际公开冻结的 harness revision 一致。原 DSP/配置参照
`4eec2329be9f2138c7ac73e8dd59026f3dc0a3ba` 的字节相等关系由构建入口检查；实际构建 revision
独立记录，不能把研究分支构建声称为该历史 main 原提交的二进制。

原 CI 工程回执保留。若测量宿主不同，必须先显式执行该二进制的新宿主合成工程 tiny，核对
同一二进制、声明延迟、默认 tuning、宿主和系统库身份。矩阵本身不自动执行工程 tiny 或
元数据查询，也没有兼容失败后的替代 binary。实际音频 subprocess 使用 AP helper 的
`execution_environment()`，与宿主库身份观察采用同一环境；身份不符即失败。

| 阶段 | 有界预算 |
| --- | --- |
| 新输入构造与回读 | 总 wall 120 s；0 解码器、0 音频处理器调用 |
| 固定矩阵、回执和哈希收尾 | 总 wall 600 s；128 次音频调用、单进程顺序执行、0 重试 |
| 单次处理器 | wall 30 s；失败立即停止，保存前缀 |
| 独立读者 | 总 wall 600 s；0 解码器、0 音频处理器调用 |
| 总输出 | 最多 4000 文件、1 GiB；128 输出 1767.36 s，不能扩例 |
| 工程回执复制 | 复用 AP 原上限：512 文件、64 MiB；仍包含在总输出上限内 |

源码控制闭包绑定计划、执行器、既有 source-only 控制、实际一方导入、AP 工程控制和 authority。
真实执行前当前文件必须与准确 Git revision 一致，完成后复核；输出保存同一控制源码快照。
原始大归档和 source receipt 重验，不重新下载或解码。来源准备中的旧角色及其 10 文件
闭包仍按原 a058 revision 校验，不能因后续研究修改旧锁。

失败不自动重试、补例或放宽预算。失败目录保留实际输出和错误；若最终封存失败，撤销
成功 report/manifest，保存 `failed-report.json`/`failure.json`。独立读者拒绝失败前缀，
要求恰好 128 个预定调用目录、每目录恰好 command/execution/stdout/stderr/output/trace/
continuity 七文件，并验证顺序 128 次处理耗时之和不超过记录的矩阵 wall 时间。
原命令的处理器路径必须是原执行目录中的已核验 bundle binary；搬移后不要求旧路径仍存在。

## 5. 结果保全和角色约束

新 corpus `tier=validation-grade`、`split=validation`。`sealed_data=true` 只表示输入 bytes
与生成方法已哈希冻结；**不表示盲集、不可访问 holdout 或没有既往曝光**。
本专属 harness 核验 `data_use`，只暴露这一个固定 128 次矩阵，不提供训练、优化或候选选择入口。
现有通用 authority 可以把 validation-grade 作为 optimizer 的 validation 角色；它没有在
平台所有入口强制理解本次 `optimizer_selection_allowed=false`。因此导出的 corpus 不是
平台级硬 ACL，本合同没有授权这样的 optimizer 使用，通用机制迁移须另立方法变更。

成功目录保留：完整 source 包和新输入，原与选用工程回执，portable binary 包，准确控制源码，
每次 command/returncode/wall/stdout/stderr/PCM/逐帧 telemetry/continuity，64 组主结果和128组
辅助结果，主/辅汇总及完整文件哈希闭包。`progress.json` 记录前缀；最终成功状态为
`MEASUREMENT_COMPLETE_DESCRIPTIVE_ONLY`，质量决定为 `NO_PROMOTION_DESCRIPTIVE_VALIDATION`。

独立 `verify` 重新校验归档、source receipt、输入合成 bytes、命令、帧连续性和两组评分。
它会进行确定性合成重构与数学评分，**不运行被测处理器或解码器**，也不重新执行宿主工程
测试；旧实际处理输出是评分输入。保存原执行宿主观察，不把读者机器当成原计时宿主。

本次不覆盖人工听评、ASR/WER、KWS、真实 RIR、机器人自噪、移动/时钟漂移、物理通道映射、
目标 SSC305 算力或新的房间。它补充已准备新原句的有限整链证据，不单独完成长期平台的
真实设备、多房间、四麦及长期数据质量目标。

## 6. 复现入口

先在已公开冻结且干净的 checkout 计算 `f05-dualmic-validation-v1.json` 的 SHA-256，记为
`PLAN_SHA`；实际 checkout revision 记为 `PUBLIC_REVISION`。下列路径为待明确填入的占位符，
目录必须全新、在 checkout 外，且不得与 source/corpus/bundle/工程目录互相嵌套。
实际运行命令、起止、返回码和输出应另行封存。不能把 tiny 成功视为真实实验已执行。

```bash
python3 tests/validation/frontend_evolution/test_f05_dualmic_validation.py

python3 tests/validation/frontend_evolution/f05_dualmic_validation.py build \
  --source-archive /absolute/dev-clean.tar.gz --source /absolute/prepared \
  --output /absolute/new-f05-corpus \
  --harness-revision PUBLIC_REVISION --plan-sha256 PLAN_SHA

python3 tests/validation/frontend_evolution/f05_dualmic_validation.py run \
  --source-archive /absolute/dev-clean.tar.gz \
  --corpus /absolute/new-f05-corpus/corpus.json --bundle /absolute/ap-bundle \
  --engineering-receipt /absolute/host-engineering/engineering.json \
  --output /absolute/new-f05-measurement \
  --harness-revision PUBLIC_REVISION --plan-sha256 PLAN_SHA

python3 tests/validation/frontend_evolution/f05_dualmic_validation.py verify \
  --source-archive /absolute/dev-clean.tar.gz --output /absolute/new-f05-measurement \
  --harness-revision PUBLIC_REVISION --plan-sha256 PLAN_SHA
```

若当前宿主与 bundle 原工程记录完全相符，可不传 `--engineering-receipt`；这只选择已有工程
记录，不触发新执行。没有真实通过的工程包或新宿主工程回执时，停止在该具体条件，不能
用 stub、静态语法检查、源码 tiny 或历史 binary 代替。
