# audio-pipeline：开放研究、双/四麦前端演进与端侧参考交付方案

日期：2026-10-05（Asia/Singapore）  
计划标识：frontend-evolution-v1  
文档状态：研究推进方案，尚未执行下列新实验；不是音质/性能验收报告。  
已核查软件基线：37a1792861a89c815bec462f819f3deac7d29b09（v2.3.55）。  
新增深入审查对象：jensen199105/aispeech-earbuds，561cd5975e93bae036b3f14060650a208d1b3573。

## 1. 总决策

新阶段允许算法结构修改、独立实现、许可允许的第三方后端、有限参数实验、神经网络训练/微调、流式化、量化、FFT/SIMD 优化和双/四麦拓扑对照。此前 candidate-zero 约束不延伸为本阶段的研究禁令。

已有 v2.3.55 是对照和回退基线，不是新候选的效果上限。I025–I040 等原始记录、失败、评估方法和结论不改写；新假设使用 FE 工作包和新实验 ID。允许在新授权、新数据和明确假设下研究同一算法家族，不能把旧结果偷偷改为支持新候选。

四麦分两项验收：原生四路输入/几何/处理/资源裁剪属于功能交付；四麦优于双麦属于需要数据证明的效果结论。前者不应依赖后者成立。

最终维持一个产品核心和一套权威评估器：经典双麦 C2、经典四麦 C4，以及经独立确认才提供的轻量增强可选档。失败候选和离线强基准保留研究证据，不无限扩张默认后端。

物理资格仍独立：当前 E001 的 v2.3.16/57e4c64… 资格身份不因最新软件发布而被自动改写。后续选择新物理资格对象，单独提交 source/release/BSP/config/policy 迁移记录；不以研究授权替代实际 DUT 证据。

## 2. 新仓库的核查结论与吸收方式

本项目 THIRD_PARTY.md 已列入 aispeech-earbuds；本次是从概念引用升级为机制审查，不重复新增同名登记。[S01]

审查的 earbuds master 为 561cd597…，最近该提交日期为 2022-04-03。GitHub 元数据 license=null；已读部分头文件包含 AISpeechTech 公司版权声明。元数据本身不是完整法律审查，也不能证明权利来源。[S02–S04]

| 已看到的实现 | 研究价值 | 不可外推的结论 |
|---|---|---|
| sevc_bf.c 引用不同间距的双麦 Q24 资源；运行路径围绕两麦和三个输出波束 | 固定多波束、频域加权、离线系数设计、运算复用 | 不是任意坐标四麦 BF；不直接复制其系数到新几何 |
| sevc_bfpost.c 区分持久局部状态和共享临时工作区 | 内存生存期分析、可验证的 scratch 复用 | 不能把会跨帧使用的噪声/增益状态误当 scratch |
| sevc_config_phone.h 有 BF/GSC/BFPOST/NN/AES/VAD/AGC 等开关 | 多阶段协作、可裁剪构建和场景配置 | 宏存在不证明当前默认构建启用、可运行或有正向收益 |
| 同一配置 WAV_CHAN=4、MIC_CHAN=3、REF_CHAN=1；BF 代码仍按双麦处理 | 明确 mic_count 与 render_count 分离 | 四个 PCM 通道不是四麦 |
| 16 kHz、FFT=512、frame_shift=384 的配置 | 帧适配、窗口和延迟审查 | 384/16000=24 ms；外层 10 ms API 不会自动消除内部帧等待 |
| 定点复数乘加和 Q 格式常量 | 溢出、缩放、饱和和浮点/定点对照 | 在耳机芯片适合的实现不必然在 Cortex-A32 更快 |

授权分轨：许可清晰的项目可在条款范围内编译、修改、链接和实验；来源/许可待核实的资源标记 REFERENCE_REVIEW_ONLY，不复制其源码、表格、权重或二进制进入公开发布物。可继续参考公开论文和功能结构，生成自身系数、数据和独立实现。研究身份不是免除第三方许可要求的通行证。[S05]

这一分轨只影响相关资源，不阻塞整个研究计划。检查代码许可、依赖许可、权重许可、训练数据条款和再分发权限是五个独立字段。

## 3. 参考体系

