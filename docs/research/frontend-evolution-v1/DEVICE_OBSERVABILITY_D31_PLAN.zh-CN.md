# D31 近端与路径失配可辨识性观测合同

日期2026-10-11；experiment=FE_DEVICE_OBSERVABILITY_D31；总体优化目标active；上一轮分类progress。
primary=adk-planning-execution-loop；claimant=root；verifier=device_capture_independent_review。

## P1 冻结身份与问题

kind=measurement-only research；implementation_permission=仅独立观测工具/测试/中文记录，不改变检测器、AEC、选择或产品算法。
question=D30能量门控遗漏合成near区间时，现有mic/ref/primary和selected echo/residual的同帧关系是否提供补充信息，路径失配是否产生重叠？
local HEAD=572b0e34a8a8e5663397ce16e378209ba9058d4d；用户dirty及D0-D30原源码、库、工件全部保留。
fresh live main=d3f89e54beed483fcc0f8ce59e74b28533ed19b5；62 check-runs中存在in_progress，不能声明main全绿。
#657 OPEN，updated2026-10-10T11:33:28Z；开放PR717/714/708/695是独立远端任务，不借其CI或制品批准本地D31。
Provider使用实际支持的task-type=debug查询后route unresolved/current为空；知识线NEEDS_REVIEW，仓内reviewing candidate，不声明正式归档。
D30根=/tmp/audio-fe-device-activity-d30-20261011；result SHA256=e0b74142093d4579615be9ffe047335b4618f46aa1116f0b24941bb921de470d；binding SHA256=2558d74e0e8377087bcb1a44fc3e13d890c4da9b641b579db9d670e207083956。
执行前后验证D30绑定的全部source/input/artifact及result/binding字节；不重跑C/DSP或改变原工件。
只消费既有32已查看field development、12合成return及repeat/future，共46记录；无validation/blind参与。

## P2 测量公式、矩阵与边界

每160点原Float32帧转为Python double累加观测；不声称是部署Float32检测实现。
固定零时延、非去均值、非频域的平方归一化内积 C(x,y)=(sum xy)^2/(sum x² sum y²)。任一能量为零时null，不加epsilon、不以零冒充。
固定六对：mic/reference、mic/primary_echo、primary_residual/reference、residual/reference、primary_residual/primary_echo、residual/echo。
另记录primary_residual和residual相对mic的功率比；mic能量零时null。无延迟搜索、滤波、平滑或参数优化。
同帧输出仅依赖当前六条输入trace，不读取near、true_echo、oracle标签、控制CSV或窗口来计算特征；输出为8列特征及frame。
返回值不是频域相干性、检测概率或声学评分。D31不新增声学裁判，不重算或改变D30权威评分。
normal44+repeat沿用D30 whole/windows的样本区间，统计完整包含的160点帧；边界向内取整且记录原/实际区间及丢弃样本数。
每列报告valid/null数量、min/max及固定nearest-rank p10/p50/p90；near_present仅在事后复制原窗口解释，field没有near标签。
future只做与normal在通知1247帧前的CSV逐byte前缀核验，不评分或用于结论选型；repeat全部特征CSV必须byteeq case07-used0。
观测接受：输入/源码起止hash一致、46case/每帧9列、finite或明确null、C容差1e-12内[0,1]且不钳位、功率比非负、重复/前缀一致、既定窗口/空值统计及独立重算。
可以保留重叠、不确定或无判别信息；不设分离率、检测阈值、选型门槛，不由同一数据批准新检测器。
固定decision=NEAR_PATH_OBSERVABILITY_DIAGNOSTIC_NO_PROMOTION；promotion_allowed=false、shipping_approved=false。

## P3 执行与收口

scope_write=新device_observability.py、test_device_observability.py、D31 PLAN/RESULT/REVIEW及README入口；原D30所有源/工件只读。
输出新根=/tmp/audio-fe-device-observability-d31-20261011；已有根/仓根/输入祖先或子树拒绝，不覆盖。
预算=46case、126486frames；每次内存只加载单case六trace；不新建DSP库、设备连接、外部依赖、CI/workflow。
retry_budget=2；子命令timeout120；父编排观察同一live handle，观察超时不重启；staleness_threshold=任一冻结输入/源码漂移即replan。
资源矩阵=主测量写新根，终态后冻结，独立审查只读；不得与主根写操作并行。
定向测试涵盖同向/反向、正交、零能量null、非finite/长度错误拒绝、缩放不变、当前帧因果、原窗向内取整；非仓help/dry-run。
负例需拒绝原D30根、仓根和已存在输出根并保持原文件；不因负例返回0或无输出宣称通过。
独立verifier不import新工具，stdlib独立计算特征/窗口统计并核输入身份、repeat/future、全部实际case/frame数量。
exit_gate=计划/实现独立审查→实际测量与定向/负向检查→独立重算→whole-change复审→文档检查/Runtime final。
open_items=3；plan_completeness=P1/P2/P3；attestation_readback=冻结hash及起止绑定；heartbeat=真实handle/Runtime。
stop_condition=pass/replan/blocked/abort；logical_task_open=true；milestone_close仅本轮观测；session_handoff_required=保留原负结果与下一因果假设。
handoff_target=单独冻结的近端检测器研究及完整后处理验证；retention=仓内reviewing candidate。
rollback=停止使用D31观测工具，原D30字节不变；无commit/push/PR/merge/发布/设备写，AISpeech产品链、SSC305资源、真人/KWS/HIL/E001/PQ未批准。
