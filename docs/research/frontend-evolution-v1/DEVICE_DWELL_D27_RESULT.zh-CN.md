# D27 固定最短保持开发实验结果

日期2026-10-11；experiment=FE_DEVICE_DWELL_D27；decision=DWELL_DEVELOPMENT_CANDIDATE_ONLY。
总体目标active；research_algorithm_changed=true、shipping_algorithm_changed=false；promotion_allowed=false、shipping_approved=false。

冻结50帧保持期后，D26设备主矩阵切换从538降至243次，减少54.83271375464684%，满足预先冻结的25%要求。
首次切换不延迟，相邻切换最短52帧；D25所有12个主shadow来源的selected两输出与原文件逐字节相同。
代价同时保留：部分设备窗口残差能量增加，最大+0.8451197379992834dB。工程稳定性候选不是音质改善或产品默认。

## 实际执行与身份

遵循[冻结计划](DEVICE_DWELL_D27_PLAN.zh-CN.md)，仅增加切换后50帧保持期，解锁后重新进行三帧确认。
32个D26主shadow源和12个D25主shadow源各legacy/dwell，另重复和有限future控制，共90次真实C选择器执行，首次全部terminal exit0。
实际246924帧、39507840个mono样本位置，两输出trace共79015680个float。
新C不链接AEC库、不更新AEC状态，四条bank trace完全继承冻结D26/D25；本轮不是重跑完整AEC或产品整链。
44个legacy臂的selected echo/residual全量逐byte等原文件，selector原字段投影全量同；这不是完整MDF内部状态字节等价。
起止源/输入/依赖hash一致；471个生成工件绑定。工件根`/tmp/audio-fe-device-dwell-d27-20261011`。
result SHA256：c8b7cf96ee67facb504e502a2b5ec5a13f5c6f06eb84c6436ff5aad0d5513985。
binding SHA256：c1d340bfea936ba6c01661245097eaa3621994479100803d0d201243348d1b4f。
PLAN SHA256：bed08018d79b0f0cb54d1fc743bf8d8c7c1f1ed480ab18f3589ecd437c9e882e。

## 设备开发数据的切换与能量代价

下表只列8个有通知场景的两坐标；另8个无通知场景的16个源，legacy/dwell输出全量不变且不切换。
每个单元能量为dwell-minus-legacy的selected残差RMS差，单位dB；正值表示能量上升，零是实际测量零。
沿用原whole及4～6、10～12、19～21秒固定PTS窗口，无新事件居中评分窗；没有clean target，不称ERLE、残回改善或人声损伤。

| case/坐标 | legacy→dwell切换 | whole | 4～6s | 10～12s | 19～21s |
| --- | ---: | ---: | ---: | ---: | ---: |
| 03/fixed1 | 53→23 | +0.258255 | +0.845120 | +0.424427 | +0.013526 |
| 03/used0 | 41→20 | +0.089349 | 0 | +0.722545 | +0.109149 |
| 04/fixed1 | 38→17 | +0.124435 | 0 | +0.103721 | 0 |
| 04/used0 | 38→16 | +0.070318 | 0 | +0.101269 | -0.056447 |
| 07/fixed1 | 29→17 | +0.067578 | 0 | 0 | +0.024592 |
| 07/used0 | 27→13 | -0.015150 | 0 | 0 | -0.025931 |
| 08/fixed1 | 18→8 | +0.057386 | 0 | 0 | -0.003907 |
| 08/used0 | 21→9 | +0.082392 | 0 | 0 | +0.472962 |
| 11/fixed1 | 54→21 | +0.124023 | +0.004048 | +0.414471 | +0.000106 |
| 11/used0 | 55→25 | +0.090788 | +0.256152 | -0.072732 | 0 |
| 12/fixed1 | 41→19 | -0.014304 | 0 | -0.035974 | -0.076034 |
| 12/used0 | 45→23 | +0.037167 | 0 | -0.028460 | -0.018656 |
| 15/fixed1 | 7→3 | +0.002483 | 0 | 0 | 0 |
| 15/used0 | 5→3 | +0.002174 | 0 | 0 | 0 |
| 16/fixed1 | 38→14 | +0.008444 | 0 | 0 | -0.021724 |
| 16/used0 | 28→12 | +0.004641 | 0 | 0 | +0.089148 |

