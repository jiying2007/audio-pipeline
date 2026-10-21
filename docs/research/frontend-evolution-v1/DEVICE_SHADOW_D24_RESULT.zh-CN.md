# D24 保留旧状态的旁路重置原型结果

日期2026-10-11；experiment=FE_DEVICE_SHADOW_D24；data_role=synthetic-engineering；总体目标active。
结论：固定纯回声工程构造中，四个稳定路径误通知场景继续选择primary，已知切换两坐标在frame1002选择shadow并改善恢复。
这是新的研究选择器原型，research_algorithm_changed=true；shipping_algorithm_changed=false；promotion_allowed=false；shipping_approved=false。
decision=PROTECTED_SHADOW_PROTOTYPE_NO_PROMOTION；不把该工程结果称产品候选资格。
[冻结合同](DEVICE_SHADOW_D24_PLAN.zh-CN.md)、[执行前修正](DEVICE_SHADOW_D24_AMENDMENT.zh-CN.md)、[独立审查](DEVICE_SHADOW_D24_REVIEW.zh-CN.md)。

## 真实原型和等价证明

17次真实20秒/2000帧执行全部exit0，严格C11/-ffp-contract=off编译、C selector self-test通过；execution_retry_used=0。
初版实施审查发现MINOR-1：完整非法参数可能在拒绝前截断新增文件，已在首次编译/回放前修复。
实际shape/offset/mode/组合四拒绝均exit2，五预置sentinel逐byte未改，真实primary/shadow处理调用0；数量标签澄清单独保留。
原D22构造/原MDF参数和函数体不变；shadow在1000帧处理前复制配置/状态并full reset自身，primary持续不reset。
所有12主臂的primary输入/echo/residual/完整state CSV全量逐byte等D22；六keep的原四trace/CSV同D22。
六shadow激活后echo/residual对D23同臂reset后半逐byte同，原状态持续和真实第二状态分别验收。
selector在两状态处理后、本帧输出前使用顺序double残差平方和；严格另一能量<0.8当前能量且连续3帧确认，规则未调。
全8trace有限/长度正确，known mic/reference构造同冻结源；primary/selected代数关系及active shadow关系≤1e-6。
inactive时仅shadow_echo/residual两个trace为0，active0明确表示未执行，不能作为消回声结果；primary两个trace始终实际有效。
三negative selected echo零/residual等mic、shadow echo零、primary权重零且无切换；repeat全10文件同、future前半同。
SYNC bridge实际调用0；源/库/头/宏/原输入与新原型身份起止同；不运行完整双麦CALL或设备链路。

## 固定窗口工程响应

单位dB，仅已知无近端/噪声纯回声使用冻结工程ERLE，非canonical独立声学评分。
下面是六shadow主臂selected输出；keep逐byte复现D22，全部统计/峰值保存在本轮result。

| path / ref shadow | whole | 0–2s | 8–10s | 10–10.5s | 10.5–12s | 12–14s | 18–20s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A / 16 | 14.793904 | 5.394948 | 40.968947 | 47.304491 | 51.586132 | 59.211126 | 86.533813 |
| A / 20 | 14.646084 | 5.229140 | 41.182499 | 47.606499 | 51.868579 | 59.548359 | 86.994263 |
| B / 16 | 14.277898 | 4.806574 | 41.139136 | 47.395073 | 51.742792 | 59.367035 | 86.735816 |
| B / 20 | 14.215081 | 4.724713 | 41.406797 | 47.716063 | 52.128704 | 59.771704 | 87.196647 |
| switch / 16 | 11.415663 | 5.394948 | 40.968947 | 1.569305 | 6.166652 | 13.756363 | 40.971763 |
| switch / 20 | 11.303505 | 5.229140 | 41.182499 | 1.448903 | 6.123778 | 13.778344 | 41.213640 |

shadow-minus-keep工程ERLE差如下；同输入residual RMS差为反号，完整精度见result：

