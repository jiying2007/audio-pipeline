# D48 测量契约修复独立计划审查

2026-10-13。claimant=root，verifier=device_capture_independent_review。仅审查冻结计划和已封存D47失败证据，未实现适配器、登记D48、执行DSP、旧测量或完整审计。

**计划范围：Spec PASS / Quality PASS / Reviewer Independence PASS，unresolved=0。允许在D47失败独立复核和本地Runtime终态处理完成后登记并实施新D48身份；不批准正式矩阵、算法收益或产品采用。**

## 合同身份与问题成立

PLAN SHA256=`6c751db7cd1832e5aa0db958011f23c8ff5ca3bf4fb56ad0a102bc2ab51724ca`。D47 RESULT=`d5fffe95a58f65121053f7117aa65a5ee116e7a49b42770e4b0b47d8fe4a7ccc`，失败snapshot=`361463948e6ac2fd872c6040c49d2ae0018da6f6e4a729229016de5f6aad7200`；后来独立D47 REVIEW=`c0707a4ddeeddf9e79033ef71e118b9478f1f56620e2b9f35bd8d649f63d950f`。PLAN写入时独立失败复审尚待的表述是历史时态；该独立复审已真实完成，不静默改写原PLAN。本次没有证据表明D47本地Runtime终态处理已经完成，登记前仍须实际核验。

D47第17条C回放exit0后被旧D42 observe的floor_mean<=D41 floor_mean约束拒绝，六项状态全3008帧相同，50个floor反例，首例351。该旧上界不由D47 currentJ/P映射保证。D48将其显式改为历史映射诊断，保留通用测量和控制门禁，有具体已验证缺陷依据。不是通过改准入阈值取得绿色结果，也没有完整D47算法准入结论。

## 计划可执行性与验收

唯一改变限定为新测量适配器；D47 C/NS/header、current H/J/P映射、系数、2N、postmax、EMA/noise/gates、旧D42源和开发准入裁判全部只读。新root与新task避免覆盖或重放旧失败。适配器采用显式受审副本，不monkeypatch或假返回值；旧单调boolean不得继续无条件声称true。

16个D47已测量保存案例足以在不重DSP的条件下逐值比较旧observe与新适配器公共统计/波形/控制字段；第17例可验证旧专有性质准确报告而通用检查不被绕过。静态逐语句差异与篡改六状态、边界/warmup、monitor raised、gate、普通NS、波形/limiter/坐标等负例互相补充。实施时新增历史诊断字段必须与公共评分字段明确区分，不能改common字段含义或把旧单调结论默认为当前算法事实。

完整11727来源域及原语义校验保持，冲突SHA拒绝、正式末尾fresh读盘；新源码/文档另锁。184执行/505944帧、21power/25bins、两mode公共状态、monitor四原输出及candidate bypass、repeat七输出全量、future1247前缀与4future不评分均可实际验证。固定snapshot算术覆盖与全帧FFT/EMA/noise历史覆盖明确分开，不夸大独立性。

全部960组新保存波形统计仍须独立复算，使用原160点alignment、RMS1e-10dB、float exact、double原容差且expected0严格0。两臂24near中位<=-3dB且18改善、72no-near最大<=+1dB、4pure-echo whole最大<=+1dB保持；新历史诊断不进入准入。实际原development_admission accepted/rejected仅作为测量诊断，D48即使accepted也不能自批准D47算法候选。

原120/1800/1800秒、22000B算法scoped、26728B observer、measurement和131072B联合预算、4MiB单工件/1536MiB总量及3GiB free均冻结。正式新编译/self-test用于绑定新运行身份，不能抹除或替代旧成功C证据；失败不得加时或删锁。

## 权限、数据与停止边界

development-and-synthetic-engineering及adaptive reuse身份保持，已看partial不能改称blind；repeat不独立，future不评分，near真值只用于离线解释与冻结评分，不反馈算法。只实施新tool/test/docs及排他/tmp控制，不改D0–47源、裁判、失败或产品默认；没有外部写、设备或发布授权。

D48成功decision仅MEASUREMENT_CONTRACT_VERIFIED_NO_PROMOTION，measurement_only=true、shipping_algorithm_changed=false、promotion_allowed=false、shipping_approved=false。数值/来源/测量合同失败保留为MEASUREMENT_INVALID_REPLAN，不在同root重放。登记、实施/负例、writer、正式终态、独立960审计及whole各阶段都须新鲜独立证据，本计划PASS不替代其中任一步。

CodifyDecision：仅形成“分离通用测量契约与旧映射专有性质”的reviewing候选；Provider route unresolved/NEEDS_REVIEW，无归档成功。总体native目标active，真人/rights/目标板/HIL/E001/72小时PQ等产品资格不由本计划批准。当前未登记、未实施、未执行D48，无正式或独立audit PASS声明。
