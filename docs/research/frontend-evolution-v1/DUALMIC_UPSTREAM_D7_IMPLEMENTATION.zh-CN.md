# D7 HPF/BF 中性观察实现说明

状态：IMPLEMENTED / NOT_EXECUTED。追踪 [#944](https://github.com/jiying2007/audio-pipeline/issues/944)；
总研究 #657 继续开放。本文不宣称构建、负例、原件读取或声学测量已经通过。
冻结 commit `4b7f4496d9d9fef5589456f4ac377ddfa29e24e3` 的
[方法合同](DUALMIC_UPSTREAM_D7_PLAN.zh-CN.md)及
[完整机器锁](dualmic-upstream-d7-input-lock.json)保持原字节。
实现必须先接受准确 HEAD 的独立审查，才可打开触发 Actions 的 PR；没有 dispatch 授权的替代捷径。

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
completion.json明确其仍须独立完成。提交本实现时，所有执行字段都仍是NOT_EXECUTED。

## 6. 原CI保持与实施边界

只扩展既有frontend-research.yml：独立D7 scope及最后追加的D7 job。
D7-only先检查从matrix到旧D6末尾整段与e348逐byte相同，然后所有旧job输出false；
混合旧研究/生产修改拒绝，避免追加D7被旧D6尾部比较误判。
原jobs和action pins不变，不新建workflow。公开ubuntu-24.04 runner，20分钟，
始终上传完整原ZIP、新结果、准入和首次失败，include-hidden-files=true、retention90天；
不上传重复解包原树。

本提交仅实施待审查代码，无PR、dispatch或实验执行。最终准确HEAD的实现审查、实际Actions、
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
