# 五条既有 CI 产物回读路径的运输修复

日期：2026-11-28（北京时间）。冻结科学基线：`21448956f65916577d13082e9dc58f275f8fbb70`。
本项源于 [#968](https://github.com/jiying2007/audio-pipeline/issues/968) 落地时实际出现的阻塞，不新增声学候选或产品资格。

## 已观察到的失败

| 原始 Verify run | job | 产物 ID | 观察 |
|---|---|---|---|
| 46037431045 | 140637770286，T1 | 15218596469 | upload 成功，紧接的按名称 download 报 NotFound |
| 46037431045 | 140637770430，BA0 | 15217762990 | upload 成功，紧接的按名称 download 报 NotFound |
| 46037431045 | 140637770609，B2-S2 | 15218608336 | 既有自检及源校验通过；upload 成功，随后按名称 download 报 NotFound |
| 46039294236 | 140644986083，B0 | 15219846925 | upload 成功，紧接的按名称 download 报 NotFound |
| 46039294236 | 140644985839，B2-S1 | 15219729638 | upload 成功，0.47 秒后按名称 download 报 NotFound |

证据：[原始 #969 Verify](https://github.com/jiying2007/audio-pipeline/actions/runs/46037431045)、[原始 #970 Verify](https://github.com/jiying2007/audio-pipeline/actions/runs/46039294236)。失败记录保留，新的成功不会改写它们。

现象证明同任务立即按名称读取未拿到刚上传的产物，尚不能单凭这些日志证明 GitHub 后端根因。
仓库其他路径已经使用有界 REST 可见性检查与精确上传 ID，本修复把同一机制接入上述五条遗漏路径。

## 冻结的修复和验收边界

1. 上传名称加当前 `run_attempt`，上传步骤提供真实 `artifact-id`。
2. 复用 `fe09_same_run_artifact_visibility.py`，仅扩展五个精确名称前缀的白名单。
3. 保留原 8 次共享元数据请求上限、单请求 10 秒、间隔最多 2 秒、响应大小、过期检查、重复 ID/名称拒绝和 source/repository/run/attempt 身份检查。
4. 仍使用原 SHA 固定的 download-artifact v7，明确 REST token、repository、run ID 和本次上传 ID；不使用候选镜像或历史成功替代本轮产物。
5. 后续原四成员集合、SHA256、source、负例、科学结论检查逐字保留。未找到、错身份或超预算仍失败；不跳过检查，不更改门槛或任务 timeout。
6. 新旧离线语义负例通过，独立比较确认其他 workflow step 的可执行内容及全部既有 helper 函数不变，随后执行真实 exact-head Verify。只有 required summary 成功后才能合并。

这里只修复运输路径。合成 API 响应仅用于离线负例，不作为真实 GitHub 产物、DSP、声学或设备证据。
