# D47 独立失败封存与定位审查

2026-10-13。claimant=root，verifier=device_capture_independent_review。本审查只读失败工件、源码和回执；未重跑正式矩阵、旧实验、deepdry或完整数值审计。仅本新增REVIEW由独立verifier写入，原失败snapshot不包含本后续文档。

**失败封存与分析范围：Spec PASS / Quality PASS / Reviewer Independence PASS，封存及事实复核新增unresolved=0。实验状态仍为MEASUREMENT_INVALID_REPLAN；测量契约耦合缺陷尚未在D47修复，不代表实验PASS或里程碑完成。** 无完整184例/505944帧测量、960组独立评分、开发准入、声学收益或shipping批准。

## 冻结证据与实际回读

- RESULT：`d5fffe95a58f65121053f7117aa65a5ee116e7a49b42770e4b0b47d8fe4a7ccc`。
- 失败snapshot `/tmp/audio-device-d47-invalid-snapshot-v1.json`：`361463948e6ac2fd872c6040c49d2ae0018da6f6e4a729229016de5f6aad7200`。
- 封存writer `/tmp/audio-device-d47-invalid-freeze-v1.py`：`add4beef6958b07ee51f5d28ab7e0cd78e7453276425413c26dd3e37863094f8`。
- 正式writer `/tmp/audio-device-d47-formal-v1.py`：`dd0406dc28e55b5904267cd702f88594bade4fe0cc543837080f376baa30fa61`。
- 正式外层回执：`6bf0c0040b367fafe550445f8b242165a8be99f18426f32583c0948861790bb9`；intent：`707ce1c8da9021674c316c54d9469d389eb0bf6f56910f2424ce22e56a579d4c`。

独立只读实际chunk1a5039/exit0逐项核验snapshot的214个partial工件和16个锁定文件：所有路径为真实普通文件且非symlink，SHA全部匹配，正式root文件集合与214工件集合精确一致；起止重新hash相同。result.json、binding.json均不存在。该核验发生于失败之后，不能替代正式run未执行的11727输入末尾guard或父source end guard，也不宣称本次重新核验了全部11727输入。

独立实际chunk142c39/exit0核23条command与intent：command/cwd/intent SHA链全部一致。六个setup退出码为compile0、self-test0、invalid-argc2、invalid-preserve-frames2、invalid-preserve-mode2、invalid-preserve-gates4；17条实际case C command均exit0。外层回执child exit2、child_terminal=true、elapsed135.3972957888618秒；stdout仅16条D47_CASE_PASS，measurement-invalid.json的completed_executions=16对应一致。主session40057终态exit1记录与此失败外层回执一致，未冒称整批PASS。

本次按精确正式tool路径与--run参数只读检查/proc，匹配进程为空；没有向socket或Runtime发送任何写操作，没有重启或终止旧运行。

本次回执链检查初次辅助命令使用当前Python3.8不支持的str.removeprefix，实际chunk51257e/exit1保留；随后仅改为字符串切片，chunk142c39/exit0。此为只读审查命令兼容性错误，未写工件或执行DSP，不删除首失败输出，也不将其当算法失败。

## 精确失败条件与审查遗漏

第17例为`monitor-primary-field-case-03-fixed1-shadow`，其C command实际exit0、0.7106703380122781秒，3008帧/481280样本，scoped22000B、observer26728B、measurement_scoped48728B。之后调用旧`device_noise_conditioned_protection.py`的observe，213行要求六项状态投影一致并要求新floor_mean不超过D41 floor_mean。

独立CSV回读确认全部3008帧的frame/far/dt/count_before/count_after/valid_bins投影相同；50帧仅违反该floor上界。首反例frame351：D47 floor_mean=0.8823121197028847，D41=0.8516626703600011；far/dt=1/0、count_before/count_after=10/10、valid_bins/raised_bins=257/0。第17例monitor的bypass/ns/final/control四输出与D41逐byte相同。此例并非C数值失败，也不是monitor实际应用候选保护。

旧floor上界是D42过去功率noise-conditioned映射的专有性质。D47冻结映射使用当前复数创新J/P，并无floor<=sqrt(1-q)的数学保证。直接继承旧observe将这个映射专有约束误作通用测量条件，导致测量契约耦合缺陷。主实现与本verifier此前实施审查均遗漏该继承条件；此审查遗漏明确保留，历史实施PASS是当时记录，不具有推翻真实失败或追认当前实验PASS的效力。

本轮应停止并保留失败，不在D47 root重放，不静默删除旧检查、不放宽原准入或改阈值。后继须新FE身份冻结测量适配合同，区分通用统计/控制/状态不变量与旧映射专有性质；保留原24near/72no-near/4pure-echo两臂准入、全部窗口及160点alignment、数值容差、120/1800/1800秒及资源/磁盘预算。没有完整准入结果，不能将本次测量无效归因为算法收益失败或成功。

## 审计与责任边界

独立审计草稿`/tmp/audio-device-d47-independent-audit-v1.py`当前SHA为`58abbf0a466fab8d69fdbe2ace1c5d061027be9fbecd6befd8f06c0a44596126`。草稿未通过最终控制复审，自测及正式audit均未执行；无独立全量审计PASS，不能消费不存在的result/binding。固定快照算术设计亦不能冒称全帧FFT、完整EMA或noise历史重建。

实际preflight-v2成功与当前失败封存是不同证据层。本审查不批准候选、不覆盖D45/D46旧结果，也不批准Runtime完成D47或native总体goal。Provider route unresolved/NEEDS_REVIEW保持，无归档成功；第三方rights、真人/KWS/ASR、目标板/HIL/E001和至少72小时Product Qualification均仍独立，无commit/push/发布或设备写。

CodifyDecision：保留“算法专有性质不得以继承helper隐式成为通用测量约束”的reviewing候选；尚无Provider成功记录，不声明正式归档或产品采纳。适用性仅为本次D47失败捕获、身份链及原因定位；新D48计划、实施和正式测量须另行授权及独立审查。