| 优先级 | 参考 | 具体用途 |
|---|---|---|
| 第一批 | 本仓库 B0、raw/单麦、固定双麦平均 | 回退与归因基准 |
| 第一批 | Athena Signal | 坐标阵列、DOA、MVDR/GSC、多通道 AEC 对照 |
| 第一批 | SOF TDFB | 离线滤波器设计、分数延时、固定 FIR 波束、白噪声增益约束 |
| 第一批 | WebRTC APM/AEC3/NS/AGC2 | 全双工、失配恢复、语音保护、先验信噪比、输出噪声增益限制 |
| 第一批 | SpeexDSP、libfvad | 低资源 AEC/预处理和独立经典 VAD 基准 |
| 第一批，资格分轨 | aispeech-earbuds | 多波束/后滤波/工作区/定点组织；执行复用取决于许可与构建资格 |
| 第二批 | ODAS、Pyroomacoustics | 定位与跟踪分离、几何仿真、噪声/房间/运动对照 |
| 第二批 | 当前 RNNoise、GTCRN、UL-UNAS | 少量固定单通道神经增强对照 |
| 第二批，先离线 | H-GTCRN 两个明确变体 | 空间分离与轻量神经增益协作，不先当作已流式实现 |
| 扩展池 | DeepFilterNet、DTLN/DTLN-aec、NARA-WPE | 效果参考、非线性回声、去混响专项 |
| 热点确认后 | PFFFT/KissFFT、平台向量内核 | FFT、缩放、数据布局与数值/资源比较 |
| 仅条件性参考 | XMOS lib_voice、ESP-SR | 授权/平台二进制限制核清后研究；不承诺 SSC305 可直接移植 |

对每个外部项目固定 upstream URL、完整 commit、依赖 commit、模型 SHA256、补丁集、编译器和构建配置。分开记录 pristine upstream 和 adapted variant；不能把移植补丁后的成绩直接称为上游原版成绩。

2026-10-05 的补充观察：

- RNNoise 官方 README 指出 GitHub 是便利镜像，最新源位于 Xiph GitLab；冻结时同时记录上游身份与外部模型文件哈希，不能沿用旧版参数量/耗时。[S10]
- UL-UNAS 已有 2026-02 发布的流式 ONNX 入口，可与 GTCRN 进入同一小规模候选轮，而不是重复大规模 NAS。[S11]
- H-GTCRN 在 2026-09-18 澄清 masking_on_noisy 与 masking_on_iva、分别提供权重；论文 Masking 1/2 标签存在对应差异。当前 infer.py 读取整段文件。前端包含 FD-WPE/AuxIVA，因此完整因果流式资格需另证，不由 GTCRN 骨干名称推断。[S12]
- WebRTC 当前主线有 neural residual echo estimator 实现和 TFLite 模型接口。可增加“经典线性 AEC＋神经残余估计”的研究方向；源码存在不等于权重已获授权、依赖适合 A32或默认启用。[S13]

## 4. 工作包、依赖与最终产物

| ID | 工作包 | 依赖 | 终态产物 |
|---|---|---|---|
| FE00 | 新研究授权、来源/许可/版本冻结、基线封存 | 无 | research manifest、reference lock、范围清单 |
| FE01 | 模块效果测量、适配器、因果与延迟校验 | FE00 | 单一评估入口、负例测试、基线对照矩阵 |
| FE02 | 1/2/4 麦数据与几何契约 | FE01 | ULA4/UCA4 配置、通道/校准/失效契约与测试 |
| FE03 | 双/四麦 BF、DOA、受控转向 | FE02 | DAS/分数延时/固定滤波/自适应对照及选择结论 |
| FE04 | SYNC/AEC/RES 与 BF 联合拓扑 | FE01；四麦联合部分依赖 FE03 | 路径变化/双讲/转向恢复报告和拓扑选择 |
| FE05 | NS/VAD/AGC 的语音保护与噪声约束 | FE01 | 模块改善、退化范围和固定候选 |
| FE06 | 机器人噪声、坏麦及运动状态融合 | FE02，联调 FE03–05 | 失效检测、受控降级与数据来源分离 |
| FE07 | 神经增强/神经残余回声研究 | FE01，集成依赖 FE04–05 | 原生/适配/流式/量化分别验收的候选 |
| FE08 | FFT/SIMD/定点、内存/实时工程化 | 各支线稳定候选 | 资源模型、性能与等效性证据、受控 SDK |
| FE09 | 独立确认、整链/KWS/ASR、发布和收口 | FE03–08 | Pareto 决策、C2/C4、条件性效果档、失败归档 |

