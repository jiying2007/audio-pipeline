# D43 过去功率与近端结束后恢复诊断结果

2026-10-11，experiment=FE_DEVICE_POWER_ATTRIBUTION_D43。正式测量、独立数值与全部固定窗口描述审计真实完成，decision=POWER_ATTRIBUTION_DIAGNOSTIC_NO_PROMOTION，promotion_allowed=false、shipping_approved=false。整批文档审查及本地收口单列，不代表总体优化目标完成。总体目标“全面推进优化迭代”继续 active。

## 正式执行与身份

执行前独立审查 Spec PASS / Quality PASS，unresolved=0。执行器 `/tmp/audio-device-d43-execute-v1.py` SHA256=`51487a34094b4e22f4a9bea110d5691d5559bd1e5d0975df39ae8abf60ecef75`。实际 session 54026 terminal exit 0；执行器耗时 411.1514506684616 s，矩阵耗时 362.27369005884975 s。正式目录 `/tmp/audio-fe-device-power-attribution-d43-20261011`，没有 measurement-invalid.json。

| 工件 | SHA256 |
| --- | --- |
| result.json | `3642acfaa5ccf2e9c452c013bae0ca5539e0ef70a418eb69862b7eaaa64d6d1f` |
| binding.json | `f6ed4dbcd4cbfc9e7a0aa4351ac00117afc63d8f966d443d30a54a799299a87b` |
| 正式执行回执 | `52c5321a3a79882c10d02ded6d49f4b63370eaf02182211f5b86dfa8d426a175` |
| 根保护负例回执 | `56e4991bcc0f0bb5122419302adee494db992366deb3fbbfae038ebd628f7aaa` |
| 全窗口描述回执 | `cdea9c9d12a0fe1920477a2ef79e765f7a5a147ffb6f2ad63f216e2b9a03bd55` |
| 独立数值审计回执 | `b6c3ae4c06d003e94762de8bebcda9b27977142a242c3a5deedcd682b85e7e98` |
| 独立描述审计回执 | `866eddfb3099794b54295f39d36d32c5c4bb326e0fe11cf03b83495f19233c5c` |

冻结来源 46 例、两处理臂、两模式，实际 184 次执行 / 505944 帧。6040 个 source/input/artifact 来源锁前后完全相同；binding 收录 1884 个工件，包含 binding 本身共有 1885 个文件。原五输出 bypass/ns/final/control/protection 与 D42 同名执行逐字节相同，原 summary 子集及 960 组 observation 完全继承，不重新评分或改变 D42 准入。新增 power.csv 全帧、bins.csv 固定稀疏全 257 bin 快照；模式投影、重复及未来前缀通过测量工具的真实核验，独立审计另列。

原算法 scoped_bytes=22000 B，observer_state_bytes=22616 B，measurement_scoped_bytes=44616 B；加 D30 原 71224 B 为 115840 B，符合冻结 131072 B 预算。最大单文件 2453623 B，目录合计 1444068700 B，符合单工件 4 MiB / 总量 1536 MiB 预算。这些是本次宿主测量资源，不是目标板峰值内存、CPU、热或功耗资格。

根保护负例 session 63912 terminal exit 0，实际耗时 15.751465340144932 s。D30、仓库、D43 三个既有目录请求均 exit 2，完整 manifest 前后完全相同，文件数分别 679 / 2560 / 1885。该文件数是执行当时的快照，不要求后续新增本结果文档后仓库仍为 2560 个文件。

## 全部固定窗口与解释边界

描述 session 78299 terminal exit 0，耗时 11.837928080931306 s，195 个实际消费来源锁。四 mode/arm 各 45 whole + 195 fixed，共 960 组；4 个 future 不评分，repeat 标注为非新增独立样本。原窗口、alignment.input_range、160 点 hop 和非完整帧样本重叠权重保持，字段的时间均值按样本加权，逐帧 N/R 分布明确不加权。

全部组的离线类别为 field_unknown_near 528、synthetic_pure_echo 144、synthetic_near 128、synthetic_no_near_before_near 64、synthetic_no_near_after_near 96。whole 可含近端及非近端混合，不能直接视为纯近端区间。类别只消费冻结 near.f32le 的实际非零样本；不反馈 DSP，也不等同真人标注。

下表披露 candidate 模式全部 fixed 窗口的类别汇总，两臂分别统计；仅排除明确标注的 repeat。field 每臂 96 窗中只有 48 窗具有非零有效功率分母，其余比值为 null，不能填零。各值是窗口统计的中位数，未作新准入、候选选择或独立样本显著性推断。

| 类别 | primary / selected 窗口数 | 旧 N/R 中位 | innovation/R 中位 | excess/R 中位 primary / selected | would_raise 有效 bin 比例中位 primary / selected |
| --- | --- | --- | --- | --- | --- |
| field，无近端真值 | 96 / 96，比值各 48 | .169124 / .167483 | .413153 / .414245 | .296308 / .293678 | .124344 / .119854 |
| 合成纯 echo | 32 / 32 | .766170 / .766170 | .372678 / .372678 | .015915 / .015915 | .064488 / .043606 |
| 合成近端前 | 16 / 16 | .754501 / .754501 | .284061 / .284061 | .009572 / .009572 | .012092 / .012092 |
| 合成近端 | 24 / 24 | .366679 / .366679 | .876518 / .876518 | .473541 / .515570 | .542717 / .542717 |
| 合成近端后 | 24 / 24 | 1.002672 / 1.002672 | .847338 / .847338 | .127703 / .144364 | .164816 / .165568 |

