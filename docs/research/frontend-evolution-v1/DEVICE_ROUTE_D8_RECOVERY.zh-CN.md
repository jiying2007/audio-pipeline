# D8失配恢复契约澄清

日期：2026-10-10；状态：FROZEN_RECOVERY_TEST_ADDENDUM。
原D8计划及候选source不改，不放宽评分/确认条件。
独立审查指出mic/render累计失配恢复1:1后差值仍保留，因此长窗永久拒绝，直到建立新epoch。
现有canonical docs/API_CONTRACT.md要求capture/render gap、XRUN、clock reset/reopen用
ap_pipeline_notify_stream_discontinuity；实际src/core/ap_pipeline_query.c通知路径调用ap_sync_reset。

裁决：D8遵循严格对应输入+显式discontinuity/reset契约，未通知失配时保持fail-closed，
不声称自动重新对齐或跨缺帧自恢复。此为产品整合前必须满足的前提，不能由PCM猜gap或AO时轴。
补充固定public-API工程测试：正常640samples路径→只push一帧render产生失配→恢复1:1但换1280路径，
未通知时不得接受新大跳→显式CAPTURE_GAP通知→40ms历史重新积累→既定1280路径恢复。
恢复完成要求原80ms目标范围与delay_jumps增加，不改原测试/超时（固定60帧恢复预算）。
数据为合成工程信号，结果不替代DUT/XRUN或物理声学资格。
