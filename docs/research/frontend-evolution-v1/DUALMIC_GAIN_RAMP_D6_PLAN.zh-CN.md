# D6 双麦 AGC 帧内线性增益过渡：执行前合同

状态：PREREGISTRATION / NOT_RUN。实验 FE-DUALMIC-GAIN-RAMP-D6。
基线 main 6c7752800838f2c7fd707593c658f250a071e98c，tree c3ff7678513e687806fc7d3de5710dd0302bbebe。
2026-11-11 对43条分支及公开开放 issue/PR 的同题检查未发现占用。
本合同与完整输入锁须作为单独提交远程冻结，经独立合同复审通过后才实施；
具体源码须再次独立审查，通过后才打开触发实验的 PR。此前没有本候选的声学结果。
研究追踪 #942；总研究 #657 继续开放，本轮只有一个实施分支、一个候选和一个现有工作流内的研究 lane。

## 1. 新假设与边界

D2 的原 AGC 在每个160样点帧上使用单一实际应用增益；该增益经过原状态更新、
output unity cap 和整帧 peak cap。原件示例 pair0 的 near-only 第193至194帧
显示微小非零输入伴随状态增益继续上升。这说明原增益随帧变化，不证明可听伪影、
主要损伤原因或移除 AGC 的正当性。D4 固定窗结果也不能以局部符号替代整段结论。

本轮提出唯一真实质量候选：保留原状态轨迹，只将输出域整帧常数增益改为
从前帧最后实际乘法系数到当前原末端增益的帧内线性过渡。
它是否改善现有双讲 SI-SDR，同时不触犯预注册退化屏障，由完整结果回答。
D3 的数字零 guard 不合并；D5 的 target gate 删除不合并。
D5 已有混合 SI-SDR 与远端相关 RMS 上升，原失败及结果字节保持。
原 target/alpha/gate 参数、状态方程及全部安全保护均不变，不扫描参数。

本轮不是已关闭的跨帧 state slew、error-adaptive release、paired target/limiter、
15dB global cap 的复活：原12-byte状态每帧必须与原基线相同。
新结构只改变本帧输出系数轨迹。禁止根据结果继续试第二种形状、长度或阈值。

## 2. 原输入、完整锁与来源

唯一实际输入为原 D2 run42321833898/attempt1，
source cc853616685b9faf7880e6d8f8f1a89d187d342a、artifact13553232106。
ZIP 474165229 bytes，SHA256 a3ab7823fdcd7586c3b72eb214b5536dcfb7531fdf0b1611d49e1575a29b2c3d，
3551成员、861385743解包字节；report SHA256
f259693095d73e8cca74e15cc60f0c4e1e157cfecab32706bee35926f2fca9ea，
manifest SHA256 e43fa150e38d65ecb43020f19a403547fce9634736735b0367512040b9c58a63。
冻结时 API expired=false，expires_at=2027-02-05T01:02:47Z；
这只是元数据检查，不冒称已经完成本轮下载准入。

新 dualmic-gain-ramp-d6-input-lock.json 包含原准入全部身份/大小/预算、
原 D2 的完整60例 catalog/events/输入/参考 hash 和顺序，以及全部23个冻结依赖的
路径、Git blob、字节数、SHA256。它不是只有计数的小型摘要。
原 D2 lock 为174511 bytes，Git blob903e5fc75ae49308b48ea9627d98b764a6515990，
SHA256 2626ef61838a4a9ecbfd944221905f91e8e77cfcaff945ac8f5ff60650c943cf；
嵌入对象须严格等于该锁解析值。D1/D2/D3 合同、原准入器、canonical scorer、
全部实际 Python 传递依赖（包括 device_alignment 与 package __init__）均显式锁定。
运行时每个仓库内导入模块必须属于留存集合，不允许未封存依赖。

复用未改动的原 D3 严格 ZIP 准入器及完整原 D2 读回。
先核全部原件，之后才构建。原 C/header 来自已准入 source archive，
原 baseline 直接链接封存静态库；归档成员须通过其原manifest及新锁核验，
不以当前仓库生产文件或一份新生成基线代替原件。
完整 archive、父来源、原 D1/D2 report/manifest、admission 与命令绑定保留。
生产 src/include/cmake/版本及 preset 树对象在锁中固定，不改其字节。

固定矩阵 A56+C4、60视图、35916帧、5746560样点、8次原reset、362固定窗，
16kHz、每帧160。所有 case 以原顺序整流处理；不按窗口初始化。
reset 仅来自原 cli_discontinuity，在原frame300处理前同时重置两臂。
echo_path_change 不重置 AGC，不额外补 lost_frames 个零帧。
32例有clean-near参考，28例原null保持。数据继续是 disclosed-regression，
英语真实录音配合合成传播，中文来自同一句录音；不是新holdout或真实阵列声场。

