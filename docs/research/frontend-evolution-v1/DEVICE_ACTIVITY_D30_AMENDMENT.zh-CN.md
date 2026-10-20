# D30 主执行前实施补充

日期2026-10-11；原PLAN SHA256=372dd673052334465fabe3e435499d011197b323646bb09d479de9df238071bc，字节保留。
本补充不改46执行、原库、算法参数、窗口、数据角色、资源预算或超时；主DSP矩阵尚未启动。
预编译第0次真实exit1：在D30包含D29 runner并重命名main时，D29内部又定义/取消main宏，导致宏重定义和入口重复。
失败回执`/tmp/audio-device-d30-precheck-0.json`、原writer和原源码base64/hash快照`/tmp/audio-device-d30-precheck-source-attempt0.json`保留。
仅改变新D30包含方式，直接复用原D26底层harness与D27/D28私有头，显式保留冻结的组合时序自测；不修改旧依赖、不关闭警告、不改变处理循环。
第1次严格编译、实际Activity自测及4项Python定向测试均真实exit0；预编译retry1，主DSP重跑0，不能称整轮零失败。
新D30工具将本AMENDMENT与实际包含的旧D26/选择/过渡头起止hash显式绑定；独立实际审计须完整核Float32能量/EMA/instant-ratio/hangover。
scope_write补充本AMENDMENT；实际shadow通知只reset shadow，Activity持续；公共路径通知会reset Activity，二者不混称。
