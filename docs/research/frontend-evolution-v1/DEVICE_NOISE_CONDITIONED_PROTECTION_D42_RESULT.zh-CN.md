# D42 过去噪声功率约束的频带创新保护结果

2026-10-11，experiment=FE_DEVICE_NOISE_CONDITIONED_PROTECTION_D42。唯一正式矩阵与首次独立全量波形审计已真实完成，工程测量通过；固定开发准入为 NOISE_CONDITIONED_PROTECTION_DEVELOPMENT_REJECTED。测量PASS不批准候选。whole review与本地Runtime最终收口分别核验，总体目标“全面推进优化迭代”继续active。

## 改动、结果与解释

本轮唯一算法改动是在D41过去帧复数交叉谱创新比例中，扣除原NS上一帧噪声估计N/R，再计算保护gain下限。N读取在当前bin原noise_tracker更新之前，原tracker初始化和更新不变。原AEC/Activity、ordinary NS、AGC/VAD、frequency_res enable1保持；无near标签输入、参数搜索或反馈AEC。N是原NS估计，并非已知背景噪声真值；binary32噪声估计与binary64 EMA统计不同，公式known-answer共同缩放不代表完整NS尺度不变性。

| 冻结开发准入，配对差值D42-D39 | primary | selected | 门槛与判定 |
| --- | --- | --- | --- |
| 24个含near固定窗，final已知near误差中位 | -2.182472687 dB | -2.182472687 dB | <=-3 dB，失败 |
| 含near严格改善窗口 | 20/24 | 20/24 | >=18/24，满足 |
| 72个无near固定窗，final能量增加最大值 | +3.709398750 dB | +3.709398750 dB | 每个<=1 dB，失败 |
| 四个纯echo整例，final能量增加最大值 | +0.387114926 dB | +0.540459776 dB | 每个<=1 dB，满足 |

两臂均拒绝。与D41的无near最大+16.5907 dB、纯echo whole最大+2.1732/+2.1080 dB相比，退化明显收窄，但near配对误差改善也由约5.15 dB降至约2.18 dB，未同时满足保护和抑制要求。不能以纯echo整例通过覆盖固定窗口失败，也不放宽1 dB或-3 dB门槛。

72个无near窗口仍全部增加能量，primary/selected中位分别+0.451929389/+0.578744592 dB，超过1 dB的窗口分别为22/72和24/72。最坏窗来自return-A-r20-dt-shadow及unguarded-shadow原sample范围[200000,224000)，两臂均+3.709398750 dB；静态A也存在near后恢复窗退化，不能仅归因ABA路径切换。含near final对bypass误差中位仍+7.156011029 dB，primary16/24、selected20/24高于bypass；本轮改善不能写成已消除近端损伤。该合成near固定窗NS与final误差相同，不归因AGC。

现场每臂99个固定窗口，含repeat控制，candidate final能量D42-D39中位+0.453340629 dB，51/99增加，最大+1.641403278 dB。无现场near真值，不能据此宣称真人语音改善或现场ERLE；repeat不是新增独立样本，future不评分。所有中位是逐窗配对差值的中位，不用两组中位相减替代。

该结果支持“原噪声估计可以约束一部分非相干误保护，但仍不能充分区分near与残余echo”的后续研究问题。它不证明背景噪声或路径失配是唯一根因，也不批准继续扫相近阈值。后续应先补充过去创新功率、原噪声估计和保护贡献的可辨识性证据，保持测量改动与算法准入分开；当前算法不能成为产品默认。

## 执行与冻结身份

唯一正式wrapper `/tmp/audio-device-d42-execute-v2.py` SHA256=`7c3ecfe186d3a3c5d888409fbca78f4d7d7d925c5b2bccc8471745b20f121c2e`，session62543真实terminalexit0，301.3867018017918s。输出根 `/tmp/audio-fe-device-noise-conditioned-protection-d42-20261011`，46来源×两臂×两模式=184次新C执行、505944帧。旧D39/D41及AEC不重跑，D18原库不重编。

result SHA256=`a2b839fbc635d1f1664d4c98d0406186e481b52aaef0a2a4fd4f4285902f31e2`；binding SHA256=`291d91f48162fa5fcab3f7deff25ec8c9baff77cbe7e39cd78004108f52883f0`。4520个来源/依赖锁起止一致，1510个主工件，binding自身另计。D41完整来源/工件及原final snapshot身份被继承；旧snapshot内README只代表历史身份，不覆写。

