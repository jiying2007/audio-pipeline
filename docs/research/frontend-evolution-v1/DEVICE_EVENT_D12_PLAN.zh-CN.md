# D12 新增现场跳变事件：冻结旁路诊断计划

日期：2026-10-10；experiment=`FE_DEVICE_EVENT_D12`；kind=`measurement`。
goal_statement：解释 D11 两个新增跳变场景的搜索、长窗、确认与重置时序，验证诊断不改变公开回放结果。
来源：[D11 拒绝结果](DEVICE_SEARCH_D11_RESULT.zh-CN.md)；用户再次授权“继续推进”。
本计划不批准算法修复，D11 REJECTED 不变；实现权限仅限独立离线测量 fixture、临时编排及研究文档。

## 基线、假设与边界

使用已冻结 D8/D11 的实际静态库、生成头、源码与原 replay receipt。
D11 final-binding SHA256=`6e17559d027df08f29c7a38e9194488811a09d4a8725d463752cb146d1d9eb5c`。
D11 comparison SHA256=`c7200d891a539ecff3566ebfa9129d65fe254edbae8eb6590432a951de3e7db5`。
D11 库 SHA256=`ead75733d45f5b78c086bed9122082d410847eea0ed6b21f8bafab102a1cb0ac`；
D8 库 SHA256=`a04ca88a75c0fd8538f7eb6d3726dfe906b2dfc284cc77c577f2328eb04b23b1`。
实际原产品 src、两个旧实验源码、输入、配置与冻结文档不得改写。

待检假设：更细网格改变实际 HPF/BF 后 mic 的搜索候选；候选满足既有短窗/长窗门限并完成三次确认，
最终 route_jump 经原 pipeline 触发 AEC reset。也可能是非连续确认或观测移植错误，需逐项区分。
单一测量变更：对原公共 API 运行的 ap_sync_track_delay 增加链接 wrapper，
在完整复制的 sync state 上重建本帧 history 和搜索；真实处理仍调用原静态库函数。
记录 actual processed mono，避免直接 raw mic 旁路替代实际 HPF/BF 输入。
诊断唯一峰是否满足仅作观察，不改变大跳分支的既有控制流。

## 冻结样本与测量契约

每版本执行四个原固定臂：

1. rpm240/far-motion `run-2908630469-2466` default。
2. 同场景 sync-default-control：同配置重复控制，不算独立场景。
3. rpm480/double-talk-motion `run-4874838670-2672` default。
4. rpm480/far-motion `run-4823498871-2661` tracked1：D8 消除 172 ms 误跳的既有目标对照。

原全部 adapted mic/render、config、帧数、初始化和 runner 均逐字节不变。
旁路记录每帧的 old/new delay samples、更新资格、coarse/refined、短窗得分、runner-up/uniqueness、
本帧加入 history 后的长窗得分、confirm/candidate 前后状态、实际 observed/route_jump/slips。
最大延迟按原配置 180 ms；coarse_step 按各版本真实 500/1000 除数派生。
copy-state 观测前后真实 sync state 必须 memcmp 不变，且候选误差与原实际 event 精确一致。
长期 CSV 只保存数值诊断，不输出原语音内容；完整工件在独立 /tmp 目录并按 SHA256 绑定。

## 阶段与验收

- P1：冻结输入/源码/库身份，strict warnings 编译 wrapper；确认 linked 原库未变。
- P2：四臂×两版本，observed 与 no-observe 各完整运行，共 16 次。
  所有 output PCM、公开 metrics 必须逐字节匹配原 receipt 和彼此；逐帧 wrapper delay/jump/slips 与公开 metrics 对齐。
  default/sync-default-control 的诊断也应逐字节一致。任一不同，诊断无效，停止结论。
- P3：从实际数值重算事件帧、连续确认与 gate，通过结果总结有限控制流因果链；无真实物理 delay 标签，不判对齐正确/错误。
- P4：独立 whole-change 复审、文档检查、Runtime 收口；形成 reviewing candidate。

预算：一版测量 fixture；只修测量实现缺陷，最多两次修正；不搜索算法/门限/参数。
staleness_threshold：源/库/input/config 任一 hash 变化即 stale 并停止；运行超 120 秒则核任务状态，不能缩短输入洗绿。
heartbeat：阶段完成更新；stop_condition=`pass/replan/blocked/abort`；任何测量不等价固定 `replan`。
claimant=`root`；verifier=`device_capture_independent_review`；required_evidence=计划、身份绑定、16 次等价回执、事件 CSV、独立复审。
初始 open_items=4；plan_completeness=四阶段明确；attestation_readback 必须检查计划及实际工件 hash。

当前 live main=`cc887b0ced20a828ed7148b9ac949f639a1e2868`，fast-code 在读取时 in_progress、summary 尚未出现；
#657 OPEN，开放 PR #695/#696 是独立 Dependabot，不借用主线 CI。immutable approved PLAN 与历史结论保留。
Provider context 返回 route unresolved，无本项目权威知识命中；本轮为仓内 reviewing candidate，未正式归档。
不改产品默认/API、AISpeech、E001，不进行 commit/push/设备写，不以输出能量推导 AEC/人声收益。
