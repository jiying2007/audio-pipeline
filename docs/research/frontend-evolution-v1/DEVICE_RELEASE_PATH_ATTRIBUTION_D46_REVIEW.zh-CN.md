# D46 独立归因审计与整批审查

2026-10-12，claimant=root，verifier=device_capture_independent_review。D46唯一主测量及首次独立全量归因审计已实际完成，测量可复算；不是算法候选或根因证明。计划/实施及正式writer/negative控制独立Spec/Quality/Independence PASS，MINOR-1 closed，unresolved0。fresh whole-change review、快照及本地收口待实际后续回执，不提前声明完成。总体native目标active。

## 真实独立审计

标准库独立struct解码、顺序float64左折叠，不import新测量helper、不DSP。脚本 `/tmp/audio-device-d46-independent-audit-v1.py` SHA256=`b8414188a50f0fdc1b21e7eab0ffc0469ad27dbccc755526fdcec480026fb805`；最新selftest-v2实际exit0、.0036462731659412384 s，13项负例及对齐/尾截/LE/能量/peak/zero/partition/旧inactive count/mode验证通过，receipt SHA=`75176c570843ccf39187396998d2b22abdc4f93ae1445201628c54eab7a705a4`。首版成功自测及对应source保留，不覆盖旧身份。

唯一audit session74308实际terminal0，67.19922770187259 s<原180 s，无重试；receipt=`476f7c686309e9fcea0bc792e5267b93f1463926bdcd0f5540a1a23f1f83db93`，intent=`53c9b23685b666ed1fabdadd45ede782f67bb37c74ecb6bde61caf2c40234a62`。主与独立均实际回读。全部24配对/168段/336 stage及48 whole，共384项统计、96000个power输入帧/48000配对帧独立重算；96PCM+48power、主199输入集合精确对应，审计206项起止锁一致，最大数值绝对误差0。

实际能量字段的expected0比较计数为0；能量strict-zero/null能力由自测证明，不能冒称本批实际零能量场景覆盖。power空有效集严格零由实际逐帧合法性核验；不混淆两种覆盖。

原FFT、逐bin算术、完整EMA/noise历史未重建，24配对不是独立新增采集样本；field/repeat/future不在本次归因集合，不能扩大为设备整批复验。D45原960评分、拒绝和产品资格边界保持。

## 根保护与结论边界

主negative session41431实际terminal0、39.03372858092189 s，旧D45/仓库/新D46三个请求均exit2，完整file manifest前后相同，当时文件数1885/2607/3。receipt SHA=`24a08546fe4bb1441e2cf965d408b259772fbdf38d9e5dc188767b8e752c3598`。后续新增文档不要求仓库仍2607文件；独立审查只核实际脚本、intent和receipt，不冒认重新执行历史manifest。

[RESULT](DEVICE_RELEASE_PATH_ATTRIBUTION_D46_RESULT.zh-CN.md)与IMPLEMENTATION/HANDOFF写入时的pending状态保留字节；本REVIEW及机器回执证明后续真实终态。所有分段和whole均独立匹配，确认纯echo ABA回A后较长时段仍有实际保护差异。该证据不支持把完整失败仅归给near释放短尾；尚未分离各状态机制的因果贡献，不推出唯一根因或新候选。

## 待执行整批审查及收口

required_evidence：冻结计划/实施/两源码，唯一主intent/receipt/result/binding，negative全部操作回执，audit及自测/intent，RESULT/REVIEW/HANDOFF、fresh docs consistency/diff check、独立whole-change review、冻结快照与固定Runtime本地收口。

当前task-f972a6cb6470af7431f4e9e1 active/open3，progress3/CP3verified/events736。已登记RESULT摘要698cdc5f9c3e9dc013e7a48166738ea7a3b8139435c976fa8fb995ef760043cb，不能以同一evidence ID改绑新快照；新repo artifact须使用独立snapshot evidence ID。后续控制先独立审查再执行，排他intent/receipt，unknown先对账，不覆盖/重放。

