# D29 独立审查与最终复验记录

日期2026-10-11；experiment=FE_DEVICE_ONLINE_D29；claimant=root；verifier=device_capture_independent_review。
primary=adk-planning-execution-loop；supporting=adk-verification-before-completion。
结论：Spec PASS、Quality PASS；Reviewer Independence=independent；未闭合finding=0。
覆盖冻结合同、实现、实际工件、六项拒绝、中文结果与whole-change快照；仅研究集成执行、测量及披露。
promotion_allowed=false、shipping_approved=false；总体native goal仍active。

## 合同与实施身份

PLAN SHA256=6daa1dada8d06b07a81bed9332f02aea99698ce8dcff016e630f24d843f4e97b。
AMEND SHA256=9ba57fd389af933b21fc5de1963bed9675d90a21bf6eb9005cb987444426212c，原PLAN字节保留。
单路输入上的primary/shadow两套AEC、外部冻结far/dt、primary诊断CSV及局部资源口径由执行前补充明确。
实际主执行前独立实施复审绑定最终tool SHA256=2f5a3cc866f0da42a1b5238f00d98db2812bf42e328be212347fb7adaa4a83d0。
新C SHA256=4e8cab79f50967d08e2f5119773dc7c1039e17ca1b627d277eee88bd1a32c026。
实际使用原D18 MDF库SHA256=eb5b0c784c316e71d6ed9f58db6cb66f190b631daa00c55a94032168d5a47aa4，不重编或替换DSP库。

预编译第0次exit1，D26全局primary/shadow与D27头参数同名触发-Wshadow。
仅调整新C头包含顺序，保留原依赖与全部严格警告；第1次编译及集成时序自测exit0。
失败回执SHA256=d43355a892f20aa6af943dce10dc8315168960f1b3c759b8a73ce779e508fbbf及原writer纳入快照。
预编译retry1；主46次实际DSP重跑0；不能称整轮零失败。

## 实际独立验证

主运行真实terminal exit0；严格C11编译、自测、argc拒绝及4个完整非法参数拒绝符合合同。
完整非法参数4组所有输出sentinel保持、primary/shadow调用0；非仓help/dry-run/4tests均exit0，dry-run未创建输出根。
result/binding SHA256=9ed85b81ee3487919b00cf441e84757c1fc7c72deb611cfdedf8c1944e0fa4ab / 2120e2e139584972311fa2ac9a47b5984acf1159fb21d8234438846e49078520。
独立audit与六负例均首次terminal exit0、retry0；不导入新测量器，不运行C/AEC/selector。
46case、368trace、161,902,080个Float32；三CSV各126,486行、252,972gate byte；184bank文件及46primary诊断文件全部等价。
正常44加repeat的selector/transition/两selected输出共180文件比较全byteeq。
future对照D26原实际future，真实反号mic/ref后独立复算选择/混合；repeat全量及future通知前11文件前缀通过。
476原窗由本轮normal+repeat240及hard236构成；1,133有效channel/295null、236delta/108near；RMS/peak/delta误差0。
mic代数max2.2351741790771484e-08；独立实际计数primary126486/shadow44564/reset30/selector和transition各126486/mixed88640/events277/sync0。
主field243/return8事件，repeat/future各13；每次scoped71196B。
另从D19原control重建32field、96,438帧gate，字节一致，脚本及实际回执绑定。
六工具负例均exit2；旧D28499/新D29655文件完整manifest起止同；仓根仅工具潜在回执路径0文件，不锁全dirty。

audit脚本/回执SHA256=5ec3ba746a76fe4edc7967cc09964b13e049556b106f7b2dee4ef0da94f1a6ce / 0770a9e594fdc1b3269d2cd5212a845d5b15765356c11ae5c44702cf53ff421f。
negative脚本/回执SHA256=a150c7d9c83a870f249575a4f84d6224e19713f3d668aa18d6c3c7248ea0d83d / be1ea089bd9ac8343c2d19f524a3cbf95e61f4894ca6dc842781eed8c11442b8。
gates脚本/回执SHA256=a74c882ca1b02037dc147e0587cceff51b05d5aa0110df581ce7f3513abe470c / 87d4d18ae1bb562174c069ffad0a9f9f33c165f0e7fe3fa09ba0b8c1d2047599。

## Whole-change与REVIEW后复验

whole-change快照`/tmp/audio-fe-device-online-d29-20261011/review-snapshot-v1.json` SHA256=68f6168c8e6a7cc719947fcd3960d7fa682a70042c97bb34e2b5cfa18f81807e。
独立fresh review逐项回读43绑定：13仓文件、5工件、22外部脚本/回执/依赖、3checks，起止字节一致。
三个docs checks及help/dry-run/4tests均exit0；651生成工件一致。
RESULT/README的单路双状态、future/正常等价、窗口口径、资源、继承代价和失败历史符合冻结合同；未发现可信blocker/major/minor。
REVIEW字节由finalcheck-0/1绑定；实际docs/git diff终态及独立追加复验在本轮收口时核验。
Runtime evidence/artifact/progress/checkpoint/heartbeat及final gate仅闭合本地D29研究里程碑，不代表总体完成或产品放行。

## 验收边界

原55事件梯度增加、设备窗最高约+0.075dB能量和合成known-near最高约+0.126dB误差仍保留；集成等价不是新声学改善。
两套AEC状态66,040B超过B0 50,000B预算；局部71,196B不含完整线程栈/stdio/库/进程开销，没有DUT资源批准。
真实Activity/双讲检测、完整BF/SYNC/NS/RES/AGC/KWS、真人保护与独立声学数据角色仍未闭合。
AISpeech产品调用链、API/default、owner/E001/Product Qualification各自未闭合。
Provider route unresolved、current为空，知识线NEEDS_REVIEW；仓内reviewing candidate，不声明正式归档。
原D0-D28及用户dirty保留；无commit/push/PR/merge、发布或设备写；总体native goal保持active。
