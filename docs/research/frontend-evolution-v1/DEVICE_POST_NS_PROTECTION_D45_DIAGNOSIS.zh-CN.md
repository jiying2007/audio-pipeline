# D45 近端结束后保护释放的定位证据

2026-10-12。本文仅对已生成D45工件作只读定位，不执行DSP、不新增评分窗口、不改原准入。独立全量审计仍待终态，候选正式decision=DEVELOPMENT_REJECTED。本定位不能批准新候选或证明唯一根因。

## 固定工件与样本坐标

根 `/tmp/audio-fe-device-post-ns-protection-d45-20261011`，result SHA256=`0d9dbf01b21510216df648d323c501166a039a5b45d44c93d2699b8eabc4e8de`，binding SHA256=`bb0fbb8b9942e2b9ca5dbecf9a53ac1f13f38d40c7bbb574d5a438506d00cff8`。

| 相对工件 | SHA256 |
| --- | --- |
| candidate-primary-return-A-r20-dt-shadow/ns.f32le | `6e5ed9ace41f359a8b71535526702fd7ddff3b735e78f6cace7a54178064fea0` |
| monitor-primary-return-A-r20-dt-shadow/ns.f32le | `e082f4a0f44dfe1503792fe257204011b646649e565da7c5f3983d47d9c5c649` |
| candidate-primary-return-A-r20-dt-shadow/power.csv | `c23c469bb64fa1158690ae583618ea2b0281109c7cba82b760b1fea9bf5e5d87` |

该例原固定无近端窗为input [192000,200000)，按原160点alignment对应output [192160,200160)。正式observation中的NS/final相对D39增幅均为+6.5516918597166125 dB。该样本坐标属于已冻结development/synthetic合同；不得馈入运行时算法或作为事后选窗替代全量准入。

## 实际逐段能量与保护计数

在同一output范围只读比较candidate与monitor的NS浮点样本，能量为double顺序累加sum(x*x)，差异能量为sum((candidate-monitor)^2)。这是定位分解，不替代原whole/window RMS评分。

| output范围 | candidate能量 | monitor能量 | 差异能量 |
| --- | --- | --- | --- |
| [192160,193760)，前10帧 | 0.00573545047648388 | 0.0007723207195552125 | 0.004065441155999965 |
| [193760,200160)，后40帧 | 0.0006375311327615594 | 0.0006375311327615594 | 0 |
| [192160,200160)，原50帧窗 | 0.006372981609245459 | 0.0014098518523167848 | 0.004065441155999965 |

本例该窗口candidate-vs-monitor差异能量100%集中在前10帧；后40帧差异为0。不能据此说所有场景均如此。

对应power.csv第1199/1200/1201帧raised_bins分别54/57/45，第1210/1250帧均0；这些帧far=1、dt=0、count_before=10。第1200帧旧residual_sum=54.442197597731649、innovation_sum=47.761117734777905、noise_sum=30.597995474934578，floor_mean=0.21221603285013935。该证据显示近端结束边界之后仍有短暂真实增益抬升，与前段差异集中相容；EMA历史、频谱叠加和其他机制的各自贡献尚未通过独立因果实验分离。

## 下一研究的边界

后续可检验保护释放是否受到旧功率统计滞后影响，但必须另建实验身份、冻结一个因果修改、保留原门槛及全部数据角色，并独立审查后才执行。D45纯回声whole也超过+1 dB，单独消除本例短暂尾部不足证明解决整个失败。不能通过只验该窗、直接读取near标签、调2.0门控系数、改timeout或弱化证据要求取得通过。

先完成D45全量独立数值/波形审计、整批review及本地收口，保存本轮失败。真人近端、真实运动、ASR/KWS、目标板/HIL/PQ与shipping资格仍分别待真实证据；知识Provider route unresolved/NEEDS_REVIEW，未声明归档成功。
