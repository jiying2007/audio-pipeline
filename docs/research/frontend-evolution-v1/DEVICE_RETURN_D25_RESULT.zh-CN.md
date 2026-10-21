# D25 路径退回与合成近端门控结果

日期2026-10-11；experiment=FE_DEVICE_RETURN_D25；decision=RETURN_NEAR_GATE_DIAGNOSTIC_NO_PROMOTION。
26次真实执行及冻结测量通过；research_algorithm_changed=false、shipping_algorithm_changed=false、promotion/shipping=false。
本轮扩展D24的控制输入与工程观测，直接复用其选择器；不是新检测器、人声或产品资格。
计划/实施/实际/whole-change独立证据见[REVIEW](DEVICE_RETURN_D25_REVIEW.zh-CN.md)；原合同和执行前澄清分别冻结保留。

## 实际执行与输入身份

16k/160点、20秒320000样本/2000帧，原MDF mu0.22f/taps1536/stride2及D18真实库/宏/头不变。
A全程原路径；ABA仅[10,12)秒为B，其余A；ref16/20仍只比较坐标，不批准产品坐标。
echo无近端；dt/unguarded输入逐byte相同，独立PRNG近端噪声只在[10,12)、[16,18)非零。
dt向原库和选择器提供两段已知标签，unguarded给dt0；这是oracle控制，不是实测双讲检测或真人语音。
24主臂=A/ABA×ref16/20×echo/dt/unguarded×keep/shadow，加repeat/future，共26实际执行首次全部exit0。
严格编译exit0；5项完整参数拒绝exit2、12个预置sentinel各自未变、两状态处理计数零。
4项测量/范围/边界/归属定向测试及非仓cwd help/dryrun通过；DSP执行retry0。

每例保存10trace及两CSV；全部finite、固定长度、输入独立float32构造与AEC代数/状态/选择符合冻结合同。
A/echo原8trace和primary CSV对D24逐byte同，selector去dt投影同且dt0；ABA/echo前10秒对D24 switch同投影。
所有keep/shadow配对primary输出/状态全量同；dt/unguarded四输入trace全量同。
repeat全12文件同，future前10秒同；不重新运行或修改D24/D23冻结工件。
shadow激活前两trace为零且不评分；keep的shadow统计全null，shadow策略whole/两事件前窗也为null。

## 双向事件、误通知与门控

全部A策略无事件；全部keep无事件；全部dt/shadow无事件，两dt段每帧streak0。
ABA/echo和ABA/unguarded两参考坐标的shadow都恰两次事件：第1002帧0→1、第1202帧1→0；repeat/future相同。
这是本轮真实原库状态/输出的反向退回，不再只有selector已知答案测试；只覆盖这一固定短B路径，未覆盖多次通知或长期退回。
1000/1200帧开始新路径后的前两帧保持旧选中bank，第三帧翻转；没有crossfade。
四个稳定A近端条件/坐标组合及两个echo控制没有选中旁路，不能推广为任何误通知都安全。
事件相邻样本差与两个状态同帧首样本差完整留在result，未设听感阈值、不称无点击。

## 已知目标输出误差

下表单位dBFS，为selected残差减去已知near目标后的RMS；越低表示本合成目标误差越小。
混合窗不提供工程ERLE，不把误差称为人声损伤或语音质量。原始残差RMS/peak、各bank误差/peak、true_echo RMS及纯回声窗ERLE均在result。

| shape / ref / condition，shadow | 10–10.5s | 10.5–12s | 12–12.5s | 12.5–14s | 16–18s | 18–20s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A / 16 / echo | -74.970427 | -79.282681 | -84.086437 | -88.390905 | -104.979585 | -114.273612 |
| A / 16 / dt | -73.842101 | -73.893630 | -74.862996 | -79.242805 | -92.345561 | -95.930780 |
| A / 16 / unguarded | -45.282615 | -41.741168 | -42.753425 | -47.062179 | -42.466076 | -45.884259 |
| A / 20 / echo | -75.272434 | -79.565127 | -84.398076 | -88.751253 | -105.425455 | -114.734063 |
| A / 20 / dt | -74.164843 | -74.204997 | -75.150249 | -79.559180 | -92.702978 | -96.367912 |
| A / 20 / unguarded | -45.253290 | -41.739887 | -42.732490 | -47.083404 | -42.438024 | -45.892352 |
| ABA / 16 / echo | -31.022143 | -35.570311 | -30.023378 | -34.451364 | -50.965473 | -59.926960 |
| ABA / 16 / dt | -25.430207 | -25.466414 | -74.862996 | -79.242805 | -92.345561 | -95.930780 |
| ABA / 16 / unguarded | -30.663045 | -34.555429 | -29.746420 | -34.179466 | -41.751686 | -45.696935 |
| ABA / 20 / echo | -30.901740 | -35.527437 | -29.927251 | -34.354361 | -51.048820 | -60.090679 |
| ABA / 20 / dt | -25.429077 | -25.465288 | -75.150249 | -79.559180 | -92.702978 | -96.367912 |
| ABA / 20 / unguarded | -30.611978 | -34.567265 | -29.664364 | -34.091112 | -41.751913 | -45.726455 |

