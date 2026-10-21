# D35 实施前来源锚与异常回执修正

原PLAN SHA256=cb8bf6c715e44c2e58cb098dec41e6c997fb7a33f1d688e652e76da6dbd7ab3b，观测公式、窗口、lag、tie、统计/数值要求和数据角色不改。
root只读预检查发现D34 binding未包含全部D31逐帧CSV，额外zero-lag一致锚的locked要求会拒绝。新增D31原result/binding精确hash及全部source/input/artifact锁，不引入新数据或候选。
最初工具保存/tmp/audio-device-d35-tool-before-anchor-fix.py，SHA256=fc068b70e5cbc3d8633c3c588b4197cbfc6a527c2ec4b16295a63ab14e328008。
独立实施审查MINOR-1：logged在TimeoutExpired/启动OSError时没有命令级回执；独立mock两异常证明receipt不存在，这不是实际DSP/命令超时证据。
加入D31锁后的原工具保存/tmp/audio-device-d35-tool-before-logger-fix.py，SHA256=782b31a6c58c217150c07de8bb61b75a98abab6f89ead9508c10439908132438。
原5tests保存/tmp/audio-device-d35-tests-before-logger-fix.py，SHA256=4980c43e1b62ff59ef8c131688ac53039f5859ffc210e1f3d39783a3607c3881。
异常路径先保存command、exit_code=null、error_type、elapsed及部分stdout/stderr（bytes显式替换解码），再传播；null不冒充exit0，已有回执拒绝覆盖。
新增两项mock异常/部分输出/不覆盖测试，fixture不替代真实测量。AMEND进入起止source锁，fresh实施PASS后才执行主wrapper。
主deep dry-run/整批测量尚未执行，无实际测量失败回执；原设计缺口与修复均保留，不称整轮零问题。
独立C、AEC库和保护算法未改，无DSP重跑；总体native优化目标active。
