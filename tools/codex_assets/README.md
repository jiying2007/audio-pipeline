# 设备采集离线研究工具

本目录保存2026-10设备采集D0–D49系列的第一方研究实现与数值/测量合同，不是产品默认DSP、外部Codex运行资产或新增公开SDK API。研究默认不赋予候选晋升或shipping资格。

可移植入口是 `device_capture`：在仓库根用 `python3 -m tools.codex_assets.device_capture --root tests/audio --dry-run` 校验原始采集；其合成fixture合同测试是 `python3 tests/validation/frontend_evolution/test_device_capture.py`，要求Python>=3.10、CMake和C编译环境。原始数据与角色见 [数据说明](../../docs/research/frontend-evolution-v1/DEVICE_CAPTURE_DATASET.zh-CN.md)。

37个模块中33个含固定`/tmp/audio-*`历史依赖。后续回放/算法/审计实验要求对应封存runner、库、波形、binding、快照和回执；它们保留原输入/源码SHA及预算，不会将缺失依赖自动替换为当前main。导入源码或语法检查通过，不等于这些历史实验已在当前main重新执行。

测试分层：

| 层级 | 例子 | 前提 |
|---|---|---|
| 可移植合同 | `test_device_capture.py` | 合成fixture及Host编译环境 |
| 本机工具集成 | `test_device_magnitude_lower_bound.py`的超时回收测试 | 本机rtk可用 |
| 封存成果回归 | `test_device_causal_residual_model_exact.py`的D37实际帧检查 | 固定D30/D35/D36的/tmp成果 |

当前CI显式执行采集合同并编译检查本目录；未添加全部设备测试的自动discover。不要将表中后两层缺项隐藏为声学PASS或通过放宽门槛处理。历史研究记录中的absolute path属于原执行来源，生成物不随本目录自动分发。当前D49执行判定为DEVELOPMENT_REJECTED，独立全量审计待完成。
