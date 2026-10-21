# D45 独立全量审计与收口审查

2026-10-12，experiment=FE_DEVICE_POST_NS_PROTECTION_D45，claimant=root，verifier=device_capture_independent_review。首次唯一独立全量审计已实际terminal exit0，measurement审计PASS，候选DEVELOPMENT_REJECTED。执行前计划/实施/正式writer及negative控制独立审查通过；fresh whole-v2 Spec/Quality/Reviewer Independence PASS，unresolved=0。冻结快照及真实本地收口另按后续回执记录。总体“全面推进优化迭代”保持active，promotion_allowed=false、shipping_approved=false。

## 已完成验证与真实身份

冻结五项D45源码、PLAN/PLAN_REVIEW/IMPLEMENTATION保持，未修改D0–44裁判、失败、参数或产品默认。定向父控制实际exit0，14项子operation均符合各自expected exit，其中7项拒绝负例实际exit2/4，不能写成14项均exit0。9项D45 unit和54项继承unit、严格C/selftest、非法argc/长度/NaN/Inf/gates及sentinel保护通过；observer-vs-NULL与新合成增益max边界、原NS/RES状态保持已测。非仓cwd help和deep dry-run实际exit0，46例9829锁、writes=false/dsp=false。

唯一正式session54607 terminal0，184次DSP/505944帧；三根negative session33006 terminal0，各请求exit2、完整manifest前后相同。正式数值、资源及SHA见[RESULT](DEVICE_POST_NS_PROTECTION_D45_RESULT.zh-CN.md)。RESULT、IMPLEMENTATION与历史HANDOFF的“尚待审计/执行”描述属于写入时状态，保留字节；本REVIEW与实际机器回执证明后续终态。

独立session87961首次terminal0，944.2311256136745 s，在原1200 s审计预算内，无重试或DSP重跑。脚本SHA256=`577f21fc0881f1c3683697ad9bfcbc5d270c48c955b5492ef6b4226ec363aac0`；receipt `/tmp/audio-device-d45-independent-audit-v1.json` SHA256=`d6d6d45f1e4abf0a03ed28155b6b6ac7c2a4bbd1fa0b8cb95242a4158b8114e7`，intent SHA256=`b9549f77cdd31c6b5a4f5e2a05cdfa717319a721abc1dbbea019722222d7852a`。主与独立代理均实际回读终态，result/binding锁匹配。

## 独立覆盖与声学结论

独立标准库加系统libm，不import项目helper、不执行DSP。全505944帧schema/count/range、7568固定快照/1944976 bin、60544汇总、34590严格零及564 inactive旧count检查通过。最大汇总绝对误差5.115907697472721e-13、相对误差2.7722744706560435e-15；原double容差保持，float操作数及gain逐步binary32要求未放宽。

460项原输出byteexact（368 monitor原输出与92 candidate bypass）、252972 mode power投影、972488 mode bin投影、28 repeat和28 future prefix、11718起止文件锁均通过。全部960组新波形及D39差值独立重算，含5760阶段统计、2592已知near统计；505944帧AGC/VAD与80951040个输出样本binary32 exact，RMS dB误差最大0。

独立确认primary/selected near中位分别-3.269613425930995/-3.269613425900271 dB、20/24窗改善；no-near最大均+6.5516918597166125 dB；pure-echo whole最大分别+1.255012175073496/+2.113633226851505 dB。near达标但后两项超过原+1 dB上限，整体拒绝。停止本映射参数搜索，不改门槛、超时、数据角色或选窗。

固定快照含真实updated_noise、合成gain-before/after，独立复算原NS/RES合成及保护max；全FFT、非快照逐bin算术、完整EMA/noise历史重建仍false。near为实际消费的离线合成样本，field没有独立near真值，repeat不新增独立样本，future4不评分。不能推导真人识别率、目标板/HIL/PQ或shipping资格。

[DIAGNOSIS](DEVICE_POST_NS_PROTECTION_D45_DIAGNOSIS.zh-CN.md)仅分解已固定最坏窗的candidate-vs-monitor NS差异能量：该例差异集中前10帧、后40帧0，与结束后的短暂保护抬升相容；这不是新增评分或已证明唯一根因。纯回声whole仍失败，下一实验必须同时守住全部原准入。

## 整批审查、冻结和本地收口合同

required_evidence包括五源码/冻结计划/实施、唯一主intent/receipt、result/binding、根保护intent/receipt、独立audit/selftest/intent、RESULT/REVIEW/DIAGNOSIS/README、fresh docs consistency及diff check、独立whole review、固定task身份与最终本地运行时回执。

v1控制已准备但未执行，独立审查发现MAJOR-1：同一device-d45-result证据ID不能从RESULT摘要改绑快照。保留v1原文件，不执行它；[收口修订](DEVICE_POST_NS_PROTECTION_D45_AMENDMENT_CLOSEOUT.zh-CN.md)冻结v2独立snapshot evidence ID及负例退出码文案澄清。v2须独立静态复审PASS后依次执行。快照只写排他/tmp新文件；verify固定snapshot/review SHA及两项真实检查；closeout核当前thread/task/CP4verified、实际auditPASS、negative保留及maintenance.required=false，再按12项operation登记工件、CP5/open0、本D45 local goal complete和final gate。未知结果先actual对账，不覆盖或重放，不调用总体native goal完成。

Fresh whole-v2 session96131实际terminal0，48.267235410399735 s，receipt SHA256=`3de8c4c57de4d0d38cf089399ebb2fb0c422c25829c7b67b126331f34b423605`。9829来源锁+1884工件及binding自身共11714唯一文件全部匹配，含文档/控制/负例逐条intent/receipt共11745起止身份一致；单例DIAGNOSIS三段能量、五帧计数及第1200帧统计独立复算一致。负例责任仅为主实际执行、独立脚本及回执核验，不冒认独立重跑完整manifest。

首版whole-v1在REVIEW并发修订时真实exit1，报start drift；receipt SHA256=`529e5050a66301b430c7c71a6174d298fb03944b8c390e2df10d5e5acf71e0f4`，原脚本/intent/receipt保留。这是文档身份拒绝，不是DSP或全量数值审计失败。MAJOR-1/MINOR-2在v2复审闭合，v2closeout静态审查PASS。freeze-v3仅在已审v2基础上将两版whole-review脚本/intent/receipt及自身一并纳入快照，须独立定向复审后执行；不重跑whole-v2或改变其已验证事实。

当前CP3verified，open_items3；待最终文档及freeze-v3定向复审、CP4、冻结与本地收口。真实后续完成另见CLOSEOUT。历史D44 snapshot中的README身份不覆写。本轮新增README入口形成新快照。

Provider route unresolved、知识NEEDS_REVIEW，未归档成功。维护v2受理但完成unverified；fresh required=false允许业务，不重发。无commit/push/PR/merge/release/设备写。