最多并行三个研究通道：空间、经典全双工/增强、神经。共用 FE00/01 的基础设施。测量工具可以先改，但相同实验不得由候选修改自己的裁判。

## 5. FE01：先确保“比什么、怎么比”成立

输入输出契约记录：sample_rate、mic_count、render_count、channel_map、interleaved/planar、S16/float 标度、frame/hop/window、latency、lookahead、reset/flush、样本数、时间戳域、算法开关和有效配置。

原版适配器保留原生 hop，通过有界 FIFO 对接 10 ms 外层；不改写为伪 10 ms 算法，不补造缺失参考、不无限缓存。精确报告 FIFO 最坏等待、算法群延迟、模型前视和设备缓冲。帧率转换不必等最小公倍数周期才输出，应按实际可用样本调度。

必须有负向测试：交换通道、错误 PCM 标度、参考信号提前/滞后、隐含归一化、输出样本丢失、伪静音输出、NaN/Inf、旧模型/旧配置哈希、执行器部分失败但返回零、整段未来泄漏。不能把第三方 CLI 的退出零作为全部样本成功的充分条件。

效果按四层测量：单模块、固定两模块、真实整链、固定下游 KWS/ASR。每层保留实际开关，AEC 单体 ERLE 与全链残余回声抑制分开。

对齐规则：只补偿协议允许的固定延迟，禁止逐样本动态对齐、逐用例挑最佳参考或归一化输出到有利响度。对 BF 的已知方向 oracle 仅作上限，对部署候选使用真实估计方向；两者成绩不能混合。

参考目标必须明确是干声、直达/早反射目标、保留房间响应目标，还是频响处理后的目标。常规降噪、波束形成与去混响不使用同一个未经解释的干声分数。相同输入分别跑完整自适应算法后的结果一般不能线性相加进行模块贡献归因；分量回放需固定处理状态/权重并标作分析对照。

保留现有 81 用例作历史回归，不把它们同时当新候选的独立效果验证集。

## 6. FE02/03：四麦和 BF

统一坐标使用米；明确坐标轴、正方向、角度定义、参考麦和通道映射。公开支持集首轮限定单麦、双麦、四麦；内部 active_mask 支持坏一路后剩三路，避免额外造一个三麦产品 SKU。

ULA4 为线性四点，UCA4 为圆周四点；允许任意四点 XYZ。麦数与波束数分开。四麦加一路回声参考是五路逻辑输入，不与四麦采集混为一谈。数据可先通过多通道 PCM 离线/实时回放输入，不依赖真实四路 Codec 已就绪。

四麦与双麦对照分为同孔径、同麦间距两组，避免把孔径增加收益误判为麦数收益。双麦保留当前 35 mm；其他尺寸只登记为研究几何，不宣称对应已制板硬件。

BF 候选顺序：
1. 原始参考麦、既有固定双麦平均、四麦等权平均（sanity 基准）。
2. 几何驱动的因果整数/分数延时求和（共同因果延迟必须计入）。
3. SOF 思路的离线设计固定 FIR/固定频域滤波求和：先扫有限长度和对角加载，再独立确认。
4. 有限固定波束库与方向选择；线性首轮 3–5 波束、环形首轮 8 方位是候选预算，不是已选择参数。
5. 在线 GSC/MVDR：只有方向不确定性、协方差、数值条件和白噪声增益保护具备后才进入部署候选。

耳机仓库提供固定多波束的参考，但自身系数按我们的几何重新设计。固定 MVDR 派生系数不称为在线自适应 MVDR。波束库 K 变化须计入运算、状态和转向成本。

DOA 起点：GCC-PHAT/SRP-PHAT 参考，有限角度搜索，置信度、目标保持、迟滞和限速；定位、选择服务对象和增强分离。优先允许控制面提供方向提示，不要求系统必须永远追踪最强声源。线性阵列按可辨认方向等价类评价，不能要求其凭空消除几何镜像歧义；平面环形不包装成完整三维定位。

