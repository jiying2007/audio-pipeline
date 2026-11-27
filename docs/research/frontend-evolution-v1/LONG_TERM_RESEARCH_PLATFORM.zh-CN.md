# 长期科研平台运行手册

本手册把已有的来源准入、仿真、算法适配、评分、失败复现和原件恢复连成一条可执行路径。
它不新建评分器、仿真框架或数据授权。执行总项为
[#968](https://github.com/jiying2007/audio-pipeline/issues/968)，原件恢复为
[PR #969](https://github.com/jiying2007/audio-pipeline/pull/969)，实际 authority 身份与
canonical 失败复现修复为 [PR #970](https://github.com/jiying2007/audio-pipeline/pull/970)。
这些链接分别记录实现、审查与后继精确源码资格，不能互相代替。

长期研究首先复用现有资产：同一输入与时轴、明确的算法边界、固定测量合同、完整不利结果，
以及可恢复的原始材料。新增后端或 seed 不会自动增加独立样本数，也不赋予旧数据新的角色。
当前研究 authority 见 [RESEARCH_ONLY_EXECUTION.md](../../RESEARCH_ONLY_EXECUTION.md)；
商业发布、历史产品认证和固定 72 小时 soak 不是研究前置条件。

## 1. 从一个已冻结问题开始

每项新实验先记录实际 base/head、单一假设、输入及角色、处理链、指标和时间窗、接受/停止
规则、总预算及失败保留位置，再执行。方法修复与算法候选分别建立证据，不能用同一项改动
同时修改评分语义并证明候选更好。现有 [PLAN.zh-CN.md](PLAN.zh-CN.md) 是原批准计划，
不是运行结果；[README](README.md) 与各结果页保留实际执行链。

| 要回答的问题 | 首先复用的入口 | 结论允许到达的范围 |
| --- | --- | --- |
| 输入、帧、状态重置或来源是否正确 | tiny fixture、source/admission、失败包 | 工程合同成立或失败；不产生音质结论 |
| 哪种扰动先在哪一阶段出现 | S001/S002、motion-v2、stage-prefix、FE04 | 固定模型上的诊断；阶段首差不等于根因 |
| 新算法是否在相同输入上有不同输出 | 已准入外部基线、固定适配器、canonical 指标 | 指定开发数据和配置的对照；保留负项/null |
| 能否泛化、在 SSC305 上运行 | 独立数据角色、真实目标端单独合同 | 需要新的实际证据；host/QEMU 不能替代 |

## 2. 来源、五类权利和数据角色

[sources.json](../../../.github/research/frontend-evolution-v1/sources.json) 和
[contracts.py](../../../tests/validation/frontend_evolution/contracts.py) 是外部执行准入入口。
每项来源单独登记 `code / dependencies / weights / data / redistribution`；必须把
commit/tree、归档与材料化文件 hash、许可证/notices、所选执行范围和 admission receipt 绑定。
`PENDING` 或未解决的 `RESTRICTED` 不会因为下载成功变成可执行。
代码许可、模型权重许可、语料获取/使用范围和再分发条件不能相互推定。

真实音频继续使用它自己的 source/data admission。第三方 AEC 库的 `data=NOT_APPLICABLE`
仅说明该源码准入没有携带语料授权；不能据此读取任意真实录音。已有设备资料的清单入口是
[device-capture-dataset-inventory-v1.json](../../../.github/research/frontend-evolution-v1/device-capture-dataset-inventory-v1.json)，
清单、公开可见性、训练许可和后续再发布授权是不同事实。新来源、新用途或新的权利声明
需要对应材料；现有缺口保持原状态。

当前四层数据权威来自
[research-authority.json](../../../validation/research-authority.json)，其中 optimizer role 与
数据 tier 不能混为一个标签：

| tier | 可用 optimizer roles | 使用边界 |
| --- | --- | --- |
| regression | development / validation / shadow | 工程回归；允许开发划分，不建立独立最终结论 |
| research-validation | development / validation / shadow | 要求封存数据；按已登记角色使用 |
| validation-grade | validation / shadow | 不允许开发划分，不供候选搜索 |
| validation-grade-blind | 无 optimizer role | 要求封存及 blind key；不回流到优化选择 |

终态是 `independent-research-review`。可选的 `target-resource / hil-soak` 单独绑定真实
设备与测量，不是所有研究都必须执行的商业门槛。已查看的 test-root 不因换目录、切窗、
重采样或新增模型而转成 development。既有 FE04 两对已披露语音、空间投影及循环拼接，
也不会变成新的 holdout。

## 3. 已有仿真和压力覆盖：按问题选择入口

以下均为现有生成器或执行器；本手册没有重新执行它们的声学效果，也不引入新的扰动扫描。
S001/S002/S003 的阶段状态以
[system-robustness-v1-result.json](../../program/iterations/system-robustness-v1-result.json)
为准：`CLOSED_CANDIDATE_ZERO_FOUNDATION_ACTIVE_REGRESSION`。
历史候选搜索已关闭，固定回归基础继续使用；新 FE 实验须有独立身份，不能重开旧机制搜索。

| 入口 | 实际覆盖 | 必须保留的限制 |
| --- | --- | --- |
| [build_system_robustness_corpus.py](../../../validation/tools/build_system_robustness_corpus.py) / S001 | 15 例：多档 SNR、echo path、双讲、双麦增益/样点错配、capture clipping/DC、样点/帧 drop 与 duplicate、稳态/瞬态电机噪声、稀疏房间 taps | 合成压力与故障定位；sample slip 是保持输出长度的时钟代理，不是物理 ADC/DAC 独立采样钟测量 |
| [build_aec_transition_corpus.py](../../../validation/tools/build_aec_transition_corpus.py) / S002 | 8 例：far/near/doubletalk、路径切换、speaker acoustic gain、render level、硬削波播放、tanh 软饱和播放 | 数字 render 保留非线性之前的信号；固定 taps 和静态失真不等于真实扬声器模型或完整非线性转场 |
| [build_aec_motion_corpus.py](../../../validation/tools/build_aec_motion_corpus.py) / motion-v2 | 12 例：刚性扬声器/麦克风对、六面墙一阶像源、静止/平移/旋转、两档直达增益、两类宽带激励 | 准静态线性分数延时模型；不是全波、完整扩散混响、真实 Doppler、独立移动声源或实测房间 IR |
| [build_stage_interaction_corpus.py](../../../validation/tools/build_stage_interaction_corpus.py) | 复用 S001/S002，展开 40 个 stage-prefix 视图，定位最早可观测变化 | 相关的阶段视图不是独立样本；首差与因果机制分开 |
| [SYNC_FAULTS.md](SYNC_FAULTS.md)、[SYNC_ROUTE_RESET.md](SYNC_ROUTE_RESET.md)、[SYNC_TIMESTAMP_ROBUSTNESS.md](SYNC_TIMESTAMP_ROBUSTNESS.md) / FE04 | 已披露 ULA4/FIR33 投影输入；固定 320-sample lead、320→800 route jump、+250 ppm producer drift；另有 route-reset、timestamp 权威、固定 jitter/dropout 对照 | BF 后的 mono 观察；不等于全部 1/2/4 麦同步组合。绝对 delay 含声学/BF 路径，不等于纯 transport lead；合成 jitter 不是设备统计 |
| [array_qualification.py](../../../tests/validation/frontend_evolution/array_qualification.py)、[ARRAY_NATIVE.md](ARRAY_NATIVE.md) | 真实消费 1/2/4 通道；10 类几何/mask/校准 × 3 解析信号 × 2 插值，共 60 例/目标；channel map、极性/增益、分数延时、chunk/reset、异常值边界 | 解析参考与工程资格，不是空间语音增益证明；64k 帧加速测试不是等时长物理 soak |
| [BF_AEC_ORDER.md](BF_AEC_ORDER.md) | 36 场景：2 对已披露语音 × dual/ULA4/UCA4 × 两种声学 bank × none/steer/path；BF→单 AEC 与每麦 AEC→BF | 固定 oracle 时轴/门控；不包含实际 SYNC/DTD/RES/NS/AGC 的整链。4 秒原语音循环形成 16 秒场景，不增加录音独立性 |

数组研究的 4 通道输入、每麦四个模块实例或后置 mono 投影，**都不等于 SDK 公共 4 通道
pipeline 已完成**。通用 canonical `evaluate_case`/PCM processor 路径当前接受 1/2 麦；
4 麦研究使用自己明确的投影/逐通道边界和现有指标函数，不能偷偷改成 mono 标签送入通用路径。
真实公共 API/ABI 扩展须接续既有 [ARRAY_SDK_BRIDGE_R0.md](ARRAY_SDK_BRIDGE_R0.md)
及 [FE09_R1_ARRAY_ABI_ADR.md](FE09_R1_ARRAY_ABI_ADR.md) 的边界。

源码可查的命令入口如下。输出应放在 checkout 外的全新目录；seed/时长来自已冻结合同，
不要把命令模板当作重跑已关闭候选的授权：

```sh
python3 validation/tools/build_system_robustness_corpus.py --output /absolute/new/s001 --seed 5107 --seconds 5
python3 validation/tools/build_aec_transition_corpus.py --output /absolute/new/s002 --seed 6107 --seconds 6
python3 validation/tools/build_aec_motion_corpus.py --output /absolute/new/motion-v2 --seed 4107 --seconds 8
python3 tests/validation/frontend_evolution/array_qualification.py --self-test
```

数组完整工程资格已有 `--output /absolute/new/array --execution-source "$source_sha" --require-arm`，
同一目录回读使用 `--verify`；`source_sha` 必须为实际执行源码的 40 位 commit。
`--require-arm` 要求工具链与 QEMU 实际存在，不允许缺少时写 PASS。FE04 各执行器要求
各自的完整 predecessor 证据：例如 `sync_faults.py --base-evidence ... --correlation-evidence ...`，
`sync_timestamp_robustness.py --sync-predecessor ... --reset-predecessor ... --exact-predecessor ...`。
它们同时要求 `--output` 与 `--execution-source`，`--verify` 仍须保留上述来源参数；先读对应
文档和 `--help`，不要用另一个实验的输出目录冒充前驱。

现有自动回归接线见
[system-robustness-v1.yml](../../../.github/workflows/system-robustness-v1.yml) 和
[quality.yml](../../../.github/workflows/quality.yml)。仿真首版已经覆盖同步、路径、非线性及
多通道的各自工程边界；目前缺的是独立真实输入与这些因素的物理联合验证，而非另一个
通用 generator。后续新增压力只针对已证明的具体覆盖缺口，先固定单一变化和预算。

## 4. 同一评分权威与失败复现

通用入口是 [run_validation.py](../../../validation/tools/run_validation.py)，音频材料化和
数值测量继续由 [run_validation_engine.py](../../../validation/tools/run_validation_engine.py)
及已有 stage-profile 适配完成。PR #970 修复的是“实际加载哪份 authority 就绑定哪份字节”
与失败输入运输；历史 `authority.json` v1 和冻结评分器不重写。

以下 S001 调用沿用现有 workflow 的参数；`source_sha` 应与已构建 `processor` 的真实
源码一致，不能拿当前 HEAD 替代别处编译的 binary 身份。S002 与 motion-v2 分别使用
`validation-aec-transition-development.json`、`validation-aec-motion-development.json`：

```sh
python3 validation/tools/run_validation.py \
  --source-revision "$source_sha" \
  --corpus /absolute/new/s001/corpus.json \
  --policy validation/policies/validation-smoke.json \
  --dataset-lock validation/datasets.lock.json \
  --processor /absolute/build/ap_process_pcm \
  --output /absolute/new/s001-report/report.json \
  --evidence-manifest /absolute/new/s001-report/evidence-manifest.json
```

是否使用 `--enforce` 由该运行的既有 policy/合同决定；不得为获取绿灯临时改变。
报告中的输入、processor、policy、dataset-lock、authority 和源码身份都要保留。研究型外部
adapter 可复用 canonical 指标函数，不因此成为公共 SDK processor 或新的独立评分器。
far-only residual、mixed-output SI-SDR、近端电平/peak/clipping、恢复曲线和 null 的语义分别
保留；不能用单个比例指标掩盖近端衰减，不能从目标语音搜索最佳 lag 来提高分数。

[validation_reproducer.py](../../../scripts/validation_reproducer.py) 的修复后入口：

```sh
python3 scripts/validation_reproducer.py --self-test
python3 scripts/validation_reproducer.py \
  --corpus /absolute/new/s001/corpus.json \
  --report /absolute/new/s001-report/report.json \
  --destination /absolute/new/failure-pack
PROCESSOR=/absolute/build/ap_process_pcm sh /absolute/new/failure-pack/CASE_ID/reproduce.sh
```

`CASE_ID` 用包内真实失败 case 目录名替换。原件按 mic/render/reference 角色分开保留，WAV
由 canonical loader 解码，不能把 RIFF 头送入 raw PCM。`input-manifest.json` 同时封存
原文件和解码 PCM hash；同 basename 不覆盖。每 case 携带确切 canonical invocation 源码
快照，`reproduce.py` 在导入前核 hash；重定位后仍检查相同输入。可选 `--processor` 会立即
回放并传播非零退出码；输入损坏、既存输出或处理失败都不能生成假成功。

方法 tiny fixture 的通过只证明复现机制。科学差异仍须回到实际原输入、固定配置和测量合同。
历史 source guard 若不接受新代码，应在独立检出恢复对应 reader/完整依赖，或走既有精确
源码派生机制；不得改历史锁、剥掉 hash 检查或以新报告覆盖旧证据。

## 5. 新 AEC3/APM 参考入口

实现分为三段，来源、工程与语音对照各自留下回执：

| 层 | 入口 | 必须成立的条件 |
| --- | --- | --- |
| 固定来源及构建 | [WEBRTC_AEC3_SOURCE.zh-CN.md](WEBRTC_AEC3_SOURCE.zh-CN.md)、[webrtc_aec3_source.py](../../../tests/validation/frontend_evolution/webrtc_aec3_source.py) | freedesktop 2.1/M131 分发源码、Abseil/wrap 归档及五权核对；完整源树复验；无隐式依赖下载构建 |
| adapter 与工程 fixture | [WEBRTC_AEC3_ADAPTER.zh-CN.md](WEBRTC_AEC3_ADAPTER.zh-CN.md)、[webrtc_aec3_ci.py](../../../tests/validation/frontend_evolution/webrtc_aec3_ci.py) | 两个固定 mode；真实 binary；repeat/reset、未来扰动前缀、1/2/4 通道、零/尾/异常、预声明延迟观测；实际 host/动态库绑定 |
| 六例描述性参考 | [webrtc-aec3-reference-v1.json](../../../.github/research/frontend-evolution-v1/webrtc-aec3-reference-v1.json)、[webrtc_aec3_reference.py](../../../tests/validation/frontend_evolution/webrtc_aec3_reference.py) | exact 原 Speex ZIP；工程 PASS bundle；同一已披露 mono 投影输入；12 次固定执行；不搜索、不调参、不晋级 |

源码是固定分发包，不声称最新/未经改动的上游 WebRTC。`aec3` 关闭外部 HPF/NS/AGC，但
AEC3 本身包含 residual suppression，因此它与 Speex MDF 的差异不能归因为纯线性 AEC。
`apm` 在同一 AEC3 上打开固定 HPF、moderate NS 和已明列参数的 AGC2；不是“只换 AEC 核”
的整链控制。完整冻结参数以 adapter 文档和实际 requested/applied config 为准。

16 kHz、160 samples/10 ms、S16LE；capture 1/2/4 与独立 mono render 分开。显式
channel map 后输出相同通道数，拒绝尾帧补齐、隐式 downmix 和覆盖。上游若不支持某个
请求通道，必须显式 `UNSUPPORTED`，不能把其它通道的成功写成该通道成功。
六例语音对照本身使用历史 post-BF **mono**，不证明四麦声学或公共四麦 SDK。

首个完整 10 ms 输入块的可用时间、宿主函数完成时间、PCM 信号时轴延迟分别记录。
由固定源码缓存结构预声明 `aec3=128 samples/8 ms`、`apm=224 samples/14 ms`；工程脉冲/
chirp 观测若不符则失败查因，绝不从真实 target 拟合 lag。参考对照同时保留 raw 时轴与
固定补偿后的有效窗口，缺失尾部不补零；HPF 的频率相关相位不冒充另一个固定延迟。

本地只需验证源码材料或阅读构建计划，不在共享宿主重复编译外部库。完整 build/工程步骤
使用既有 Frontend Research 的独立 AEC3 job，和历史候选执行隔离。固定来源回读及取得
合格 bundle 后的参考入口是：

```sh
python3 tests/validation/frontend_evolution/webrtc_aec3_source.py verify --prepared /absolute/bundle/prepared
python3 tests/validation/frontend_evolution/webrtc_aec3_reference.py run \
  --bundle /absolute/bundle --archive /absolute/archive/speex-original.zip \
  --output /absolute/new/aec3-reference
python3 tests/validation/frontend_evolution/webrtc_aec3_reference.py verify --output /absolute/new/aec3-reference
```

`run` 是真实 12 次声学执行，只有对应预登记和预算允许时才执行，`verify` 是原件回读。
换宿主先按 adapter 文档运行真实 tiny engineering，再用
`--engineering-receipt /absolute/new-host/engineering.json` 传入当次回执，保留原 CI 回执；
研究库 hash 与实际系统依赖/宿主身份分别核对。`ldd`、host wall-time 与 x86 工程结果都不
代表 SSC305 的 CPU、RSS、p99、热或功耗。

### 本轮结果入口（仅此处维护新 AEC3 的可变进度）

2026-11-28：实际源码 `819849ee3ed6b269b8417ef8700eecfcf29f7958` 的 Actions run
[46043812502](https://github.com/jiying2007/audio-pipeline/actions/runs/46043812502) 已完成真实构建与工程验证。
同一 binary 在 Debian 13 宿主工程复验后，六例已按冻结合同执行 12 次并独立回读，
状态为 **VERIFIED_DESCRIPTIVE_REFERENCE**，无训练、搜参或额外声学重试。
完整结果、失败保留、数据与计时边界、原件 SHA256 见
[本轮真实结果](WEBRTC_AEC3_RESULT_20261128.zh-CN.md)。
AEC3 远端抑制与双讲保真呈现明显取舍；本轮保持诊断参考，不替换默认算法、不产生晋级或实机结论。
方法集成 [#970](https://github.com/jiying2007/audio-pipeline/pull/970) 与研究集成
[#971](https://github.com/jiying2007/audio-pipeline/pull/971) 各以实际受保护 merge/main 记录为准。

## 6. 原始 ZIP 长期恢复与证据保全

F03 的 [DUALMIC_ARCHIVE_RECOVERY.zh-CN.md](DUALMIC_ARCHIVE_RECOVERY.zh-CN.md) 与原 PR #969（已汇入方法集成 #970）
提供一个严格限定的 D1/D2 恢复入口：既有 D3 锁指定原 run/attempt、source、artifact、
474165229-byte ZIP 及 SHA256，复用冻结 D2 reader 只读核验。不是任意工件导入器，
也不重新运行 D5/D6/D8/D9 以制造替代证据。

```sh
timeout 300s python3 -B tests/validation/frontend_evolution/dualmic_archive_recovery.py \
  --archive /absolute/archive/frontend-research-dualmic-stages-d1-42321833898-attempt-1.zip \
  --output /absolute/new/dualmic-original-recovery
```

先取得**完整原 ZIP 字节**；重新打包的 ZIP 不能满足原 hash。保留归档、成员清单、原
report/manifest、input/source locks 和恢复回执。恢复无需当前 Actions 元数据仍存活，
但不能改写原在线入口的 `expired` 事实或伪造 live acquisition receipt。哈希、run/source、
缺失成员或 reader 依赖不符时失败；冻结 reader 不兼容新源码时使用对应独立检出。

恢复成功状态 `RECOVERED_ORIGINAL_EVIDENCE_NO_NEW_EXPERIMENT` 只证明原证据取回。
实际恢复身份与既有测量仍各自记账。另一个算法的 Speex 原 ZIP 使用它自己的精确来源锁，
不能把 D1/D2 包作为替代。原件仍可下载时完成封存；短期 Actions 下载可用性不能作为长期
唯一保存策略，也不应为了过期工件重跑已关闭实验。

## 7. 受保护 PR/main 与失败运输

提交只是一份源码身份。每次变更保留 base/head、适用检查/`summary`、workflow run/attempt、
artifact ID/原 ZIP hash、独立回读和审查记录；head 移动后旧绿灯不能借用。仅经受保护 squash
PR 合并，再检查新的 exact main，不直推主线、不以手工跳过替代必需门禁。
PR #969/#970 和 #968 的结果以各自实际 SHA 与 Actions 为准，版本号不是科学完成状态。

同 run 上传后的 reader 也必须核对实际 artifact identity 和完整性。暂时不可见、过期、
下载失败、超时或源身份不符属于运输/测量失败，保留真实尝试并作限定修复；不能把它解释成
算法质量好坏，不能取消 hash/attempt 检查或改评分阈值让运输问题变绿。
来源准入 PASS、方法测试 PASS、工程 PASS、描述性对照和独立确认应分别陈述。

## 8. 已关闭范围与下一阶段真实缺口

| 固定历史范围 | 保留的决定 | 本平台不据此推导 |
| --- | --- | --- |
| [D5 target gate](DUALMIC_TARGET_GATE_D5_RESULT.zh-CN.md)：只去掉 target unity cap | 受控诊断、无推广；收益与远端电平/peak/clamp 风险一起保留 | 所有 AGC 或 gate 都无效，或可以直接取消保护 |
| [D6 单一帧内 ramp](DUALMIC_GAIN_RAMP_D6_RESULT.zh-CN.md) | 有效测量、NO_ADVANCE，该候选关闭 | 任意 ramp 都无效；允许换参数继续原实验 |
| [D8 broadside 输出 lag=0](DUALMIC_BROADSIDE_OUTPUT_D8_RESULT.zh-CN.md) | 有效测量、NO_ADVANCE；此前失败不覆盖 | 下一种 lag 扫描已获授权；D7 关联已经被证明为因果 |
| [D9 受限增益回升](DUALMIC_GATED_RISE_D9_RESULT.zh-CN.md) | 有效测量、NO_ADVANCE，单一候选关闭 | 全部动态增益结构没有研究价值 |
| [GTCRN/UL-UNAS 固定后置配置](EXTERNAL_BASELINES.md) | `REJECT_D0_POST_AEC_CONFIGURATION`；停止该 AP 后置固定图/流式适配配置 | 模型在所有任务无用，或换名重跑同一已否决配置即可产生新证据 |

I025–I040、#962 和 S003 已终止机制链继续保持原结论；新 AEC3 参考不重开它们。
[Speex 参考](SPEEXDSP_AEC_REFERENCE.md)、SOF FIR、BF/AEC 顺序及已做阶段诊断均直接复用，
不再以“补基线”为名重复旧声学批次。

下一阶段需要增加的是与明确研究问题相匹配的证据：合法且独立的新说话人/房间/设备输入，
真实双麦/四麦校准和方向误差、实测同步/route/采样钟分布、扬声器非线性及路径联合变化，
以及 SSC305 对应编译器/系统/路由上的实际资源测量。已有合成分项覆盖不能证明这些联合
物理因素已测过；没有独立数据准入或实际 DUT 的项目继续为 `NOT_RUN`/`BLOCKED`。
CALL 质量与 ASSISTANT 的 ASR/KWS 也需各自固定任务、目标及数据合同，不能用几条 SI-SDR
改善代替识别、听评或交互结论。

首版平台的可持续性来自复用上述入口并保留每项证据边界。新的结构算法实验应由固定参考
结果暴露的具体缺口驱动，逐项预登记、限定预算并接受有效负结果；不需要再建一套并行
评分器、泛用仿真框架或重复历史仓库清单。
