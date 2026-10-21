# D25 路径退回与合成近端门控：冻结合同

日期2026-10-11；experiment=FE_DEVICE_RETURN_D25；kind=engineering diagnostic；总体目标active。
primary=adk-planning-execution-loop；supporting=adk-verification-before-completion。
目标是在不改变D24选择器/比例/确认规则的前提下，执行路径退回和已知近端污染，测出双状态实际行为及门控缺失代价。

## P1 基线、假设与边界

固定D24 result/binding SHA256为894417dda2d7240726c464a7197b517fd11e715eadc4ab021c8efcd892c8bcce /
870405d2a9145672066f222bcb4ec895f632e9b3b346e288ea42b0737c4191a9；继承D18真实MDF库/宏/头和119设备development输入锁。
仍为16k/160点、20秒、mu0.22f/taps1536/stride2、双状态原库、1000帧只reset shadow、primary不reset。
新first-party诊断fixture仅改变输入路径时间表/加入合成近端/显式提供已知dt标签；直接include冻结D24 selector header。
research_algorithm_changed=false、shipping_algorithm_changed=false；无阈值搜索，无事件检测新实现，不改D24历史结果。
本地HEAD572b0e34a8a8e5663397ce16e378209ba9058d4d及既有dirty保留；live main373008e89f2ebaabc298d2c9613420b1d4811c78，部分checks仍运行，不能称main全部通过。
#657仍OPEN；PR714/708/695与本轮局部原型分离。Provider route unresolved保持NEEDS_REVIEW。

假设只作为待测：旧状态可能在短B路径后退回A时更合适；已知dt保护会暂停适配和选择，但恢复时延可能变差。
任何没有反向翻转、额外翻转或近端污染都原样保留，不改B持续时间或幅度取得预想结果。
data_role=synthetic-engineering；合成近端是独立伪随机噪声，不能叫真人/语音/感知或独立声学证据。

## P2 固定输入、选择与测量

远端xorshift32初值0x12345678，每样本依次xor<<13、xor>>17、xor<<5；低16减32768再float除262144。
路径A/B沿D22：A(48,.5),(176,-.25),(400,.125)，B(80,.375),(240,-.125),(560,.25)，float32顺序乘加禁FMA。
shape=A全程A；shape=ABA在[10,12)秒B，其余A。ref为raw延16或20样本，负索引+0。
condition=echo时near全零；condition=dt/unguarded时near独立xorshift32初值0x87654321、同更新、低16减32768除524288，
仅[10,12)和[16,18)秒非零。所有条件均推进该近端PRNG；mic=float32(true_echo+near)。
dt条件在两段传dt=1给两个原库状态及选择器；unguarded输入完全相同但dt=0；echo条件全dt0。enabled/far始终1。
选择器保持当前帧double顺序残差平方和、严格另一能量<0.8×当前、连续3帧确认、双向相同、无crossfade。
keep只primary；shadow1000帧前复制并full reset第二状态，之后同输入/门控运行。

24主臂=A/ABA × ref16/20 × echo/dt/unguarded × keep/shadow；repeat=ABA/ref20/unguarded/shadow；future同臂但raw/near从10秒起反号，共26真实执行。
保存10条trace：mic/reference/selected echo/residual、primary/shadow各echo/residual、true_echo/near；selector.csv新增dt标签，state.csv primary沿D22字段。
每例2000帧/320000样本；主调用2000、shadow0或1000/reset0或1，inactive shadow两trace全零，SYNC实际calls0。
逐帧重建input/原生float32、有限/长度、AEC代数≤1e-6、状态范围/门控、选择能量/标签/输出字节、repeat全12文件、future前半同。
A/echo主臂全12文件与D24 A同policy可比项等价（新增near/true_echo和dt列显式单独解释），ABA/echo前10秒同D24 switch对应前缀；
dt/unguarded每配对mic/reference/near/true_echo逐byte同；keep/shadow输入及primary全状态/输出逐byte同，证明选择不污染primary。
dt段selector不得翻转、streak必须0；不得把weight不变当适配计数。真实原库dt是否冻结权重另独立核，不默认声称。

whole及固定窗[0,2),[8,10),[10,10.5),[10.5,12),[12,12.5),[12.5,14),[16,18),[18,20)秒：
记录selected/primary/shadow残差RMS/峰值、error=residual-near的RMS/峰值及true_echo RMS。
error是合成已知目标输出误差，混合时不叫ERLE/人声损伤；仅near全零窗口报告true_echo/error的工程ERLE，零分母按冻结D21公式。
报告shadow-minus-keep误差RMS dB、dt-minus-unguarded同policy误差RMS dB，完整数值保留；inactive shadow不评分。
输出事件帧/方向、门控段事件、切换处相邻样本差及双状态同帧输出差，只是工程边界观测，不听感标准。
decision=RETURN_NEAR_GATE_DIAGNOSTIC_NO_PROMOTION；promotion/shipping=false，未测资源CPU/peak/DUT。

## P3 执行和独立验收

scope_write=新D25 C/tool/tests/PLAN/RESULT/REVIEW及README本轮入口；旧D24/D23/产品DSP不改。
先独立计划和实施审查，再严格编译、完整非法参数拒绝且预置文件未变、26真实执行、非仓cwd help/dryrun、定向测试。
实际独立audit不得导入新测量器或重DSP：核hash/输入/trace/CSV/选择/统计/差值/事件；真实工具负例对既有根/仓根应拒绝且不改工件。
新/tmp根；retry_budget=2（失败必须保留）；每命令timeout120秒；任一基线/锁漂移即replan；真实handle heartbeat/attestation起止hash。
claimant=root；verifier=device_capture_independent_review；open_items=3；plan_completeness=P1/P2/P3；stop_condition=pass/replan/blocked/abort。
completion_claim仅本轮工程诊断；logical_task_open=true；handoff_target=真实开发回放/真人保护/边界及目标资源；retention=仓内reviewing candidate。
原稳定性拒绝、AISpeech、ASR/KWS、HIL/E001/owner资格不被本轮替代；无SCM外写、设备写或正式归档。