共同检测：方向错配、增益/相位失配、非共同时钟、坏麦、削波、近场和混响；报告波束频响、旁瓣、白噪声增益和目标损伤。动态转向采用受控权重插值/交叉淡化，并验证新增瞬态与 AEC 重适应。

## 7. FE04：同步、回声和联合拓扑

保留两条主要拓扑对照：
A. 每麦轻预处理 → 固定/受控 BF → 单路线性 AEC → RES/增强。
B. 共享 render 时基/延迟观测 → 每麦线性 AEC → BF → 共享后级 RES/增强。

A 优先低成本；B 是空间动态下的效果对照。首轮不永久维持三四条产品管线。多通道 AEC 可共享参考分析与控制，但自适应滤波状态逐通道保留，不能拿一条回声路径套全部麦克风。为保护跨通道空间关系，独立非线性后抑制/AGC 不默认放在 BF 前。

SYNC 研究涵盖固定/变化延迟、独立时钟、分数残差、丢帧、timestamp reset、codec reopen、periodic reference ambiguity。外部库自带延迟跟踪时不重复叠加两个未知控制环；记录谁拥有最终时基。

AEC 以当前 MDF、WebRTC AEC3、SpeexDSP、Athena 作原版/适配对照，核查失配检测、粗/精或前/后景滤波、饱和保护、单双讲更新节奏、增益变化与路由变化分开处理。不能把已有的机制重新算新增功能。

RES 以近端保护为共同约束：强回声衰减必须同时报告近端损伤和双讲恢复。研究 NN 残余估计与经典线性 AEC 的组合，权重来源和运行依赖单列；不先用全神经 AEC 替换所有经典路径。

指标按远端单讲、近端单讲、双讲、转换段分别报告。路径恢复使用预先冻结的窗口和持续时间定义，保留未恢复/censored 例，不通过事后改阈值消除失败。

## 8. FE05/06：NS、VAD、AGC 与机器人噪声

NS 分支先比较当前 Wiener、Decision-Directed 先验 SNR＋语音存在概率，以及 BF 后滤波。允许新增结构和有限参数试验；不再把旧噪声域诊断结果当作当前候选禁止令。噪声越小不等于语音越好，必须同时报告 ESTOI、目标失真、谱伪影、辅音和尾音损伤。

VAD 比较当前实现、libfvad/WebRTC 经典 VAD、固定 Silero 参考。阈值在开发集以相同召回标定后冻结。神经 VAD 不是标签真值。AEC 双讲概率、通用语音概率、KWS 触发是不同语义，不简单共用一个 bool。

AGC 比较噪声上限约束、可信语音电平、增益增速/恢复、limiter headroom 和饱和保护。现有禁止增益上升接口保留；新增条件应来自同处理域、同时基的观测。语音电平与噪声输出分别报告。

机器人噪声分成相关结构噪声、扩散噪声、非平稳电机启停、轮地摩擦、风噪/气流、其他人声、电视音乐；不能只叠加独立白噪声来夸大阵列收益。

麦克风健康不是“能量小就坏”。联合饱和、断流、频谱异常、通道一致性与历史；覆盖安静场景、遮挡、近端说话、单侧噪声等反例。4→3/2→1 的降级要绑定有效几何，平滑输出，并协调回声路径状态。

已有 IMU/轮速/电机指令可作为可选控制面输入，先验证时间同步、相关性和失效模式。合成运动标签与真实遥测分开；不能把电机电流/PWM当作天然正确的声学参考，也不能在移动时永久降低语音敏感度。

## 9. FE07：神经/混合增强

首轮单通道候选：当前 RNNoise、GTCRN、UL-UNAS；双通道离线参考：H-GTCRN noisy/IVA 两变体。DeepFilterNet、DTLN-aec 与 WPE 按专项触发进入扩展池，不同时训练所有项目。

每个模型依次验收：原生复现 → 统一适配 → 因果/流式 → 配对效果 → 量化/小型运行器 → Arm 参考构建。未通过因果验证者保持 OFFLINE_REFERENCE，不与实时候选混排。对 H-GTCRN，将 FD-WPE、AuxIVA、mask target 和 NN 分开计时与消融；不能只报 GTCRN 骨干计算量。

因果验证用相同前缀、不同未来后缀的输入：除明示 lookahead/输出延迟外，既有输出不应改变。审查 centered STFT、全句归一化、未来 padding、离线多迭代分离、双向网络、训练/推理状态差异和 flush 行为。

