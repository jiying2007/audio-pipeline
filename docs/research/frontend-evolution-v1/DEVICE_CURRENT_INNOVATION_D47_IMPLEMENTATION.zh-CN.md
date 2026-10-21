# D47 当前帧复数创新实施冻结

2026-10-13。experiment=FE_DEVICE_CURRENT_INNOVATION_D47。PLAN、PLAN_REVIEW、AMENDMENT 和 AMENDMENT_PREFLIGHT 保持原字节。本文件冻结实施及定向证据，正式184路矩阵与独立全量审计尚未执行；没有候选准入或产品批准结论。

## 冻结源码与结构

| 文件 | SHA256 |
| --- | --- |
| device_current_innovation_d47.c | ca1ba081b344e6554473328510fbaf15c56d9b2657dee06b9ce9b5d7f328b733 |
| device_current_innovation_ns_d47.c | 8dd2db9027d972aac3f6ea7f75a8bbd84c9e8c2eef6b0ab09b24aa9f7234916a |
| device_current_innovation_d47.h | 28c0520df7a9c3932fff32e0c9a8f4a0bb6eba08bdbcecd404f05103ae031d59 |
| tools/codex_assets/device_current_innovation.py | 71b5e2eb0cd0626179b1b459bb02977913f43b11dcd4ba293fff9908af72cd44 |
| test_device_current_innovation.py | cb76c720e43fc8503e3c961ee91b5d29ea8e296ef789847f5aecab11198b788b |

只有floor映射改变：由更新前的 E/Cr/Ci 得到复数 H，预测当前 echo 对 residual 的贡献，取当前误差复数模平方 J 与当前 residual 模平方 P。有效旧状态和有限数检查成立时，P>1e-12 且严格 J>2N 才应用 sqrt(clamp(J/P,0,1))。P=0 时floor保持0；原始J允许超过P，诊断不压缩。候选在原NS组合gain之后取max；monitor不应用。映射先于原EMA更新，原计数、far/dt、reset、noise tracker、RES、FFT、OLA和下游保持。没有新增算法状态。

power.csv的旧18列与bins.csv的旧25列含义保留；另追加current_residual_sum、current_innovation_sum、prediction_overshoot_bins。旧均值功率与当前帧功率分别核验，不能用旧float加epsilon的power替代P。原observe/development_admission、数据角色、评分和预算未变。

## 实际定向验证与保留失败

targeted-v1父回执 `/tmp/audio-device-d47-targeted-v1.json` SHA256=b618727409a7d2cd5f0bd4c9f7d31bee9a65ab1c95ca48ee7789a36063117472，session37900实际terminal1。六个子项中严格C编译exit0、C self-test exit0、非法argc exit2、非法gate exit4、非仓库help exit0；旧完整deepdry实际TimeoutExpired 120.103275秒。父末尾guard未执行，不能声明其PASS。随后单独回读五源/lib/flags和10个非法gate输入/哨兵字节一致，正式root不存在；旧失败保留，不重复已成功C检查。

新13项Python单测主侧chunk1aa34c实际exit0/.023秒；独立侧chunk8245a1实际exit0/.027秒。新增测试验证同SHA去重、多语义callback保留、冲突SHA、缺失与漂移、未声明语义输入、JSON缓存不能跳过语义校验、非法gate/PCM长度/非finite，以及start缓存不能替代end读盘。最初新增测试错误期待缺文件抛OSError，实际bounded契约抛ValueError，已修正；一次主命令模块名误含斜线导致ImportError，随后按正确模块名实际通过。两次失败保留，不归因于算法。

## preflight-v2 输入域与性能

旧v1工具完整字节保存在 `/tmp/audio-device-d47-preflight-v1-source.py`，SHA256=b19748a1fec0b8f3adb72171b6a4320fcb6a39ad697dce24d20e56e541508cd3，不作为漂移fallback或执行入口。v2先核固定D45源/result/binding，合并完整9829 locked和1884 artifacts，冲突SHA拒绝，固定身份确认后解析JSON。每个唯一路径仅在start阶段读取并hash一次；PCM不缓存。同路径多个语义引用全部执行，原case/role、PCM finite/长度、gate及非future near检查保留；正式run结束仍逐路径fresh读盘hash。

独立只读manifest对照chunks94e173/a564e9确认原D45 domain为11714唯一输入，无SHA冲突；D30/D39/D40/D41/D42/D43/D44全部原manifest条目覆盖且SHA对应，遗漏/不一致为0。46例242个语义输入路径均在domain。五项新源与八项新文档/阶段证据加入后，新总锁数11727。

排他新控制 `/tmp/audio-device-d47-preflight-v2-dry-v1.py` SHA256=26055a9df9dfc22a35cbf015651a95105a5621b6361ce5bb9e9f86bf86bf882f 经独立静态审查PASS/unresolved0，异常回执字段MINOR已修正。主仅执行一次：session95951、chunk75f528真实terminal0，55.845427785秒，保持原120秒上限。非仓库cwd=/tmp，仅--dry-run，46 cases/11727 locks，writes、DSP、promotion、shipping均false，source起止一致、正式root缺失。回执SHA256=5af518e223eca24b6b0530a9742f7f6f2c9cbac7e387706619f3803633253d8a；intent SHA256=e14b6259646a23b011ae59df8d8cffb93e0d607efe805c3bbf094cb391c29ca2。独立实际回读PASS/unresolved0，没有重跑dry。主追加/proc回读chunkc328b4匹配进程为空。

该结果证明完整预检在原预算内完成；没有分段计时证明递归重复读取是唯一耗时来源，也没有D47声学准入结论。

## 接续门禁

必须独立审查本文件与新排他正式writer，冻结source/document/controller pins并登记实施检查点后，才执行唯一正式184路/505944帧矩阵。单命令120秒、正式矩阵1800秒、独立全量审计1800秒、旧评分、资源/磁盘和数据角色保持。独立审计须复算复数预测/J/P、binary32 floor及组合gain、完整旧评分；固定snapshot覆盖不能冒称全帧FFT/EMA/noise历史重建。没有审计/整批终态证据前不登记result/review完成或批准候选。

当前D47 task-bfc3481a4f502887da1f244e仍active，CP3是草稿接力检查点。新维护请求1791860433123只证明受理，120.402秒回执ACCEPTED_COMPLETION_UNVERIFIED；实际进程已结束，禁止重发。fresh policy维护required=false允许业务继续，不能推导该请求已完成。Provider route unresolved保持NEEDS_REVIEW，没有归档成功声明；无commit/push/发布/设备写。