| path / ref | whole | 0–2s | 8–10s | 10–10.5s | 10.5–12s | 12–14s | 18–20s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A / 16 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| A / 20 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| B / 16 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| B / 20 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| switch / 16 | +2.481796 | 0 | 0 | +4.162289 | +4.464389 | +4.519994 | +4.647182 |
| switch / 20 | +2.462726 | 0 | 0 | +4.132827 | +4.492612 | +4.535236 | +4.580512 |

四个稳定shadow场景switch_count0且selected始终primary，避免本构造D23直接reset的约45dB损失；不称所有误通知安全。
两switch场景各只在frame1002翻转一次，后续bank1，首次三帧确认的前两帧仍用primary，首窗收益小于D23立即reset。
本轮实际DSP未出现反向切回；反向规则只有C已知答案与Python定向测试覆盖，真实恢复/反复通知仍待。
三negative whole/全部窗ERLE恰0；repeat同switch/ref20/shadow；future仍翻转1002，whole11.368964、末窗41.316519。
0.8/3没有优化，低残差能量在人声场景不能直接表示回声改善或人声保护。直接切银行无crossfade，边界不连续/听感尚未资格化。

## 实际状态资源和身份

实际宿主构建sizeof(ap_aec_state_t)=33020 bytes，新增一份shadow状态；本wrapper无论keep/shadow都保留该静态存储。
此外还有观测buffer/stdio等开销，33020不是总内存或全进程峰值，更不是目标板RAM预算。
每例primary_calls2000；shadow激活例shadow_calls1000/reset_calls1，事件后1000帧每帧两次AEC调用；keep影子调用0。
调用次数不能推成CPU比例、实时周期或热功耗；目标板性能未测。
工件根`/tmp/audio-fe-device-shadow-d24-20261011`：result SHA256
`894417dda2d7240726c464a7197b517fd11e715eadc4ab021c8efcd892c8bcce`；binding SHA256
`870405d2a9145672066f222bcb4ec895f632e9b3b346e288ea42b0737c4191a9`，绑定216执行/自测/拒绝门禁工件。
库SHA256 `eb5b0c784c316e71d6ed9f58db6cb66f190b631daa00c55a94032168d5a47aa4`；D23全源/106工件及旧依赖/119输入锁继承。
非仓cwd help/dry-run、4项定向测试通过；独立actual与whole-change证据见REVIEW。

独立实际审计通过：3779次hash核验、136条trace共43520000个float、10880000个独立构造输入样本、
primary与selector各34000行、119组统计及42组差值。17例primary共85文件与D22逐byte一致；
11例激活shadow的后半共22文件与D23逐byte一致；每帧double顺序能量、严格0.8与三帧确认及selected字节均相符。
选中/primary最大代数误差7.450580596923828e-9，shadow为3.725290298461914e-9；
统计/差值最大误差1.4210854715202004e-14，能量复算误差0。
六项真实工具拒绝均exit2；D23/D24完整130/220文件清单前后逐hash不变，仓根潜在回执路径保持不存在。
独立审计首次因系统Python不支持dict union停止，修正兼容写法后仅重跑读取审计；失败摘要保留，
未改实验或重跑DSP，D24执行retry仍0。审计及拒绝脚本/回执与失败摘要均进入最终快照绑定。

```sh
rtk python3 tools/codex_assets/device_shadow.py --help
rtk python3 tools/codex_assets/device_shadow.py --root tests/audio --output /tmp/d24-new-output --dry-run
rtk python3 tests/validation/frontend_evolution/test_device_shadow.py
```

接续必须加入近端/双讲/边界切换及反向退回控制，并核真实开发回放和资源；不能按纯回声能量选择器直接改产品。
历史候选拒绝、AISpeech链路、真人/独立声学/ASR/KWS/目标资源/HIL/E001/owner资格独立未闭合。
Provider route unresolved保持NEEDS_REVIEW，本文仅仓内reviewing candidate，未正式归档。
