# D16 提交锚候选结果：一致性契约通过，完整回放仍拒绝

日期：2026-10-11；experiment=`FE_DEVICE_ANCHOR_D16`；[冻结计划](DEVICE_ANCHOR_D16_PLAN.zh-CN.md)。
最终决定 **REJECTED_DEVELOPMENT_COUNTER_REGRESSION**，selection=`REJECTED`；
`promotion_allowed=false`、`shipping_approved=false`；总体“全面推进优化迭代”保持active。
新增检查能阻止缺乏原history支持的锚被提交，但设备原新增事件仍会随后发生，不能晋升候选。
本轮阶段收口只覆盖一版算法实验、测量修正及完整结果；不是声学、设备或整体落地完成。

## 唯一算法改动

精确D14研究基线，仅在third确认后取保存anchor、实际提交前增加五行history检查，
调用原40 ms helper和原0.0324门限；低支持则observed=0返回。
confirm计数已清零保持原语义，不替换实际提交对象、不新增状态或改变门限。
[增量patch](../../../.github/research/frontend-evolution-v1/device-anchor-d16.patch)独立check/实际重放byte-exact。
搜索/guard、原refined history gate、0.5 ms确认容差、三次确认、drift/AEC/API/default均不改。
产品src不启用；最终候选根 `/tmp/audio-fe-device-anchor-d16-r1-20261011/source`。

## 初次失败保留及测量纠正

初次输出 `/tmp/audio-fe-device-anchor-d16-20261011`，新增fixture附加“拒绝后下一更新”的断言exit-6，
按计划停止，P2–P4未执行；原失败结果/库/日志未删除或覆盖。
GDB独立复现rate8000、truth7、实际候选552、confirm1、error232（旧320）、无jump/observed。
附加断言误把“重新开始确认”要求为“搜索必然立即回到生成真值”。
按[测量补充](DEVICE_ANCHOR_D16_AMENDMENT.zh-CN.md)经独立复审，
只将该附加断言改为实际refined=old+error、范围合法、计数1/保存新候选，信号与原主弱锚/强锚断言不改。
初次fixture快照hash=`3f6b0eba41ae882c320c5353fa65805fdcd9aa9edd99f830b6fc7ab7e376d809`，
与初次binding匹配；原binding仓内fixture路径因纠正而漂移，恢复用明确attempt0快照映射。
不能声称初次binding仍匹配当前fixture，或把552称为正确恢复。
r1保留8 kHz selected552/truth7诊断；16 kHz后续selected15/truth15，仅此固定帧相同。
候选五行代码未改，使用一次测量修正，无参数/验收洗绿。

## 工程与冻结矩阵

| 验证 | r1实际结果 | 范围 |
| --- | --- | --- |
| strict build/CTest | 14/14通过 | Host工程 |
| 原D8 engineering/recovery | 全通过 | 原SYNC与公共恢复 |
| D11 oracle、D14确认性质 | 21618项及两率确认性质通过 | 搜索/确认 |
| 新anchor fixture与原D14对照 | 两率弱锚/强候选及强锚正例通过 | actual tracker，无mock score |
| 拒绝后重新确认 | count=1、actual selected保存、旧delay/无jump保持 | 不是生成真值获取保证 |
| 完整state | 78840 / 80000 bytes，sync33464 | Host结构大小 |
| 原D13事件矩阵 | 56+1执行，52/52 mandatory | 原input/config/evaluator不变 |
| 原D9获取矩阵 | 100+1执行，26/26 mandatory | 原输入与末20帧±3 ms不变 |

直接弱锚例：8 kHz truth7/anchor10、16 kHz truth15/anchor20。
原D14在2/3确认后提交弱锚；D16拒绝并保持旧delay/drift/last-best状态、无route_jump/observed，
同时原mic history追加和搜索计数更新照常。确认清零后可以按实际新候选重新开始，不承诺永久抑制。
strong anchor=truth两版均提交、清零drift、保留原refined error语义。
error在observed0时仅诊断，不能称有效观察；AEC reset由公共事件矩阵/完整回放验证。

D13正例获取39帧、切换149帧、exactly1jump/reset、首次/末窗/本帧入带及切换前保护全通过；
短pulse/steady/silence/unrelated原规则全通过。4个pulse3保留diagnostic：8k无jump，16k149/179帧各两jump。
D9全部100条summary与D14完全一致，原26个mandatory通过；合成双讲0/24、未通知gap两例不入带保留。
指定新进程repeat原input/output/metrics及D13 config逐字节一致。
无新增alloc/state；third完成路径最多追加一次原40 ms/stride4相关，8/16k80/160点。
结构工作量不等于DUT CPU/p99/热/功耗资格。

