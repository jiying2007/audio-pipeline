# D47 定向失败保留与 preflight v2 优化合同

2026-10-13。原PLAN20906d11、AMENDMENT0645bf01及PLAN_REVIEWff344052保持。D47尚未执行正式184矩阵。旧算法五源码实施已独立PASS；MAJOR-1为自测变量遮蔽，在任何C执行前仅重命名新增double j，静态闭合。主与独立Python8tests均通过。

唯一targeted-v1 session37900实际terminal exit1，parent receipt SHA=`b618727409a7d2cd5f0bd4c9f7d31bee9a65ab1c95ca48ee7789a36063117472`。严格C编译、自测、非法argc、非法gates、help的实际退出码为0/0/2/4/0，符合其各自预期；第六条deepdry于120.10327538661659秒TimeoutExpired，exit_code=null、stdout/stderr为空，未冒称exit0。父状态FAIL并保留全部intent/receipt，不覆盖或重放。严格编译约.672秒、自测约.082秒；成功的C检查无需重复。

主只读/proc按精确目标script argv与--dry-run过滤，chunk844950返回空集合，原session37900有实际terminal；没有证据表明该旧dry子进程仍live。正式root `/tmp/audio-fe-device-current-innovation-d47-20261013`未创建。后续操作须再次核同operation实际状态，不能仅以观察超时重启。

原工具完整字节已排他保存到 `/tmp/audio-device-d47-preflight-v1-source.py`，与当时仓内工具同SHA=`b19748a1fec0b8f3adb72171b6a4320fcb6a39ad697dce24d20e56e541508cd3`。该备份用于失败来源追溯，禁止运行或作为漂移fallback。新工具将产生新的source identity；原targeted-v1的源码锁与失败只代表其执行时点，不称旧工具SHA永远等于新版本。

经源码读取，旧preflight逐级调用D45→D44→D43→D42，各层又遍历父locked_files/artifacts，新D47还全读D45工件；同一冻结路径会重复读取与hash。耗时根因尚须由新优化的实际时间验证，不把静态重复读取直接冒称唯一系统瓶颈。

拟实施唯一测量准备优化：从精确固定的D45 result/binding构造完整domain输入期望SHA并集，冲突SHA失败，每个唯一文件在本次preflight只读/hash一次。完整保留原D45的9829输入锁、其全部1884artifacts、父源/库/flags、原D30/D39/D41等身份，以及本D47五源/计划/修订/审查和D46来源身份；不删锁、不忽略旧失败。继续实际检查46例角色/集合/长度/gate/finite及固定父结果角色；旧D42 observe/development_admission不改字节。归一化/评分/near标签/候选floor/资源/磁盘/数据角色全部保持。

新preflight source-v2须定向单测并集冲突、相同路径不重复读取、缺失/漂移与非法case/gates/finite等行为，fresh独立审核覆盖与旧domain集合对应，再使用新排他preflight-v2 intent/receipt namespace唯一执行120秒deepdry。保持原超时，不增加120秒或重跑已成功compile/selftest/help。超时或失败保留并replan，不换限追绿。只有实际dry成功及独立回读成立，才能冻结实施、准备正式控制。

本文为执行前修订候选；preflight-v2尚未实施/执行，独立设计审查和实际验证尚待。原D47本地任务active/open3/CP1verified、总体native active；Provider NEEDS_REVIEW，无算法效果或产品批准。