允许使用新训练和微调；训练、超参选择、独立验证三种数据角色严格分开。量化按具体算子和 recurrent state 的数值需求选择 PTQ/QAT/混合精度，不因“8-bit”名称认为 A32 自动更快。先测运行器完整代价，再决定专用 C 推理、精简 ONNX 或 TFLite；不在默认 SDK 同时携带多个大型运行时。

研究可产出 mask/特征/噪声估计等中间信号，但同一频域中权威的增益所有者要唯一，避免 NN、RES、NS 无控制地连续压制。

## 10. 数据、评价与统计

使用现有 validation authority/locks/replay；增量引入 Pyroomacoustics 几何生成、Microsoft AEC/DNS 开发数据、RealMAN 动态阵列、Pyramic 标定/方向数据与适当 RIR。具体下载/修改/再分发按原条款核查，不默认下载 TB 级全集。[S14–S18]

数据分层：D0 工程回归；D1 公开训练/开发与合成开发；D2 新的独立跨说话人/房间/噪声/设备验证；D3 真正隔离的最终留出；D4 产品真实数据。已看过的 D3 退为回归，不继续称 blind。不同 seed 共享相同语音/房间不算独立来源。

首轮筛选建议上限：12 场景家族×4 输入形态×3 seed×4 独立语音/房间组合=576 个 case，8–12 秒为主，长转换/状态测试另列。不可适用组合标 N/A，不为凑数量虚构输入；按风险交互抽样，不穷举所有角度/距离/噪声/房间笛卡尔积。进入最终候选后再扩独立说话人/房间和长负样本。

建议场景含：干净近端、安静、平稳/非平稳噪声、相关机身噪声、风噪、远端回声、双讲、回声路径变化、用户移动/BF 转向、失配/坏麦、低音量/削波/丢帧。

| 模块 | 主要评价 | 保护项 |
|---|---|---|
| BF/DOA | 目标保持条件下的干扰抑制、ESTOI、方向误差分布 | 方向歧义、WNG、频响、转向瞬态 |
| AEC/RES | 有效远端段 ERLE、残余回声、恢复时延 | 双讲近端质量、起音/尾音、发散 |
| NS | ESTOI、同域失真、噪声衰减、感知代理 | 语音损伤、音乐噪声、幻觉/伪语音 |
| VAD | 同召回下 FPR、onset/release、帧/事件误报 | 不与 KWS FAR/h 混用 |
| AGC | 语音电平、稳定时间、输出噪声和峰值 | pumping、clipping、静音放大 |
| 整链 | 固定 ASR WER/CER、固定 KWS FRR/FAR、对话中打断 | 自身 TTS 误唤醒、远端泄露、延迟/资源 |

DNSMOS/AECMOS 仅作固定版本的感知代理；不替代人工听评，域外不可靠时不当唯一裁判。实际采用 AECMOS 等工具前记录模型、服务或本地实现、可用性和条款，不依赖不可用服务卡住其他指标。[S17–S18]

初始成功门槛属于研究建议，不是既有产品标准：例如 BF/NS 在目标独立场景达到 ≥1 dB 主指标改善或 ≥0.01 ESTOI 改善；相邻关键场景不越过预先定义的语音保护边界；VAD 在固定召回下相对降低 FPR ≥20%；AGC 降低非语音噪声 ≥2 dB 且稳态语音响度变化受控。不同候选只选择一个主目标，绝不从多个指标事后挑一个好看的作为成功理由。

使用按独立说话人/房间/录音分组的配对 bootstrap 和尾部统计；不把逐帧当独立样本制造显著性。FAR 必须报告负样本时长与不确定区间；零误触不等于已证明极低 FAR。功效不足为 INCONCLUSIVE，不伪装 PASS。

## 11. 资源与数值预算

B0 的 50,000 B pipeline+runtime arena 硬上限保持原定义，不偷偷放宽。新研究配置单独命名并单独预算。

以下为建议的首轮工程筛选预算，尚非实测可达承诺：

