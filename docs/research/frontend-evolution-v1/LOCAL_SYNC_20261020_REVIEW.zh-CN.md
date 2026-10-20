# 2026-10-20 本地同步提交候选独立审查

审查者=device_capture_independent_review。范围为 `/tmp/audio-pipeline-sync-20261020` 的研究源码/文档、采集数据与五项跟踪文件整合；基线HEAD实际为 `c416a5f8e44b36a6af5be4dc53c71456dd6ba5ef`。本文件写入时尚未本地commit，不声明已提交、push、PR或远端CI通过。用户授权为同步后保存有效数据并本地提交，未授权本轮push。

## 独立只读核验

- 原目录 `.git/index.lock` 仍存在，未删除或改写；原dirty未回退。本次采用独立worktree承接候选，不把失败stash说成已保存。
- 备份manifest `/tmp/audio-sync-20261020-presync.json` SHA=`d424f5e7587c9d4b76fae4232fd8a45b9570f868e53bb3a2e591193a132bbd66`；archive SHA=`cb83286227037ad14a0eeb100d449961291998f16c245df6a65b4b74433e154a`。已只读流式核507个归档成员为普通文件且逐SHA与manifest完全一致，没有解压覆盖原目录。
- 341个原目录同名、恢复到候选的新研究文件逐字节一致；119个采集文件逐项与原目录、inventory及D0输入锁的SHA/bytes完全一致。合计114131862字节，68 WAV共110056280字节，未重新编码或生成音频。
- 研究文档相对链接扫描无缺失；被引用历史README修订保留。新数据说明、工具README及验证索引准确解释历史依赖与本地授权。
- 五项跟踪文件相对新base的diff已读：只增加采集合同测试、研究模块语法检查、测试说明、研究入口整合及显式release-neutral文件名单；上游门禁未由本地旧版本整体覆盖。
- `DEVICE_RESEARCH_FILES` 的37项精确等于当前37个Python模块；未使用宽泛tools前缀。既有`is_docs`已将工具README归为文档；未知backend负例保持。该分类不免除科学验收或产品资格。

本次核验没有执行旧DSP、全量数值审计、自检或全suite，也没有播放或转写录音。

## 验证层级与可移植性

[实际验证索引](LOCAL_SYNC_20261020_VALIDATION.zh-CN.md) SHA=`05fb3d05c8b3126127999f36a271ddb1a2a7615c8fcf6335da037e1780355079`已全文审阅。19项capture合同测试、16case/119SHA intake、71份Python AST、docs/shell语法及最终37白名单版本29项CI分类自测均是主执行者的实际工具证据索引，不冒称本verifier重新执行或远端runner签名。最终CI分类自测为session82179/5c85bc，不套用改动前的旧版本结果。

默认CI仍只显式运行capture合同并做研究模块语法检查，未加入34个device测试文件的全量discover。33模块含固定/tmp历史依赖，D37实际失败帧回归依赖D30/D35/D36封存数据，D49超时测试依赖rtk；工具README已经明确这两层，不能把源码提交说成fresh clone全部实验可复现。Host合成fixture/C构建不替代真人音频效果。

数据元数据保持development角色、training_allowed=false、human-not-verified/acoustic_verdict=pending；rpm指令/记录不等于实际运动证明。先前只读元数据与WAV容器检查未见个人身份字段或INFO/BWF块，但没有听音/转写，声音内容隐私及播放素材再分发权利仍未评估。用户本地保全授权不扩展为外部传播许可；68个WAV应按明确119文件清单暂存，不能宽泛force-add其他材料。

D49主矩阵的DEVELOPMENT_REJECTED与独立audit未完成保持；本轮不启动旧审计补绿色结果。D0–D48历史失败、source身份和README历史映射不因同步提交变成当前main重新执行证据。Provider unresolved/NEEDS_REVIEW不是归档成功。

## 结论与提交条件

**本地同步提交候选 Spec PASS / Quality PASS / Reviewer Independence PASS，unresolved 0（在本次授权范围内）。** 可以按研究源码/文档与原采集数据分批本地commit；主执行者仍须在实际提交前核暂存清单、精确119数据范围、diff检查及最终文件身份，提交后回读commit/tree与剩余dirty。审查之后新改动须另核，不从本记录推导未来树自动通过。

建议本地提交保持研究资产说明与数据授权/隐私说明同批可达，不提交/tmp runner/archive、模型控制回执或无科学引用的会话维护材料。没有push/merge/release/设备写授权；总体native优化目标active。此PASS仅为可审查的本地版本保全与配置整合，不代表D49声学通过、完整新CI、产品默认变更或HIL/E001/PQ资格。

## 新base定向复核：a424276（未commit）

原上述审查版本SHA为`8f1439c8c197af975d0334803177a223f752064eb5540f2490e2e67dc44c9414`，针对c416a5f的事实保留。本追加于新worktree实际HEAD快进至`a42427693484409f9954125dada37d5db6c6f51e`后进行，不覆盖旧base历史或把旧CI沿用为新CI。

已只读检查c416a5f→a424276的3文件增量：新增T1-M2说明与PR消费者源码，以及docs gate新增该消费者的离线自测调用；未改变设备研究算法或数据。两个新增文件当前字节精确等于a424276提交对象：

