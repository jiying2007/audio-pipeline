# D6独立复审与本地软件闭环结果

日期：2026-10-10；状态：LOCAL_SOFTWARE_REVIEW_CLOSED。
本报告为 [D6冻结计划](DEVICE_REVIEW_D6.zh-CN.md) 的后续结果，不改写其执行前状态或D3/D4/D5历史证据。
Provider路由未解析，本文件是仓内reviewing候选，不表示正式知识归档。

## 修复与独立结论

D5独立审查发现blocker=0、major=0、minor=1：run_logged超时/输出超量时丢失命令回执。
D6仅修复该取证缺口，并增加启动失败取证和三类负例；无算法、配置、输入角色或验收阈值变化。
超时/启动失败的退出码为null，原异常传播；超量输出保存截断文本并拒绝成功。
回执文本上限不是子进程采集内存上限。

独立审查者device_capture_independent_review对完整24文件快照起始及最终hash核验一致：
Reviewer Independence=independent，Review Target=working-tree，Spec Verdict=PASS，Quality Verdict=PASS。
MINOR-1=FIXED；blocker/major/minor=0/0/0，reopened=0，Contract Change Decision=none。
未发现问题不保证不存在未识别缺陷；本结果不是owner签收或产品放行。
本报告为根代理按独立审查返回结果整理，报告自身不属于24文件审查快照。

## 证据身份与验证

证据根：`/tmp/audio-fe-device-review-d6-20261010`，raw不进入Git。
本地HEAD：572b0e34a8a8e5663397ce16e378209ba9058d4d；全部本地改动未提交。

| 文件 | SHA256 | 结论 |
| --- | --- | --- |
| review-snapshot.json | a532271f30b1de863d7ac8c6b132b187e056933052fe532f6f0388581d906d65 | 24文件独立核验未过期 |
| tests.json | 95c4a6799c062dea700e887c0095e6ebb8832ff8be2fc9b4794bc0375b505309 | 19 tests，exit0 |
| docs-gate.json | d0b9c83fddff33e82b0116495abd9822b2842ed9c2f00ca93552a4277d8f7398 | 完整门禁exit0 |
| replay/receipt.json | d2e4c5fb82c2ca795d576f42618b8204e47ae16b7f96c232fdc161d542bf4b36 | 16例70固定+2复跑，独立verify通过 |
| equivalence.json | 09600b7db1e13a856f34ee71222e564a5c0cbe2846bb666c823dea1e5cdc688b | 144实际PCM/metrics逐字节等价 |

独立审查者按新receipt列举72次运行对应的144文件，核集合、实际bytes及记录SHA均一致。
独立运行三项失败回执负例通过；mock仅为契约测试。根代理从非仓库cwd核help/dry-run通过，
dry-run无写入、无processor执行；git diff --check通过。
Python3.10及临时Git2.43离线fixture环境延续D5，不改变测试要求。

临时首个验证编排在测试/回放/docs gate均exit0后，因比较文件名写错导致count0断言失败。
原脚本及orchestration-failure.json保留；新独立比较脚本按case/mode文件名核验144项通过。
未重跑算法或覆盖旧结果。该编排失败不能解释成算法失败，也不能隐去。

只读复核live main=4ea71ff7bd2717c9d56cbfc06197f9958107d42e，其required summary及读取的checks成功；
开放PR #702/#696/#695不在本次修改范围。main托管CI不替代本地快照CI；未来整合需保留主线D1 gate入口。

## 后续边界

D4仍REJECTED_REAL_ROUTE_RECOVERY_REGRESSION；D5仅测量诊断，D6仅失败取证修复。
原始119文件锁不变，16轮已查看development，不升级blind、validation-grade或独立人声标签。
设备侧麦位置/render时轴/制品身份、人工语音标签、独立声学、owner验收、shipping、E001及
Product Certification保持待验证。多帧同步算法若继续，应另冻结单因果假设和验收，不调阈值洗绿。
本次无commit/push/PR/merge或设备写入；Runtime conformance单独执行，不推导产品资格。