| 类别 | 状态+工作区建议上限 | 额外约束 |
|---|---:|---|
| C2 新经典双麦 | 96 KiB | 先证明效果，再向 B0 成本收敛 |
| C4 固定/受控 BF 经典四麦 | 192 KiB | 不乘四复制整条单麦链 |
| 四麦自适应研究候选 | 512 KiB | 仅在独立效果收益下保留 |
| 轻量神经候选 | 权重≤2 MiB；状态/工作区≤4 MiB | 运行器/系统库/RSS 另报，效果不值成本则保留离线参考 |

预算包含组件内部 heap/arena/scratch，但不把线程栈、I/O环、Flight Recorder、libc/运行器常驻和页缓存藏起来；发布报告需列出各项与峰值口径。外部参考原版允许更高资源，超过预算不阻止学术比较，只不能标为保守端侧候选。

16k/S16 输入双麦 64,000 B/s、四麦128,000 B/s；每10ms分别640和1280B，只说明输入吞吐，不能据此推断全链CPU或内存翻倍。

每次记录同 runner 单线程 cpu_ms/audio-second、p50/p95/p99/max、RSS/分配高水位、arena、静态库与最终链接text/rodata、模型/运行器、最坏控制切换与算法延迟。跨架构指令数、QEMU耗时不能直接折算 SSC305 CPU。

未来板端继续保留10ms硬截止、p99<9ms优选/<10ms硬限、p95<7ms、名义零丢帧/overrun等既有目标；CPU分母明确为一个核，不能用双核平均隐藏worker饱和。现在可做工具链/ELF/静态栈分析和QEMU功能验收，真实调度/热/功耗与板端时延保持未测。

数值顺序：FP32原型 → 测热点 → vector/定点/混合精度。一致性区分同二进制重复确定性、跨后端数值等效、实际声学指标保持；算法结构改变不能强求和旧算法PCM完全相同，也不能把原本bitwise失败悄悄转成容差通过。

共享频谱/临时工作区仅在FFT尺寸、窗口、时基、频域含义与生命周期一致时启用。先画状态和scratch活跃区间再复用，专测诊断开关、重配置与多实例并发不串扰。

## 12. CI、仓库与发布组织

不建平行评估器、不新增十几条一次性 workflow。复用现有 validation/resource/replay/SDK 架构，增加一个矩阵化研究入口、source lock 和结果索引。路径只是一种建议：tests/validation/frontend_evolution/ 与 docs/research/frontend-evolution-v1/；最终以现有仓库结构最小改动为准。

短实验分支PR合入研究路径可被允许，但不自动修改默认DSP/发布配置。FE00需把新的研究授权写成明确路径与行为契约；历史 program 不被假装重新出现READY任务。release-neutral研究改动不制造软件版本；更改公开默认/接口时按SemVer执行。

外部源码与权重在只读快照或隔离缓存，构建环境无production secret、无写main/token、无宿主挂载权限，依赖下载固定hash/allowlist。模型加载和构建脚本按不可信输入处理。大音频/权重不放Git，也不为每个job复制同一份长日志/PCM；保留hash、失败最小复现和有保留需求的证据归档。

CI层次：PR快速契约/短回放；算法候选paired quality/resource；需要时完整矩阵；nightly/手动长稳/fuzz。文档PR保持轻量，未知路径默认扩完整门禁。失败样本先落盘再执行退出门禁，禁止失败被CLI吞掉。

每轮记录base、candidate、有效配置、source/model/data/evaluator hash、帧/前视契约、计数与退出码、逐例结果、bootstrap、资源、决策与限制。license欠缺、未运行、基础设施失败与声学失败是不同状态。

多麦公开API在原型稳定后再冻结。若扩容公共数组/结构破坏2.x ABI，则进入3.x预发布；不能仅改宏却继续宣称ABI不变，也不为保住版本号留下长期双套shim。新增独立接口不破坏ABI时，不为研究本身强制升级主版本。

## 13. 执行顺序与停止条件

第一批可执行任务：FE00授权/锁定，FE01重放B0并验证测量；建立原始单麦、双麦基准，接入WebRTC/SpeexDSP/libfvad和Athena的最小适配；审核earbuds有效构建路径/许可，不运行未经审查脚本。

第二批：FE02统一几何与四路输入；FE03分数延时/固定滤波；并行FE05语音保护与AGC/VAD；数据和评价不随候选移动。

第三批：FE04四麦联合AEC、FE06坏麦与机器人噪声；FE07少量神经候选；只有潜在收益者进入昂贵流式化/量化。

