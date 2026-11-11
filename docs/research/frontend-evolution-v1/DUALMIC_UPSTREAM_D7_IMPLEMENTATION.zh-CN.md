# D7 HPF/BF 中性观察实现说明

状态：首次执行 MEASUREMENT_INVALID；下述 flags 兼容修订仍为 NOT_EXECUTED。
追踪 [#944](https://github.com/jiying2007/audio-pipeline/issues/944) 与 [PR #945](https://github.com/jiying2007/audio-pipeline/pull/945)；
总研究 #657 继续开放。首次失败与实际通过的准入前缀见末节，不宣称取得新阶段声学结果。
冻结 commit `4b7f4496d9d9fef5589456f4ac377ddfa29e24e3` 的
[方法合同](DUALMIC_UPSTREAM_D7_PLAN.zh-CN.md)及
[完整机器锁](dualmic-upstream-d7-input-lock.json)保持原字节。
首次实现已独立审查并打开PR。后继修订先仅创建无ref更新的commit对象，经准确字节独立审查与授权后
才更新PR分支；分支更新会触发Actions，没有dispatch授权的替代捷径。

## 1. 原件身份的来源和执行前提

D2 ZIP 固定为 run42321833898/attempt1 的 artifact13553232106，
474165229 bytes，SHA256
`a3ab7823fdcd7586c3b72eb214b5536dcfb7531fdf0b1611d49e1575a29b2c3d`。
旧 D3 原件读取器不修改，以同进程方式调用，完整下载、大小/hash、安全成员、D2全量回读都必须成功。
不另行下载 A/C；原ZIP中父D1的 originals 与 original-archives 已同时存在。

父D1新增显式固定的两个hash来自既有
[cc853 D2结果记录的“实际保存对象”](https://github.com/jiying2007/audio-pipeline/blob/e348843a570503728930f06451633262b2546fa5/docs/research/frontend-evolution-v1/DUALMIC_GAIN_D2_RESULT.zh-CN.md)：
report.json 为 `472e050dd155973c0a49fca1fb17c8204e240411ca37d99e3a81c1b777d8e958`，
artifact-manifest.json 为
`84c6884037fc61aeee222033cf0b5a6f06c644114ffdeee1349ed61e6c2e86cf`。
这是历史公开记录的出处，不是本轮已完成二进制读回的声明。
执行仍需匹配这两个hash、完整父D1 payload、D2 parent-binding，并由原
D1 verify_origins 将全部选定原PCM、metadata及端点逐byte绑定到嵌套A/C ZIP。
机器锁中的60个 input_member_bindings 必须再由实际catalog重建并核对。

旧plain/原A/C生产基线4daa、父D1/D2的cc853、当前生产e348/2.3.64、
本次实际HEAD及派生HEAD-D7-observer分别记录，绝不混为同一个身份。
原件缺失、过期、准入失败或新旧输出不等均停止，不替换输入/原件、不放宽相等。

## 2. 两个包装器与真实状态

dualmic_upstream_d7.c 只新增HPF/BF两个观测包装器，仍调用原实现。
七个生产定义rename和一个仅D1 helper末尾main的rename完全按冻结锁生成，
每个命中一次，函数体不变，逆变换等于原blob。旧D1源码和旧4daa专用builder均不改动；
新builder不调用旧builder的build入口。

D1自身会define/undef其生产CLI main，因此没有采用外围main宏。
派生D1的最终入口为ap_d7_d1_main，D7在前后打开/关闭新tap。
实际顺序受计数器检查：HPF0、HPF1、BF、Activity、可选AEC、NS、AGC。

每例保存五条未经归一化/量化的Float32LE：
hpf_input_l/r、hpf_output_l/r、bf_output。
HPF输出在BF入口与两路参数逐byte比较；BF输出再与真实D1 AEC输入或capture-only NS输入比较。
旧七lane及control.csv仍单独保存，并逐byte等于原D2中的父D1；
当前plain/currentobserver/原A/C的PCM和metrics JSONL必须三方逐byte相等。

state.bin 每帧472 bytes：16-byte frame/actual tracking/alias/n，
HPF0 before/after、HPF1 before/after各24 bytes，BF before/after各180 bytes。
实际sizeof及所有offsetof同时有编译断言、运行检查，并将实际偏移数组写入observer.json。
完整17个lag_score EMA及双路8样点history都保留在binary；它们不是局部aa/bb/xy/coherence的直接观测。

解析器检查全流连续state、两个HPF调用之间的state、未处理通道、末端x/y、
BF原输入history、±3半径、每次更新±1slew、cadence、counter/score_updates、
非更新与半径外score不变、actual tracking及fallback路由。
只有原8个frame300 render-gap重置HPF/BF，lost_frames=4不插零帧；
path-change处保持上游连续，不能伪造一次reset。
HPF运算及BF输出方程另用独立Float32算术核对，不把重建量称为额外C内部观测。
effective_output_lag 取after的active ? fallback_lag : lag。

## 3. 当前完整构建与来源闭包

新builder位于tests/validation/frontend_evolution，使用e348固定的65个生产/build/notice文件，
26个冻结helper及当前D7完整闭包。helper JSON未列出的Git mode由不可变e348 tree再次绑定，
不是从可修改manifest推断。生产根tree对象同时核对，不能偷偷新增生产文件。

精确HEAD的selected Git archive保存上述全部源码，不宣称是整个161MB仓库。
Git archive显式tar.umask=0022以保留固定644/755文件模式；archive成员模式/内容、当前Git blob/树、plain与observer源目录、逆变换、runtime imports
都核验。历史corpus generator和HPF-aware oracle仅保留作为解释来源，禁止导入/执行，
因此不冒称保留了这两段历史工具自身的执行依赖。

plain/observer独立CMake Release构建，保持-O3 -DNDEBUG、C_FLAGS空、SCALAR/MDF/EMA/
BANDLIMITED、完整module mask1023、tracking开、无fast-math。
新机器上的GNU编译器实际lookup、symlink selector、realpath、普通文件hash、版本、target均保留；
不声称等于旧环境。版本信息取真实编译器，传入实际argv的是解析后的普通文件路径。
flags、compile_commands、Unity源码、实际库/程序、generated headers、依赖文件、编译/链接日志保留。
手动编译observer仅增加-MMD/-MF依赖证据选项，不改变DSP数值flags。
两份header必须等于冻结模板/默认值及真实host身份重建值，不能仅相互比较后自封存。

来源上限16MiB、新结果上限512MiB；完整旧ZIP及861385743-byte解包树单独计量。
源目录及case目录严格文件/目录闭包，构建记录完整生成物inventory，结果seal保留所有新payload。
JSON全帧关联不重复binary历史数组，固定窗仍统计全部实际EMA值；
完整report采用紧凑JSON，以明确遵守预先冻结的512MiB上限，不更改原始数据。

## 4. 固定评分、实际状态关联和解释边界

只使用冻结D1 measure_lane/stage_delta、canonical si_sdr_span和D19 energy。
五条新lane的offset0，旧NS/AGC offset160；60例、35916帧、362个原固定窗、
32条clean reference与28条null全部保存，无lag search、选窗、选通道、平均L/R或换参考。
旧D1全部stage scores也重算后精确等于旧report。

全帧及每个固定窗/whole记录actual tracking、tracked/effective lag变化与直方图、
score_updates、fallback/hard/strong-channel/恢复/arm/fixed-health状态、原far/DT及事件。
binary保留所有完整state，JSON每帧给出准确byte range；最后一帧仍在全流记录中，
但依原规则不进入common评分窗。
A且有clean_near才标注frame[150,550)来源放置；其它A无near source，C保持unknown。
这些不是人工VAD、speech-onset或DTD真值。

S003 HPF-aware oracle已关闭raw-clean HPF分数下降即滤波损伤的解释。
本轮只生成阶段与状态关联，不声称echo-following因果、不批准候选、
不推导ASR/KWS/MOS或真机改善、不自动启动后继搜索。所有既闭合拒绝线保持关闭。

## 5. 阶段、失败和实际负例

七个阶段各300秒，单一Python主监督器在本进程执行分析/读取工作，
SIGALRM覆盖I/O、hash与终态写盘；没有将300秒分析worker藏在一个新子进程里。
每个新git/compiler/CMake/CLI等子进程硬限制min(30,remaining)，超时杀进程组，
stdout/stderr、真实argv/cwd/env范围、退出码/timeout及首失败都保留。
完整job仍20分钟，失败不扩预算，路径必须全新，不覆盖既有失败。

C工程控制覆盖840组固定/跟踪、lag0/正/负、normal/soft/hard、
独立输出/左别名/右别名/双输入精确别名及初始化/中途reset，
并真实检查8种非有限、geometry、次序、首错保全、write/close失败。
Python另实际启动一个剩余约0.2秒的有界子进程以验证timeout，
随后第二个失败验证不会覆盖首失败。这些是工程控制，不是声学样本或原件中性桥。

test_dualmic_upstream_d7.py 的REASONS在执行前固定51类专属拒绝理由。
negative阶段先完整验证未经修改证据一次，然后对真实证据的隔离副本做51项targeted corruption；
每个targeted guard先接受其未经篡改的同一份slice，再拒绝持久化mutant。
调用与生产readback相同的guard，不重复51遍完整canonical分析；
无关ValueError、I/O、timeout、未拒绝均令负例失败。
source/body/entry/header、实际信号/state、旧端点、窗口/null/near、
compiler/argv、闭包与各失败回执均覆盖，mutant及hash/reason报告单独留存。
额外文件/目录/symlink用外部临时hardlink副本，仅新增节点，绝不写原inode；
不会把三份重复整包计入上传。

常规readback与独立作者审计必须分别报告。当前driver不伪造独立审计PASS；
completion.json明确其仍须独立完成。首次实现提交时所有执行字段均为NOT_EXECUTED；
后来的首次执行只通过准入前缀，尚未到达这些负例或completion，见末节。

## 6. 原CI保持与实施边界

只扩展既有frontend-research.yml：独立D7 scope及最后追加的D7 job。
D7-only先检查从matrix到旧D6末尾整段与e348逐byte相同，然后所有旧job输出false；
混合旧研究/生产修改拒绝，避免追加D7被旧D6尾部比较误判。
原jobs和action pins不变，不新建workflow。公开ubuntu-24.04 runner，20分钟，
始终上传完整原ZIP、新结果、准入和首次失败，include-hidden-files=true、retention90天；
不上传重复解包原树。

首次提交仅实施待审查代码；首次实际运行的失败另记于末节。后继准确HEAD的实现审查、实际Actions、
独立原件审计、保护合并及fresh-main门禁仍是后续独立步骤。无生产修改、SDK bump、tag或发布。

## 实现静态复审修订（仍未执行）

首次实现head a99a88c的静态审查发现三类真实实现缺口：phase起始/终态写盘未完整处于硬alarm内；
seal、summary及completion收尾在phase外，且512MiB计量漏掉completion自身；
固定窗/whole缺少已有完整帧状态中的recovery、arm、fixed-health和counter/cadence汇总。
这些不是声学负结果，也不调整冻结合同。

修订在首个mkdir/open/write之前装上同一300秒alarm，只在终态receipt、finalizer与最后边界检查之后恢复。
enter失败安全恢复handler；终态写盘/收尾失败仍保存最早错误，不让清理错误替换它。
时间耗尽后不启动额外hash/receipt写盘，不补一个清理预算；初始PENDING/FAIL或部分证据保留，
最早错误、phase和目标继续送到Actions日志。失败job的已成功前缀回执不能自证整轮成功。
phase.elapsed_seconds诚实标记为终态回执准备时的已用时间；同一硬deadline还覆盖后续终态I/O与finalizer，
不把这个早于最终写盘的时间戳宣称为完整最终耗时。

analysis seal在该phase的终态finalizer内生成。negative的终态finalizer在原300秒内完成
回执检查、summary、completion和全部最终hash；completion关闭后再次核全目录字节数及原payload不变，
512MiB计量包含completion本身。没有新增phase或延长20分钟job。
每个固定窗及whole补上counter/score_updates/recovery/arm/fixed-health的before/after直方图、
首末状态和变化次数，以及counter模4、实际更新delta、全部tracking更新帧，以及由真实mode/counter按源码重建的fixed-health调用节奏（不声称有效health证据）。
评分、窗口、样本、原件中性桥及51类负例保持原定义；所有新增执行证明仍待准确head批准后的真实Actions。


## 首次真实执行失败与有界 flags 修订（2026-11-11）

### 实际观察，不能被后继重跑覆盖

- 实际源码：62bf806998aa2c6d551dbaa44544db72d751b8cc；PR #945。
- [Frontend Research run43040461777 / attempt1](https://github.com/jiying2007/audio-pipeline/actions/runs/43040461777)，
  [dualmic-upstream-d7 job130590627912](https://github.com/jiying2007/audio-pipeline/actions/runs/43040461777/job/130590627912)。
- 日志的原D3读取器回执为 INPUT_ADMITTED_NO_DSP_EXECUTION：
  原D2 ZIP13553232106、3551成员、861385743解包字节、60例、35916帧、
  5746560样点和 original_D2_readback_exact=true，读取器elapsed94.602123182秒。
  这是程序输出的完整准入前缀，不冒称已独立读取本轮ZIP中的每个文件。
- 根监督器首次失败为 MEASUREMENT_INVALID / ValueError / D7_BUILD_FLAGS；
  phase=plain-build，target=/tmp/ap-dualmic-d7/result/plain-build-phase.json，
  first_failure.stage=body，根累计elapsed101.45739900499998秒，退出码1。
  此前生产plain configure/compile/build-info命令已由控制流到达flags()；
  未运行60例音频、observer工程控制、分析、readback或51类实际负例，无新HPF/BF结果。
- [失败artifact13863789529](https://github.com/jiying2007/audio-pipeline/actions/runs/43040461777/artifacts/13863789529)，
  名称frontend-research-dualmic-upstream-d7-43040461777-attempt-1，377个上传文件，
  474615764 bytes，上传/API SHA256
  78f210dc83f93778442d94425ec03af4cda471c5afa3e3911e6ac627a67fadc7，
  API expires_at=2027-02-09T14:38:45Z。保留原ZIP及失败构建证明，不删除或覆盖。
  本次connector诊断读了job文本/API；没有解包读取artifact的flags.make或compile_commands，
  因此不虚构该次实际compiler/CMake版本、完整argv或具体失败比较分支。
- 独立Verify run43040462098的validation-smoke Ubuntu libopus0安装DNS故障另行保留；
  本修订不修改共享CI/安装/transport。后继准确head仍必须取得自己的适用Verify资格。

### 从源码确定的守卫缺陷，以及仍未证实的边界

旧flags()将parse、defines、flags、includes的失败统一成D7_BUILD_FLAGS，
且只允许std位于末尾的完整序列：
-O3 -DNDEBUG -Wall -Wextra -Wpedantic -Werror -std=c11。

runner实际日志标识image ubuntu24/20261101.360；
[该image公开软件清单](https://github.com/actions/runner-images/blob/ubuntu24/20261101.360/images/ubuntu/Ubuntu2404-Readme.md)
声明CMake3.31.6。这不是本次cmake-version.stdout的直接读取。
[CMake3.31.6 GetTargetCompileFlags](https://github.com/Kitware/CMake/blob/v3.31.6/Source/cmLocalGenerator.cxx#L1649-L1720)
先AddLanguageFlags、后AddCompileOptions；
[AddLanguageFlags](https://github.com/Kitware/CMake/blob/v3.31.6/Source/cmLocalGenerator.cxx#L2082-L2114)
在配置flags后添加language standard。因此相同固定生产CMakeLists配方生成
-O3 -DNDEBUG -std=c11 -Wall -Wextra -Wpedantic -Werror。
CMake4.1.2相同代码顺序。旧守卫确定会拒绝这个等配方的完整顺序；
这是本次失败最有依据的解释，仍不称artifact-confirmed的实际差异。

原末尾顺序也有明确来源：
[CMake3.25.3 AddCompileOptions](https://github.com/Kitware/CMake/blob/v3.25.3/Source/cmLocalGenerator.cxx#L957-L1028)
先添加target options，再调用AddCompilerRequirementFlag追加standard。
只保留这两条已解释的完整序列，不接受任意排列、set/subset或extra flags。
生产CMakeLists固定的13个defines及3个include顺序不变。

### 最小修改和未执行测试

仅修正D7 builder的严格解析兼容性，不改configure_argv、Release/O3/NDEBUG、
任何编译token、compiler选择、observer argv拼装或实际argv记录，不改变DSP。
返回原始实际token顺序；两次构建C_FLAGS仍必须完全同序，observer实际编译沿用它。
失败仍为D7_BUILD_FLAGS，附上bounded category（parse/defines/flags/includes）、
observed/expected、实际flags文件目标、cmake-version/configure回执与compile_commands路径。
正常完整诊断在4KiB内；异常长输入明确截断，只保留有界前缀，原flags文件仍留存。
详情通过既有首失败receipt和根Actions日志通道输出，不在超时后增加诊断I/O或预算。

plain-build原300秒phase内增加107个明确标为synthetic parser fixture的持久化工程测试，
不是本次实际编译命令或声学证据。2个正例保留全部原tokens；
105个负例覆盖每个flag缺失/重复、extra、O2、fast-math、冲突std/Wno-error、
替代flags和不支持的重排、全部宏/include缺失/重复/替代、extra include/宏、
include顺序、缺失/重复赋值、破损quote及超长诊断。
另检查首次D7_BUILD_FLAGS详情不会被后继失败覆盖；receipt纳入原输出闭包和readback。
这些新增测试已写入源码，但本修订尚未执行，不写PASS结果。
原51类真实证据篡改的类别、实现与拒绝理由保持原字节。

冻结两文件、旧D1 builder、全部生产源码、D7 C/driver、现有workflow与全部
300秒phase/30秒child/20分钟job/16MiB source/512MiB新结果上限不变。
下一次运行仍须从完整原件准入开始，任何中性桥、数值或预算失败照原规则停止。
本说明只是保全失败及提出可审查修订，不把未运行阶段晋升为合格。
