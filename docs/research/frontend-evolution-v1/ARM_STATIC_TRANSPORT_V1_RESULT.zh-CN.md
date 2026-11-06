# ARM 静态证据无损传输修复：结果 V1

原失败 candidate `ce5d3f460c3fdb371c8ce9182b4443b2c262fb79` 的两份 size 日志已用 base64 无损运输；原 manifest 原字节归档，其余 22 个原成员逐字节不变。原 report SHA-256 为 `825e51db18c0e43d70e17595d3bdf32505b0e5da21ad0069be154ac7a84fbf79`，原 ARM 总任务预算失败仍保留。

实际重建全部 24 成员并与原提交逐字节核对：PASS。重算外层 manifest 后篡改 encoded 日志或原 report 的两个负例均被拒绝。受保护 base 原 checker 对原 candidate 仍 FAIL，对运输提交 `642a7bfc19ffa7bb10f3a53a2729d371d0197a89` 为 STRICT_PASS、exceptions=0。DSP、CMake、workflow、checker/policy 未改。

验证结束 UTC：2026-11-06T08:11:31.123273+00:00；按 root 提供的约 08:06:15 起点计算为 316.123273 秒，预算 300 秒；验证时预算判定 False。独立工作树建立以来为 189.82396054267883 秒，两种起点均明示，不以局部编码时间代替总时长。最终提交耗时由后续原始检查补充。

[完整实际核验](evidence/arm-static-transport-v1/verification.json)；[无损传输与解码入口](../../../validation/research/evidence/dualmic-arm-static-9a9202e/TRANSPORT.md)。失败 Verify 42185156796、job 127783643002 的完整原日志文本与 base/head/实际 merge checkout 身份在 transport receipt 中保留，未将原失败改报通过。未编译、安装、运行 DSP 或重跑测量。