D46 measurement_only=true/algorithm_changed=false/promotion_allowed=false/shipping_approved=false；本地里程碑不完成总体native目标。Provider route unresolved/NEEDS_REVIEW，无归档成功；无commit/push/PR/merge/release/设备写，真人/目标板/HIL/PQ与AISpeech产品链分别待真实证据。

## 独立整批审查实际终态与签署

2026-10-12，verifier=device_capture_independent_review。本节在原pending记录之后追加，保留上述各段写入时状态。独立语义结论：**whole-change Spec PASS / Quality PASS / Reviewer Independence PASS**；unresolved=0。MINOR-1已定向修复并独立复审闭合。这个结论针对冻结来源、测量、文档和受控收口准备，不批准新算法、根因或产品资格。

独立whole writer `/tmp/audio-device-d46-whole-review-v1.py` SHA=`2176f4993fd721128b5a8ca2ccab7d0fb129ebf118cbe9f5e66c07e831f3e756`，唯一实际session46808 terminal exit0（chunka4ff7e），1.8311216803267598 s。机器回执状态为MECHANICAL_WHOLE_READBACK_PASS，不能代替本节的独立语义审查；receipt SHA=`db09fc6fbd2647c1a726a60a3bbcf56aa9ebb9bcbb5bf35fd9e3cf84f2a7f097`，intent SHA=`deefe50c5aabb613d4eeceab444e76b527c7c2b3583ba99eb3a6bdedbc2a3a08`。共231项当前文件起止锁一致，并再次只读回核，未重跑384项数值统计、DSP或负例。

原199项历史消费身份明确为198项其余当前输入加唯一旧README备份；旧README SHA625af26c…完整保存，当前追加README SHA=`ac998973955f56f63cc7e0bd73e203c595e21c71d703f001f0ba43074914ecb8`单独锁定。[README修订](DEVICE_RELEASE_PATH_ATTRIBUTION_D46_AMENDMENT_README.zh-CN.md)的映射只适用于原README及精确SHA，原binding及D45 snapshot保持历史身份，不声称旧199路径或旧47项全部仍为当前工作树字节。source_input_start_end_equal仍只证明formal与首次audit实际执行时点。

本次审查时REVIEW SHA=`cb0304a570c2d87df1a9f8746f2ba3a4bd1230cb82d90c4bfeb8ccfe39968dfd`，完整原字节已在whole intent的review_at_review_bytes_base64保存并核摘要。REVIEW签署文档不在whole locked_files中，单独记录审查时身份，审查期间保持未改；本节追加产生新的签署身份，由后续最终快照另行锁定，不能把旧SHA称为当前SHA或用任意fallback略过文档漂移。

RESULT两个描述表逐项对应已完成独立复算的正式result字段；纯echo ABA回A后持续差异与near结束短尾的区别准确，24/168/336+48whole、96k/48k帧、实际能量expected0计数0及strict-zero自测边界均未扩大。negative只审主实际历史manifest控制/intent/receipt，不冒认独立重跑。

freeze-v1 SHA=`86674b03771d74b561418a258fe8e1d0ea7f635db793995d2996de95a09f438e`、closeout-v1 SHA=`01f1df2696dfbb3d3189888667e6b059dcf7fc4b6346581767d3e753adaddfdb`静态审查通过：唯一README映射、当前签署版快照、required旧RESULT保持、新snapshot evidence ID、固定task/CP4/open3和维护门禁、排他intent/receipt、异常保存及未知不重放。build仅指宿主测量bundle，不是目标板编译。

截至本签署，最终快照、verify及12项closeout尚未执行。后续必须完成CP4、唯一freeze、两项真实verify和当前快照独立回读后，才可唯一local closeout；实际终态另记，不提前声明D46里程碑或总体native目标完成。