- `.github/program/T1_M2_PR_CONSUMER.md` SHA=`e372a09a5671d77cb2f4cf3c539b0cd6e69075fa1877cd8d255ac3e37e396ebd`。
- `.github/program/workflow_pin_pr_consumer.py` SHA=`be63c093dac9125ac7c2603b69ea1c8211705eea1a8d143b110a3f0c01d5dab7`。

新增消费者区分明确的直接PR依赖维护与原科学执行；源码保留protected-base身份、事件/父树、run/attempt及fail-closed门禁，未在本次设备研究整合中接入自动跳过科学工作流。本次仅定向静态读取，没有运行其自测或live probe，不独立签署其GitHub消费者执行资格。

当前`verify-docs-gate.sh` SHA=`7089eeae8249b2171d44fad0b96a2643b723ea12c0a5c4e1e40d3ef85a3dd55d`。移除唯一新增的capture合同测试行后，剩余字节与a424276上游文件完全相等，故新旧上游门禁完整保留；capture行移动到ci_impact之后未扩大测试范围。研究37项CI分类和Verify配置的当前SHA与前次审查一致。未重跑既有测试、数据/DSP或审计。

主执行者报告新远端检查当时为65success+1skip+1pending；此处不声明新base全绿，也不将该观察作为本地候选CI或merge许可。新base定向复核无新增问题，**本地提交条件仍成立，Spec PASS / Quality PASS / Reviewer Independence PASS，unresolved 0（本地保全范围）**。提交前暂存清单/身份检查与提交后树回读仍须完成；无push授权、科研或产品资格推导。

## 暂存空白检查失败：有界历史字节例外待验证

暂存后完整`git diff --cached --check`实际exit2，尚未commit。本verifier以只读子进程重新观察同一检查，确认44条警告分布16个路径，仅为trailing whitespace/new blank line at EOF。16项均在原presync507 manifest中，当前worktree SHA、暂存index blob SHA和原manifest SHA逐项相等；独立核验chunk227bfb，未修改或归一化任何字节。

这些包含采集原CRLF说明、旧patch上下文及已绑定科学身份的历史源码/记录。为通过样式检查修改它们会破坏输入锁或source身份。允许评审严格有界的LEGACY_WHITESPACE_PRESERVED方案：保留完整失败输出及固定16项路径/SHA；每次实际检查必须核原manifest、工作树与index blob一致；任何新增警告路径、非预定错误类型或SHA漂移均拒绝。只将已核原字节排除于本次样式检查，其余所有暂存路径继续严格检查；不得设置全局配置/attributes豁免或放宽科研验证。

此处仅批准例外设计，不冒称新strict检查已经执行或完整cached检查通过。**当前最终提交放行待stage-v2实际严格检查成功及独立附核**；前述源/数据审查历史保持，不用旧PASS覆盖该新失败。主执行者应保存失败v1及新v2证据，不覆盖原记录。

## Stage-v2实际附核与最后两文档restage边界

Stage-v2主执行session81688/c47dda实际exit0。计划`/tmp/audio-sync-20261020-staging-v2.json` SHA=`7d0077b5a83181f26414136e90fb229952e332461b5389143a25bed937e3a6c3`；实际staged回执SHA=`8a47a62c7a200bd3aef45d553516f67be5bb4988e75dc2471cec27d18102eabb`；whitespace回执SHA=`dc5b374e85e772104373d07f3b2b207cd3e1a83c3eb9203c34a7624d84e7cd96`。回执记录staged tree为`a32b9249520abb65b453bc71fcf562d2a6803a90`，这不是尚待restage后的最终树。

本verifier只读核470项实际index blob的SHA/bytes与v2计划逐项相等，并核Git blob ID及index/worktree可执行模式；分组为123data+338research+9integration。完整cached检查实际仍exit2，44条原警告及输出与whitespace回执完全一致；16例外路径/SHA均来自presync507 manifest。另对其余454项独立执行严格cached whitespace读取，实际exit0、stdout/stderr空，未设置全局豁免。故前述stage-v2严格检查待验证项已闭合，真实结论仍为LEGACY_WHITESPACE_PRESERVED而非完整cached检查PASS。

回读期间发现唯一当前文件与v2 index差异为VALIDATION文档在实际成功后追加终态段，已全文核对为真实时态补记；其余469项当前字节与v2 index一致。最初以470项全部当前相等为前提的只读断言因此失败，随后定向对账确认该明确单文档变化，没有重跑staging或修改原v2计划。该段及本review最终签署均须由主执行者仅对这两份文档精确restage，并生成新的final manifest/strict记录；不得把v2树和SHA冒称最终工作树身份。

**本地提交范围Spec PASS / Quality PASS / Reviewer Independence PASS，unresolved 0；允许按用户授权本地commit，执行前仍须完成上述两文档restage及最终manifest/strict守卫。** 数据/冻结研究源码不得再变，提交后须实际回读commit/tree。没有push、全workflow、科研声学或产品批准；D49独立audit待完成及总体目标active边界保持。此次仅变更ownedreview，没有改index/其它文件，没有DSP、数值审计或全suite重跑。
