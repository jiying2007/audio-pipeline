# D8 双麦 broadside 输出：执行前冻结合同

状态：PREREGISTRATION / NOT_RUN。实验 FE-DUALMIC-BROADSIDE-OUTPUT-D8，科学候选数1。
基线 main 1b5b01e0f2580ec9e05dfacff2ee1d292c438172，
tree db25581db2ad683499ec2c7b2e22686787d39db2，生产版本2.3.64。
追踪 [#947](https://github.com/jiying2007/audio-pipeline/issues/947)，前驱#944，总研究#657保持开放。
2026-11-11已通过连接器重新读当前main、required summary success及开放PR/issue；
没有同题D8占用，#925/#714不属于本轮。先冻结本文与完整机器锁，再独立审核准确字节；
实现须另经独立审核，才允许移动触发CI的ref或打开PR。本文不声称运行DSP或得到质量结果。

## 1. 独立假设、唯一干预与不变边界

原DUALMIC_RECORDED_SPEECH_V1_PLAN.zh-CN.md独立预定near broadside、两麦同相，
echo为35mm/60度合成TDOA。D7只建立实际lag/fallback状态与stage分数的有限关联，
没有证明“BF跟随回声”或“near损伤原因”，不能把已见关联当因果前提。
本轮只检验：在FULL tracking与状态完全相同的条件下，输出取零延时是否改善最终交付音频。

唯一数学改动位于src/frontend/ap_beamformer.c，
原blob cb9f5c3a0f8d2c910eff62e9599f866b444de3c3的逐样点循环：
const int output_lag = s->fallback_active ? s->fallback_lag : s->lag;
仅在生成的candidate研究副本中，准确一次替换为：
const int output_lag = 0;

另一个用于reverse/alias的局部lag表达式保持原字节，不把两处一起替换。
track_direction实际仍为1，不用LITE、tracking-off或把state.lag/fallback_lag清零。
原lag_score/cadence、fallback检测/strong-channel/hard/soft、权重、fallback_gain、
history、HPF、初始化/reset及全部下游源码不变；无参数扫描、第二候选或后继自动变体。
生产src/include/default/API/ABI、SDK2.3.64、既有结果和历史拒绝均不改。

两个完整pipeline各自从流首处理原输入，SYNC在BF后、Activity前读取BF mono；
SYNC、Activity、AEC、NS、AGC、VAD及控制可自然分叉。禁止给candidate灌入baseline gate、
控制或下游状态。所得是唯一干预的整链总效应，不是固定gate条件下的分解。

## 2. 唯一原件、完整矩阵与原角色

唯一原D2 run42321833898/attempt1，
source cc853616685b9faf7880e6d8f8f1a89d187d342a，
artifact13553232106，ZIP474165229 bytes，
SHA256 a3ab7823fdcd7586c3b72eb214b5536dcfb7531fdf0b1611d49e1575a29b2c3d。
原3551成员、861385743解包字节、report/manifest完整hash在机器锁内。
最后已查API未过期、expires_at=2027-02-05T01:02:47Z；不把元数据说成已完成本轮准入。

完整机器锁嵌入未经改动的D3原件准入身份、D2全部60例锁、原输入路径/argv/事件、
clean-near和父tap身份及嵌套D1/A/C来源。复用原严格下载/成员/路径/hash准入与完整D2读回，
再核原D1 payload、source/build/readback/phase及verify_origins到保留的内部A/C ZIP。
不另下A/C，不换包、重新生成、换参考、替代hash或伪造未直接读取raw的独立hash。

全部60视图=A56+C4，35916帧、每完整lane5746560样点、362固定窗、8原reset。
AEC实际30058帧/4809280样点，capture-only5858帧；每臂HPF71832次、BF/Activity/NS/AGC35916次、
独立时域RES仍0次。32近端参考、28原null，C mixed duplex不当clean truth。
原四个英语near/far pair与两profile相关，中文是同一句相关视图；全为disclosed-regression，
不是60独立受试者、独立holdout、真人阵列录音、MOS/ASR/KWS或物理目标证据。

## 3. 四种构建、独立中性桥与可逆观测

分别构建baseline plain/observed、candidate plain/observed，科学候选仍只有1。
全部使用准确当前HEAD的闭合selected-source archive与同一实际GNU compiler：
Release、-O3 -DNDEBUG、C_FLAGS空、SCALAR/MDF/EMA/BANDLIMITED、
mask1023、direction tracking on、fast_math=0，真实source_revision后缀见机器锁。
保留compiler lookup、symlink selector及解析后普通文件realpath/hash/version、
全部实际argv、compile_commands、generated headers、静态库、程序和日志。
不声称当前compiler/libc/libm等于原环境；baseline不等立即失败，不能改flags/容差。

只接受D7已验证的两种完整C_FLAGS顺序和完整Unity文档形式，不能接受任意token排列、
丢宏/额外flag、任意去注释或未知依赖。完整原生产根、notice、35冻结helper和新D8闭包
逐文件mode/blob/bytes/SHA256及根tree均绑定；所有运行时仓库imports有留存来源。
旧D1 builder和D7合同/代码完全不改，不通过改D7候选数0的断言运行新候选。

观测变换与唯一数学变换分开登记。七个生产函数定义rename分别为原D1五处
Activity/AEC/NS/AGC/RES，另HPF/BF定义改成_d8_real。生产函数体和调用点都不变。
D1最终main定义单独改成ap_d8_d1_main；再将D1 AGC wrapper定义
void ap_agc_process_controlled(ap_agc_state_t *state, float *samples,
准确一次改为
void ap_d8_d1_agc_process_controlled(ap_agc_state_t *state, float *samples,。
新D8同名wrapper只保存实际AGC before/after、调用这个未改body的D1 wrapper一次、
记录状态和执行时序，不反馈重建值。每一处before/after/inverse hash和完整changed-file集合保留；
同一D1文件上的两项变换按冻结顺序应用、逆序撤回，不能按path字典丢掉一项。

每帧独立记录两路HPF各before/after24 bytes、BF before/after180 bytes，
加frame/track_direction/output_alias/n的16-byte header，共472 bytes。
两个真实arm的全472 bytes逐byte相同；四条实际HPF输入/输出lane也须逐样点byte相同，
两边先真实记录、比较、保留各自descriptor，之后才允许共享一份内容。
绝不能复制baseline状态假装candidate观测，不能仅比较hash/一份fresh输出而缺原件。
实际AGC state为12 bytes（gain,target_linear,limiter_linear）且before+after=24 bytes/frame；
两臂分别保留。sizeof、每个offsetof、IEEE Float32和小端必须编译及运行核验。

每例必须同时满足：
- baseline plain/observed的最终PCM和原metrics JSONL逐byte等于原A/C；
- baseline实际D1全部7lane和control.csv逐byte等于原parent D1；
- baseline实际AGC的before/after三个字段回转为Float32后逐bit等于原D2 gain.csv；
  实际和独立重建的AGC f32输出都等于原D2 replay_final及原D1 agc_output；
- candidate plain/observed最终PCM和metrics逐byte相同；
- 全部near-only/silent-render在两臂的全部stream/state/control/metrics/endpoint逐byte不变。
其它场景的实际下游变化是实验结果，不误作为必须两臂相同的约束。

## 4. 连续状态与独立数值重建

原stream首帧初始化；只在原8个render-gap的frame300处理前重置HPF/BF。
flags=2、lost_frames=4不插新零帧；path-change事件不重置HPF/BF。
before必须等于前次after，两个HPF调用间完整state连贯；BF history为当前HPF输出原尾部。
实际track_direction必须每帧1，max_lag3，完整score、计数和fallback状态必须符合原时序。

baseline输出按实际after.fallback_active ? after.fallback_lag : after.lag重建，
candidate按0重建；沿用原normal/soft/hard、强弱通道、权重/gain及before.history的Float32顺序。
全样点bit相同，不能用tracked lag替代fallback有效lag，不能把重建值称真实内部观测。
实际NS输出、实际AGC before/after和原allow控制分别重建gain/target/peak/gate/clamp，
逐bit检查actual f32输出和状态，保留每帧peak-cap/gate/terminal-clamp事件。
所有lane和state有限；任何NaN/Inf、路径、顺序、历史、原件中性、代码或闭包错误为测量无效。

## 5. 固定交付终点评分与提前冻结的否决规则

主要终点为实际最终out.pcm的S16/32768，与原clean-near S16/32768比较。
准确调用既有dualmic_stages_d1.measure_lane及canonical si_sdr_span，
物理共同跨度[0,N-160)对应output[160,N)，全部原1秒窗和短尾窗，不搜lag、不挑pair/窗。
严禁aligned_si_sdr及会做±3ms搜索的通用评估路径。
保留每例/窗的原SI-SDR、null原因、D19 RMS dBFS/linear peak，native whole energy另列；
AGC float和上游stage仅为次要描述，不代替S16的候选判据。

所有比较用完整浮点精度，没有epsilon、展示舍入或平均后放行：
1. nominal/weak × CALL/ASSISTANT ×4pair的16个共同跨度delta各自>=1.0dB。
   这是有限研究预算的保守继续门槛，相当于canonical regularized distortion/target ratio
   至少约20.6%降低，不是听感JND、临床阈值、统计显著性或独立样本检验。
2. 全32有参考共同跨度及每个原可评分near窗delta>=0。全部正负/null行照原顺序保留。
3. 防静音假改善：canonical SI-SDR对全零estimate可能为0dB，不能因此战胜负baseline。
   使用原quality_metric_support.projection_gain_db；共同跨度输入完整raw S16两数组，
   delay_samples=160；窗[a,b)输入clean[a:b]与output[a+160:b+160]，delay_samples=0。
   适用的两臂gain均须finite且严格>-120.0dB，candidate>=baseline，不能只比较delta。
   -120是helper对极小projection的返回哨兵，不是全局数学floor，本处是明确screen。
   必需gain为None或finite但<=-120则NO_ADVANCE，NaN/Inf则MEASUREMENT_INVALID。
   适用性仅由原normalized clean span决定：count>=16且sum(reference^2)>1e-12，
   与原canonical SI-SDR一致。原zero-reference/too-short窗保持null和原原因，不产生自动否决；
   禁止依据candidate输出或得分决定适用性。
4. 24个far-only/path-change/render-gap及4个C视图，最终PCM在common、每固定窗和
   native whole的RMS及linear peak都不得上升。C无near truth保持null；
   此保守风险否决不代表C语音语义质量判断。
5. 全60视图canonical S16 clip count（abs(sample)>=32760）不得上升；
   从各自实际NS/AGC状态及全f32bit重建得到的实际terminal clamp count也不得上升，
   因-2dB limiter下S16 clip可能本来恒为0。峰值cap/gate/clamp不混成一个事件。
6. 原quality_metric_support._window_erle(echoRawS16,outRawS16,16000,160)
   与_settling_ms定义不变。24个far相关视图都测start0 convergence；
   16个path-change/render-gap再测start48000 recovery，far-only后事件保持not-applicable/null。
   必需两臂值均为finite且candidate<=baseline；合法None为NO_ADVANCE，不补0，
   非有限为MEASUREMENT_INVALID。保留完整curve、final level和能量。
   该时间相对各自tail目标，不能把更差终点造成的更快时间称音质改善，必须同时过能量否决。

身份/算术/连续性/原件/闭包/预算失败优先MEASUREMENT_INVALID。
测量有效但任一screen失败为NO_ADVANCE，关闭这一个固定候选，不再扫lag/参数。
仅全部通过才是REVIEW_FOR_INDEPENDENT_CONFIRMATION_NO_PROMOTION，
仍不能自动新跑、晋升生产/default或完成独立质量验证。

## 6. 精确lean文件映射、去重证据与512MiB可行性

机器锁retention.files是保存路径模板，{key}必须是原60 catalog key。
cases/{key}/shared保留4条实际HPF lane；candidate保留BF、reference/echo/AEC residual、
NSoutput/AGCoutput的6种独立f32内容、out.pcm、metrics、control。
两臂各保留state.bin（472B/frame）及agc-state.bin（24B/frame）。
每例retention.json保留去重前每个真实form/stream的长度/hash、逐byte比较结果、实际原路径、
最终源指针；observer回执另存receipts，不谎称未测baseline已观测。

baseline原7lane/control/PCM/metrics在实际比较后引用保留D2内部原件。
baseline BF先与其实际D1 aec_input或capture-only ns_input比较，再引用原D1对应lane。
candidate aec_input在AEC present时alias保留BF；ns_input alias保留AEC residual，
capture-only则alias BF；absent AEC三lane保留显式absent及0-byte文件，不伪造存在。
candidate plain/observed endpoint/metrics亦先实际比较再只留一份。
只允许按原顺序一次处理一例；先证明/记录，再atomic move或删除已被证明等价的重复内容，
不允许积攒两臂全量observer后事后压到预算。失败current scratch必须保留。

冻结新输出类别上限（bytes，包含临时、失败和最后写盘）：
- shared四HPF lane：91944960。
- candidate独立6信号：126670080=4*(3*5746560+3*4809280)。
- 双臂472B state：33904704；双臂24B AGC：1723968。
- candidate S16一次：11493120。固定小计265736832。
- candidate JSONL<=2048B/frame，全类别73555968，含换行。
- candidate control<=1024B/frame，全类别36777984，含CSV全部header/换行。
  每例file也不得超过frames*1024；不能在外部遗漏header。每JSONL记录和CSV数据行分别守2048/1024。
- 全源码/archive/derived copies/编译/来源证明合计64MiB；selected source archive另<=16MiB。
- 全reports/receipts/command logs/negatives/seals/completion合计64MiB，明确包含最后文件自身。
- 单例所有transient/未完成失败prefix最多24MiB。

persistent最高510288512；加scratch总535454336，
小于512MiB=536870912，剩1416576不是可挪用的任意扩容。
此为执行前保守记账，不是实测尺寸或已经证明实现可运行。
实现审查必须证明互斥分类、原60例max629帧的单例上界、写前保留额度、
实际写时硬限制和最终完整计数；超限即失败，不截断、移走到不计量路径、追加预算。
所有report/源码/build/负例/日志归唯一类别；源和数据共享不掩盖重复实存字节。
原ZIP474165229与原解包861385743另计输入预算；保留原ZIP上传，
不重复上传整份原解包树。不得把压缩后artifact大小当512MiB的新输出字节。

## 7. 时间、负例、CI与独立审查

admission、baseline-build、candidate-build、run、analysis、verify、negative各最多300秒；
build阶段各含该arm的plain和observed。新child在启动时硬timeout=
min(30秒,phase剩余,job剩余)，包括compiler/git/构建命令，不是事后超时计数。
root从首个I/O前到所有seal/completion/输出flush及最终计量结束最多1200秒。
失败/清理写盘沿用同一原deadline，无额外收尾时间；最早错误和已有prefix保留，不覆盖旧失败。
只在已授权公开GitHub Actions真正执行DSP，无Codex Cloud/CLI/local、ChatGPT Work或付费资源。

工程控制覆盖normal/soft/hard、两strong-channel、正负零tracked/fallback lag及不同lag、
separate/left/right/both alias、reset与连续history、FULL实际mode、全部逆变换、
AGC实际state/全输出重建、固定坐标/空参考、门槛上下与等号、防静音假改善、
分类/CSVheader/最后写盘/24MiB scratch超限及hard timeout/first failure。

机器锁预列76类实际负例，含D7原51类语义范围与新增：
第二数学改动、tracking-off、fallback weight/gain/history/state改动、强灌baseline下游、
错offset/lag-search、遗漏bad/null窗、静音伪提升、1dB/0dB/-120边界、
伪造dedup、缺真实candidate/AGCstate、AGC输出/clamp、near/silent变化、
None recovery转0、曲线改动、各分类超限及漏finalization。
各guard先接受同一未损坏slice，再拒绝隔离持久化mutant，确切专属拒绝reason
在实现独立审查前固定；未拒绝、I/O、timeout或无关异常都不算负例通过。
标准readback与独立作者原件二进制审计分开，后者不得冒称已经完成或重跑DSP来代替审计。

只在现有frontend-research.yml添加scoped dualmic-broadside-output-d8 job；
旧matrix至D7末尾jobs和既有action pins逐byte保持，D8-only不选旧jobs，不新增workflow。
始终上传原ZIP、首次失败/有效prefix与完整新证据，hidden=true，retention90天。
紧凑完整case/window/log projection在同一negative收尾deadline内输出，
不重复D7巨大frame JSON，不删负值/null/window，完整真实状态留binary。
精确PR head与fresh main各自获取适用Verify和required summary；先审实现后触发，
保护squash前重查head/base，合并后不借旧head资格。

D3/D5/D6、AGC target/limiter/globalcap/error-adaptive/slew及D41-D49 NS/RES保持关闭；
S003参考域混淆原结论不改，不把HPF raw-clean分数差解释为听感损伤。
RealMAN #693/#697、实际clock/calibration/近端truth及真实SSC305/房间声学等缺口保持原状态。
无新model/ASR/listening、commercial release/tag、独立质量/真人/物理资源结论。
