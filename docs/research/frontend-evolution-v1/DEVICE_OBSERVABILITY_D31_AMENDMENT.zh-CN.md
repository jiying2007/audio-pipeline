# D31 生存期修复及执行顺序偏差

日期2026-10-11；原PLAN保持字节不变，SHA256=60e0cb66f15e1e9ad3c559ff68acae1e295e10b356e3d780bc25179c2fe13cd3。
第一次观测在实施审查返回前已开始，违反原合同顺序。主进程实际terminal exit0，不掩盖为未执行；不作为D31合同合格结果。
verifier发现MINOR-1：下一case六array字典完整构造前，上例六array仍生存，瞬时可有12条trace，违反单case六trace合同。
attempt0源码SHA256=e3b1345cf7255943239403f0a75b83a552f0f4107e4bb249264db6ed7d384873，base64原字节保留于/tmp/audio-device-d31-attempt0-source.json。
attempt0根/tmp/audio-fe-device-observability-d31-20261011、全部结果及/tmp/audio-device-d31-execution-0..3.json不覆盖。
最小修复仅在每case完成CSV、窗口及计数后释放traces/rows；不改公式、区间、阈值、原D30依赖或分数。
增加实际run三case弱引用生命周期测试，观测同时活跃trace array峰值必须6、返回后全部释放；这是局部生命周期，不是总RSS/目标资源证明。
新执行根=/tmp/audio-fe-device-observability-d31-attempt1-20261011；新dry根独立；新工具preflight额外锁本AMEND字节。
先等修复实施独立审查PASS，再启动attempt1；原attempt0与新attempt1的46CSV及result应逐byte相同，binding因源码不同允许不同并分别保留。
retry_used=1/2；DSP重跑=0（两次均仅观测原trace）；本轮不得声称零失败或原执行顺序合规。
其余合同不变；未晋升、总体native goal仍active。
