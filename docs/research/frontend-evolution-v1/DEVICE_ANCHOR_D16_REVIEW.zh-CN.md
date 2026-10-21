# D16 独立复审与阶段收口

日期：2026-10-11；experiment=`FE_DEVICE_ANCHOR_D16`。
独立审查者：`/root/device_capture_independent_review`；Reviewer Independence=`independent`。
最终 whole-change verdict：**Spec PASS、Quality PASS**；未发现新增 blocker、major 或实质 minor，不保证无缺陷。
PASS 覆盖实施、测量合同、执行证据与拒绝记录；候选仍为
**REJECTED_DEVELOPMENT_COUNTER_REGRESSION**，`promotion_allowed=false`、`shipping_approved=false`。
总体“全面推进优化迭代”保持 active，仅本轮 D16 实验里程碑收口。

## 审查对象与实际证据

审查覆盖[计划](DEVICE_ANCHOR_D16_PLAN.zh-CN.md)、[一次测量补充](DEVICE_ANCHOR_D16_AMENDMENT.zh-CN.md)、
[结果](DEVICE_ANCHOR_D16_RESULT.zh-CN.md)、中文研究入口、五行 patch 和新 fixture。
冻结快照：`/tmp/audio-fe-device-anchor-d16-r1-20261011/review-snapshot-v1.json`，
SHA256=`308421b4801427de9e777f62ad43c974a329d4f6034810799ceb894ef4248b2d`。
独立复审起止快照均匹配；6 文件、5 工件、3 脚本、3 检查回执共17项当前字节匹配。
本复审记录在快照之后写入，由阶段 Runtime 单独绑定其 hash，不修改冻结对象。

| 验证层 | 实际结果与独立复核 |
| --- | --- |
| strict 工程 | 14/14 CTest；恢复、搜索/确认性质及新锚 fixture 通过 |
| 冻结事件合同 | D13 mandatory 52/52；输入/config/repeat 身份匹配 |
| 已知延迟获取 | D9 mandatory 26/26；全部100行与D14相同，历史负结果保留 |
| 内存结构 | pipeline78840/80000 bytes，sync33464；无新增状态/alloc |
| 原设备开发回放 | 16场景、70固定臂、2重复臂；独立 receipt verifier exit0 |
| 完整比较 | 全70行计数/时点/delay/rail 与210组PCM窗口RMS独立复算一致 |
| 工件身份 | P1–P3独立核975项hash；P4独立核1249项final-binding关联hash |
| 文档 | 自测、一致性检查、git diff --check 回执均exit0 |

70臂相对D14有66臂PCM/metrics逐字节相同，相对D8有42臂相同，34个tracker-off控制保持相同。
工程库与replay库、原输入/config、default/control及两个repeat均匹配。
6条counter差异对应3臂、2场景：case07两臂727→1247帧仍新增jump/reset，
case16 default与D14逐字节相同，仍1247帧新增jump/reset。
case15原已有jump的事件延后与slips变化未冒充新增拒绝场景；tracked1单项稳定不能晋升。

## 失败记录与边界

attempt0附加断言失败已独立GDB复现并保留，按冻结早停规则未执行P2–P4。
修正只覆盖“下一更新开始重新确认”这一错误测量假设；信号、主断言、门限及候选五行不改。
原binding仓内fixture路径已漂移，恢复须核原attempt0快照映射，不能称旧路径仍匹配；
8 kHz selected552/truth7未被描述为正确恢复。修正记录与r1工程证据准确分离。

RMS、事件延后与工程获取不是ERLE、人声保真、听感、物理对齐或产品资格。
无本轮内部trace，不编造后续确认三元组；结构工作量不等于目标板CPU/p99/热/功耗证据。
该候选不部署，原产品src、AISpeech/E001和历史实验结论保持原有身份。
Provider route unresolved，当前仅仓内reviewing candidate，未正式归档；tmp工件须恢复时重新核hash。
无commit/push/设备写。阶段Runtime final仅本地conformance，不批准候选或关闭总体目标。

下一阶段核原采集参考与回放适配的同步/初始延迟契约，先冻结新集成假设和验收。
独立人声标注、固定下游唤醒/ASR、物理目标板resource/HIL和owner资格仍待真实证据。
