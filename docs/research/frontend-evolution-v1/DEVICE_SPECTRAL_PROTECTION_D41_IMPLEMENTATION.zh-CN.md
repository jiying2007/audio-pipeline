# D41 实施与预验证记录

2026-10-11，FE_DEVICE_SPECTRAL_PROTECTION_D41；当前实现及独立fresh实施审查Spec PASS / Quality PASS、independent、unresolved0，正式184次主矩阵未执行。总体目标active。primary=adk-planning-execution-loop。

PLAN+AMENDMENT独立Spec/Quality PASS、independent、unresolved0，初审QUESTION1准入whole歧义由AMENDMENT闭合；原PLAN保持。原D18 ap_ns.c SHA256=92e35db7f13269d52ae9b01b5b5b830813940e1397b40ca6fdf659fa9dc78e3b，研究派生新符号ap_ns_process_d41，原库不重编、不改原符号或产品默认。新增header提供finite-first过去EMA floor及复数update；target=max(original,floor)仅candidate，原NS noise tracker/增益平滑/OLA保持。

count连续有效帧上限10不是严格十帧滑动窗口。保护先读取旧EMA，再更新当前FFT统计；inactive清新增state，保留原RES gain历史释放。monitor/candidate的EMA仅取相同输入FFT，不读取抑制后输出；expected保护trace除raised_bins全字段exact。floor及update直接拒绝非finite，不能用coherence clamp掩盖NaN/Inf。

## 当前身份

- runner C：472a098aedae22bd295b40452242f9230a4168a188ce6293e363ab9179e73a5f。
- header：761460359cb0ec16938a4b4ac84a95c62b60f0b798e2ccf84718977f2ef08c49。
- 研究NS：c62750f9ae2e0afef564d67e29203747f2e1fb96565d1e5f1d417eff1b3784aa。
- tool：a512b6cfa70e80e128cd89efbeb50218cbf976a1fc14bde7abb110c18947a7b1。
- tests：2ff926c0e9c4963f89ebecb22f1a591c0840faa34038de7d9e51af557fe5f4aa。

一次性执行wrapper `/tmp/audio-device-d41-execute.py`独占新root/intent/receipt，核上述及三份计划文件exact、固定task-2071a5c74c869f5d54f6fd7b、当前maintenance.required=false才进入正式主矩阵；观察同handle，不重启。子timeout120及主1800保持，拒绝/失败真实保存。矩阵是两模式×两arm×46来源=184执行/505944帧，960测量组；开发准入固定24near/72no-near fixed与4枚举pureecho whole每arm独立，不用whole含near或repeat/future改变分母。

## 实际预验证

首次strictcompile和旧版C selftest实际exit0；新增真实NS warmup/zero-residual/inactive清状态测试后使用新命名v2独占编译回执，旧回执保留。`/tmp/audio-device-d41-build-v2.py`实际exit0，command-d41-preflight-v2-build及self-test各exit0；原FLAGS/ffp-contractoff/D18defs/includes/lib，未重编D18。C自测包含coherent/orthogonal、count9/10、zeroenergy、非finite拒绝、coherenceclamp、复数交叉积已知答案、11次实际NS warmup及inactive清污染状态。自测不是完整NS/perbin或声学资格。

Python定向14项实际exit0（0.012s）：继承9项坐标/float边界/预算/异常真实null与拒重放，加5项冻结准入边界与集合保护；不把继承9项计成额外新测试。非仓cwd help实际0；deepdry session20594 terminal0、46cases/3001locks/writesFalse。随后仅修正tool错误消息前缀，当前tool身份如上；当前身份fresh深preflight session67745 terminal0，同46cases/3001locks/writesFalse。独立reviewer从/tmp另行真实复跑14项测试exit0，核v2 compile/selftest回执与intent匹配、完整NS fork diff、原平滑/noise_tracker/OLA保留，新增因果/count/finite以及开发准入与预算合同无未解决发现。

主根 `/tmp/audio-fe-device-spectral-protection-d41-20261011`未创建，正式intent/receipt均未生成，不将编译自测或dryrun写成184 DSP执行。独立实施fresh PASS、维护解除后才唯一启动。formal failure保留根与MEASUREMENT_INVALID，不能改门槛或重跑同根。

## Runtime 与恢复边界

新request SHA256=eeaf6ff163e458320e3e36e5a2fe0f9725d21de4377df0464b436ef62dea7d7f，routing2071a5c74c869f5d54f6fd7b5a427138373cfd76b7611e3e4b8054efd922bf69，attestationabe42fb9fbeb031e1cefafb9d792d4b1135ac7292993cbe73db8d9fd99f9e151。ensure dry/apply均实际exit0，REGISTERED/localtaskactive/open3；16000000/86400仅localRuntime控制，总体native无上限。

fresh08:37:32.956047Z context_ratio=.554365、maintenance.required=true。先固化检查点及交接，再维护恢复核即时门禁，不借原D40maintenancefalse越过当前压力。旧D40 nativecompact仅ACCEPTED_COMPLETION_UNVERIFIED，request_ms1791706365602；只读新history对账，原三回执不改、不重发。

NS FFT与实际全部bin EMA未独立重算边界保留。NO_PROMOTION；Provider unresolved/知识NEEDS_REVIEW，产品、AISpeech真人/QIVW、目标板、rights/owner分别待证。原dirty/D0–D40保持，无commit/push/PR/merge/release/设备写。