## 3. 唯一 Float32 干预

从归档原 C 确定性生成隔离候选，重命名导出符号避免碰撞。
原 energy/RMS、target及target unity gate、alpha、state update 的代码保持原样；
CALL/ASSISTANT target -20/-18dBFS，limiter -2dBFS，target范围0.25..8，
alpha0.25/0.015、原epsilon全部不变。
原 ap_agc_state_t 仍恰好12字节；另设8字节 P(float32)、initialized(uint32)，
不将 extra state 写入原状态，也不改变生产API。

定义 cap(c) 为当前帧的两个原条件，按此顺序、逐操作Float32执行：
1. 若 !allow 且 c>1.0f，c=1.0f。
2. 若 f32(peak*c)>limit 且 peak>f32(1.0e-6)，c=f32(limit/peak)。
peak 来自当前输入帧，limit 为原state.limiter_linear。
不能替换成无条件 min(c,limit/peak)，也不能去掉原1e-6guard或改变比较顺序。

G 为原state更新后、经过原两cap的实际末端增益。
流开始或reset：P=+0.0f、initialized=0，本帧 S=G。
以后 S=cap(P)，P是上一帧最后实际乘法系数，不是output/input、均值或clamp后比值。
对 i=0..158，冻结 weight-first 中间结果：
- d=f32(G-S)
- w_i=f32(float(i+1)/160.0f)
- q_i=f32(d*w_i)
- h_i=f32(S+q_i)
i=159 明确赋 h_159=G，不靠插值累加碰到端点。
每样点 c_i=cap(h_i)，实际执行 y_i=原clamp(f32(x_i*c_i),-limit,limit)。
在乘法之前保存实际 c_i；帧末 P=c_159、initialized=1。
cap(G)与G、c_159与G必须逐位相等。首帧/reset帧及S=G帧必须完整PCM和系数等于基线。

所有中间赋值均为标准IEEE binary32，FLT_RADIX=2、FLT_MANT_DIG=24、
FLT_MAX_EXP=128、FLT_EVAL_METHOD=0、FE_TONEAREST。
固定 C11/O2/ffp-contract=off/Wall/Wextra/Werror，不用fast-math/FMA或重新结合。
该运算与 ((G-S)*(i+1))/160 的另一舍入次序不同，以以上冻结次序为准。

延迟结论限于不增加未来帧或额外帧缓冲。原算法本来使用整帧energy/peak，
所以不称逐样点因果或零前视。安全cap收紧可以产生较大边界跳变，
不声称系数绝对连续、无click或主观更好。

## 4. 实际观测与强控制

各帧保存 baseline/candidate before/after 四份完整12-byte状态；
baseline须逐帧逐字节复现原 gain.csv 的gain/target/limiter及原输出PCM。
candidate的全部12-byte before/after 必须与baseline相同，任何分叉均测量无效。
near-only/silent-render不再要求全部PCM相同，因为本干预也适用于allow=true；
它们同样参加质量退化屏障，不能搬用D5的旧控制定义。

额外保存真实 extra before/after、实际S/G、allow/reset/digital-zero标志，
trace每帧84字节，以及全部5746560个直接C观察的Float32乘法系数。
系数必须是本次实际使用值，不能只存Python重建值。
独立Python只读重建逐帧状态公式、S/G、全部160系数、cap和sample clamp，
与全部实际系数及PCM逐字节比较；使用原Float32原语，不另跑候选DSP。
raw/bounded/effective target、alpha、cap/clamp事件若由公式重建须明确标记，
不将其称为未插桩的内部测量。

记录首差帧/样点、改变帧/样点数、边界系数/帧内首末系数、两臂cap/clamp计数。
数字零/非零仅是数字性质，不充当人工语音标签。
NaN/Inf、错误长度/顺序/控制位或extra初始化位均失败。
所有allow=0系数必须<=1，所有输出满足原sample clamp边界。

## 5. 原评分与执行前发展屏障

只调用冻结 D1 measure_lane/stage_delta、唯一si_sdr_span及D19 energy。
共同物理跨度[0,N-160)、输出[160,N)，原1秒窗及短尾窗全部保留。
不搜lag、不改窗、不归一化、不改变level或PCM格式。
baseline所有端点、共同跨度、窗口、native levels须等于原D2。
两臂完整SI-SDR、rms_dbfs、linear peak及null原因全部报告，
包含全部中文、far-only/path-change/render-gap和近端电平风险。