所有设备whole/窗口差范围为-0.07603389444414788～+0.8451197379992834dB。
case15通知25.57秒晚于最后固定窗，固定窗0不说明通知后输出没有变化。
首次接管与legacy逐臂相同；保留逐次事件帧/方向/相邻样本边界差/两bank首样本差。没有听感阈值或crossfade，不称无点击。
影子统计仍仅完整active窗口有效，跨inactive的whole保留null；候选没有改变这一评分资格。

## 已知路径、近端和因果控制

D25 A稳定六源、ABA两坐标dt源均无切换；ABA两坐标echo/unguarded四源均仍1002帧0→1、1202帧1→0。
全部12源的dwell两条selected输出全量等原D25，因此whole及原八窗口的残差/known-near error差共108项各为0。
原0.5dB工程近端误差上限通过；合成近端独立噪声和oracle dt仍不是实际真人保护。
原D25退A首窗误差增加及dt期间路径恢复代价仍存在，本轮没有消除或改写这些历史取舍。

case07-used0-dwell重复三文件全量相同，实际13次切换。
future仅在通知后把primary bank两trace乘1.125f、shadow两trace乘-0.875f；三文件通知前前缀相同，后半实际3次切换。
future后半不是真实AEC轨迹、没有代数或Activity新结果，measurement=null，不参与现场和候选评分。
90次总事件813次，包括全部legacy、dwell和两控制；243只指设备主矩阵dwell，不能混用计数范围。
实际选择器状态sizeof20字节、AEC调用0；既有双状态AEC存储/运算仍须另外计入集成成本，不能据此宣称产品只增加20字节。
未测DUT CPU/峰值RAM/功耗/热；500ms是输出切换保持，不新增音频lookahead或帧缓冲。

## 验证与接续

独立计划/实施Spec和Quality审查通过，6Python定向测试从/tmp实际exit0。
严格编译、自测legacy/保持边界/有限性/失活/时钟/门控exit0；4个完整非法参数sentinel均exit2、三输出文件不变且selector_calls=0。
90次真实执行exit0，执行retry=0；非仓cwd help/dry-run/6tests三份回执均terminal exit0。
独立actual审计不导入本轮或D26/D25测量器、不重C/AEC，核90例/180trace的79015680个float、246924行CSV、740772个gate byte。
88个legacy输出文件全量逐byte一致，120438行原字段投影一致；476窗口组、1133有效bank/295null、236个差值窗口及108项known-near差全部核实。
813次事件与首切/52帧最短间隔独立重算，RMS/peak/差值最大误差0；D25 dwell的24输出文件全量一致。
独立重判工程候选准入全部满足，保留candidate-only/promotion=false，不扩展为声学资格。

独立审计首版真实terminal exit1：复用D19统计比较器要求samples字段，冻结D25 rms_peak只有RMS/peak，进入return的true_echo比较时KeyError。
首版脚本和完整stderr/terminal失败回执均保存；仅修独立统计schema适配后进行一次纯工件重审并exit0，没有重C或AEC。
首版脚本/失败回执SHA256：37d1a5b1e5317e848653e52109fe646b928ddb33070a6fa0d7e179ed5204762b / b42ff8129eb108aa3bcbecf0d89960e4e8ac84db569faf73121d3ab9fcccfc48。
最终审计脚本/成功回执SHA256：aef1b786c85ad47f9de736b04a5b63483114636216f1ef0b55542566a2bd134f / 37162df128c710bb76de2cf58330e59f7236eb2efb6c6e3d86ef552decf9118e。
六项工具missing/真实input×旧D26/新D27/仓根均真实exit2；旧D26完整739文件、新D27完整475文件manifest前后逐hash相同。
仓根仅潜在measurement-invalid影响路径未写，不声称锁定全部dirty。
负例脚本/回执SHA256：a5e46ed83f60b3d310169bcbf0ece4b9a2549c971d2057583f1e93583ce3125e / d738a9fd9f24e5a81ffa111c32f9436085d6f41bdbdcd997860165a4a1da5d18。

本轮只形成固定状态轨迹上的开发工程候选。后续在保持已暴露能量代价的前提下验证输出切换边界、真实近端保护、检测闭环和完整后处理；不继续扫保持时间找有利分数。
尚无独立声学、目标板资源或AISpeech/QIVW/KWS/ASR、HIL/E001/owner资格；产品默认不改。
未commit/push/merge、未部署设备、未正式归档；Provider route unresolved，知识线NEEDS_REVIEW，仓内reviewing candidate。
