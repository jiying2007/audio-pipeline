# D41 本地里程碑收口

2026-10-11，experiment=FE_DEVICE_SPECTRAL_PROTECTION_D41。本轮计划、实施、184次主执行、首次独立全量测量、拒绝结果披露、whole review及本地Runtime收口已完成。独立最终Spec PASS / Quality PASS，Reviewer Independence=independent，unresolved=0。Candidate保持SPECTRAL_PROTECTION_DEVELOPMENT_REJECTED；总体native目标“全面推进优化迭代”仍active、无token上限，未标记总目标完成。

## 终态证据

- 主session93203 terminalexit0，279.56960721872747s，184执行/505944帧；result SHA256=`38d6f5eab2e3c3f6c8d9bea66f267015f7f02cde5ce73e5f3db29d32c1e3ce47`，binding SHA256=`a61625805a15ac877724064c1777bd2681751b1398b4cb86f1d206d35160a35f`。
- 首次独立audit session52581 terminalexit0，491.47727013379335s，retry0；全184例、960测量组、4512合并路径锁通过，RMS最大误差0 dB。回执SHA256=`93ee3a4a26426bc65db01802d5b370e23dfd249abe0f77ced4fade56b90200fe`。
- 最终文档检查session32051 terminalexit0，docs consistency PASS、git diff check0，两回执绑定REVIEW SHA256=`a7135d8042a8e62c639bd473d2b5da9e1543981d33bec6d4b394f6b0d8c32d2b`。
- 唯一freeze真实exit0，42个文件；snapshot SHA256=`aedf5529766fbe90e5260b75cff3e092cda942314a53f7dc171201fe88cce3b4`。独立执行前及收口后全部current文件起止hash一致；本CLOSEOUT在其后追加，不改原42项冻结文件或历史快照。
- 唯一closeout session42247 terminalexit0，14项操作0–13全部exit0；`/tmp/audio-device-d41-closeout-{0..13}.json`及对应intent均由独立reviewer核验command、intent/writer/snapshot/REVIEW/固定thread绑定。

固定thread=`01a1212f-b85c-7a21-885d-4cf591efd653`，D41 localtask=`task-2071a5c74c869f5d54f6fd7b`，已completed/open0；progress revision3、checkpoint revision3 verified，绑定device-d41-review。repo/build/review artifacts分别绑定snapshot、主binding、当前REVIEW；PLAN/PLAN_REVIEW/HANDOFF既有证据身份保持。

实际final gate `2026-10-11T09:04:39.655952Z` 返回pass、gate_allowed=true、completion_allowed=true，missing/reasons为空，maintenance.required=false。Runtime证据只证明D41本地conformance，不能推导真人、AISpeech产品集成、目标板或shipping批准。维护原回执仍保留ACCEPTED_COMPLETION_UNVERIFIED，未伪造完成或重发同一请求；当前门禁解除和请求完成核实分别陈述。

## 拒绝结果与下一步

两臂含near误差中位下降约5.15 dB、各20/24改善；无near固定窗残余能量中位增加约14.11 dB，最大16.5907 dB；纯echo整例最大增加2.1732/2.1080 dB，超过冻结1 dB门槛，因此拒绝，不调宽验收或以含near收益抵消纯echo代价。静态A纯echo末窗也退化，后续需核绝对创新量、低能量非相干残余和near的可辨识性；不是已证明唯一根因或下一算法的执行资格。

数据继续为已查看development和合成工程对照，repeat/future控制不升级为独立样本。实际全部bin EMA/NSFFT未独立重算，资源93224 B不是目标板资格且B0 50000 B未满足。Provider route unresolved、知识NEEDS_REVIEW，未声明归档成功。产品链路固定点SEVC/QIVW、真人识别、CPU/RAM/功耗/HIL、owner和shipping分别待证；后续新研究先冻结新身份、唯一假设、测量和验收，再实施验证。

参见[结果](DEVICE_SPECTRAL_PROTECTION_D41_RESULT.zh-CN.md)、[独立审查](DEVICE_SPECTRAL_PROTECTION_D41_REVIEW.zh-CN.md)、[执行前集合澄清](DEVICE_SPECTRAL_PROTECTION_D41_AMENDMENT.zh-CN.md)。原D0–D40失败与用户dirty保持，未执行commit/push/PR/merge/release/设备写。
