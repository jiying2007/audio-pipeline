# D36 已冻结合同内的测试修复

2026-10-11，独立实施审查发现MINOR-1：原反相用例的实际最优首lag恒为0，却手造prior=[0,1,0]。该用例只能证明元数据读取，尚未证明冻结PLAN的“当前最优lag变化但past固定”。主诊断尚未执行，保持PLAN接受规则、数据角色及测量公式。

原测试字节保留于/tmp/audio-device-d36-tests-before-known-answer-fix.py。修复拆为两项：反相连续例保持prior=[0,0,0]；第二例从帧1开始设residual[j]=-reference[j-1]，解析最优首lag变为1，合法prior=[0,1,1]。帧1仍用前帧lag0且held小于current_max；帧2用前帧lag1、held=1、lag_changed=0。周期参考可能有等价较大lag，首个最优lag仍为1。未新增lag搜索，未改观测工具或准入阈值。

执行wrapper对真实TimeoutExpired/OSError保留exit_code=null、异常类型、elapsed及已获取的部分stdout/stderr，再传播失败；主命令timeout=None，其余120s。没有把mock或控制脚本测试当真实测量成功。

等待fresh实施复审后首次主运行；旧失败/问题不覆盖。D36仍仅诊断NO_PROMOTION，算法、产品default、目标板、真人和外部验收保持独立。
