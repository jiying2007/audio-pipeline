# D33 独立审查与最终复验

日期2026-10-11；experiment=FE_DEVICE_GUARD_INVALIDATION_D33；claimant=root；verifier=device_capture_independent_review。
primary=adk-planning-execution-loop；supporting=adk-verification-before-completion。
fresh whole-change Spec PASS、Quality PASS、Reviewer Independence=independent、unresolved findings=0。
执行、测量、拒绝记录及修正后的收口脚本一致性通过；候选仍为GUARD_INVALIDATION_DEVELOPMENT_REJECTED，总体native优化目标active。

## 冻结合同与因果边界

PLAN SHA256=9091611aa194268ec4f475e84a37ac07d5900fabb5d800c887874e4d3b842116；独立计划和实施审查通过后才执行主矩阵。
唯一改变为feedback模式在真实notify帧、Activity与gate计算前清零全部40B保护历史；monitor和无通知状态不变。
Activity、primary、selector、transition不重置，shadow仍只执行原通知复制/重置；D32阈值、100帧稳定条件、hold3与Float32运算保持。
每个return来源唯一notify1000；静态A也保留原误通知；ABA1200是路径返回，不添加第二次通知。
field沿用原D16首counter通知，实际帧为457/627/1057/1247/1977/2557；repeat/future通知为1247。
同一单路输入上两套AEC状态，不是双麦逐路处理；旧D0-D32专属源码、采集与制品不改，无验收阈值调整。

## 主执行与独立审计

接受根=/tmp/audio-fe-device-guard-invalidation-d33-20261011。
result/binding SHA256=09cc3b8156436c033adf353d03a9db5079a660c14ab89a574b8238f84596af72 / fe9d21710ed6a2ca35ed9b7b7eba8579ea64d46d57ed8cf4012cda4d3cb0cf79。
主wrapper四份真实回执均exit0；严格预编译、自检、五项Python测试通过；主DSP retry0，独立audit retry0。
92次真实C执行、252972帧；primary/Activity/observer/selector/transition各252972次，shadow89128、reset60、mixed179840、switch562。
局部资源71264B、guard40B、两AEC66040B；研究128KiB与原B0 50000B预算不改，不据此认证目标板资源。
monitor全13输出复现D32、原12输出复现D30；feedback无通知13输出一致，有通知之前13输出前缀一致；重复与未来前缀控制成立。
独立stdlib audit不import项目helper、不重跑DSP；首次真实terminal exit0，elapsed334.253647s。
audit脚本/回执SHA256=12435caf8a6632b67ca321242c85599b2f05be48809779ecac9bb88809c00e5d / 0c5a7b18a8054aa6e0542f2e3fcc09caebe069e7bfb834c67558d4080df1991a。
9556次起止hash核验；92case/252972帧、736新trace/323804160个Float32样本、480新窗口与480 D30 delta全量复算。
另独立重算720个D32 trace/316062720样本、480 D32窗口与480 D32 delta；806个D32全量文件和390个通知前前缀比较成立。
monitor对D30比较552文件，repeat26/future26；30个实际失效帧的armed_before/stable_before/guard/useddt均为0。
guard/selector/transition差异0，代数最大abs2.2351741790771484e-08，评分最大abs1.4210854715202004e-14，两类delta差异0。

## 拒绝结论与失败保留

五项准入独立重判：near coverage FAIL、static near onset FAIL、echo no false guard PASS、original return error PASS、field switch count PASS。
8个near首段[1000,1200)保护覆盖均0/200、首次保护null；第二段[1600,1800)均199/200、首次保护延迟1帧。
4个纯echo的[800,2000)误保护均为0；ABA原D32的895/892帧误保护被消除，但不能抵消首段near遗漏。
相对D32，A-r16/r20首段窗口error明显增加，12.5–14秒分别增加21.015872/20.880889dB；ABA纯echo18–20秒改善33.016651/33.136973dB。
相对D30，12个return的原整段及窗口最大error增量为0dB；这不表示每个窗口delta均0，也不表示真人声学或KWS合格。
候选拒绝，不能以误保护下降或局部恢复收益批准算法。
root实际执行旧D32根、仓根、已有D33根三类输出保护负例，均exit2；D32完整1387文件与D33完整1364文件manifest前后保持。
negative回执SHA256=caa281ecc74dfda9a7fd4eeb1c87185a232146eacb3224e5999d387061200f1b。
verifier审计负例脚本、回执和计数，未独立重跑历史manifest或负例；独立数值复算与root负例责任分列。
argc及五项非法参数均exit2、13个sentinel保持、primary/shadow/Activity/observer调用0。

