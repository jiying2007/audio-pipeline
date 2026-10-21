# D21 执行前依赖路径修正

首次预检exit2，尚未创建输出根、编译或执行DSP：编排把D20分析器的BASE常量（实际为D19基线）误作为D20工件根。
哈希检查拒绝`D20 dependency drift`，实际失败回执保留`/tmp/audio-device-d21-preflight-failure.json`。
修正版明确使用合同中D20真实根`/tmp/audio-fe-device-timing-d20-r1-20261011`，依赖SHA不改变。
机器结果同时补全三path的offset20-offset16 whole/四窗口residual RMS与工程ERLE差；配对mic必须逐byte相同。
没有改变DSP、输入、参数、窗口、阈值或11次执行集合。retry_used=1；首次失败保留，不解释为通过。