D19现有rms_dbfs=20*log10(max(raw_RMS,1e-12))，peak=max(abs(samples))。
本轮不改此测量方法，所谓RMS无增量只指该冻结带floor指标，
不声称证明floor以下raw energy没有上升。

先判 measurement_valid，再判 development_screen：
- 全32个有参考共同跨度 candidate-minus-baseline SI-SDR>=0。
- 每一个原有可评分固定窗的同一差值>=0，不能用中位数抵销负窗。
- 16个nominal/weak双讲视图中，至少一个共同跨度差值严格>0。
- 全24个far-only/path-change/render-gap视图，在共同跨度、每个原固定窗、
  native_whole_buffer_energy三个层级的原rms_dbfs和linear peak均不得上升。
- 全60例分别要求最终sample clamp改变样点数<=该例baseline。
- 全部参考/null身份与原因精确保持；非有限、漏项或身份漂移属于测量失败。

以上比较使用原canonical全精度值，不加epsilon、不四舍五入后判断、不事后换阈值。
这可能拒绝无害的末位负差，也可能被末位正差满足严格>0；
正值不是预注册的实质改善量，不能称显著或可听改善。
有效但任一屏障失败为NO_ADVANCE，不是MEASUREMENT_INVALID；
有效且全满足为DEVELOPMENT_SCREEN_PASS_NO_PROMOTION，
至多允许考虑不改候选的独立确认，不自动执行后续研究或推广。
无实际测量/身份/算术/闭包/预算不合格为MEASUREMENT_INVALID，保留首失败。
不得在见到结果后增加、删除或放宽门槛。

## 6. 工程、自读回与负例

C/Python工程控制覆盖两profile、allow0/1、原gain初值0.25/0.75/1/2/8、
zero/signedzero/tiny/normal/peak输入、非有限拒绝、完整原state等价、
首帧/reset/常数G中性、上升/下降/不变增益、unity/peak收紧、
1e-6边界、端点G、extra状态连续性及原事件坐标。
工程测试不是声学证据，也不增设第二个声学候选。

实际负例必须先完整验证未改动合格原件，再对锁内列出的40类篡改逐项验证：
样点、完整state、真实系数与端点、P/initialized/S/G、controls、target/alpha、
错窗/漏case/null、屏障结论/谓词、tree/source/argv、重新封存后的源码/header、
额外文件/空目录/symlink、失败phase/command、原admission/输入绑定/readback。
每项只有实现审查时冻结的专属预期拒绝理由才通过；
I/O、timeout、其它异常及未拒绝均为FAIL。只复制到隔离目录，不修改原件。

记录精确HEAD/tree、完整源码/输入/构建/命令/产物闭包；全部仓库依赖留存。
编译器记录lookup path、直接symlink目标、解析后的普通文件真实路径/hash/version；
实际argv使用真实文件。此例外仅限cc selector，不放开证据symlink。
不声称当前compiler/libc/libm等于原环境；baseline不复现就停止评分。
源闭包16MiB、result闭包256MiB，文件和空目录都严格核验。
每阶段输出与回执必须新建，不覆盖旧成功/失败；只允许本次刚创建的回执登记最终写盘超时。

## 7. 固定资源、工作流和落地

仅用现有公开 Frontend Research workflow 中新的scoped D6 job。
D6-only变更逐字节保持历史D1/D3/D4/D5 job区域，历史lane均不选中；
不用新的一次性并行workflow。checkout/upload action使用已锁SHA。
准入/build/run/analysis/readback/negative各300秒，包括I/O、hash与最终写盘；
每个子进程实际timeout=min(30,剩余阶段秒)，整job20分钟。
D5历史helper的具体timeout实现不改写；D6新实现必须在启动时硬限30秒，
不是结束后才检查。不得在失败后增加预算或换输入、编译flags、科学规则。

独占/tmp/ap-dualmic-d6/input及result，全部产物在checkout外，
始终上传完整首次失败与结果，原D2 ZIP以已锁原artifact独立保留。
无新模型、额外数据源、私有数据、付费服务、Codex Cloud/CLI/local、
ChatGPT Work或真机任务。此处GitHub Actions本身是既有公开仓库已授权CI，
不使用上述禁用资源。

合同独立复审后才实施，源码独立复审后才执行。
首次科学run与后续运输/文档提交身份分别登记。
exact-head Verify/required summary、独立审查、受保护squash合并、
fresh-main全部适用门禁分别核对，不借用旧head资格。
生产DSP/default/API/版本不变；没有听评、ASR/KWS、真实WAN、
完整反馈整链或物理SSC305资源结论。所有历史失败和关闭研究保持不变。