## Whole-change修复与收口复验

原docs self-test、docs consistency、git diff三项实际检查均exit0。
v1快照29项SHA256=f9ffca88aaeeee6d4670a0fe32906f3dbfa8c03d803b17ece9809faa54d09cde。
首次whole-change Spec/Quality FAIL，MAJOR-1：原finalcheck/closeout writer漏改大写实验编号，指向不存在的D32 PLAN/REVIEW。
两原writer尚未执行，未产生实际FileNotFoundError或exit1回执；保留其原字节及v1快照，不覆盖失败设计证据。
新finalcheck-v2只绑定D33 REVIEW；新closeout-v2绑定D33 PLAN/REVIEW、v2快照与两份finalcheck-v2回执。
finalcheck-v2/closeout-v2 writer SHA256=7352fcdb06de720e871a7303f0c9173cc97bbb9dca46c8114995a0714c05f812 / 51d60a16259b03f45b5cb6d8e6b3a07933350c242993c657e25cff165c8c5d82。
v2快照33项SHA256=e250dbf7773fe144978ae038c16e0aaeb057e4a522e7c9ba339cf8ed50b00ddf；独立起止全部一致，原29项未变。
fresh whole-change关闭MAJOR-1、Spec/Quality PASS、未闭合finding0；不重跑DSP、评分或audit。
本REVIEW完成后运行finalcheck-v2，回执绑定本文件当前hash，再独立附核并执行closeout-v2；实际终态以这些新回执为准。
首次REVIEW附核发现MINOR-2：把return的notify1000过度扩展为所有来源。原REVIEW保留于/tmp/audio-device-d33-review-before-minor2.md，SHA256=ed5a06d3a250166088011058cb6dc986852ea73e3971ae6df6ae8ead937a0b92；原finalcheck-v2两回执均exit0，只绑定修正前文档。
修正仅限定通知文案；新finalcheck-v3与closeout-v3沿用已审逻辑，分别生成新的v3回执并绑定修正后REVIEW及各writer身份。v2快照33项不改，不重跑DSP或audit；以v3复验和独立附核为当前收口依据。
Runtime仅收口本地D33里程碑，总体native目标保持active；Runtime final不是domain或产品资格。

## Codify Decision与下一步

delivery_goal=检验通知时失效保护历史是否同时消除路径误保护并保持near保护；实际得到完整保留的开发候选拒绝。
reusable_pattern=单因果失效实验、monitor复现、真实通知身份固定、事后near标签与选择分离、独立逐帧及原窗复算。
affected_asset=研究C/header/tool/tests与中文入口，无公共API或产品default改变。
promotion_candidate=false；do_not_promote_reason=全部near首段保护丢失，静态误通知也破坏保护，缺独立真人及目标资格。
next_task_friction_reduced=已区分历史保护对恢复与near的相反作用，不再猜测清零是否足以闭合两者。
reduced_by=92次冻结执行与独立9556hash/252972帧复算；reduction_evidence=result/binding/audit/negative/v1-v2快照及原writer保留。
owner_review=无产品owner批准；rollback_path=停用新feedback实验入口，monitor保持原结果、保留旧库与用户dirty。
verification_evidence=独立计划/实施/whole-change审查、实际主执行、自检/负例、独立audit与REVIEW后绑定复验。
下一研究需分别冻结通知可信度与near保护依据，保留本轮失败，不改阈值或裁判追绿；尚未批准或执行下一实验。
AISpeech产品链、NS/RES/AGC/VAD/KWS、真人near、SSC305 CPU/热/功耗、HIL/E001/PQ和owner资格分别未闭合。
Provider route unresolved/current为空，知识线NEEDS_REVIEW，无正式归档；无commit/push/PR/merge/发布/设备写。
