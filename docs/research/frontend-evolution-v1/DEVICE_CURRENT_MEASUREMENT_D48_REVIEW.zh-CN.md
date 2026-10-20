# D48 测量契约与原准入负结果独立审查

2026-10-15。claimant=root，verifier=device_capture_independent_review。执行证据产生于2026-10-13，本文件为后续独立只读复核与签署。仅新增本REVIEW；未修改RESULT、生产源码、原裁判、失败工件或历史文档，也未重跑DSP、parity、负例、deepdry、自测或完整审计。

**源码/适配合同、实际测量、独立数值审计与RESULT语义范围：Spec PASS / Quality PASS / Reviewer Independence PASS，unresolved=0。** 结论仅为MEASUREMENT_CONTRACT_VERIFIED_NO_PROMOTION。固定D47算法原开发准入两臂均失败，不批准候选或产品；当前尚未完成整批封存、README历史映射/追加、机械whole和Runtime收口，不能将本审查称为整批已closed。

## 当前审查身份

- PLAN：`6c751db7cd1832e5aa0db958011f23c8ff5ca3bf4fb56ad0a102bc2ab51724ca`；PLAN_REVIEW：`9f8e05a570551a0df39d5353c51a585ae0215792c463441c1ad0b23401d93086`。
- 当前tool：`27b5ae3e00d9e74e2cbbc1c8b37a185119d493e295243236ff1b1e936a6c3fed`；test：`4f9a5a536bdb699119d72ef62c5b3691611bf91c7b08d0596ac6376010bc5c85`；IMPLEMENTATION：`99ec372bc85e4dddd96ba534f0fd68bc2a1e2676c32cda38d96bfb810a24136a`。
- 本次全文审查RESULT：`786ca6eba329f48839f1db3c6a2c7ce7df0ec27f59cb2377c524298438153d84`。
- 正式result：`d8c80ee2c612fccd62de1bae86bf107e71062e95c1609cddf7abe5714992a6cf`；binding：`5f8fa795e386e32c83743f66ffdc1361bf48cc00705f13f11efa7238c0d3e9ff`。
- 正式outer：`fe25ce75a2833dd4258b514b54340e175db0b980a1ec9e864e30bf8cfd3a0a59`；intent：`352aad96e17cfc7173bb31e956e7f70a8ca69241b533e2c172494751fc5a56a0`；writer：`f61770a0865f275c72ac8df261e8c60696f4e2cac11189b3dfe893689418458f`。
- 独立audit writer：`06dfdd4cd47dcc9b80fa9c84b1c28fb54ef24982d60ea2588929e08e810d3195`；receipt：`a583e4d2097b298f6c57f1833b8a4521dbbe328bd0f146d62cd40545563060a9`；intent：`8f4a8236355e45640b02e31d6f253ea23a4d389a8bc27b79ad5eb5f4ce269c40`。

主实际执行正式session12387与audit session97408并回收终态；独立verifier编写审计脚本，主完整静态审查后唯一执行，verifier随后只读核验脚本、真实回执、command/cwd/intent及原准入对象。脚本不import生产helper、不运行DSP。当前复核不冒称verifier重跑了主的执行或历史manifest，也不把回执转录当成新的数值计算。

## 测量修复、发现及历史证据映射

D47的旧floor<=D41约束耦合失败完整保留：17条C成功但仅16例测量通过，无最终result/binding；旧task aborted，并非实验成功或当时的完整算法拒绝。主及独立实施审查遗漏旧映射专有上界的事实不抹去。

D48只新增显式observe测量适配器，将旧上界报告为historical_floor_diagnostic，保留六状态、通用统计/波形/控制、原开发准入和数值预算；D47 C/NS/header及current H/J/P/strict2N/postmax算法不变，原D42文件不改。适配器初版缺Path的MAJOR为静态发现，实际return运行之前显式导入修复；不制造运行NameError。新增分支依赖测试及真实保存return-echo fixture验证后闭合。

parity回执`902ec0a5fc66a47c186e253d7846f8f45035b982c22b9a94d595ddf27e7355f6`实际exit0/47.765931472秒，16例公共字段逐值一致，加1例冻结D45 return-echo fixture真实执行Path/known-near-error分支；不代表近端非零或新增算法收益。第17例旧拒绝保留，新历史诊断50帧超旧上界，max_mean_excess=0.16372198941990557；237消费路径起止检查成立。

负例回执`436216ea12a2a62c11ac2bf66de59d15f6b54137fb1247fcae5ba7173b457ce7`实际exit0/18.086488755秒，24项按指定ValueError消息拒绝。独立只读比较120个fixture确认每例仅目标文件变化，坐标例仅改私有case，范围差异0；原输入起止检查成立。历史parity/negative绑定草稿完整模块AAA135，旧源码备份`aaa135292a42de9818938007f3575661d47535cb62cb71d0b73de8b449d8c18f`及旧test`9e7763f1984fe9c800746faa2032ab8b543218688f2325a295139d998168561a`保留；当前observe/common函数正文与草稿逐字相同，独立源码对照成立，不把历史整文件SHA冒称当前SHA，不执行备份或fallback。

当前完整5项unit独立实际exit0/.060秒；新deepdry回执`5c853e8a3a23d47eb7b898355605a21b8b7a73f2682941c49f06da195abe8e67`实际exit0/63.945382092秒，46来源/11744锁、measurement-only且无写/DSP。新run及其helper投影没有再次引入旧floor上界；compile/拒绝sentinel/资源、mode控制、全部固定坐标、repeat/future及末尾fresh hash保持。

