# D36 独立审查与最终复验

日期2026-10-11；experiment=FE_DEVICE_HELD_LAG_D36；claimant=root；verifier=device_capture_independent_review。
primary=adk-planning-execution-loop；supporting=adk-verification-before-completion。
fresh whole-change Spec PASS、Quality PASS、Reviewer Independence=independent、D36范围unresolved finding0。
decision=HELD_LAG_DIAGNOSTIC_NO_PROMOTION；本地里程碑仅收口前帧延迟预测诊断，总体native优化目标active。

## 计划与实施修复

PLAN SHA256=244bd87cde99c336e3fc791de0a49eb3ada5cb66159a522d74851586781ca501，独立计划PASS。
每帧仅以前帧有效chosen_lag解释当前160点残差；当前最大值直接消费D35，保留自身valid/null，不重新搜索或运行AEC/DSP。
首次实施发现MINOR-1：波形最优lag恒0却手造变化元数据，未覆盖冻结计划的真实最优变化known-answer。
原tests完整保留/tmp/audio-device-d36-tests-before-known-answer-fix.py，SHA256=bb84ca1bafa1eb85e906235751d1278b21cea8e38ced96b1a1d25e87a6b06dba。
按AMEND修复为反相延续及真实延迟0→1两例，验证切换帧past仍0、下一帧past1且held1；不跑新lag搜索、不改合同/阈值。
独立从/tmp复跑最终7tests实际exit0，fresh实施Spec/Quality PASS、unresolved0后才root首次execute。
最终tool/tests/execute SHA256=bfffb7987e54b2520baa1833f742548819ec3aa1207ad5170b3550d7383a3461 / 781193aa1296b3f9e85a24b855c41c283eedd3fbec0b05f847fea61fd86e6758 / d80268af3bb9521364fa710b3a036f698822b9223b773739b21d82e9ef59333f。
wrapper对TimeoutExpired/OSError先保留command、null exit、type、elapsed、已获取partial stdout/stderr，再传播；主命令timeout=None，其余120s，不把mock或回执存在当实际终态。

## 实际运行与数值验收

接受根=/tmp/audio-fe-device-held-lag-d36-20261011。
result/binding SHA256=8b1123301e08caa8e695188e8005a1022e0f023500e5151046454bb90f28c8b9 / 800b73b466054e606eeb6a70210d0027e01fde3eb1d225738ea84ff4bf09820e。
root四份execution实际exit0：非仓help、deep dry-run、7tests及主测量；main36.02549481391907s，retry0；dry根未创建。
46例126486帧，3792 input_files及4 source_files起止一致；binding47工件。原D35全部来源/helper及两独立审计/REVIEW均锁。
纯Python Float32解码后double正向累加，无补零/均值扣除/未来索引/clamp；无前帧/前帧无效不保持旧lag，五种reason优先级与-1无效值明确。
repeat CSV全量exact，future通知前1247帧前缀exact且measurement=null；240原whole/window向内完整帧及边界丢弃、guard前帧与near真值区间保持。
独立审计stdlib-only、不import项目/tool/helper、不编译C或重AEC，反向160样本累加全46/126486逐帧10列及全部240窗/near/no-near/guard统计复算。
audit脚本SHA256=3f6eae447150c25726a8084963ba0bd1c871195ee798688dfe9fe84b48852b23。
首次同一真实session38758 terminal exit0、retry0、elapsed34.126244775019586s；3844项起止锁保持。
回执SHA256=d4729fe1f725e4e7d5913d1f8b8da7a9bcfa17fc41261cb1da83851cfbd3aed4。
held/gap最大绝对误差1.4432899320127035e-15、energy最大相对误差2.7788185565234714e-15；固定1e-12未放宽。整数/reason/直接current_max精确一致、零能量和-1 sentinel239879次精确断言。
全46例reason0/1/2/3/4=66443/46/59716/0/281；actual零残差窗口0，零残差仅known-answer，不冒称现场覆盖。

## 结论与replan

RESULT表格与实际JSON一致：纯echo held p50约0.422–0.449、多数gap0；静态near held p50约0.0033且200/200 lag改变，证实有时间预测增量。
ABA首near held p50约0.173108/0.170724、max0.424288/0.422626；139/140帧lag不变且gap p50=0。near和稳定可解释echo可共存，仍与纯echo重叠。
field32主例96438帧reason计数37743/32/58418/0/245，current_max保留原37988有效对照；16整例参考全零、field无near标签，不从null推导没有回声/检测正确。
因此按PLAN停止条件replan至可解释残差创新模型，拟合时间与应用时间另行冻结；不继续相近相关性诊断、阈值寻优或批准保护反馈。
Python诊断Host时间不代表allocation-free/实时、完整前端或SSC305资源/热/功耗；既有资源超限及D32/D33拒绝不重写。

## 负例、whole-change与最终复验

root负例三根旧D35/仓/已有D36均拒绝exit2；完整125/2469/48文件manifest前后相等，elapsed2.72007417678833s。
negative回执SHA256=98efb0e6951ad2f5a77e3bc9a8ecba52801c3e1b826171fec626d563872a7156；verifier只核root脚本/实际回执，不冒认独立重跑历史manifest。
docs self-test/consistency/gitdiff3项实际exit0；snapshot28项SHA256=93e3dc9eb2ba9ba71578626b163194304da69b57c1c5bc15522de69019abec2b，独立核全部当前字节。
whole-change核来源、实际回执、表格/null/窗口、失败前tests、维护历史、negative及收口writers，Spec/Quality PASS、independent、unresolved0。
snapshot/finalcheck/closeout writer SHA256=3b877aef9a1e40dabd197c996165cb25aba457dce3f1add4660bba6881edde08 / 9dd37bd602d062d3fb509f2ae65b5b146b97c685719d06482cf30c0f6ec308e5 / 5e8446562d16d08a8b66bab579913e9c6e0e7490ff7c6f01342c15b98a19e405。
本REVIEW后执行两份finalcheck并独立附核，再执行14份Runtime closeout与独立终态附核；本文件只记录已发生证据，待执行项以绑定回执为准。
Runtime build引用binding只代表本地conformance，不是新产品制品或domain资格。README追加D36使旧D35快照README条目历史化，旧专属source/input/artifact保持。

## 维护历史与交付边界

宿主真实上下文压缩后fresh steady required=false、context_ratio0恢复。旧HANDOFF/CONTEXT_MAINTENANCE原字节保持，CONTEXT_RESUMED追加实际恢复。
v3控制的MAJOR-1/QUESTION-1未修未用；本轮没有发送compact请求，不将宿主维护归因v3，不把控制支线finding冒称D36实施finding闭合。
delivery_goal=检验前帧历史峰值是否有时间预测性、决定是否有理由进入新因果结构。
reusable_pattern=过去lag固定/当前max自身null/原因优先级/统计选择时间/逆序全数值与精确零单列。
promotion_candidate=false；do_not_promote_reason=混合near仍含可预测echo，不能形成独立验证的近端保护器。
next_task_friction_reduced=有时间预测echo但不能排除near，后继需分解可解释残差与创新；另冻结新PLAN，不从本轮自动生成产品阈值。
owner_review=无产品owner批准；rollback_path=停用D36入口，原算法/库/封存数据/失败/用户dirty保持。
AISpeech整链、真人near/KWS、SSC305 CPU/RSS/栈/热/功耗、HIL/E001/PQ、第三方权利与owner分别未闭合。
Provider route unresolved/current为空，知识线NEEDS_REVIEW、无正式归档。无commit/push/PR/merge/发布/设备写；总体native目标active。
