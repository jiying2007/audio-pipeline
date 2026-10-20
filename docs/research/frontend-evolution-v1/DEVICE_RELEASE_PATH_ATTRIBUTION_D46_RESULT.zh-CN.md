# D46 保护释放与路径失配时序归因正式结果

2026-10-12，experiment=FE_DEVICE_RELEASE_PATH_ATTRIBUTION_D46。唯一正式测量session91816已实际terminal exit0，status=MEASUREMENT_VALID_ATTRIBUTION_ONLY；首次独立全量复算脚本正在准备，尚未执行。本文只记录已完成主测量，后续独立终态及整批审查另录。总体native目标active，D46 measurement_only=true、algorithm_changed=false、dsp_executions=0、promotion_allowed=false、shipping_approved=false。

## 正式操作与身份

root=/tmp/audio-fe-device-release-path-attribution-d46-20261012。outer耗时40.21940243802965 s、工具40.06531832925975 s，均在180 s预算内。全部24个return配对、168固定分段、336 NS/final分段统计及48个stage-whole直接重算完成；96份PCM、48份power、96000输入power帧（48000配对帧），199输入/源锁起止一致。无DSP或新录音，配对、处理臂和条件不冒充独立新增样本。

| 工件或回执 | SHA256 |
| --- | --- |
| result.json | `562057335c9e6b49aad19519a799da1f466b47d51f1248bec778600af043f94d` |
| binding.json | `4feead7e4982576ee7cbb450179de87a26fb64618435064708d69946c536f22b` |
| root intent.json | `47cfea316077ddd762eb5fab174756317210e8dec87e3269bbaa2a4c31f95e10` |
| /tmp/audio-device-d46-execute-v1.json | `b00f77c61c0de6ff803af627a26d1eebe6a2a6158c835be0e8241285aa8f740d` |

root共3文件420400 B，最大332623 B，低于单文件4 MiB/root16 MiB预算；没有measurement-invalid.json。启动free>=512 MiB已实际核，资源仅为宿主预算，不是目标板性能。

## 坐标、对照与数值含义

七个原frame区间固定为[0,1000)、[1000,1200)、[1200,1210)、[1210,1600)、[1600,1800)、[1800,1810)、[1810,2000)。原160点alignment使有效output连续覆盖[160,320000)，共319840样本；最后原input末160点截断，无tail flush。10帧是离线归因切分，不能成为候选时间常数或新准入。

差异能量为同坐标candidate与monitor的sum((c-m)^2)，不是已知near误差或声学效果分数。诊断dB为10log10(candidate_energy/monitor_energy)，与D45原D39对照RMS差的表达和舍入顺序不同，不覆写原准入数字。NS/final分别读取真实文件与计算；分段能量按冻结容差拼接回whole，峰值exact，严格0与null保持。

## 纯回声的固定路径与ABA对照

下表为整段candidate-vs-monitor诊断dB；该八例NS/final值相同，不据此推广到所有产品场景。

| 来源 | primary | selected |
| --- | --- | --- |
| A-r16 echo | +0.11987607133804908 | +0.11987607133804908 |
| A-r20 echo | +0.16696140652215025 | +0.16696140652215025 |
| ABA-r16 echo | +1.2536541440011175 | +2.0803309202386675 |
| ABA-r20 echo | +1.2550121750734684 | +2.1136332268514764 |

固定A纯echo差异能量主要在初始适配；其后虽偶有少量bin抬升，波形差异能量很小。ABA仅在原frame[1000,1200)切B再回A；差异在B期间和回A后的较长后续区间持续，不能只归给near释放，因为这些echo条件near样本严格为0。

| ABA-r20纯echo时段 | primary NS差异能量 | selected NS差异能量 | 实际raised帧 primary/selected |
| --- | --- | --- | --- |
| [0,1000)初始A | 0.04211195814023199 | 0.04211195814023199 | 81/81 |
| [1000,1200)B | 0.9106467745461782 | 0.8615316631264394 | 198/91 |
| [1200,1210)回A短尾 | 0.20477182046889414 | 0.34768807064465806 | 10/9 |
| [1210,1600)回A后续 | 0.2537770303660845 | 0.47653972594966393 | 375/377 |
| [1600,1800)后续A | 0.0001429047128713497 | 0.00014290471305128172 | 191/191 |
| [1800,1810)第二短尾坐标 | 0.000026898544263073445 | 0.000026898544263073445 | 10/10 |
| [1810,2000)末段A | 0.000033060700912643516 | 0.000033060700912643516 | 176/176 |

第二短尾坐标只是固定分析区间，echo条件在1600–1800也无near，不能误称真实近端结束。power原帧和对齐波形分段分别报告；FFT/OLA等机制尚未独立因果分离。

## 对下一研究的影响与待完成工作

先前D45单个固定50帧无近端窗的差异集中前10帧是有效局部事实，不能外推为所有后续帧无差异。D46完整固定分段显示近端例的[1210,1600)也有差异，纯echo路径变化例更有广泛真实保护。下一算法假设必须同时解释保护释放和路径失配误保护；仅调短释放时间或仅修最坏50帧窗不足以证明守住全部原准入。本测量不证明唯一根因，也不批准新候选。

D45原DEVELOPMENT_REJECTED、源/裁判/失败/47快照未改。D46首次独立复算、负例及whole review、快照和Runtime本地收口仍待；未以主结果自批准。真人/真实运动/ASR/KWS、AISpeech产品链、目标板/HIL/PQ及shipping资格仍分别待真实证据。

Provider route unresolved/NEEDS_REVIEW，未归档成功。无commit/push/PR/merge/release/设备写。