shadow-minus-keep误差RMS差如下，负值为误差减少，正值为增加。所有A及ABA/dt差均零。

| ABA / ref / condition | whole | 10–10.5s | 10.5–12s | 12–12.5s | 12.5–14s及之后 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 16 / echo | -1.572623 | -4.162289 | -4.464389 | +0.178141 | 0 |
| 20 / echo | -1.565415 | -4.132827 | -4.492612 | +0.170083 | 0 |
| 16 / unguarded | -1.393189 | -3.881305 | -3.774581 | +0.165149 | 0 |
| 20 / unguarded | -1.408922 | -3.918943 | -3.867740 | +0.156889 | 0 |

反向退回的首窗误差增加约0.157～0.178dB，因最初两帧仍用shadow；后续selected回primary并恢复keep同输出。
保留该退化，不调整确认3帧或切换规则消除它。未出现额外抖动不能证明任意输入不会抖动。

dt-minus-unguarded在相同shadow策略的误差RMS差：

| shape / ref | 10–10.5s | 10.5–12s | 12–12.5s | 12.5–14s | 16–18s | 18–20s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A / 16 | -28.559486 | -32.152462 | -32.109570 | -32.180626 | -49.879485 | -50.046521 |
| A / 20 | -28.911553 | -32.465109 | -32.417759 | -32.475776 | -50.264953 | -50.475559 |
| ABA / 16 | +5.232837 | +9.089015 | -45.116576 | -45.063339 | -50.593874 | -50.233845 |
| ABA / 20 | +5.182901 | +9.101977 | -45.485885 | -45.468068 | -50.951064 | -50.641457 |

固定A下oracle dt减少了近端污染；ABA的B段中dt阻止适配/选择，误差反而高约5.2～9.1dB，回A后因保留原状态而明显更低。
这说明近端污染保护与同时变化的回声路径存在取舍，不批准永远冻结或无门控适配。
dt的原库权重/调度行为需按实际字段解释；CSV weight_l2只是平方和，不当完整权重快照或适配计数。
独立观察确认dt各例400帧weight_l2均等于前一帧，仍只支持平方和观测，不升级为完整权重冻结快照。
所有whole和8固定窗、12×9 shadow差和8×9 gate差完整保留；repeat同原臂，future事件相同但后半统计改变。

## 制品、资源与接续

每例primary_calls2000；shadow策略shadow_calls1000/reset_calls1，keep影子调用0；dt例标签400帧，SYNC实际调用0。
实际构建state_bytes33020，只支持额外状态大小；本fixture还有观测buffer等，不是CPU/峰值内存/目标板预算。
工件根`/tmp/audio-fe-device-return-d25-20261011`；result SHA256
`5ceae16bc4e9587e669aac90c9f8fa8be55a60077b98733606190e7ea2a466d6`；binding SHA256
`d5b5e273b311bb38d91d3a68b16986a12f6c548af83d721ded774b6a2e6f626e`，绑定407工件，源/119输入锁起止一致。
真实库SHA256 `eb5b0c784c316e71d6ed9f58db6cb66f190b631daa00c55a94032168d5a47aa4`。

独立实际审计首次通过，无审计重试：4412次hash、260条trace/83200000个float、
4输入共33280000样本逐byte构造、state/selector各52000行、234窗口组/552有效channel组/150null shadow组，
108项shadow差及72项gate差；D24共72文件及12000帧selector投影、primary84配对文件、gate32输入文件均核实。
AEC代数最大误差7.450580596923828e-9，统计/差值最大误差7.105427357601002e-15，逐帧能量与事件边界复算误差0。
六项真实工具拒绝均exit2，D24/D25完整242/411文件清单前后逐hash不变；仓根潜在回执路径保持不存在。
独立审计/negative脚本、回执及原helper身份显式进入最终快照，不导入新测量器、不重DSP。

```sh
rtk python3 tools/codex_assets/device_return.py --help
rtk python3 tools/codex_assets/device_return.py --root tests/audio --output /tmp/d25-new-output --dry-run
rtk python3 tests/validation/frontend_evolution/test_device_return.py
```

下一阶段需真实双讲/近端语音、实际检测标签与状态保护联动、无crossfade边界及资源验证，不能把独立噪声当真人。
AISpeech固定点/256点双麦、ASR/KWS、物理对齐、目标资源/HIL/E001及owner资格独立未闭合。
Provider route unresolved保持NEEDS_REVIEW，本文仅仓内reviewing candidate，未正式归档或SCM/设备外写。