第四批：FE08资源/数值工程化，FE09独立确认和固定下游评测；选择C2/C4，条件性增加一个效果后端，生成reference SDK、操作文档、资源/效果矩阵、SBOM与可复现证据。

有限实验建议：每家族首轮不超过4种结构，每结构不超过3个预注册配置，最多两个开发迭代轮；这不是永远禁止后续研究，而是本轮预算。超预算或否定后再继续需新假设/新记录；不能反复在同留出集调试。

各工作包允许五种诚实终态：QUALIFIED、REJECTED_WITH_EVIDENCE、OFFLINE_REFERENCE、INCONCLUSIVE、BLOCKED_EXTERNAL。功能必须明确实现/未实现；任何失败不得借上述分类含糊写成支持。

完整软件研究收口条件：原生单/双/四麦契约与ULA/UCA可运行；所有纳入候选可复现且有效配置可见；关键单模块/整链与固定KWS/ASR已评；独立确认无裁判污染；部署候选因果/实时资源资格完成到可测边界；许可/模型/数据来源明确；没有未归类实验或临时默认；SDK/profile/evidence绑定，物理未测清单清晰。

不要求每条研究路线都成功。复杂方案未显著优于基础实现时，保留简单方案是合格结论。若研究候选有声学收益但超A32预算，保留为效果上限，不能包装成SSC305已可部署。

## 14. 事实来源（核查日2026-10-05）

引用均指公开原始仓库或官方文档。未在本次执行新算法benchmark。动态上游在FE00执行时仍须固定完整commit和模型hash。

```text
S01 https://github.com/jiying2007/audio-pipeline/blob/37a1792861a89c815bec462f819f3deac7d29b09/THIRD_PARTY.md
S02 https://api.github.com/repos/jensen199105/aispeech-earbuds/branches/master
S03 https://github.com/jensen199105/aispeech-earbuds/blob/561cd5975e93bae036b3f14060650a208d1b3573/algorithms/modules/sevc/src/sevc_bf.c
S04 https://github.com/jensen199105/aispeech-earbuds/blob/561cd5975e93bae036b3f14060650a208d1b3573/algorithms/modules/sevc/include/sevc_config_phone.h
     https://github.com/jensen199105/aispeech-earbuds/blob/561cd5975e93bae036b3f14060650a208d1b3573/algorithms/modules/sevc/src/sevc_bfpost.c
     https://github.com/jensen199105/aispeech-earbuds/blob/561cd5975e93bae036b3f14060650a208d1b3573/algorithms/modules/sevc/include/sevc_mem_alloc.h
S05 https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository
S06 https://github.com/athena-team/athena-signal
S07 https://thesofproject.github.io/latest/developer_guides/algorithms/tdfb/time_domain_fixed_beamformer.html
S08 https://webrtc.googlesource.com/src/+/refs/heads/main/modules/audio_processing/aec3/subtractor.cc
     https://webrtc.googlesource.com/src/+/refs/heads/main/modules/audio_processing/ns/noise_suppressor.cc
     https://webrtc.googlesource.com/src/+/refs/heads/main/modules/audio_processing/agc2/adaptive_digital_gain_controller.cc
S09 https://github.com/dpirch/libfvad
     https://github.com/xiph/speexdsp/blob/master/include/speex/speex_preprocess.h
     https://github.com/introlab/odas
S10 https://github.com/xiph/rnnoise
S11 https://github.com/Xiaobin-Rong/gtcrn
     https://github.com/Xiaobin-Rong/ul-unas
S12 https://github.com/Max1Wz/H-GTCRN
     https://github.com/Max1Wz/H-GTCRN/blob/main/infer.py
S13 https://webrtc.googlesource.com/src/+/refs/heads/main/modules/audio_processing/aec3/neural_residual_echo_estimator/neural_residual_echo_estimator_impl.cc
S14 https://github.com/LCAV/pyroomacoustics
S15 https://github.com/Audio-WestlakeU/RealMAN
S16 https://github.com/fakufaku/pyramic-dataset
S17 https://github.com/microsoft/AEC-Challenge
S18 https://github.com/microsoft/DNS-Challenge
     https://github.com/microsoft/DNS-Challenge/blob/master/DNSMOS/README.md
S19 https://github.com/fgnt/nara_wpe
```
