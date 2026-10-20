# D48 当前创新测量契约解耦结果

2026-10-15整理，执行证据产生于2026-10-13。experiment=FE_DEVICE_CURRENT_MEASUREMENT_D48，kind=measurement-contract-repair。结论：MEASUREMENT_CONTRACT_VERIFIED_NO_PROMOTION；固定D47算法开发准入诊断为两臂accepted=false。测量修复验证通过，不批准该算法或产品。

## 唯一变化与实际执行

新增显式测量适配器，将D42 observe中旧floor<=D41专有性质分离为historical_floor_diagnostic；原六项状态、统计、控制、波形、对齐、warmup、范围和原开发准入保持。原D42/D47源及D47失败证据不改；本轮冻结D47 C/NS/header，不调整算法系数、门槛或状态。当前tool=27b5ae3e00d9e74e2cbbc1c8b37a185119d493e295243236ff1b1e936a6c3fed，test=4f9a5a536bdb699119d72ef62c5b3691611bf91c7b08d0596ac6376010bc5c85，IMPLEMENTATION=99ec372bc85e4dddd96ba534f0fd68bc2a1e2676c32cda38d96bfb810a24136a。

16个D47已通过案例的公共字段逐值parity，加第17例旧性质反例准确报告；parity receipt=902ec0a5fc66a47c186e253d7846f8f45035b982c22b9a94d595ddf27e7355f6，实际47.765931472182274秒/exit0。24个篡改负例实际18.08648875541985秒/exit0，receipt=436216ea12a2a62c11ac2bf66de59d15f6b54137fb1247fcae5ba7173b457ce7。两项运行对应已保全的历史observer草稿AAA135版本；当前源码中observe/common函数与该草稿正文逐字一致，不能把历史回执谎称绑定当前完整模块SHA。新模块完整deepdry实际63.945382092148066秒/exit0，receipt=5c853e8a3a23d47eb7b898355605a21b8b7a73f2682941c49f06da195abe8e67；46来源/11744锁齐备。均只执行既有唯一操作，不为收口重跑。

唯一正式根 `/tmp/audio-fe-device-current-measurement-d48-20261013`，184路、505944帧，原46来源×primary/selected×monitor/candidate；内部矩阵680.0206774584949秒，outer735.061845571734秒，均小于1800秒。actual session12387真实terminal0，来源开始/末尾hash一致。result=d8c80ee2c612fccd62de1bae86bf107e71062e95c1609cddf7abe5714992a6cf；binding=5f8fa795e386e32c83743f66ffdc1361bf48cc00705f13f11efa7238c0d3e9ff；outer=fe25ce75a2833dd4258b514b54340e175db0b980a1ec9e864e30bf8cfd3a0a59；intent=352aad96e17cfc7173bb31e956e7f70a8ca69241b533e2c172494751fc5a56a0；writer=f61770a0865f275c72ac8df261e8c60696f4e2cac11189b3dfe893689418458f。正式intent记录时CP3 verified绑定实施文档，后续CP4/CP5接力不覆盖历史CP3。

## 独立全量复算

主侧完整静态检查独立审计脚本；其唯一自测实际exit0，receipt=da30a4438233cb3232f2a75fb35b805edf0b4eced664a324c461135f5bccd272，包含9项复数已知答案、2项溢出/nonfinite和阈值/postmax/strictzero/CSV/波形反例。独立reviewer执行前核验身份链后，主唯一启动full audit，不import生产helper、不DSP、不修改正式根。

actual session97408最终0151c4 terminal0，990.6784172942862秒，小于冻结1800秒；receipt `/tmp/audio-device-d48-independent-audit-v1.json` SHA=a583e4d2097b298f6c57f1833b8a4521dbbe328bd0f146d62cd40545563060a9；intent=8f4a8236355e45640b02e31d6f253ea23a4d389a8bc27b79ad5eb5f4ce269c40；writer=06dfdd4cd47dcc9b80fa9c84b1c28fb54ef24982d60ea2588929e08e810d3195。独立reviewer随后实际回读终态、command/cwd/intent/writer和准入对象，未重跑审计，确认审计范围Spec/Quality/Independence PASS、unresolved=0。

| 已核项目 | 实际覆盖 |
| --- | --- |
| whole/fixed新测量及D39比较 | 960组，RMS最大误差0 dB |
| power与AGC/VAD递推 | 505944帧；80951040 AGC输出样本，binary32 exact |
| 固定快照 | 7568帧、1944976 bin算术 |
| 汇总检查 | 75680项，其中41690项严格零 |
| double汇总误差 | 最大绝对5.115907697472721e-13、相对3.062613005952661e-15，原容差内 |
| 未改输出 | 460项byteexact检查 |
| 两模式投影 | 252972 power行、972488 bin行 |
| repeat/future | 28文件全量exact、28前缀exact；4future不评分 |
| 来源与工件 | 13636项起止hash一致 |

全帧schema/count/range、固定snapshot复数H/prediction/J/P/floor/postmax、历史D41诊断准确性均在覆盖内。完整FFT重建、全帧bin算术、完整EMA/noise历史重建仍false；快照不能替代这些缺失覆盖。host sizeof/scoped/磁盘预算不代表目标板CPU、栈/RSS、热或功耗测量。

## 原开发准入的独立负结果

保持原24near/72no-near/4pureecho、160点OLA对齐、原固定窗口和D39比较对象，未改变准入阈值。两臂原全部条件须共同满足，实际均失败。

| 原准入条件 | primary | selected | 结论 |
| --- | --- | --- | --- |
| near误差中位≤-3 dB | -5.549494772309668 | -5.54949477191996 | 满足 |
| 24near至少18项改善 | 20 | 20 | 满足 |
| 72no-near最大增量≤+1 dB | +16.872746384480372 | +16.872746384480372 | 失败 |
| 4pureecho whole最大增量≤+1 dB | +2.3946506830306262 | +2.7978050756589425 | 失败 |

因此只能确认当前保护映射在该开发数据上改善部分近端误差，同时明显增加无近端及纯回声输出；不能把创新量J认定为近端真值，不能以中位收益覆盖最坏退化。本轮不对系数/阈值搜索。原D47测量耦合失败保留；D48补全测量后取得独立算法负结果，两者属于不同事实。

## 边界与后续

数据仍development-and-synthetic-engineering/adaptive reuse：32已查看field、12合成return、repeat/future；field无人声真值，repeat不是独立样本，future不评分。80/100为用户确认音量，rpm实际运动、物理mic映射和真人标签不足保持unknown。AISpeech固定点256/QIVW产品链与160点float研究链分别验收；不推导真人ASR/KWS或设备收益。

measurement_only=true、shipping_algorithm_changed=false、integration_changed=false、promotion_allowed=false、shipping_approved=false。新结果全文独立REVIEW、整批封存、README历史字节保存/追加与Runtime阶段收口仍待完成；本文不自批准这些后续步骤。下一算法结构假设须在D48证据保全后以新身份冻结、独立计划审查；不在D48中实现或放宽裁判。

跨日预算stop事实与同一任务窗口重规划单列AMENDMENT_RUNTIME_BUDGET，原执行上限不变。最新main已移动且检查未齐，不继承旧main绿色结论。Provider WORKSPACE_UNBOUND/route unresolved保持NEEDS_REVIEW，无归档成功。无commit/push/PR/merge/release/设备写；总体目标仍active。
