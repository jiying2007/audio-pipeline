# D31 近端与路径失配观测结果

日期2026-10-11；experiment=FE_DEVICE_OBSERVABILITY_D31。
decision=NEAR_PATH_OBSERVABILITY_DIAGNOSTIC_NO_PROMOTION；promotion_allowed=false；shipping_approved=false。
本轮增加可复算的观测，不改变Activity/AEC/选择器/过渡或产品默认，不新增声学评分。

## 实际执行与偏差保留

原PLAN SHA256=60e0cb66f15e1e9ad3c559ff68acae1e295e10b356e3d780bc25179c2fe13cd3。
AMEND SHA256=207d5e3077493681d0c926b179858c7b22bda2b8fc6f124056035c369d95b30f。
attempt0在实施审查返回前启动，真实terminal exit0；审查发现下一case加载期间上例数组仍存活，瞬时12条trace违反单case六trace合同，因此不接受其合同合格声明。
原源码SHA256=e3b1345cf7255943239403f0a75b83a552f0f4107e4bb249264db6ed7d384873；可还原base64快照/tmp/audio-device-d31-attempt0-source.json SHA256=751c6565264b7bff05a4fe977485690c53155014ea23254faa5d2bed91944195；原根与四回执完整保留。
修复每case末释放traces/rows并绑定AMEND，新增三case实际run的weakref测试；五项定向测试通过，局部同时活跃array峰值6，返回后释放。
修复实施独立审查Spec/Quality PASS、MINOR-1闭合、unresolved0之后才启动attempt1。
attempt1 tool SHA256=93fb57afb716801dec4a14a25d2ebe82ec5499b9138da00327eb804e98e3ffb7；tests SHA256=ecb9478aba4e36a257a11882980d1191cbe027e5302633b410f8c1b358b054da。
本轮retry1，不称零失败；两次仅观测原trace，DSP执行0，不重编库。

## 工件、数量与验证口径

接受根=/tmp/audio-fe-device-observability-d31-attempt1-20261011。
实际46case、126486帧、六条原输入trace；六对平方归一化内积加两个功率比，共1011888个特征单元。
result SHA256=d1465d24fb2b26d378dd2e6590c661f2a67d5e23ca1255ab7f6bd5970961aee2。
binding SHA256=04990be63adfb174d37f6483fa6e1d3e0679276ee6581577eba59baf30cdc506。
主观测生成48工件=46CSV/result/binding；后续检查/审查/Runtime回执另计。attempt0与attempt1的46CSV及result共47文件逐byte相同，修复未改变公式或输出数值。
非仓help/dry-run/五tests/主观测四步骤均实际exit0，dry-run无输出根；重复CSV全量同，future通知1247帧前header+1247行逐byte同。
normal44+repeat的原whole/windows共240区间，向内取完整160点帧，明确原区间、实际区间及丢弃边界样本；future无窗口评分。
特征由本帧六trace计算，不读near/true_echo/oracle/控制CSV；near_present只复制原窗口，用于事后解释。
原D30 source/input/655绑定工件起止hash相同，原分数不重算；D30根679实际文件和新根48文件在三项输出拒绝负例中全量manifest保持不变。
三项拒绝原D30根/仓根/已有新根，均实际exit2；negative回执SHA256=474190fd00d4a619659f70ce0f8186a29e1f8b47a4cdd5be89cdf873cc7b1a61。
独立stdlib审计首执行真实exit0、retry0；不import项目tool/helper、不执行C/DSP。
独立核46case/276trace/121426560个Float32样本、126486帧/1011888特征单元；逐帧误差最大2.220446049250313e-16。
独立核240原区间/1920组特征统计及3416次hash起止检查，repeat/future/47文件等价、派生12表48中位数/8计数与negative完整manifest均通过。
audit脚本SHA256=d8ea0d5a7eeb5550f315831ae3c81844ee02b48e4fb970eb6404f4126e0e9ab3；回执SHA256=dc0f0c54181b262d23eb2d6f2ea2a97b6ff14a749370590a40c1bb2a201f43f2。
whole-change复审及最终文档检查以本轮REVIEW为准，不仅凭主工具退出0批准测量。

## 实测信息与混淆

下表全部来自原窗口的固定nearest-rank中位数。C为零时延、非去均值平方归一化内积，不是频域相干性、概率或检测准确率。Ê为primary估计回声；R、Ê为selected残差及估计回声。

| 原工程场景/窗口 | 原near_present | C(mic,Ê) | C(R,Ê) | R/mic功率比 |
| --- | --- | ---: | ---: | ---: |
| A-r20 dt，10–10.5s | true | 0.563443 | 0.002522 | 0.434212 |
| ABA-r20 echo，10–10.5s | false | 0.015716 | 0.400660 | 0.621806 |
| ABA-r20 echo，12–12.5s | false | 0.457283 | 0.007763 | 0.540543 |
| ABA-r20 echo，16–18s | false | 0.997721 | 0.388875 | 0.003908 |
| ABA-r20 dt，16–18s | true | 0.545967 | 0.003135 | 0.454046 |
| ABA-r20 dt，18–20s | false | 0.987036 | 0.003328 | 0.012922 |

静态A已收敛后，near出现伴随mic/估计回声关系下降、残差占比增加；这是本批合成数据的观测，不是通用检测规则。
纯路径失配也会降低mic/估计回声关系并增加残差占比；ABA纯echo退回12–12.5s同时出现低C(R,Ê)与高残差比。因此不能直接把某一项异常当双讲标签。
ABA dt近端结束后18–20s的C(R,Ê)中位数仍约0.003328，与16–18s的0.003135接近，但残差功率比显著下降；单一低内积值不足以证明near存在。
原reference与残差的零时延C在上表相关窗口约0.0022–0.0034，near有无均低；该零时延观测未补偿真实回声滤波/延迟，不能据此否定频域或经过路径估计的相关方法。
没有拟合分类器、扫描阈值、计算新检测准确率或判定多特征能否可靠分离；本轮只冻结下一假设需要面对的混淆。
派生披露/tmp/audio-device-d31-disclosure.json SHA256=467393002e60dfaea0fec2290b1f57304c5d41a9d49317519a731bad4f77efd2，原12窗口和全帧null数量可回读。

## 零能量与资格边界

三项涉及reference的C各66403有效/60083 null；三项涉及估计回声的C各66629有效/59857 null；两项功率比各126486有效/0 null。
null表示某一分母信号能量为零，不能填0或包装为“低相关且检测到近端”；全null统计的min/max/分位数仍null。
Python double累加是离线观测，不是Float32部署实现或SSC305性能证据；六array生命周期测试不代表总RSS/栈/热功耗资格。
D30双状态局部71224B及两AEC自身超过B0预算的负结果保持；D28局部输出代价不被新观测豁免。
后续单独冻结因果近端检测假设，需要路径/适配可信度、通知/恢复期与多特征共同对照，并验证检测反馈与AEC保护的时序；不可从本批窗口直接批准阈值或收益。
完整NS/RES/AGC/VAD/KWS链、真人near与目标资源继续独立推进；AISpeech产品链不是本工具的DSP执行对象。
Provider route unresolved/current为空，知识线NEEDS_REVIEW；仓内reviewing candidate，无正式归档。
无commit/push/PR/merge/发布/设备写，用户dirty和原D0-D30保留；总体native目标active。