N/R、innovation/R、excess/R 来自不同历史统计和逐 bin 非线性截断，不能先在总量上扣除 N 再宣称 excess 为零；N 不是背景真值，innovation 不是近端真值，excess 不是物理声源分解。上述类别汇总由主代理从完整描述回执只读汇总，独立审查代理随后真实复核全部类别计数、表内中位和最坏原窗口。

独立描述审计 session 65805 terminal exit 0，实际耗时 16.278342488221824 s，intent SHA256=`59a425e5018861c2b26142579e59ef0fa1752a0f9db6333e96cc0cb99f4e0958`。独立脚本不导入描述工具或项目 helper，以反向 math.fsum 逐字段复算：960 组、14464 个 binary64 浮点字段 exact、2832 个 null 字段 exact；493848 个非 future power 帧、15360000 个离线 near 样本及 200 个起止来源锁核验通过。4 个 future 不评分，16 个 repeat 组标注非新增独立样本。此覆盖只复算已有算法功率估计与固定窗描述，不增加物理声源真值或真人证据。

## 最坏既有窗口的直接观测

D42 最坏窗口为 return-A-r20-unguarded-shadow / 原坐标 [200000,224000)，即 12.5–14 s，合成近端已于 12 s 结束。candidate primary/selected 的新诊断相同：150 帧、24000 个输入样本、6168000 个有效 bin 样本权重；旧 N/R=.9109134238967707、innovation/R=.8153196408638436、excess/R=.08894228586383535。

noise_dominant 有效比例 .6293385214007782，positive_floor .37066147859922177，would_raise / raised .3348378728923476；全 257 bin 的 floor_mean 样本均值 .14984892158380114。逐帧 N/R 的 minimum / median / maximum 为 .7339370137050305 / .8251321182290203 / 1.298648558758311。旧噪声扣除已限制约 62.9% 的有效 bin，但仍有约 33.5% 的有效 bin 抬升 target。这直接描述残留保护行为，不能据相关性证明唯一根因或批准某个修正。

## 准入保持与后续闭环

D42 的 NOISE_CONDITIONED_PROTECTION_DEVELOPMENT_REJECTED 原样附带：near 配对中位 -2.18247 dB 未达 -3 dB；no-near fixed 最大 +3.70940 dB，primary 22/72、selected 24/72 超过 1 dB。原纯 echo whole 上限通过不能豁免上述失败。

独立数值审计 session 22555 terminal exit 0，实际耗时 213.39218179136515 s，receipt 与 intent `a071f5377865ad003f4093b7e83b443f970b8d294043cf5e54d9e69da9f41a0e` 绑定已读回。独立脚本不导入项目工具、不执行 DSP。全 505944 帧 schema/count/range、7568 个固定快照 / 1944976 行 bin 的旧状态与当前保存操作数公式、60544 项汇总检查及 33742 项严格零检查通过；包含 564 个 inactive 首帧保留旧非零 count 的真实记录。

920 项原五输出 byteexact、960 组 D42 observation identity、252972 项 mode power 投影及 972488 项 mode bin 投影、28 项重复文件和 28 项未来前缀检查通过，7925 个来源起止锁相同。最大汇总绝对误差 5.115907697472721e-13，最大相对误差 2.7722744706560435e-15，满足冻结 binary64 汇总规则；per-bin binary32 floor/target/gain 要求 bit exact，未用此汇总容差放宽。

本轮只新增测量，未改 NS/AGC/VAD/guard 算法、门槛、窗口、shipping default、API 或产品链路。全部帧 FFT、非快照帧 bin 算术、完整 EMA 和旧噪声历史不独立重建；960 组旧波形测量仅继承 D42 exact identity，不冒称新鲜重算。whole review 及本地收口另见审查记录；后续算法假设须新身份、新冻结计划和独立审查，不能让 D43 诊断自批准。

执行前 fresh 远端 main=`70aeb4aa1458e20917ac551d1fe5f7468df721e2`，#657 OPEN；PR 717/714/708/695 OPEN，部分 CI 仍 in_progress，required summary 当时尚未出现。最新实读工件 11701076067 / 11701023285 / 11701021412 未过期，分别绑定该 main / PR714 / 该 main。远端变化未混入本地冻结实验，CI 不作本次测量或产品证据。

Provider 查询 route unresolved / zero-hit，知识状态 NEEDS_REVIEW，未声明已归档。AISpeech 固定点 256 点/QIVW 产品链路与本 160 点 float 研究分开验收；真人效果、目标板、HIL/E001、第三方权利和 shipping 资格保持独立待证。无 commit/push/PR/merge/release/设备写。
