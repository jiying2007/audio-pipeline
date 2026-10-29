# FE09 B3/F0 file-I/O source R4 registration

This release-neutral prerequisite registers the exact v2.3.60 source proposed
in [PR #864](https://github.com/jiying2007/audio-pipeline/pull/864), head
`ebd2690e02e805b6f003ce507aaca7ad5d9344b3`. It does not include that PR's shipping
changes. Its first Verify run, 40806782836 attempt 1, remains a recorded failure
at the unregistered maintenance-version gate; the full matrix had not started.

## Exact source boundary

The [immutable registration](PREREGISTRATION.json) binds the candidate by full
Git blobs, byte counts and SHA-256. The proposal head is provenance, not a
required ancestor after protected squash merges. Actual execution still needs
its own clean committed head, exact source and new R4 receipt.

The original B3 lock has 77 members: 66 current and 11 historical references.
The F0 lock has 88 members, sharing those same 66 current members and adding 22.
R4 retains the nine reviewed exceptions relative to those frozen locks. Of
those nine files, only CMakeLists.txt differs from R3: it declares v2.3.60 and
registers thirteen ALSA file-I/O regression cases. All other eight reviewed
files and all unchanged locked members remain byte-identical. The private C4
study build recipes, input fixtures and scientific code remain unchanged.

The independent Runtime maintenance qualifier binds exactly CMakeLists.txt,
docs/API_CONTRACT.md, include/audio_pipeline/audio_runtime.h and
src/platform/linux/ap_runtime.c. Its new fixed forward patch reverses to the
original 2.3.56 maintenance image. The old policy, inverse patch and 2.3.57,
2.3.58 and 2.3.59 registrations retain their complete identities. A version-only
edit of 2.3.59 to 2.3.60 still fails the full CMake blob check; 2.3.61 is rejected
as unregistered.

Both new `.patch.b64` files contain one base64 line. Their registered patch
identities refer to decoded patch bytes, not the different encoded-file blob.
The checks apply and reverse the exact patches, verify every before/after
identity and reject extra, duplicated or missing paths.

## Preserved science and negative controls

R1/R2/R3 plans, locks, source gates, collectors, scientific results and budgets
remain unchanged. R3 still rejects 2.3.60 under its own identity. The new gate
checks all 13 original R2 and 27 original R3 source negatives, then 27 R4 source
negatives. The maintenance gate retains 16 original and 12 audit negatives and
adds 12 file-I/O registration negatives.

The separately pinned R4 derivation contract compares the collectors against
the corrected, unchanged R2 parents: 39 B3 scientific functions and three
classes, plus 33 F0 scientific functions and one class, are byte-identical.
The original C timing driver identity remains distinct from collector receipts.
Forty-two source/metadata negative controls cover scientific edits, top-level
execution, definition-time changes, budgets, sanitizer settings, receipt and
timing identities, including rejection of both R2 and R3 receipts as R4 evidence.
These source checks execute no DSP process and create no measurement result.

## Execution and delivery order

First merge this independent source-only prerequisite through protected-main
gates and verify its actual new main. Only then may the v2.3.60 candidate execute
the R4 collectors. The current 2.3.59 branch continues to use its unchanged R3
collectors and receipts. The workflow admits only the exact known versions;
all other versions fail before collection.

R4 retains the complete original matrix: B3 has three targets, eleven
trajectories per target and 600 frames per trajectory; F0 has 36 processes,
21,600 frames and 144 statistics groups. Time budgets, compiler flags,
sanitizers, error expectations, input roles and failure-retention rules are
unchanged. Each actual candidate PR and main gets its own execution identity,
per-attempt artifact namespace and independent verification. Historical results
cannot be inherited. Registration does not approve the shipping fix.

The independent shipping PR must still pass its complete gates, protected merge,
fresh-main verification and governed Release. Hosted/QEMU engineering evidence
does not establish device, acoustic, HIL or public four-microphone SDK authority.
The frozen #833 attempt and the physical E001 identity are unchanged.

## 中文操作边界

本登记只处理 v2.3.60 文件 I/O 修复引起的精确源码身份变化，版本仍为 2.3.59，
不携带 #864 的产品修复。先让本登记 PR 通过受保护合并及独立主线检查，再接续
#864 的真实新提交验证；不能把首次失败改写成通过，不能借用 R3 回执。

运行 `fe09_b3_f0_r4_source_admission.py --self-test --check-current` 检查源码；
运行 `fe09_b3_f0_r4_derivation_contract.py --self-test` 检查派生代码和负向控制。
这两个命令不执行 DSP。原 R1/R2/R3 入口继续按各自冻结版本工作；2.3.60 的完整
矩阵由现有工作流选择 R4 入口，并保留每次实际执行的原始输出与失败。

源码登记、软件回归、SDK 发布和物理产品资格分别验收；#833 的冻结失败与重试
预算、E001 的原物理对象、所有历史科学阈值和负结果均保持原义。
