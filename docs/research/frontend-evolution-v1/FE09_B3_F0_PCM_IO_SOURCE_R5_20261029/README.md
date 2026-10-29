# FE09 B3/F0 offline-PCM source R5 registration

This release-neutral prerequisite registers candidate
[a65fe10c9ea02ded884a63a9129cb2a19b9c74a4](https://github.com/jiying2007/audio-pipeline/commit/a65fe10c9ea02ded884a63a9129cb2a19b9c74a4)
for [#866](https://github.com/jiying2007/audio-pipeline/issues/866).
It does not include or execute the proposed shipping processor changes.
The current software remains v2.3.60 until the independent fix is qualified.

## Fixed identities and unchanged measurements

[PREREGISTRATION.json](PREREGISTRATION.json) binds the proposed v2.3.61 CMake
blob, all nine existing reviewed source exceptions, their original preimages,
and a fully reversible exact patch. Only CMakeLists.txt differs from R4: the
version and 21 offline-processor CTest registrations. All eight other reviewed
members, all unchanged B3/F0 source members, private build recipes, datasets,
scientific functions/classes, compiler flags, thresholds and budgets are unchanged.

The original B3 lock keeps 77 members (66 live and 11 historical). F0 keeps
88 members (the same 66 live plus 22 original additional files). Old R1–R4
plans, gates, collectors, source patches, receipts and failures stay byte-identical.
R4 still rejects v2.3.61 under its own authority. The new gate delegates older
versions to their unchanged entry points and requires a distinct R5 receipt
for the new source; neither a version-only edit nor an unregistered v2.3.62 passes.

The source gate preserves the 13 R2, 27 R3 and 27 R4 negatives and adds 27
R5 source negatives. Runtime maintenance retains its 16 original and two
12-case registration controls and adds 12 exact-v2.3.61 controls. The independent
AST derivation contract pins all collector bytes and checks the unchanged
39 B3 functions / three classes and 33 F0 functions / one class. Its 45 negative
source/identity/timing controls reject old R2/R3/R4 receipts as R5 evidence.
These source and metadata checks run no compiler or DSP process.

## Execution order

First qualify and protected-merge this source-only prerequisite, then verify
its distinct actual main through the unchanged full gates and release identity
guard. Only afterwards may the candidate PR run R5's complete native/sanitized/Arm
B3 and F0 matrices. Each PR and fresh main receives separate original artifacts,
including failed attempts; no historical measurement is inherited.

The proposed I/O fix is separately reviewed and tested by its own 21
deterministic cases plus nine predecessor false-success controls. It changes
an offline tool, not DSP algorithms, acoustic parameters, the public API/ABI,
or #58 physical authority. A source-registration PASS does not approve that fix.

## 中文操作边界

本 PR 只预登记 #866 的确切 v2.3.61 构建身份，主线软件仍为 v2.3.60；
不把候选修复混入预登记，不提前执行新的 B3/F0 科学采集。
先完成本 PR 的受保护合并、独立 main Verify 与既有 Release 身份核验，
再对修复 PR 执行全量检查、新 R5 原件回读及正式软件 Release。

新增的文件 I/O 测试只证明软件错误报告；真实 PCR02 采集、SSC305 HIL、
Extended Real、E001、至少 72 h Product Certification 及不可变归档仍归 #58。
双麦/四麦研究结果、原有失败和冻结预算均保持，不据此新增产品权限。
