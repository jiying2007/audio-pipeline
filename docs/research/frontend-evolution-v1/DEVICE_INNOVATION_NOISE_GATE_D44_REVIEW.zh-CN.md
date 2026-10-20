# D44 独立审计与整批收口审查

2026-10-11，experiment=FE_DEVICE_INNOVATION_NOISE_GATE_D44。claimant=root，verifier=device_capture_independent_review。执行前源码/控制审查、首次真实独立全量数值审计和fresh整批源码/结果文档审查均Spec/Quality/Reviewer Independence PASS、unresolved=0；候选DEVELOPMENT_REJECTED。冻结快照及本地Runtime收口另行记录，不从静态审查推导实际写入。总体目标active，promotion_allowed=false、shipping_approved=false。

## 冻结合同及已闭合发现

MAJOR-1 原计划要求monitor五输出全部旧exact，与真实新floor诊断矛盾。执行前AMENDMENT和独立计划审查明确：四原波形/control exact；protection排真实floor_mean；candidate bypass exact；旧统计操作数/当前FFT/power/original_target/q/valid/count/gates保持相应投影exact。两D44模式仅排raised和old_gain/applied_target/res_gain；future和repeat仍按原前缀/七文件合同验证。不能将新floor伪写为旧值。

5个D44定向unit和继承26个unit实际exit0；严格C构建/selftest exit0，包含严格2N相等及nextafter邻界、N=0、q端点、warm/power门槛、NaN/Inf/negative/overflow、旧EMA known-answer与40帧observer-vs-NULL对照。非仓cwd help0、invalidargc2、deepdry session28397 terminal0：46例7935锁，writes=false/dsp=false。定向记录为实际工具输出转录，不能称为独立subprocess回执。

IMPLEMENTATION和HANDOFF_EXECUTION是绑定过的历史工件，保留字节，不覆写当时待执行/待审计状态。其后真实terminal状态由机器回执和本RESULT证明。

## 实际测量和独立资格

主session74128 terminal0，184次505944帧；根保护session45916 terminal0，三既有目录exit2、完整manifest前后相同。独立session59897首次terminal0，自测首次0，真实耗时844.4431319795549 s。回执、准入数字和覆盖边界见[RESULT](DEVICE_INNOVATION_NOISE_GATE_D44_RESULT.zh-CN.md)。

独立脚本不import项目helper、不执行DSP；以系统libm和binary32逐步舍入复算floor/target/gain、原AGC/VAD递推及全部80951040个输出样本。960新波形组及D39差值独立新算，RMS误差最大0；全帧schema、固定快照、严格零、旧count、mode投影、原输出exact、repeat/future及9824起止锁均通过。独立确认两臂near/no-near准入失败、pure-echo上限通过，测量有效但候选拒绝。

完整FFT、全部帧bin算术、完整EMA与噪声历史未独立重建。此PASS不等于独立声学、真人识别率、目标板或产品资格。原18改善窗门槛保持，不能误写为20门槛。无参数搜索、改判、重跑历史DSP或旧裁判变更。

## 整批独立审查与待执行本地收口

Fresh whole review已实际完成：独立只读重新核7935来源锁+1884工件，共9819唯一文件，零SHA不匹配。五个D44源码、PLAN/AMENDMENT/PLAN_REVIEW/IMPLEMENTATION原pin保持；RESULT/REVIEW/README审查起止身份一致，全部准入、960新评分、资源和覆盖边界准确。根保护只审实际脚本和回执，不冒认独立重跑。Spec/Quality/Reviewer Independence PASS，unresolved=0。

收口控制静态审查PASS：freeze SHA256=`404ea2f1f992f4df01120a8bc9ca838fcfdc319eb8800a1327139d2eec06ad12`，closeout SHA256=`1b6289247716e3f8474721e9dad7af11a88bd078eae9910506c4fefca9b20917`。固定本D44身份、snapshot/review CLI pins、排他intent/receipt；unknown对账不重放。仅本地Runtime登记，不调用总体native goal完成或外部发布。

required_evidence：实际result/binding、唯一主回执、根保护回执、独立审计及其自测/intent、冻结源码与计划、最终RESULT/REVIEW/README、fresh文档一致性和diff检查、独立whole review、当前task身份及最终本地回执。

open_items：exact文件冻结快照、本地Runtime证据登记及收口。CP3 verified/progress3是历史状态；CP4绑定实测RESULT文档，actualstate回读通过后才能依控制推进CP5。不能预先声称completed。stop_condition为实际验证通过后本地里程碑收口，发现新major则replan。

重试预算：主DSP/negative/独立全量审计均已terminal成功，不重跑；收口写控制采用排他intent/receipt，任何未知结果先读actualstate。保留所有历史实验和用户dirty。后续新研究保持单因果新身份，停止本固定2.0门控系数搜索。

Provider route unresolved、知识NEEDS_REVIEW，未归档成功。维护v2只确认受理；恢复freshrequired=false允许业务，未升级为完成证明。无commit/push/PR/merge/release/设备写。
