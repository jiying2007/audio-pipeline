# D8 双麦 broadside 输出：执行前冻结合同

状态：PREREGISTRATION / NOT_RUN；合同revision2（执行前资源/超时修订，待独立复核）。实验 FE-DUALMIC-BROADSIDE-OUTPUT-D8，科学候选数1。
基线 main 1b5b01e0f2580ec9e05dfacff2ee1d292c438172，
tree db25581db2ad683499ec2c7b2e22686787d39db2，生产版本2.3.64。
追踪 [#947](https://github.com/jiying2007/audio-pipeline/issues/947)，前驱#944，总研究#657保持开放。
2026-11-11已通过连接器重新读当前main、required summary success及开放PR/issue；
没有同题D8占用，#925/#714不属于本轮。先冻结本文与完整机器锁，再独立审核准确字节；
实现须另经独立审核，才允许移动触发CI的ref或打开PR。本文不声称运行DSP或得到质量结果。

## 0. 执行前修订历史与真实限制

原冻结14083f84b8ec213d85f10cf31a56e42a774410f5及其两份完整文件保留在父commit中，
独立结论是METHOD_ACCEPTED_FOR_IMPLEMENTATION_ONLY，从未授权DSP、ref/PR或CI执行。
实现前发现：RLIMIT_FSIZE只限单个inode，RLIMIT_NOFILE只限同时打开的FD，
不能证明未固定旧版本的GNU/CMake在短时内顺序产生文件的总量；
同时D3 acquire捕获Exception并在finally写admission.json，抛TimeoutError不能保证停止写盘。
没有运行任何候选或观察质量结果后再改门槛。

本revision2仅透明修订资源执行边界与fatal监督机制，保持原512MiB保存闭包、
24MiB科学单例scratch、自有writer写前预检，以及全部原科学、输入、身份和否决规则不变。
单独披露工具链临时工作目录的有限控制：进程/单文件/时间上限及事后完整inventory，
不再声称编译器每次写入都受到总字节配额。任何需要额外权限、ptrace、mount、quota、
sudo、安全设置改动或未登记资源的步骤必须停止报告，不能用其它资源绕过。
本修订须再次独立审核；实现源码及精确head还须另外独立审核，均不等于执行授权。

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
- 全部near-only/silent-render在两臂的全部stream/control/metrics/endpoint及实际记录的HPF/BF/AGC state逐byte不变。
  不声称直接记录或比较了未观测的完整SYNC/AEC/NS state。
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

冻结保存结果及科学scratch类别上限（bytes，包含自有writer临时、失败和最后写盘；工具链临时目录的明确例外见6.1）：
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
实现审查必须证明互斥分类、原60例529..629帧的科学单例上界、自有writer写前保留额度、
实际写时硬限制和最终完整计数；保存结果及科学scratch超限即失败，不截断或追加预算。
工具链临时目录是本次明确登记并单独计量的例外，不能把科学文件移过去逃避512MiB。
所有report/源码/build/负例/日志归唯一类别；源和数据共享不掩盖重复实存字节。
原ZIP474165229与原解包861385743另计输入预算；保留原ZIP上传，
不重复上传整份原解包树。不得把压缩后artifact大小当512MiB的新输出字节。


### 6.1 明示工具链临时例外与单例硬界

单独工具工作目录为/tmp/ap-dualmic-d8/toolchain；TMPDIR也在该目录内。
每个外部工具命令退出后、挑选任何保存输出前，完整inventory必须<=128MiB=134217728 bytes。
这只是事后接受上限：命令内部或两次检查间可能超限，已删除临时文件不再可见，
不声称该inventory测到peak、累计写量或阻止了每次超额写入。
查到超限即MEASUREMENT_INVALID并停止后续命令/复制，保留prefix；不得清理后再判通过。
仅登记源码、derived副本、实际compile/link产物和provenance可在预留目的类别后复制进build/**；
保存后的64MiB build类别和512MiB结果闭包不变，两处实际副本在各自域中都计数。
工具临时目录不自动上传，失败时不删；科学数据、原件、report不能转存这里规避保存预算。

每个工具child同时降低soft/hard RLIMIT_FSIZE=16MiB、AS=512MiB、NOFILE=128、
NPROC=128、CORE=0。主实验worker为AS=1GiB、FSIZE=512MiB（保留474165229-byte原ZIP能力）、
NOFILE=128、NPROC=128、CORE=0；外部supervisor为AS=128MiB、NOFILE=128、CORE=0。
从原继承limits先fork，再分别降低parent/worker hardlimit，不能先把parent降到128MiB后
尝试给child提升到1GiB。不得提高已有更低limit，记录全部原值/实值；不能无权限建立所需限制则停。
NPROC对整个真实UID的进程/线程计数，runner已有活动占用额度，不是128个本job独立配额；
要求非特权身份且无capability elevation，不把rlimits说成进程、内存或磁盘的隔离总量配额。

原件I/O前观察磁盘可用>=4GiB；每个外部命令及保存复制前观察>=2GiB。
这些是即时观察，不预留空间，也不能阻止其它进程耗尽磁盘。
原ZIP+原解包+512MiB结果+128MiB工具目录的声明接受量合计2006639612 bytes，
另有原准入小metadata；工具瞬时超额仍可能发生。资源耗尽就是失败，不是追加预算理由。

科学scratch仍保留硬24MiB，不能使用工具例外。固定原60例F为529..629。
每个arm的plain目录有2文件；observed端点2、D1目录9、D8目录8，
合计两个plain process各2文件、两个observed process各19文件，八目录42文件。
固定CLI每帧PCM320B、metrics行<=314B（含换行）；D1每lane<=640F，
control header455B、数据行<=440B（capture-only399B），D1 receipt<=2019B并预留4096B；
D8每lane<=640F、state472F、AGC24F、receipt<=4096B。
严格原capture640F-byte输入限制循环次数，discontinuity的lost_frames不产生额外输出帧。

科学plain child的soft/hard FSIZE=320F，observed为640F，CORE=0，stdout/stderr用pipe。
即便发生部分写或close失败，42-file count×limit上界
2*2*(320F)+2*19*(640F)=25600F<=16102400B。
第一form前预留该完整最大数；另把当前例所有logs、command receipts、metadata、
atomic-write临时/最终同时副本及failure写入联合预留8MiB。
总24491008B，距24MiB还剩674816B，不能把剩余解释成任意扩容。
其中最多8份stdout/stderr各64KiB、4份命令receipt各64KiB，余7602176B覆盖其它ancillary。
每个parent写入先预留完整增长；D1/D8的O_EXCL文件不预创建，仅创建空真实目录。

这一硬界依赖已绑定binary/source/argv及allowlist环境、无LD_*注入，
原输入不可写，输出不得alias输入；目标唯一、空、无symlink，一次一例一process，
首次失败即停止，无重试或另建prefix。去重先实测比较和descriptor，之后仅同文件系统atomic
move或已证明等价删除，无copy fallback。界定的是逻辑文件内容字节，不是磁盘block quota。

## 7. 时间、负例、CI与独立审查

admission、baseline-build、candidate-build、run、analysis、verify、negative各最多300秒；
build阶段各含该arm的plain和observed。除单一主实验worker外，每个命令child在启动时fatal timeout=
min(30秒,phase剩余,job剩余)，包括compiler/git/构建命令，不是事后超时计数。
外部supervisor在首个实验I/O前启动不可重置的monotonic1200秒root计时，覆盖所有seal/completion/输出flush及最终计量。
失败/清理写盘沿用同一原deadline，无额外收尾时间；最早错误和已有prefix保留，不覆盖旧失败。
只在已授权公开GitHub Actions真正执行DSP，无Codex Cloud/CLI/local、ChatGPT Work或付费资源。


### 7.1 外部fatal监督协议

新增dualmic_broadside_output_d8_supervise.py并纳入当前D8闭合来源。
supervisor先在repository imports及实验source/data/network/log I/O之前取monotonic root start；
Python解释器/bootstrap加载不冒称已被计为实验I/O。root绝对deadline为start+1200，不可重置。
它在外部监督唯一长期主实验worker，该worker只为fail-stop隔离而fork到新session/process group，
明确是30秒child规则唯一例外，不是给额外DSP/分析worker暗开300秒时限。

通过私有继承IPC传递有界、递增序号的phase/command请求；supervisor核验七phase固定顺序，
phase绝对deadline=min(phase start+300,root)，child绝对deadline=min(command start+30,phase,root)。
worker必须在phase受保护I/O、每次Popen之前收到ACK；active command未结束不能换phase，
后来消息不能删除、延长或重置更早deadline。全部compiler/git/CMake/CLI命令仍受30秒上限。
worker的所有child继承同一group，不用start_new_session/process_group、shell job control
或改变group的preexec；绝不调用D7旧launch路径。记录并核对实际group与已知工具调用。

到最早active deadline，外部supervisor首次获得调度时向整个worker group发SIGKILL，
不发graceful cleanup请求、不向worker抛可捕获的TimeoutError，
所以不能依赖D3捕获Exception后finally写盘作为“超时处理”。
超时分支不新做hash、inventory、receipt改写、finalization或stdout写入，
不追加清理宽限；保留已有有界PENDING/失败prefix。
普通错误只能在原deadline仍有效时保留首错；不能覆盖旧首错或新开attempt。

最后negative phase与root计时持续到seal/completion、全部final writes、
有界stdout drain/flush、worker退出和无遗留descendant检查结束，缺terminal completion不成功。
root输出总量<=4MiB，包含中间文本和完整紧凑投影，不把输出传输排除在时间预算外。
必须明确：SIGKILL和实际退出有调度/kernel延迟，已提交kernel I/O可能稍后完成；
不是保证精确timestamp物理零写入。group连续性是经审核的已知launch/tool要求与运行时断言，
不是syscall confinement；snapshot不能证明任意外部软件从未逃逸。
发现未知descendant或group逃逸即无效停止并报告，不能为处理它申请额外权限或转用不受控资源。

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
