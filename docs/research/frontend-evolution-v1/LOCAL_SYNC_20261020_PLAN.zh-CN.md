# 2026-10-20 远端同步与本地研究分批提交

用户明确授权同步远端并提交本地有效数据，真机采集数据可按需提交。本阶段使用adk-planning-execution-loop，支持adk-commit-pr-quality-gate；本地提交不代表推送、PR、Release、设备写或产品资格授权。总体优化目标保留，本阶段先处理同步与提交。

## 冻结输入与完成条件

开始时本地main=572b0e34a8a8e5663397ce16e378209ba9058d4d；fresh origin/main=c416a5f8e44b36a6af5be4dc53c71456dd6ba5ef，落后54、无本地commit分叉。5项tracked dirty、433项未跟踪文本/元数据及被忽略的采集WAV需保全，实际路径集合以备份manifest为准；不凭初步计数批准提交。3个untracked RealMAN文件与远端字节相等。4项tracked改动涉及远端更新，需要恢复时逐项整合；新增研究模块的CI接入另验。

真实采集目录119文件、114131862字节：4个80/100输入/echo和16轮schema-v2 capture配套mic/output/reference/事件/逐帧元数据。80/100为用户确认音量；目录rpm不能代替session中的真实转速或真人标签。采集数据只作已查看的development/regression，绝不升级为blind/独立真值；来源、隐私、文件体积与checksum检查后才纳入本地提交。

完成条件：原dirty与采集内容有可回读完整备份；工作分支包含精确远端基线；有效源码/文档/采集文件精确路径暂存、分批验证及本地commit；原无关内容保持或有明确保留位置；最终检查当前HEAD/remote包含关系、commit树、数据校验、验证结果和未纳入清单。不能用当前远端绿CI替代变更后的本地验证。

## 执行步骤与风险

1. 生成排他/tmp备份archive及逐文件SHA manifest，覆盖全部tracked修改、untracked文件和完整tests/audio；检查归档成员与当前字节。保留Git stash作为同步恢复锚点，不drop。
2. 新建本地同步分支，stash现有tracked/untracked后ff-only纳入已拉取main。恢复stash；3个远端同字节文件无需重加；如冲突，用apply_patch逐项整合，保留双方有效变化，不恢复过时上游配置。
3. 筛选有效研究代码/科学记录，临时上下文/会话维护与机器私有回执保留本地。冻结旧证据仅只读；提交索引明确哪些实验只是历史本机研究，不能在fresh机器上凭/tmp路径推导复现或PASS。
4. 真机数据补充可移植inventory/README，原始session/CSV/WAV字节不改；精确路径强制暂存被忽略WAV，不全仓force-add。若发现隐私/来源缺口，保留本地并明确不纳入原因。
5. 运行适用的格式/元数据/输入合同/新代码单测及必要配置检查；独立审查后按数据、研究代码/证据、集成职责分批本地提交。不得为提交重跑全部历史DSP或放宽门槛。

retry_budget=2（仅明确可修复失败），staleness_threshold=当前Git/CI与每批commit前重核；stop_condition=pass或replan，无法安全同步或数据权利不明时仅阻断对应项。claimant=root，verifier=device_capture_independent_review。修改仅本仓和排他/tmp；不清理原数据、不rebase、不覆盖无关dirty、不修改第三方音频库或产品默认。

## D49 恢复事实

上次中断后的正式操作已真实结束：outer exit0/child_terminal=true，555.5245135296136秒，184路/505944帧，decision=DEVELOPMENT_REJECTED；resultSHA=6e4b460a101131e950888c947d7210210b948c749ea5e2184e3fce182b5fe6b6，bindingSHA=db417f95db9ca6d3467fd85c7975b8de372b7c79c45c6e9ce99c9a205d67229f。两臂near中位约-3.191886dB、20/24改善；no-near最大+13.404531dB，echo whole最大primary+1.164761/selected+1.695652dB，未满足原全部门槛。独立审计草稿尚未完成主方全审/自测/全量审计，不能改写为独立声学确认。旧formal intent/root/receipt禁止重放，本阶段备份并保留这一未闭合边界。
