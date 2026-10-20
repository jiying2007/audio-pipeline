# D39 独立整批审查

2026-10-11，FE_DEVICE_DOWNSTREAM_D39。Reviewer=`device_capture_independent_review`，Reviewer Independence=independent。计划、实现修复、实际全量数值审计与整批文档/代码审查均已给出 Spec PASS / Quality PASS，unresolved=0。该结论仅覆盖本轮冻结下游接续与工程诊断，不完成总体目标、真人声学或产品资格。

## 实际核验

主矩阵root仅执行一次：92臂/252972帧、actual exit0、132.676866秒。独立审计唯一session11957 terminal exit0、191.720627秒、retry0；回执SHA256=ac61aabb9d3d43700cebfa759c02a5566ac1e0a5d4c3324aefa3456a7ed8b60a。独立未import项目measurement helper，未执行C/AEC/主矩阵。

92个intent/command/summary、276个PCM长度/finite/旁路字节、40475520个AGC输出样本binary32 exact、AGC/VAD状态递推、Activity gates/频域分支与allow、repeat/future、90whole+390fixed共480测量组均通过；1440阶段RMS/peak、648known-near统计，最大RMS误差0dB、peak exact；2308合并来源/输入/制品/result/binding路径起止SHA一致。NS FFT未独立重算，其身份/长度/finite/分支检查及作为AGC/VAD递推输入的角色明确，不宣称独立NS FFT数值oracle。

独立描述审计26组摘要exact，192个原窗口near_present按near trace核验；24near窗口/arm共3200帧的控制重叠数字独立只读确认。near误差中位+9.3418dB与无near残余能量下降同时保留，不能推导门控因果已隔离、真人准确率或产品可采用。

目录负例脚本和root实际回执已独立审查，三个既有目标各exit2、完整manifest起止相同；reviewer没有重跑三负例。资源仅scoped11696B，合计82920B，未改变原B0预算或声称目标板资格。

## Finding 关闭与文档身份

MINOR-1：D39 local logged helper在TimeoutExpired/OSError时缺异常回执；追加先intent、异常null exit/partial stdout/stderr回执及拒绝重放，实际7定向测试和独立复审通过。原helper和首链接失败保留。

MINOR-2：PLAN把每臂240总组写成240fixed windows；新增[计数勘误](DEVICE_DOWNSTREAM_D39_COUNT_ERRATA.zh-CN.md)，保留原PLAN及所有锁定字节。每臂45whole+195fixed，两臂90+390=480总组；实现逐原列表无丢窗/造窗/阈值变化，独立审查关闭。

whole审查实际核身份：RESULT faa845f29c9153132632abce797286eb9b7b548cc016770013ba66795cf9cd0b；COUNT_ERRATA 0e725e9bfdd3767eba7136ed5647fe21a68014c8ad8367f410463cadac11baf9；README 4f34763d08fbbf1521a3f260b92a79b4f2f716b8bbdb833799a45164ec297977；closeout writer 0b9caf135e29a10182f30d4b569aae6ca62a2eb273a4b9b5aeb968037a876563。

## 本地终态门禁

closeout控制审查PASS：固定D39 localgoal active/open3/checkpoint2/progress2及未占用result/build/review IDs，snapshot/review SHA及文件锁，audit PASS与双finalchecks；14操作各先xintent、异常回执并停、既有operation拒绝重放。当前尚未执行；必须先生成本REVIEW、真实docs/diff回执、冻结快照并独立最终readback后，才运行唯一closeout。

本地Runtime完成后只能宣称D39局部里程碑完成。固定决策DOWNSTREAM_INTEGRATION_DIAGNOSTIC_NO_PROMOTION，promotion_allowed=false、shipping_approved=false。总体nativegoal继续active，完整SDK、AISpeech产品链路、真人/KWS/QIVW和目标板资格待证；Provider route unresolved、知识NEEDS_REVIEW，无归档成功声明。未commit/push/PR/merge/release/设备写。