## 完整设备开发回放仍触发拒绝

原119文件锁、16场景、70固定臂+2repeat完整执行，receipt verifier通过。
适配mic/render及config与D8/D11/D14一致；工程库与实际replay库逐字节匹配。
34个tracker-off控制PCM/metrics与D8/D14完全一致，default/control及两个repeat等价。
70固定臂相对D14有66臂相同、4臂改变（两个场景）；相对D8仍42臂相同。

| 原拒绝场景 / 执行臂 | D8 jumps/resets | D14事件帧 | D16事件帧 | D16 jumps/resets |
| --- | --- | ---: | ---: | --- |
| rpm240 far-motion，run-2908630469-2466，default | 0/0 | 727 | 1247 | 1/1 |
| 同场景，sync-default-control | 0/0 | 727 | 1247 | 1/1 |
| rpm480 double-talk-motion，run-4874838670-2672，default | 0/0 | 1247 | 1247 | 1/1 |

6个counter差异对应3个执行臂、2个采集场景，不是六个独立事件场景。
case07原727帧不再提交，但1247帧发生后续事件：提交锚检查没有让整段零新增jump/reset。
case16与D14输出/metrics逐字节相同，符合D15已观察的refined/anchor相同且支持强。
帧从0开始、每帧10 ms；上述为适配回放处理时序，非校准后的声学时间轴。
没有本轮内部observer trace，不能从公开event编造D16后续三元组或给新增路径物理真值。

另case15 rpm480 far-motion的default/control原本就有jump：D14的1047帧延后到D16的2557帧，
jump/reset仍1/1，slips27→17；未当作新增拒绝场景。
同场景目标tracked1与D14逐字节相同，无172 ms跳变，jumps/resets0/0、slips29、delay集合0/1 ms。
全部70臂counter变化时点、slips、delay集合、rail samples和原窗口RMS保留。
例如case07 default的10–12 s与19–21 s输出RMS相对D14变化+7.773257/-2.691272 dB；
case15 default同窗口变化+5.209807/+5.486580 dB。
缺clean target/独立人声标签，RMS变化不能证明残回减少、人声保真或ERLE收益，更不能豁免硬失败。

## 身份与恢复

最终工件根 `/tmp/audio-fe-device-anchor-d16-r1-20261011`；初次失败根独立保留。

| 工件 | SHA256 |
| --- | --- |
| 实际libaudio_pipeline.a | `4a748de3501241ff66787c8fdb4ccf445126ae49b1be3c4420b7e15e1ffb1170` |
| engineering-result.json | `366ccd8bf594f24cdaaf7295f3caf425471973ea5dee76d32d111adc2b1b9a85` |
| engineering-binding.json | `11d4699b3bd42b20a3c485629fce0c88f5567f36f05fb9d26247e1e4b3ebb3d9` |
| replay/receipt.json | `2a1ed561e142a991b9c5679b35df0e44f12ab32ecc6e3e67c42e4582377f85f2` |
| comparison.json | `033d5badbe6cb1956d852b2c19d7db3a7eccb45d26e2d4f3da1ea1c540711a43` |
| final-binding.json | `5d273d10dd9b63ab5fabd9da43d5bd55e52165ab725e5d6bf5a0b99963af815a` |

engineering binding锁59个source、fixture/patch/计划/补充、旧evaluator及初次失败依赖和838项工件；
final binding追加完整回放/comparison和1190项工件。文档快照与独立whole-change另绑定。
tmp不是永久证据仓，恢复先核hash，工件丢失/漂移则stale。Provider route unresolved仅仓内reviewing candidate，
未正式归档；无commit/push/设备写，AISpeech/E001/历史结果不改。

## 下一阶段

本版不部署，不追加门限/容差修改绕过拒绝。
目前已区分提交对象支持一致性与真实路径资格：前者可工程验证，后者仍缺校准时间轴、物理delay及声学真值。
下一步应核对设备适配配置与原采集的同步/初始参考延迟契约，并冻结可验证的集成假设；
不能一边要求合成真实路径正常获取，一边凭无真值的默认40 ms保持认定现场迁移错误。
原D8稳定性拒绝规则继续保留；任何新集成验收都须单独预注册，不事后改本轮结果。
独立人声标注、固定下游唤醒/ASR、实际目标板resource/HIL仍待真实证据；总体goal保持active。
