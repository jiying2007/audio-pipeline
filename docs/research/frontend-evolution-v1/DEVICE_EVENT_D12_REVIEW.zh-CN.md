# D12 独立 whole-change 复审与恢复记录

日期：2026-10-10；reviewer=`device_capture_independent_review`；independence=`independent`。
**Spec PASS / Quality PASS**，仅覆盖测量实现、执行证据及结果披露。
未发现新增 blocker、major 或需修复的实质 minor；该结论不保证无缺陷。
决定=`ENGINEERING_EVENT_DIAGNOSTIC_NO_PROMOTION`；D11 Candidate 仍为 **REJECTED**。
`promotion_allowed=false`、`shipping_approved=false`，没有算法或产品采用批准。

## 冻结快照

对象：[原计划](DEVICE_EVENT_D12_PLAN.zh-CN.md)、[截获验收补充](DEVICE_EVENT_D12_AMENDMENT.zh-CN.md)、
[入口重计划](DEVICE_EVENT_D12_REPLAN.zh-CN.md)、[结果](DEVICE_EVENT_D12_RESULT.zh-CN.md)、README 与 fixture。
`/tmp/audio-fe-device-event-d12-20261010/review-snapshot-v1.json`
SHA256=`aa27ada801d505a99c4c9dc5d55b8109d080b94da34d2221a9fdde586e79153a`。
独立起止核验六个仓内文件、四份工件、三个临时编排脚本全部匹配，未 stale。
本 REVIEW 由根代理收到最终独立结论后补写，不属于被审快照文件。

## 独立证据核验

原 --wrap P1 两次完整运行均 3,024 capture、零截获，负结果保留且未当作有效观察。
新的 measurement library 只改原函数定义名，函数体原字节不变，实际符号入口得到核验：
unity 对原公共函数为未定义引用、对改名原函数为定义；observer 实际提供公共函数并调用改名原函数。
无 --wrap。fixture 原 library 注释的歧义由 RESULT 明确限定为 body unchanged/new measurement identity。

独立核验 binding 中 489 项 hash；16 次运行 **48,384 帧** PCM/public metrics 对原 receipt 逐字节等价。
逐 CSV 重算 delay/jumps/slips/reset 全部对齐，八次 observed 共 **2,400 eligible epoch**。
实际 HPF/BF 后 mono、copy-state history 添加时点、观测前后 memcmp 和原 helper 符号隔离符合重计划。

第 457/617 帧的 4.57/6.17 s 仅为适配后处理时间。D11 实际采用首次保存候选 **15/31 samples**，
并非跳变本帧 refined 的 24/16。第 417/427 帧先前一次确认确由 history gate 清零，
第 587/597 帧 59→31 超过容差重新从一次开始。三次确认没有跨这些失败累计。
D8 第二事件前漂移到 642 samples，与 D11 的 640 不构成瞬时同态反事实，文档已明确限制解释。

两个事件的六个确认 epoch 均通过 short/history 门限，旁路 unique 均为 1。
large-jump 分支实际不调用 small-jump uniqueness，但文档没有宣称增加相同检查可以阻止两事件。
README、结果表格及资格边界与实际文件一致；独立审查只读，未修改、spawn、提交或访问设备。

## 根代理定向检查与连续性

Python 3.10 `scripts/docs_consistency.py --self-test` exit 0/OK；
实际 `scripts/docs_consistency.py` exit 0/PASS；`git diff --check` exit 0。
Runtime 证据绑定和 final 门禁另外执行，不由独立审查结果推导其状态。
未重跑无关旧全套门禁，不改旧实验/原库/产品源码/default/API、AISpeech 或 E001，无 SCM/设备写。
Provider route unresolved，仓内 reviewing candidate，未正式归档。

恢复入口：读取 RESULT、三份冻结计划、result/binding/audit-v2 和快照；原 --wrap 失败工件保留。
下一阶段应先冻结初始获取与稳定跟踪/实际路径切换的事件契约，使用可独立判定的正常获取、
错误候选和真实路径变化用例，再单独注册算法实验；本测量不可直接批准修改后的算法。
固定 development 控制流解释不能升级为物理延迟真值、声学收益、人声标签或目标板资源资格。
main CI、Host 等价和 Runtime conformance 不替代 shipping、owner、HIL、E001 或 Product Qualification。
