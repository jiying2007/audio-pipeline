# D43 功率诊断独立审查记录

2026-10-11，experiment=FE_DEVICE_POWER_ATTRIBUTION_D43。Reviewer Independence=independent，claimant=root，verifier=device_capture_independent_review。独立实测审计与整批源码/最终文档审查 Spec PASS / Quality PASS，unresolved=0。冻结及本地收口终态另列，不能从静态控制审查推导实际执行。总体目标继续 active，promotion_allowed=false、shipping_approved=false。

## 已闭合的发现与执行前验收

QUESTION-1：过去功率汇总的操作数和累加规则未定义。独立澄清后冻结 AMENDMENT：旧 E/R/N、ascending binary64 左折叠、独立 fsum 容差与 per-bin binary32 exact 分开。原 PLAN/AMENDMENT/PLAN_REVIEW 字节不改。

MAJOR-1：测量校验误要求 inactive count_before=0。实际原 NS 在当前 inactive reset 前保留上一帧旧 count。实现改为 count_before=previous_count，然后 count_after 按 active 增长或清零；12 帧序列（11 帧 active 后 1 帧 inactive）的正例及伪造零负例通过。独立审计实际核 564 个 inactive 首帧旧 count 非零，匹配冻结生命周期。没有改 NS 算法。

MINOR-1：描述工具漏锁 D30 元数据及 near 冻结身份。最终工具补入 result/D30/near/power 来源匹配及全部 end lock。独立描述审计真实验证该完整消费集合和 200 个审计起止锁，闭合。

执行前最终审查 Spec PASS / Quality PASS / unresolved=0。12 个定向单元测试实际通过；严格 C 构建和 known-answer self-test terminal exit 0，包含 IEEE width、FLT_EVAL_METHOD=0、little endian、33/44 固定选帧及 40 帧 observed-vs-NULL NS/guard/output exact 对照。非仓 cwd help/deepdry terminal 0，46 例 / 6040 来源锁，writes=false、dsp_executed=false。实际定向控制 session 30362 五操作全 0；build-v2/selftest 回执分别 `c44b900ac05fcdfebca643d124d94388987ecd6f5a256fc4bc78c917b18098e7` / `25de43a31fa00c102b259c1fc8dff4f0edc25adc4769dfdafdbb8202e8f24917`。

## 真实执行及独立覆盖

正式 session 54026 terminal 0，184 次 / 505944 帧；根保护 session 63912 terminal 0，三既有目录 exit 2、完整 manifest 前后相同。描述 session 78299 terminal 0，全 960 固定组。结果与回执 exact SHA 见 [RESULT](DEVICE_POWER_ATTRIBUTION_D43_RESULT.zh-CN.md)。原 D42 拒绝及原五输出 identity 保持。

独立数值脚本 SHA256=`d91501fd80c1528528594b6ea64adf33c3393c579bef12e1601b0f7d46143f83`，只使用标准库和系统 libm，不 import 项目工具、不执行 DSP；自测实际 exit 0。实际审计 session 22555 terminal 0：505944 全帧 schema/count/range，7568 固定快照、1944976 bin 行数值、60544 汇总及 33742 严格零检查；920 项 D42 原输出 byteexact、960 组旧 observation identity、两模式投影、重复/未来前缀和 7925 起止锁全部通过。

独立描述脚本 SHA256=`ed0eabe68875e631f91123f0f6d7bbe4b4e2faab9cff1788c271bcf859676775`，只使用标准库，未导入主描述实现。自测真实 exit 0，部分 hop、valid/null、五 near 类别、signed-zero 和五负例通过；root 逐行控制审查 PASS。实际 session 65805 terminal 0：960 组、14464 binary64 浮点字段 exact、2832 null、493848 非 future power 帧、15360000 near 样本和 200 起止锁通过；future4 不评分，repeat16 组标为非独立。类别汇总及最坏窗所有数字另经独立只读复核。

覆盖边界：只复算固定快照保存操作数，不能宣称全部帧 FFT、非快照 bin 算术、完整 EMA 或原噪声历史独立重建。旧 960 组波形测量完全继承 D42 identity，不称新测量重算。近端标签是离线合成非零样本，field 无 near 真值；无真人、识别率、目标板 CPU/功耗/HIL/PQ 新证据。

## 最终整批门禁与后续

fresh whole review 已实际完成：Spec PASS / Quality PASS / Reviewer Independence PASS，unresolved=0。独立只读 session 28640 terminal exit 0，6040 来源锁 + 1884 工件共 7924 项 SHA256 均匹配。MINOR-2 原文案将 12 帧序列误写为 12 帧 active，已按真实 11 active + 1 inactive 修正；没有修改源码或重跑 DSP/审计。

两项收口控制静态审查通过：closeout-v1.py SHA256=`a5305acb825c49ac56ba3596b10af64acfc3314f0b7811983220cbb47a87fe69`；freeze-v1.py SHA256=`1ab07bbb5fc115e83b223ddceb6ed8d4c7afc0bf881b326359e7070ac6c98369`。仅当前 D43 本地 task，固定 progress/checkpoint 4→5，排他 intent/receipt；unknown 先对账不重放。接下来冻结 exact bytes、执行双 verify，并独立读回当前身份后，才允许一次实际 local closeout。最终实际状态在 CLOSEOUT 单列，保持本 REVIEW 冻结身份。

IMPLEMENTATION 是被正式执行器绑定的历史记录，不为更新进展覆写其字节。旧原生维护受理事实不重写成完成；正式执行时 fresh maintenance=false，独立实验资格由实测及本审查证明。

后续新算法应针对已测得的逐频点保护与恢复行为冻结单一因果假设，同时保留近端保护和无近端能量准入；不能通过总量 N/R 或对诊断窗口的事后阈值搜索放行。D42 候选拒绝保持，下一实验需新身份与独立计划审查。

Provider route unresolved，知识 NEEDS_REVIEW；未归档成功。Runtime 维护回执保留 accepted/completion-unverified，当前 fresh 门禁允许才执行正式测量，不伪造维护完成。无 commit/push/PR/merge/release/设备写。
