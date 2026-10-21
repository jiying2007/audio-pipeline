# D40 频域 RES 单因果对照结果

2026-10-11，experiment=FE_DEVICE_FREQUENCY_ABLATION_D40。正式主矩阵及独立全量数据复算已通过；whole review 与 local Runtime 收口分别核验。总体目标“全面推进优化迭代”继续 active。

## 结论与后续方向

在冻结的 development-and-synthetic-engineering 数据上，全帧关闭频域 RES 确实减少多数合成含 near 固定窗口的工程误差，但明显损失纯回声抑制。不能据此推荐产品全局关闭 RES。普通 NS、AGC/VAD、AEC 输入和 Activity gates 保持原配置；本实验只归因该频域支路开关在此完整持续状态链路上的影响，不证明真人音质、识别率或目标板效果。

每臂24个合成含near固定窗口，final已知near工程误差 D40-D39 中位约 -6.1926 dB；primary 18/24改善、6/24退化，selected 20/24改善、4/24退化。D40 final相对bypass的误差中位仍为 +1.9293 dB，两臂各16/24高于bypass，普通NS剩余代价仍需解释。配对差值中位不能用两组中位直接相减替代。

每臂72个合成无near固定窗口，final残余能量 D40-D39 中位 +16.7177 dB，72/72退化，范围 +3.9925 至约 +20.0000 dB。D40 final相对bypass仍有中位 -3.9921 dB抑制。这些是冻结合成窗口的能量/工程误差，不能写成现场ERLE或真人音质资格。

现场固定窗口每臂99组（含重复控制，不是99个独立现场样本），final能量 D40-D39中位 primary +4.1166 dB、selected +4.0811 dB，各51/99增加；其余受原频域未激活控制影响。D40 final相对bypass各48/99增益，中位约 -0.4279/-0.4126 dB，最大 +15.8773 dB。现场没有已知near真值，不能把能量增加直接写成语音改善或回声退化。

后续研究应先冻结可从实际输入取得的非oracle双讲保护假设及测量契约，保持纯回声代价与含near代价分别报告；不得根据near标签选帧、调双讲阈值取得绿灯或直接修改AISpeech默认配置。现有数据只支持该方向，不构成下一算法的执行证据。

## 正式执行和身份

唯一正式主过程 session81803，terminal exit0，elapsed_seconds=138.29805134236813。新根 `/tmp/audio-fe-device-frequency-ablation-d40-20261011`；92次新C执行、两臂独立持续状态、无flush、未重跑D39或AEC、未重编D18原库。

result SHA256=`333d6a42b9dfc96f527f76e99ec177ab8a8407389cc1dfad3e02a86127e7d3e6`；binding SHA256=`ea98a23e0cb66d390b0b94a36634a6e1d80937725a5e7b0619613e3f9e6a4f4f`。D39原result/binding严格锁定，来源/输入起止相等；全部2313依赖锁，未修改原D0–D39证据。

唯一DSP配置差异：enable_frequency_res 1→0，全帧统一。主程序核验普通NS speech_probability/noise_rms_dbfs恢复binary32后逐帧exact、Activity/allow exact、frequency_active=0/residual_gain=1、bypass exact、AGC有效gain/limiter逐sampleexact。每臂16个D39整例频域从未激活的现场case，其全部四输出逐byte相同。repeat全输出、future通知前1247帧及CSV前1248行相同；future不评分。

测量组严格每臂45whole+195fixed，两臂90whole+390fixed=480总组。保持原range/160点坐标/tail/null，各stage分别测量并存储同坐标D40-D39差值。源码与数据角色不因结果调整。

## 验证和资源边界

实现修复后定向测试9项通过；strict C编译、自测和非仓cwd deepdry通过。正式矩阵内非法argc/frames/mode/gates保护通过。主完成后另行实际已有root负例 session13134 terminal0：D30/仓库/D40已有根三个命令各exit2、完整文件manifest起止相同，回执 `/tmp/audio-device-d40-negative.json`。

描述摘要由 `/tmp/audio-device-d40-observations.py`实际exit0生成 `/tmp/audio-device-d40-observations.json`（SHA256=`9c5fcd92eaedea4feb7c530c4eedbfc292550b268644e9a9f852ae39790ea425`），未反馈算法、未选候选。独立描述审计真实exit0，40组summary exact、192个near标签按真实near轨迹核对，回执SHA256=`3bf9120f9ebaaf4c8e71f6936d5cfc576e619c1b25683ea4142b69feb825fe04`。

独立audit脚本 `/tmp/audio-device-d40-independent-audit.py` SHA256=`a47aa897e28f5e47c8f1a8b3084551024fdae55a31fd5d8669b9aacef076ab46`，唯一首次审计回执实际exit0/PASS，elapsed_seconds=201.74540446605533，回执SHA256=`7a2f65155692ee2a2ede70181efd7e7b893d14996900e15f84d35dc10d4d2e98`。覆盖92次执行/252972帧/276条PCM，40475520个AGC输出sample和VAD递推binary32 exact；480测量组、1440组stage统计、648组已知near统计、480组D39差值坐标全部复核，最大RMS反算误差0 dB。2993个合并来源/输入/输出路径起止锁一致；252972帧普通NS统计exact，32个整例inactive控制四输出exact，2个future不评分，repeat/future前缀通过。NS FFT未独立重算，不能用逐sample AGC/VAD审计替代该边界。

sizeof下游 scoped11696 B，加D30 scoped71224 B为82920 B，符合本实验65536/131072 B预算。原B0 50000 B保持且该合计超过B0；不是整线程、目标板RAM、性能、功耗或热资格。

固定decision=FREQUENCY_ABLATION_DIAGNOSTIC_NO_PROMOTION，promotion_allowed=false，shipping_approved=false。Provider route unresolved，知识NEEDS_REVIEW，未声明归档成功；AISpeech固定点/QIVW/真人和目标板资格分别待证。
