# 同步候选验证记录

## 历史字节空白检查

首轮整批暂存已完成，但完整`git diff --cached --check`实际exit2（ea327a/48d510），共有44条警告、16路径：原采集说明CRLF、冻结patch上下文、若干历史源码末空行和旧尾空格。未执行commit，旧stage-v1计划保留。独立核验确认16路径的原备份SHA、当前worktree SHA与index blob SHA均一致；不修改这些历史原字节，不全局关闭whitespace或添加宽泛attributes豁免。

stage-v2采用固定16路径/精确SHA/44条已知类型守卫；任何多出路径、未知类型或身份漂移拒绝，其余全部暂存文件必须strict --check实际exit0。归档例外结论只写LEGACY_WHITESPACE_PRESERVED，不能将完整检查冒称PASS。末尾实际结果和独立附核由新回执记录。本段只记录执行前设计与已观察的原失败，不预称stage-v2成功。

后续stage-v2已实际完成（session81688/c47dda，exit0）：470项候选=123数据+338研究+9集成，全部index blob/文件SHA及可执行模式匹配。完整空白检查仍真实exit2/44条；16项固定原SHA保全，其余文件strict --check实际exit0。staged tree=a32b9249520abb65b453bc71fcf562d2a6803a90；planSHA=7d0077b5a83181f26414136e90fb229952e332461b5389143a25bed937e3a6c3；具体回执保存在/tmp/audio-sync-20261020-staged-v2.json及whitespace-v2.json。最终审查附记和本段只改变集成文档，提交前将精确重暂存该两文档并冻结最终manifest；不改数据、冻结研究源码或重放旧测试。

## 后续远端增量复核

提交前远端main又前进至a42427693484409f9954125dada37d5db6c6f51e（#819），本工作分支已实际ff-only同步，未修改原工作树。增量仅新增T1_M2_PR_CONSUMER.md、workflow_pin_pr_consumer.py及上游verify-docs-gate一行；原本次数据、37模块、测试、CI分类及其他整合内容保持。为ff暂时移出的本地capture单行已恢复，最终相对新base仍只有一行新增。下表c416是首次验证时态，不冒称其远端绿CI适用于后来版本；刚读取新base时65success+1skip+1pending，当前不声明新远端全检查通过。最终独立定向复核和提交前检查将覆盖该增量，不为不相关上游增量重跑全部历史DSP。

新同步Runtime登记默认token预算300000在实际计量中已超限，已按本会话用户持续“提高预算继续推进”授权恢复到此前本地阶段采用的64000000（event866）；该预算是本地执行治理，不是科学门槛、超时或native总体目标上限。没有放宽验证规则。

2026-10-20；base=c416a5f8e44b36a6af5be4dc53c71456dd6ba5ef，worktree=/tmp/audio-pipeline-sync-20261020，branch=codex/device-capture-sync-20261020-land。记录者为本次执行agent；以下是实际工具调用的证据索引，不伪装为自动runner签名或远端CI回执。本文件写入时尚未执行本地commit，最终提交树与状态另行回读。

## 已实际完成

| 命令/核验 | 实际结果 | 证据定位/层级 |
|---|---|---|
| Git fetch及精确远端检查 | c416a5f，落后54；远端89success+2skip | a0102f/708cf2/31192d；只证明远端base，不替代本地候选CI |
| 原现场备份archive与manifest | 507成员逐SHA、源起止相等，VERIFIED | da85a7；原目录及旧index.lock保留 |
| 新worktree基线 | 精确等于远端c416a5f | 889f1b/c1f23b；无merge/rebase或受保护分支写 |
| 恢复文件对照 | 460个既有候选/采集文件与原备份完全相等；5个整合文件单列 | 3df839；另有备份后新增计划修订及被引用文档 |
| `python3 -m tools.codex_assets.device_capture --root tests/audio --dry-run` | exit0，INPUT_CONTRACT_PASS，16case、原119SHA、noDSP/no writes | session65889/8ed3e4；development输入合同 |
| `python3 tests/validation/frontend_evolution/test_device_capture.py` | exit0，19 tests，6.152秒 | session55834/947ff0；合成fixture和Host C合同 |
| `python3 scripts/ci_impact.py --self-test`（最终37项显式名单版） | exit0，29 tests，4.135秒 | session82179/5c85bc；CI/Release分类，不是声学验收 |
| 新研究Python语法 | 71个模块/测试AST解析PASS | b77e15；不等于全部测试已执行 |
| `python3 scripts/docs_consistency.py` | exit0，documentation consistency PASS | e7a4c0；包含整合入口和数据说明 |
| `bash -n .github/scripts/verify-docs-gate.sh` | exit0 | a5ee0a；仅shell语法 |
| `git diff --check` | exit0 | 8c305c；暂存树仍需提交前再核 |

Python验证使用本机已存在CPython3.10.20；CI分类自测PATH使用既有/tmp Git2.43.0工具和该Python，未安装或替换系统Git2.25.1。未重新执行所有历史DSP、完整历史审计、远端全workflow、板端/HIL或声学评分。

## 配置变化与影响

- verify-docs-gate只新增合成`test_device_capture.py`入口；保留上游新增的全部RealMAN/FE09/工作流门禁。没有加入全部设备测试discover。
- Verify的py_compile追加`tools/codex_assets/*.py`，其余上游检查保持。
- ci_impact明确列出37个研究工具为release-neutral；没有按整个tools目录或通配路径放行，未登记的`unregistered_backend.py`和产品`src/core/ap_pipeline.c`负例继续保留。此变化防止离线研究保全误触发产品版本发布，不降低声学/物理资格门槛。
- README三方整合保留远端external baselines及本地D0–D48科学结果，新增D49原准入拒绝/独立audit未完成说明。原README完整字节已保全，不改写旧快照。
- 原119采集文件、D3数据角色和输入锁不变；68WAV仅按明确路径本地暂存，音频内容隐私/再分发权利仍未评估，无外部传播。

## 有意保留的边界

原工作树仍有2026-10-14遗留空index.lock与全部原dirty，本次未直接修改.git；没有可用stash可声明保存成功。原仓暂时分支保留，新worktree承担提交。40份未被科学引用的context/handoff/runtime维护文档及/tmp二进制/生成物保留本地，未混入候选。两份历史README修订因科学文档链接被补入，保证入口闭包。

33个研究工具有固定/tmp历史依赖；部分测试需要封存数据或rtk。原实现身份和负结果可追溯，但不能声称fresh clone自动复现全部D0–D49。D49原矩阵DEVELOPMENT_REJECTED、独立审计待完成；真人ASR/KWS、目标板成本、E001/HIL与产品资格均未被本地Git提交解决。独立提交审查、本地commit与最终树回读仍是后续步骤。总体优化目标保持active。
