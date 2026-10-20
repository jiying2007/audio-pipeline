# D11 搜索几何修复候选计划

日期：2026-10-10；experiment=`FE_DEVICE_SEARCH_D11`；状态=FROZEN_CANDIDATE_PLAN。
授权=用户继续推进 D10 明确的搜索覆盖修复；primary=`adk-planning-execution-loop`。
goal_statement=判断固定 1 ms coarse 几何能否修复已知短延迟获取且维持误跳/资源约束。
baseline=D8 receipt `eb85a87a494d08ce35be0f9cd47ba0030be9336ec85e35ade0322837d10cbedc`；
D9 result `564a2d3d6b6200c728ad09469b455b0595a584286d56ea2c0fd3899e1a9624b6`；
D10 diagnostic `9c63a6d5eee8f1f13a77f711a08054ac77e22127daf488ea4a78b063e8afe613`。
live main=`025e266c2ade3a1923ae10f5c8759ee49a437ea5`，本次读取 summary/release/convergence 成功；
tracker #657 OPEN，#706/#695/#696 独立；不借 main CI 证明本地候选。

## Phase A：单因果实现与证明

kind=implementation；implementation_permission=仅临时第一方研究副本、持久研究 patch/fixture/文档。
数据均为已查看 development：D9 合成工程数据与原 tests/audio 119 文件锁；不是 validation-grade/blind。
复制精确 D8 源码到新隔离目录，唯一算法改动为 `coarse_step` 从 `rate/500` 改为 `rate/1000`，最小值仍 1 sample。
这是一个搜索几何参数变更，其 coarse 网格、局部 refine 半径、uniqueness guard 和 route candidate tolerance
都沿用同一个派生变量，故同步约 2→1 ms；不声称只改变搜索循环而保持其余几何不变。
原最低相关 0.0324、峰值比 1.01、三次确认、大跳界限 20 ms、D8 40 ms gate、漂移公式和 AEC 均不改。
无第二参数候选、无 sweep，不变更 shipping 源码/default/API 或输入数据。

top4 证明：coarse 点按 step 均匀排列，闭区间 [refined-step,refined+step] 至多排除三个点，
保留四个最高 coarse score 足以得到区间外的最高 runner-up。缩小网格时 guard 同步缩小，原证明结构成立。
新增只读工程 fixture，在 8/16 kHz、max100 ms 的全部整数 refined-delay 位置，
使用固定 flat/scattered/clustered 分数与低门限/通过/竞争三类 best score，
将真实 top4 helper 与全 coarse 列举 oracle 对比，并验证排除点数≤3；不用于算法选型。

## Phase B：工程硬门禁

kind=validation；固定原 14 项 strict CTest 全部必须通过，禁止改旧断言/超时洗绿。
原 D8 直接 SYNC engineering 与 public recovery fixture 均需通过，保留低相关/失配/reset/isolation/periodic 负例。
上述任一失败→REJECTED_ENGINEERING_REGRESSION，保留失败，停止后续候选执行，不调参数重试。
完整状态实际 sizeof 必须保持 D8 的 78840 bytes，原 ceiling=80000 不放宽；无新 malloc/TLS/state 成员。
max100 ms、8/16 kHz 的 worst-case score-call 上界按真实循环独立计算，候选/基线均≤2.0 倍。
调用数不是 CPU/p99/功耗；Host ELF/code size 独立报告，不宣称 SSC305 资源资格。

## Phase C：已知延迟矩阵与真实开发回放

kind=research；沿用字节不变的 D9 public fixture，候选 100 固定用例加指定 16k/seed1/acquire/7ms 一次独立重复。
不重跑原 baseline，重读保存的 D8 100 例；候选输入全部须 byte-exact 等 D9 输入。
mandatory 仍为 24 无噪宽带加 2 已通知 gap，最后 20 个 capture 帧均需位于生成器真值 ±3 ms。
本轮候选明确要求 26/26：这是新的修复候选验收，不改 D9 baseline limit 或历史决定。
否则 REJECTED_KNOWN_DELAY_REPAIR，停止真实回放；周期/低参考/双讲/未通知 gap 原样完整披露。
指定重复输入/输出/metrics 必须逐字节相同；summary 从实际 CSV 重算。

通过上述硬门禁后，执行原 16 例 70 固定臂+2重复 device_replay，原 receipt verifier 必须通过。
34 个 tracking 关闭控制臂 PCM/metrics 与 D8 必须逐字节相同；同配置 default/sync-control 保持等价。
指定 rpm480/far-motion tracked1 不得重新出现 172 ms 误跳；quiet 不得新增 jumps/resets。
任意固定臂 jumps 或 AEC resets 超过 D8 对应臂→REJECTED_DEVELOPMENT_COUNTER_REGRESSION，
不能以已知矩阵获益解释无真实延迟标签的现场新增跳变为正确。
所有其他输出/延迟/slips/RMS 差异完整披露；不以总能量选择或宣称 ERLE/保真收益。
即使全部硬门禁通过，也只 DEVELOPMENT_CANDIDATE_ONLY / INCONCLUSIVE_ACOUSTIC_EFFECT，不批准 shipping。

## Phase D：独立审查与闭环

kind=review；claimant=root；verifier=已授权独立审查者；review_mode=whole-change。
required_evidence=冻结计划、增量 patch/唯一峰 oracle、精确 source/build/config/input/output、原 tests、100+1、
有条件执行的 70+2、资源上界、失败/不利变化及独立复核。
预算=1 候选 strict build/14CTest、3 工程 fixture、1 known100+1、1原70+2与verify；无参数搜索。
retry_budget=测量/执行错误最多2次后replan；算法硬失败不重试洗绿；staleness=任何规则/源码变化需新锁。
open_items=实现/验证/决定及审查三项；heartbeat=阶段完成；stop_condition=pass/replan/blocked；
attestation_readback=hash/实际逐帧或 receipt 重算。
Provider route unresolved，仅仓内 reviewing candidate；不正式归档、不 commit/push/设备写。
短期产品仍为 AISpeech 链路；研究候选、SSC305、独立声学、HIL、E001、owner 和 PQ 分别验收。