## 正式与独立全量证据

正式实际184次/505944帧，outer735.061845571734秒、matrix680.0206774584949秒，child exit0/terminal=true，source起止检查成立、无measurement-invalid，11744锁/1884工件。正式intent记录的CP3 verified精确绑定IMPLEMENTATION；之后的CP4/CP5接力不覆盖或替换历史CP3。

独立自测receipt`da30a4438233cb3232f2a75fb35b805edf0b4eced664a324c461135f5bccd272`实际exit0，9个复数已知答案、2个溢出/nonfinite反例及严格阈值、postmax、strictzero、CSV/波形反例；actual_matrix_audited=false。随后唯一full audit实际exit0/990.6784172942862秒，低于原1800秒。verifier实际只读回读intent、writer、command/cwd与正式身份链，当前result/binding SHA及准入对象仍一致，精确audit进程匹配为空，没有重新执行。

| 审计项目 | 实际覆盖 |
| --- | --- |
| 新whole/fixed及D39对照 | 960组；5760项stage统计，2592项known-near统计，最大RMS差0 dB |
| 全帧与下游传播 | 505944 power帧、505944 AGC/VAD递推帧、80951040输出样本binary32 exact |
| 固定snapshot | 7568帧、1944976 bins，复数H/prediction/J/P/strict2N/floor/postmax复算 |
| 原power及current三列 | 75680汇总检查，41690严格零，raw overshoot及P0/J正语义保留 |
| 汇总误差 | 最大绝对5.115907697472721e-13、相对3.062613005952661e-15，在冻结容差内 |
| 原输出与模式投影 | 460项byteexact；252972 power行、972488 bin行 |
| 复跑/因果 | 28文件全量repeat、28项future前缀；4future不评分 |
| 来源/工件 | 13636项开始/末尾SHA一致；564个inactive旧count行合法核验 |

全帧schema/count/range和历史D41诊断在覆盖内。完整FFT、全帧bin算术、完整EMA/noise历史重建仍false，固定snapshot不能升级为这些覆盖。sizeof/scoped/磁盘为host局部边界，不证明目标板CPU、栈/RSS、功耗、热、实时性或完整产品资源资格。

## 原准入负结果与适用范围

独立准入对象与正式result逐字段相同，原两臂分别判定，没有平均或改阈值：

| 原条件 | primary | selected |
| --- | --- | --- |
| near中位≤-3dB | -5.549494772309668 | -5.54949477191996 |
| 至少18/24改善 | 20/24 | 20/24 |
| 72no-near最大≤+1dB | +16.872746384480372，失败 | +16.872746384480372，失败 |
| 4pureecho whole最大≤+1dB | +2.3946506830306262，失败 | +2.7978050756589425，失败 |

两臂accepted=false。部分near误差中位改善不能覆盖无near及纯echo退化，不把J称近端真值，不据此选择算法、搜索系数或批准产品。D48测量合同验证与固定D47映射的开发负结果分别成立，不能倒推D47当时测量无效已经形成完整准入结果。

数据仍development-and-synthetic-engineering/adaptive reuse：32已看field、12合成return及repeat/future；field没有真人近端真值，repeat不独立、future不评分，near参考不作在线门控。音量80/100仅用户确认；实际运动、mic物理映射和真人标签不足保持unknown。160点float研究与AISpeech固定点256/QIVW链路分别验收，不代表真人ASR/KWS、目标板/HIL/E001或72小时PQ。

## 跨日恢复、当前未完成与CodifyDecision

AMENDMENT_RUNTIME_BUDGET保留跨日恢复时原本地86400秒耗尽、策略stop的事实；后续同task仅本地日历窗口更新604800秒，不重新ensure、不重跑。独立通过新固定`codex-policy.sh`入口只读当前状态：仍同task-fe8e96504fd58d9d71dd496b、原started_at、active/open3/progress5/CP5 verified，窗口604800秒、token64000000、events812；fresh steady为continue、维护required=false、completion_allowed=false，required result/review仍待登记。原单命令120秒、formal1800秒、audit1800秒及评分/容差/资源预算未变；不能把本地窗口更新冒称科学预算内完成或总体预算变更。

AUDIT_PREFLIGHT的`438d299f16f965f9a5568b7571d6f3122b26bcfc24d5b4af0854f32fdbe04248`与HANDOFF_AUDIT_RUNNING的`dc726779289d97c30495090a868663ced320f626d7030403d40c21058dff8447`是历史阶段记录，分别准确说明当时尚未执行与运行中，本次真实终态不覆盖它们。D48 native受理未证实完成的回执保持，不因fresh维护解除推导请求完成，不重发。

当前没有整批机械whole/最终snapshot/README历史字节保存和追加/Runtime阶段closeout的完成结论。本REVIEW本身尚未纳入这些后续证据，也不替主执行Runtime写或final。后续freeze须绑定最终签署版及实际独立审查证据，历史README只有显式保全映射后才能更新，不改旧snapshot或宣称旧README永远current。

CodifyDecision：测量通用契约与算法专有性质应显式分离，形成reviewing候选；Provider WORKSPACE_UNBOUND/route unresolved保持NEEDS_REVIEW，不声明成功归档或推断主体。最新main/PR head已变化且检查未齐，不继承旧CI或制品作为D48及产品证据。无commit/push/PR/merge/release/设备写，总体native目标保持active，后续新结构假设须新身份和独立计划。
