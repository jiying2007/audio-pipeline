# 设备采集落地实施契约

状态：LOCAL_IMPLEMENTED / NEEDS_REVIEW，FE01/04/05/06开发诊断，不晋升shipping或E001。
授权：用户在当前会话要求“全面推进落地闭环”。
基线：572b0e34a8a8e5663397ce16e378209ba9058d4d；本轮开始live Verify/Release成功。
隔离：PR #692属于A1证据保留，避开其文件；保留已有tests/audio和D0报告。
收口时该PR已合并，live main=4395782b9b7e7c352bff56e1c240e3751465d59e；compare仅两个不重叠文件，
本地基线/source lock保留；新main Verify仍执行中，身份与结果详见D3记录。
primary_skill：adk-planning-execution-loop；supporting：adk-code-review-loop、完成验证。

## 冻结目标与验收

落地独立的schema-v2采集校验与帧适配、现有公共AP的固定研究回放、逐例输入/源码/配置/运行器/输出身份、
损坏输入/伪成功/越界路径负例和现有docs/Verify接入。Python工具进入tools.codex_assets；shell不承载逻辑。
不依赖AISpeech源码或运行库；不改产品DSP、公共ABI、版本、默认preset、历史PLAN/TASKS和物理资格身份。

固定数据角色为development/regression，锁定原始119文件哈希和16轮精确集合。
旧80/100录音只做完整性/削波诊断，不自动赋予通道身份或进入AEC回放。
16轮每轮两臂default/BF共32；四远端场景三臂default/tracked1/fixed1共12；四双讲场景两臂共8；
两quiet fixed1共2；两quiet与两motion的AGC/NS隔离共8；另八远端/双讲场景各增加tracked1-no-drift共8。
合计70固定执行，重复控制另外计数。此前62回放的相同配置必须逐点复现，
新增8臂只用于分离delay_tracking与drift compensation，不按本批音质选择shipping候选。
1ms来自已查看开发数据，永久标注为D1派生诊断假设；没有独立确认、真实render timestamp或clean target。

退出：输入锁与全部结构检查先通过；运行器拒绝partial/短参考/额外样本；输出样本、有限metrics、索引和配置身份一致；
原始文件复验；receipt拒绝缺例、缺配置、输出变更、失败退出、虚假promotion；既有契约与本次tests通过。
定向门禁、full applicable local检查、fresh独立审查、修复及复审分别记录。
无commit/push/PR/merge授权，完成声明限本地软件与开发诊断。后续精确head托管CI不可假造。

## Phase A：输入与可恢复证据

kind=implementation；permission=用户本轮；owner=当前线程；scope=tools.codex_assets、固定输入锁与新研究manifest。
验收：严格类型/JSON、WAV长度、frame/PTS/epoch、scene bounds、参考逐点关系、motor反馈与显式256→160尾部。
exit_gate=单元负例和16轮实际数据；handoff=Phase B；retention=源码/hash可入Git，raw音频保持忽略。

## Phase B：回放与测量

kind=implementation；scope=research-local C runner及Python编排；资源=单个新/tmp输出目录，串行build/replay。
验收：70固定执行+默认/零参考/重复控制，逐例封存成功及失败，receipt独立回读；不新增质量评估器。
exit_gate=定向C/sanitizer和实际数据；handoff=Phase C；retention=输出PCM本地受控、仅脱敏summary/hash候选。

## Phase C：审查、文档与收口

kind=implementation/review；scope=现有docs gate、中文入口、状态文档；不得扩写上游PR范围。
验收：现有契约/适用local checks、fresh只读review、当前快照复验、Provider回执和Runtime门禁单列。
exit_gate=软件证据齐全且无未处理blocker/major；handoff=独立声学/产品owner后续。
Provider route unresolved时仅REVIEWING候选，不把本地生成receipt当正式归档；物理/权利/独立数据缺项分别保留。

## 连续性与停止条件

retry_budget：同类失败最多2次无新证据后replan；新blocker/design-change先更新契约。
staleness：live main移动即复核身份/范围；heartbeat=每里程碑及持续工作每60秒以内进度说明。
plan_completeness=3 phases；attestation_readback=复读本契约+机器manifest+测试结果。
goal_statement=可复用数据研究入口与本地验证闭环；completion_claim=本地实施和数据回放通过，全量门禁及独立审查待闭环；claimant=当前线程；
verifier=定向tests、独立artifact回读与fresh reviewer；stop_condition=pass/replan/blocked。
open_items=独立近端/声学/KWS、SSC305 AP执行/资源、Provider路由、远端SCM门禁；均不由Host数据替代。
excluded_context=旧AISpeech候选参数、未验证README声学成绩、历史candidate-zero、raw录音内容及个人身份。
风险回滚=仅新增工具/研究文件和docs命令，逐文件可撤回；保留原数据及失败；不清理用户dirty或旧/tmp证据。

2026-10-10收口见 [D3本地结果与后续验收](DEVICE_CAPTURE_D3.zh-CN.md)。Phase A/B本地验收已通过；
Phase C保留Git 2.25.1既有fixture门禁失败、独立review和Provider unresolved。
作者自审与独立文件回读不能代替独立reviewer；不得标记整个阶段完成或可合并。
