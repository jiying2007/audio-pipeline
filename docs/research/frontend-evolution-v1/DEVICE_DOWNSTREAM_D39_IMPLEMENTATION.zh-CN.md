# D39 实施与构建记录

2026-10-11，原PLAN+AMEND独立Spec/Quality PASS、independent、unresolved0后实施。新增device_downstream_d39.c、tools.codex_assets.device_downstream及test_device_downstream.py。固定两臂独立原NS/AGC/VAD状态，配对echo/residual，原current-frame gates，CALL FULL参数不变。C输入长度、有限值及gate预扫描在创建输出前完成，输出独占创建；旁路、NS、final与control分别记录。actual sizeof及预算仍待正式执行。

5项区间/尾截断/输出clamp定向单测actual exit0；非仓cwd help actual0；deep dry-run actual0，46cases/1628 locks/writes=False。新D39 localgoal task-0833374ba4bae43ebcf11896 registered/persisted，PLAN/AMEND evidence、progress1/checkpoint1/heartbeat五操作actual0，总体nativegoal仍active。

第一次定向编译actualexit1：原D18库为unity archive，内部capture函数引用已改名观察器的ap_sync_get_reference，链接器报告undefined reference；保留/tmp/audio-device-d39-build-0.json，不重跑该writer。与原D26一样补shim，仅转发ap_sync_get_reference_d18_real并计数；下游不调用SYNC，正式处理要求sync_calls=0。这是既有库的链接适配，不重新实现或重编库，不改变下游算法。新编译回执用独立v2命名，失败不改判。

正式92矩阵及独立audit尚未执行，不能声明数值/工程/声学通过。实施完成后fresh独立审查再启动矩阵；源和输入起止锁、全部原窗口、固定160点坐标及尾截断、known-near工程代价、repeat/future/negative与资源验收保持。NO_PROMOTION；产品与设备资格仍独立。

随后v2定向构建与C self-test实际各exit0，保存/tmp/audio-device-d39-build-v2-0.json与1.json；未重编原库。self-test真实验证allow0内部gain从.25向1恢复，以及输出limiter边界；未执行92矩阵，也不以这个自测替代下游全帧核验。

fresh实施独立审查发现MINOR-1：复用旧logged helper在子命令超时或启动失败时丢实际command回执。仅在新D39工具增加本地logged，发送前独占保存intent，已有操作拒绝重放；异常先独占保存null exit_code、error_type、command/cwd/elapsed/partial stdout+stderr再传播。原helper不改。增加两项异常回执定向单测，7项actualexit0；fixture仅验证异常保存，不合成runner/DSP可用性或正式结果。源改动须fresh复审后主矩阵；尚无92矩阵结果。