主测量核monitor92次执行的四原输出逐byte复现D39及D41；505944帧ordinary NS speech_probability/noise_rms_dbfs恢复binary32后exact，gates/allow/bypass不变。64个两模式inactive整例控制四输出相同，92个observer配对除raised_bins外exact。D42逐帧count/valid与D41exact、floor_mean<=D41，属于公式算术不变量，不能写成声学准入。五输出repeat相同、future前1247帧/CSV1248行exact，四future保持measurement/differences null。

四mode/arm各45whole+195fixed，共960组，保持原160点坐标、tail/null/no-flush及D39同坐标差值；准入只用candidate每臂24near/72no-near fixed与四个全轨迹纯echo whole，不包含field/repeat/future或含near whole。

## 已验证事项与独立复核边界

14项定向unit测试实际通过，strict C编译及known-answer自测真实exit0，非仓cwdhelp/deepdry通过，46cases/4520locks/writesFalse。真实C自测覆盖warmup/inactive清新增状态、N=0退化、N=.75/R=1正交floor=.5、N>=innovation归零、非法N拒绝及仅公式输入共同缩放；原AGC、复数交叉谱自测保持。主矩阵非法argc/frames/mode/gates和sentinel保护通过。原错误wrapper未执行，首审MAJOR1为NS哈希pin被文本替换污染，v2修复后独立复审关闭；原文件保留，算法及门槛未变。

已有根负例session64120真实terminalexit0，D30/仓库/D42三命令各exit2，完整manifest679/2545/1511起止相等；12.425954199396074s，回执 `/tmp/audio-device-d42-negative.json` SHA256=`6d5b2fc4f3ce5ef320da559f79c87bb455b986eabbef366bf3cdb0c459a3e0e1`。该历史全仓manifest产生在新增RESULT/REVIEW之前，不能称为后续当前总树身份。

描述摘要实际exit0，回执 `/tmp/audio-device-d42-observations.json` SHA256=`c4ea892bad7c50afee0a543bbb2b23f479582a24914930cd494fed450ebcc923`，四mode/arm共80组。独立描述审计实际exit0，0.9662440270185471s，80组summary exact、384个near标签按原轨迹核验；回执 `/tmp/audio-device-d42-observation-audit.json` SHA256=`ef1b517b79a9814f8a56a26a42cee66f0ea2cb52abaae3fdbe95c54d37e6820d`。描述复核不替代全量波形复算。

独立全量audit脚本 `/tmp/audio-device-d42-independent-audit.py` SHA256=`b6c9e255188d06ca5fafada572d0fd350ea645a44c37eb3d97934423b34e05b7`，唯一首次session99347真实terminalexit0/PASS，retry0，507.73973527830094s。回执SHA256=`65f1df1812e9817bb5cd5ac8303cf5b044af8487bfde6edc6388a7762e885b4c`，intent SHA256=`78893dfeaf398457e12375e20e3a9b5e628aa13437c44e4110c07d8ef956bebe`。不import测量helper、不重跑DSP；184执行/505944帧/552PCM/80951040个AGC输出sample，AGC/VAD binary32 exact。960测量组/2880stage/1296已知near统计/960组D39同坐标差值全复算，最大RMS误差0 dB、peak exact，6033个合并路径起止锁相等。

独立审计核92个monitor四原输出D39及D41 byteexact、64个inactive整例控制、505944帧ordinary NS统计和D41floor单调/count/valid不变量、92个observer配对、五输出repeat/future及四个future不评分。按真实near波形分别重判每candidatearm24/72/4集合及准入，拒绝与主结果精确相同；额外只读独立核验22/72及24/72超限窗、两臂中位及最坏来源坐标。NS FFT、全部实际bin EMA和旧noise逐bin状态未独立全量重算，回执三项覆盖字段false；known-answer、monitor等价和汇总trace不能扩大为该覆盖或声学/设备资格。

实际sizeof下游scoped22000 B，加D30原71224 B为93224 B，满足本实验65536/131072 B预算；B0 50000 B仍未满足。该数值不是完整SDK、整线程或目标板RAM资格。CPU、功耗、热、真人音质/识别率和AISpeech固定点/QIVW集成分别待证。

promotion_allowed=false、shipping_approved=false；Provider route unresolved，知识NEEDS_REVIEW，未声明归档成功。无commit/push/PR/merge/release/设备写。Runtime最终收口另行核验，只收口D42里程碑，总体native目标保持active。
