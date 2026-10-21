# D40 实施与执行前验证

2026-10-11，FE_DEVICE_FREQUENCY_ABLATION_D40。计划独立Spec PASS/Quality PASS/independent/unresolved0后实施；正式矩阵尚未执行，以下不代表对照结果有效或效果改善。

新增C由冻结D39 C派生，完整diff仅3处：自测标签D40、ap_ns_process的enable_frequency_res参数1改0、运行检查改frequency_active==0且residual_gain==1。其他DSP顺序、门控、缓冲、状态、原库link shim、异常输入预扫描与独占输出完全保持。当前SHA256=7405c11cfce7f3e03c9882974c87a5cfb6195bdd44d537fc38dbb818f114816b。

新增tool `tools/codex_assets/device_frequency_ablation.py` SHA256=4b75e91e670f63eac5a35057eb9b1e047898ba0bc57fb425f8297d483408609a。实际完整核D30来源/输入/输出、D18原source/headers/flags/library、D39 result/binding及全部既有专属来源/输入/制品锁，不强锁后续可追加README或Runtime收口文件。非仓cwd deepdry actual exit0：46cases/2313locks/writes=False。

每臂D39对照按同名记录，原bypass byte exact、actual gate/allow exact、普通NS speech_probability/noise_rms_dbfs逐帧恢复float32 exact；frequency_active0与residual_gain1。原field整例未激活频域RES才要求4输出byte exact。逐原whole/window坐标与对照逐项一致，保存各stage对D39的工程RMS/known-near差值；future只因果前缀不评分。未import或重跑D39 DSP。

保留新输出/tmp根独占、每命令先intent/异常真实回执、原strict flags、非法argc/frames/mode/gates与sentinel保护、repeat/future、sizeof及有限性、原数值预算。工具对照只诊断单因果配置变化，不从near标签选择算法帧，不设效果晋升门槛。

新增tests SHA256=02a10182639887f2a06102c91fd51b06eeee48e35ce509d544e729fe6d2470a1，actual7tests exit0，覆盖固定坐标/尾/null/异常范围/f32 clamp与timeout/startfailure回执及重复拒绝。mock只用于异常回执单元行为，不模拟runner/声学数据/资格。非仓cwd help actual0。

`/tmp/audio-device-d40-build.py`实际首次编译和C自测均exit0，回执 `/tmp/command-d40-preflight-build.json`、`/tmp/command-d40-preflight-self-test.json`；编译严格C11/O2/Wall/Wextra/Werror/Wconversion/Wshadow/pedantic/ffp-contract=off、原D18defs/generated headers与原archive，未重编库。自测为受控AGC状态恢复/limiter，不能替代NS开关主对照。

本地Runtime ensure dry-run实际PLANNED、apply实际REGISTERED/persistedtrue，fixedtask=task-ff15de3257f8f1cdc58ba6cf，requestSHA=a5a704daa9baf35a9c8254ffbfeef0764699fb733b5f9f3756c2e33c776b214e。计划及计划review证据、progress1/checkpoint1/heartbeat5项actual0。native总体goal active无预算上限；localcontrol16M/86400s不改变总体目标。

首次独立实施审查发现MINOR-1：case开始时间检查没有覆盖最后case结束，可能超1800s仍写PASS；正式矩阵未执行。最小修复新增matrix_budget，case/arm开始、每臂observe之后和写result之前均检查同一matrix_started，预算及timeout不变。新增1800s边界允许与刚超限拒绝两测试，实际9tests exit0。修复后tool SHA256=f2c41e0c3374830a518467574325043ea477e4eb9359cb5e77b0c1e1829a3917、tests SHA256=8fe9b6970ee1a5cffae7917ae7f6586ac4eb1cfa955d486153752da845a0ca4f，C保持；execute wrapper固定SHA同步更新。前文初始身份和7tests保留为首次审查证据，不作为当前放行身份。

待MINOR-1独立fresh复审通过、freshcanonical允许且源身份无漂移后，唯一正式根 `/tmp/audio-fe-device-frequency-ablation-d40-20261011` 主矩阵。任何失败按原计划保留，禁止宽阈值或重发未知操作。Provider route unresolved、知识NEEDS_REVIEW；未声明归档、shipping、真人或目标板完成，未commit/push/PR/merge/release/设备写。
