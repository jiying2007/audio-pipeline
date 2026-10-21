# D7：多帧相关信息可行性测量

日期：2026-10-10；状态：FROZEN_MEASUREMENT_PLAN。
授权：用户继续推进；primary=adk-planning-execution-loop。仅本地研究，无SCM或设备写。

目标：在D5误跳和已知延迟工程恢复事件上，观察较长历史是否提供额外区分信息。
基线：本地HEAD 572b0e34a8a8e5663397ce16e378209ba9058d4d加D6源码；
D6 receipt SHA256=d2e4c5fb82c2ca795d576f42618b8204e47ae16b7f96c232fdc161d542bf4b36。
现场读取main=f05eecb69ab5ac1a0968381f109510c939b53e50，新增RealMAN独立元数据/gate研究，
不混用其CI或主线研究身份。D4拒绝、D5诊断及D6通过均保留。
Provider route unresolved，归档资格NEEDS_REVIEW；仓内计划/结果只作reviewing候选。

## Phase A：临时观测实现

kind=measurement；question=更长历史相关分数是否与单帧提供不同信息？
scope_write=新D7文档和/tmp独立源码快照的观测；产品src/include/API/default不改。
在临时SYNC state增加2048点麦克风历史，仅测量使用；reset按现有memset清零。
track入口按真实frame输入追加历史，不改变任何原有决策或事件赋值。
仅在实际render_total与mic历史长度一致且所需历史完整时计算，否则eligible=false，禁止补零。
冻结窗口=160/640/1600 samples（10/40/100ms，16kHz），stride=4，同原平方归一化相关。
各窗口记录原old/best候选分数、固定16点诊断分数、原32点coarse网格加局部逐点细化的最优delay/score，
及guard之外runner-up。只观察，不将长窗结果回写tracking，不新增接受阈值或自动选择候选。
这不是新的声学评估器、算法修复或resource benchmark。临时state尺寸增加不代表shipping ABI。
exit_gate=严格构建+原14CTest通过；源码变更只在声明的两份临时SYNC文件。

## Phase B：固定执行与等价

kind=measurement；evidence=D6 source lock、实际临时source/build hash、trace、PCM/metrics。
执行集=原ap_drift_res_tests一次；rpm480/far-motion default/tracked1/fixed1三臂各一次。
数据角色=已查看development；工程已知路径不是真实设备/HIL证据。
验收=三臂PCM/metrics逐字节等D6，全部完整观测有限；160点score与原score误差不超过1e-6；
不完整窗口明确拒绝计分。输出不等价或原恢复失败立即保留失败并拒绝本次观测有效性。
结果可以是信息不足；不能凭单次误跳/恢复区分率宣称有效算法或独立声学收益。
预算=1严格build、1原CTest、3回放、固定三窗口，无搜索，无调阈值；同类失败2次replan。

## Phase C：审查与收口

kind=review；goal_statement=完成D7测量可行性与边界判断；claimant=root；verifier=独立审查者。
required_evidence=冻结计划、source/build/trace绑定、原测试、三臂等价、真实计算记录、独立审查。
review_mode=whole-change；复用已授权独立代理，shared contract串行。
staleness_threshold=源码或计划变化立即重锁；heartbeat=阶段完成刷新；stop_condition=pass/replan/blocked。
attestation_readback=逐hash及JSON回读；open_items=观测实现/固定测量/审查三项。
下一候选须另冻单因果研究，不与本测量互相批准。设备声学/owner/shipping/E001/PQ保持待验证。
