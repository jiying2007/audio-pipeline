# D10 独立复审与工程决定

日期：2026-10-10；reviewer=`device_capture_independent_review`；independence=`independent`。
whole-change：**Spec PASS / Quality PASS**，覆盖冻结测量实现、证据一致性与有限诊断披露。
未发现 blocker、major 或 minor；contract change=`none`。
决定=`ENGINEERING_DIAGNOSTIC_SEARCH_COVERAGE_LIMIT`；不批准 D8 或下一算法修复。
`promotion_allowed=false`、`shipping_approved=false`。

## 冻结快照

对象：[计划](DEVICE_TRACKER_D10_PLAN.zh-CN.md)、[结果](DEVICE_TRACKER_D10_RESULT.zh-CN.md)、fixture、README 与实际工件。
`/tmp/audio-fe-device-tracker-d10-20261010/review-snapshot-v1.json`
SHA256=`ff49414499ee796686c054a300341f324b59f8cea1e26fb6083e811f237bfda5`。
审查起始与结束核验的 4 个文件及 2 个工件 hash 全部匹配，未 stale。
实际源码、生成头、输入、编译/运行回执、计划、fixture、编排和工件绑定也全部匹配。

## 独立证据核验

旁路 coarse/refine 在实际 tracker 更新前调用原 static score，使用原比较与搜索顺序，
观测前后整个 state byte-exact 不变。D8 history 在原 tracker 已追加当前 mic 后读取，亦不修改状态。
从 14 个实际 CSV 重算全部 result 行，并核对 4,200 帧 delay_ms、累计 jumps/slips
与 D9 公共 API CSV 逐点一致；D9 resets 全部为 0。

| 固定观察 | 独立结果 |
| --- | --- |
| 每版本五个短延迟输入 | 145 个搜索 epoch |
| refine 排除 true-lag | 每版本 137 次 |
| refined 精确命中真值 | 每版本 8 次 |
| true-lag score 最低值 | 0.999985039 |
| 真值 route jump | 0 次 |
| D8 正确大跳候选长窗拒绝 | 0 次 |
| D8 非真值候选长窗拒绝 | 28 次，按原 gate 前提过滤 |
| 两个 80 ms 正例 | 每版本 58/58 精确命中，均第 39 帧正确 route jump |

基线 6 次正确大跳命中与 D8 的 8 次正确大跳命中未完成三次确认；
基线 seed2 另外两次真值命中属于 small/uniqueness/drift，文档正确区分。
独立直接核验基线 seed2 第 79/89/99 帧 refined 为 158/163/169 samples，
细化区间均为 128–192，真实延迟 16 samples 被排除；原确认器接受首次候选 158 samples，即 9.875 ms。
后来真值命中时旧延迟 160/161 samples，确实属于小偏差路径。

这些证据确认的是这 137 个已观测 epoch 的搜索覆盖不足及已披露的确认/漂移行为。
它们不覆盖全部 D9 失败、switch 或真实声学；D9 BASELINE_FIXTURE_LIMIT、D8 INCONCLUSIVE 均保持。
后续 top4/guard 证明约束的说明符合原代码适用前提，不能未经验证改变搜索间距后沿用旧上界。
独立审查者只读，未修改、提交、spawn 或访问设备。

## 定向检查、连续性和下一步

根代理 Python 3.10：`scripts/docs_consistency.py --self-test` exit 0；
实际 `scripts/docs_consistency.py` exit 0/PASS；`git diff --check` exit 0。
本轮新增测量 fixture 与中文文档，未修改产品 processor、参数、ABI 或默认构建。
根线程 Runtime 门禁另外绑定和执行，不由独立审查 PASS 推导其状态。

收口时读取 live main 仍为 `025e266c2ade3a1923ae10f5c8759ee49a437ea5`。
此前针对该 SHA 的 check-runs 读取为空，未借用上轮主线 CI；#657 继续 OPEN。
当前冻结实验身份仍是 D6/D8，线上最新源码与本地研究身份分别记录。
未执行 SCM 或设备写；Provider route unresolved，仓内记录为 reviewing candidate，未正式归档。

恢复入口：先读 D10 RESULT 和上述 bindings，再冻结单一搜索覆盖修复的独立计划。
验收至少分开覆盖：已知延迟获取、连续确认/误跳保护、uniqueness 证明、资源代价与真实回放不利变化。
不可用本测量与修改后的同一实验互相批准；不改 D9 门限/时长/历史失败，不把 development 变为 blind。
SSC305、声学、render 时轴、HIL、E001、owner、shipping 与 PQ 保持独立。
