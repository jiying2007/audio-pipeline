# D9 独立复审与交付边界

日期：2026-10-10；reviewer=`device_capture_independent_review`；independence=`independent`。
对象：[冻结计划](DEVICE_ACQUISITION_D9_PLAN.zh-CN.md)、fixture、[结果](DEVICE_ACQUISITION_D9_RESULT.zh-CN.md)、中文入口与实际工件。
whole-change verdict：**Spec PASS / Quality PASS**，仅覆盖测量实现、证据一致性和失败披露。
未发现 blocker、major 或 minor；contract change=`none`。
算法工程决定仍为 **BASELINE_FIXTURE_LIMIT**，D8 选型继续 **INCONCLUSIVE**；
`promotion_allowed=false`、`shipping_approved=false`。审查通过不表示 26 个 mandatory 获取检查全部通过。

## 冻结身份与独立核验

快照 `review-snapshot-v2.json` SHA256=`7fe6427fbb8280b8061e61d90f96b611b35066403c635123df6f00a070ca3652`，
位于 `/tmp/audio-fe-device-acquisition-d9-20261010`。
审查起始和结束时，4 个持久文件与 4 个冻结工件 hash 全部匹配，未 stale。

| 独立核验 | 结果 |
| --- | --- |
| 原始 binding | 615 项实际 artifact hash 全部匹配，原绑定保留 |
| Processor 身份 | 各 56 个构建相关源码匹配 D6/D8 receipt；版本差异仅为冻结 `ap_sync.c/h` |
| 静态库 | 各自 byte-exact 匹配对应 receipt；候选 strict/replay cache 差异明确 |
| 实际输入 | 100 对逐字节一致 |
| 指定重复 | 两版本各一次，输入、输出、CSV 均与各自首次执行逐字节一致 |
| 已知因果输入 | 独立 float32 重算 76 例、2,736,000 个 mic 样本，不匹配数为 0 |
| Metrics | 从 200 份实际 CSV 独立重算帧集合、capture 数、first、last20、final、counters，全部匹配 |
| 分类与结果 | 26 个 mandatory、16 个 baseline limits、0 个指定相对硬回归及全部诊断差异一致 |
| CLI 负例 | 两版本无参数及非法 repeat 共 4 次调用，均在初始化前拒绝，exit 2、输出为空 |

附加 CLI 负例工件 SHA256=`12d35bfabe20ac8121a4c308ca82c399481b4573dfdcccb6fb013cef279d8e7f`。
该核验不重跑有效矩阵、不改变冻结验收。

## 失败保真

两版本均仅通过 10/26 mandatory：80 ms 宽带 8/8，已通知 gap 2/2；
1 ms 和 7 ms 各 0/8，16 个共同失败的末窗全部为 0/20。
16 kHz/seed2/acquire/1 ms 的基线最终 10 ms、候选 40 ms，仍均不达标，已完整披露。
未通知 gap 两例中基线最终 80 ms/20 个末窗达标，候选 40 ms/0 个末窗达标；
它们保持 diagnostic 身份，不能被解释为候选恢复成功或物理对齐正确。
合成双讲 0/24、周期及低参考各 8/24 的诊断计数亦保留，不能转换为真实音质或成功率。

coarse/refine/三次确认可作为下一项有限观测方向，当前根因尚未证实。
不能由零指定相对回归数推导批准，不能修改时长、容差或门限洗绿。
独立审查者只读，未写文件、未 spawn、未提交或访问设备。

## 根代理定向检查与范围

Python 3.10 执行 `scripts/docs_consistency.py --self-test`：exit 0；
实际 `scripts/docs_consistency.py`：exit 0/PASS；`git diff --check`：exit 0。
本轮仅增加研究 fixture 与文档，不改变产品 processor、默认参数、公共 ABI 或 shipping 构建。
本地 Runtime 门禁由根线程另行绑定和执行，不能从本文件的独立审查 PASS 推导其状态。

收口读取 live main=`f05eecb69ab5ac1a0968381f109510c939b53e50`；
tracker #657 OPEN；其他 open PR #704/#696/#695 分别保留自己的范围。
该 main 的 summary/release/convergence 成功，但 gc 失败，不声明线上全绿。
main 检查不能替代本地未提交 D9 快照的验证，未执行 SCM 写或清理。

Provider route unresolved，仓内记录仅 reviewing candidate，未声明正式归档。
D9 为已查看的合成 development 工程测量；真实声学、render 时轴、SSC305 资源、HIL、E001、
owner、shipping 与 PQ 仍分别验收。下一阶段先冻结失败例内部观测，再决定因果修复。
