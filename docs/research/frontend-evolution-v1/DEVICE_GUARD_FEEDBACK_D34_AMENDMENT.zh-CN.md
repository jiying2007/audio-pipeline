# D34 实施兼容性偏差与最小修复

原PLAN SHA256=d51c6e21402f5dae92e485449e7a4540317aaeccf4dc3c217bdb0f1d5c87106c，不改变测量合同、角色、阈值或候选边界。
首fresh实施复审发现MAJOR-1：真实入口rtk python3为Python3.8.10，而原工具case映射使用3.9新增str.removeprefix。
首次5tests真实exit0未覆盖deep preflight，不能证明实际兼容。主wrapper/dry-run尚未执行，没有实际AttributeError终态回执；该失败设计不能冒认运行失败。
原tool保存/tmp/audio-device-d34-tool-before-major1.py，SHA256=96725d6fc15ee4dd976d1eeff7b752467a0826fa8ac436ba8db1c9440da49c0b。
原tests保存/tmp/audio-device-d34-tests-before-major1.py，SHA256=a7528afc92de40fa3351b2b47fc1c7799bd032a032519f9a916a739bb3cf0263。
最小修复=先验证mode前缀，再按长度切片；重复case拒绝；新增真实映射Python3.8正例/错mode/重复负例测试。
AMEND纳入起止source锁；不切换解释器、不放宽冻结预检。fresh实施PASS后才执行deep dry-run和主诊断。
无DSP执行或算法变化，总体native优化目标active。
