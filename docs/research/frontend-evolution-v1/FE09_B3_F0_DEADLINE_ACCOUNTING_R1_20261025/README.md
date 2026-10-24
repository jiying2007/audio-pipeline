# B3-F0 持续时间记账修复 R1

本变更新增 `FE09-B3-F0-DEADLINE-ACCOUNTING-R1`，用于修复 [#848](https://github.com/jiying2007/audio-pipeline/issues/848) 的实际主干阻断。原 B3 collector、所有原预登记和源码锁保持原字节；原 F0/F1 对它的引用继续指向原文件。

## 原始失败保持拒绝

[#846](https://github.com/jiying2007/audio-pipeline/pull/846) 合并得到 `e3c5cc0c9e9d033438a16c29344d9b54409f84ed`。其 [Verify 40142128655/a1](https://github.com/jiying2007/audio-pipeline/actions/runs/40142128655/attempts/1) 的 `frontend-reference` job `121016268890` 在 B3 最终只读校验中拒绝。原始 [artifact 12579416636](https://github.com/jiying2007/audio-pipeline/actions/runs/40142128655/artifacts/12579416636) 为 3,771,645 B，SHA256 `359d4d904701c00569372a7b5d4a04e0a13267ba9485fb1b2c94071789cd41cc`。

原 receipt 的 `elapsed_seconds` 为 `28.813288861000046`，保存的允许时长却为 `300.00000000000006`。它来自 `(started + 300.0) - started` 的浮点回减，恰好比 300 多一个 binary64 ULP。原严格 `effective <= 300` 因此拒绝。全部 33 个 case 的 19,800 行已保存；**完整 invocation 的 qualification 仍为 false，完整准入 cohort 为 0**。后续 F0 步骤未运行。此次修复不会改写、补判或拼接原失败。

## 单一因果改动

新文件 `fe09_b3_f0_deadline_r1_qualification.py` 是原 67,040 B collector 的独立派生副本，采用明确的新 receipt 身份。原文件 SHA256 `f782660590731e73f43c2fab638e84d277c11d36119560dfb8878b28e2456f6c` 被新入口显式核验，并与新入口、回归文件、预登记一起绑定实际 Git 提交。

在起点采集 monotonic origin 与 epoch 后，保存一次允许的持续时间：本地为 `300.0`；CI 为 `min(300.0, original_job_deadline_epoch - started_epoch - 60)`。剩余预算使用保存的时长减去自原起点经过的时间，receipt 直接保存该时长，不再先相加形成绝对值、再相减重建时长。独立读回还要求该保存值与原 job 推导式完全一致。

严格 `0 < elapsed <= effective <= 300` 保留，未加入 epsilon。原 300 秒总预算、三 target 的 120/180/300 秒、command、原 job 900 秒和归档预留 60 秒、32 MiB 原件上限全部保留。编译、输入、11×3 轨迹、帧/流比较、覆盖、48 个实际 API 拒绝、8 个语义元数据负控和失败停止规则均由原代码保留。

新入口没有改写或 monkeypatch 原模块。现有 Quality job 只切换这一处 B3 入口与显式标识，继续使用原 image、job deadline、权限、失败传播和失败上传；不会并行运行旧、新两个 cohort。原 F0 入口保持原样。

## 执行前登记及验证范围

[PREREGISTRATION.json](PREREGISTRATION.json) 已在任何修复源码和新运行之前保存为 [262eb95226a60391232782725ff1139f4595eb14](https://github.com/jiying2007/audio-pipeline/commit/262eb95226a60391232782725ff1139f4595eb14)，SHA256 `8e4f73e2726a4d30b64c48050cdffcc3ac9475d35ea3563bf888d3543091fc0e`。其中固定了全部允许差异、16 个元数据回归、10 秒单批预算和实际执行闭环。首次元数据控制和新 DSP 执行之前，静态算术复核发现初稿 C01 示例得到恰好300，故 revision2 将该示例改为独立诊断中的212.2；它确实得到300.00000000000006，并非伪称原 runner 起点。原登记版本继续保留，控制数、语义、预算和科学输入均不改变。当前 revision2 SHA256 `9a4f3193a2275199e40850a47325d94d96b0dc4570cae79590c8a5ef0d3d654a`。

元数据回归使用明确标注的合成时钟和 job 对象，仅验证时间表示与拒绝逻辑。它们不证明真实 runner、实际进程终止或 DSP 执行。旧浮点反例、较短 job 窗口、超时、原 job 身份和 `nextafter(300,+∞)` 仍然拒绝等均属于固定库存。

源码独立审查和元数据控制通过后，新的 exact-head PR 与 protected squash 后的 main 分别执行完整既有 gates。e3 已被本缺陷阻断，因此仅此阻断修复作为已登记的顺序例外推进；其他合并必须继续等待修复后 main 自身 Verify、required summary 和 matching Release/convergence 完成。新源码、PR 检查或原 19,800 帧均不能提前证明该闭环完成。

本修复不发布新 SDK、不修改 E001，不产生声学、硬件、SSC305 或产品资格 promotion。
