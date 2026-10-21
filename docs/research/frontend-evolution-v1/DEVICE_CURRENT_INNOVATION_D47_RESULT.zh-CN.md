# D47 正式测量失败：旧映射单调约束耦合

2026-10-13。experiment=FE_DEVICE_CURRENT_INNOVATION_D47，decision=MEASUREMENT_INVALID_REPLAN。正式执行已停止，完成16例，第17例C回放成功后被旧测量约束拒绝；没有184路最终结果、原开发准入或独立全量审计结论。算法收益、候选准入和产品资格均未证明，promotion_allowed=false、shipping_approved=false。

## 实际终态与身份

唯一writer `/tmp/audio-device-d47-formal-v1.py` SHA256=dd0406dc28e55b5904267cd702f88594bade4fe0cc543837080f376baa30fa61，在实际CP4 verified且绑定实施185a31a6后运行。session40057真实terminal1，chunk728139；实际child exit2、child_terminal=true，135.397295789秒，stderr为 `D41 noise-conditioned monotone floor`。未超1800秒，不是进程超时。外层回执 `/tmp/audio-device-d47-formal-v1.json` SHA256=6bf0c0040b367fafe550445f8b242165a8be99f18426f32583c0948861790bb9；intent SHA256=707ce1c8da9021674c316c54d9469d389eb0bf6f56910f2424ce22e56a579d4c。

正式root `/tmp/audio-fe-device-current-innovation-d47-20261013` 保留，不覆写、不重放。measurement-invalid.json记录completed_executions=16、MEASUREMENT_INVALID_REPLAN及上述错误；result.json和binding.json均不存在。stdout仅16条D47_CASE_PASS，不把17条成功C command回执误记为17个测量案例通过。正式run的末尾11727输入fresh guard未执行，父source end guard也未完成，不能声明这两个历史guard PASS。

## 精确触发与证据解释

第17例为monitor-primary-field-case-03-fixed1-shadow。实际C command exit0、0.710670338秒、3008帧、481280样本、scoped22000B、observer26728B、measurement_scoped48728B；随后原 `tools/codex_assets/device_noise_conditioned_protection.py` observe第213行要求六项状态投影一致且新floor_mean不超过D41 floor_mean。

主只读chunkd0df6b与独立实际CSV回读一致：六项状态在全部3008帧exact；50帧仅违反floor上界。首例frame351，D47 floor_mean=0.8823121197028847，D41=0.8516626703600011；far/dt=1/0、count_before/count_after=10/10、valid_bins/raised_bins=257/0。monitor四个原输出bypass/ns/final/control与D41逐字节一致。第17例并非C异常或monitor应用保护。

旧上界属于D42由过去功率构造的noise-conditioned映射性质。D47使用当前复数预测误差J/P，冻结公式没有保证其floor小于D41的sqrt(1-q)，不能沿用这种单调关系。PLAN要求新floor及派生值可变，同时要求原observe原字节；实施直接复用原函数，未分离其中的旧映射专有约束，暴露测量契约耦合缺陷。主实现及独立实施审查都遗漏了这一继承条件，记录为审查缺陷，不改写前述历史审查结果。

该解释不是声学准入失败或算法有效性的结论：原两臂24near/72no-near/4pure-echo准入尚未跑全，也没有独立960组评分。不能删除检查后在本root复跑；不能改变声学阈值、容差、窗口或预算获取通过。

## 失败字节封存与后续边界

只读封存控制 `/tmp/audio-device-d47-invalid-freeze-v1.py` 实际chunkda742a exit0，生成新 `/tmp/audio-device-d47-invalid-snapshot-v1.json` SHA256=361463948e6ac2fd872c6040c49d2ae0018da6f6e4a729229016de5f6aad7200，冻结214个partial工件与16个源码/文档/定向及正式控制证据。追加当前回读核对应SHA、文件/磁盘预算和匹配正式进程为空；这是失败之后的当前核验，不能替代未执行的历史末尾guard。该snapshot尚待独立逐文件回读。

独立审计草稿 `/tmp/audio-device-d47-independent-audit-v1.py` SHA256=58abbf0a466fab8d69fdbe2ace1c5d061027be9fbecd6befd8f06c0a44596126已保存；自测和正式审计均未执行、没有审计PASS，不能消费不存在的result/binding。此前完整preflight-v2实际55.845秒PASS与独立输入域核验仍有效，但不替代本轮测量终态。

下一步用新的FE身份冻结测量适配方案：分离通用统计、控制/资源/状态不变量、声学评分与旧算法专有性质；完整保留原声学准入、160点alignment、全部窗口/两臂、容差、120/1800/1800秒和资源预算。对适配器须建立正反例及独立与旧评分逐值对等验证，然后独立审查才执行新root。D47五源、原D42裁判、全部旧失败、原正式root和本RESULT保持不变。Provider NEEDS_REVIEW，无归档成功、提交/推送/发布/设备写；总体优化目标仍active。
