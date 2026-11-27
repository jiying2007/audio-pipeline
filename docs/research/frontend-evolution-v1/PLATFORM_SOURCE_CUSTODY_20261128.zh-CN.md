# 本轮科研源分支的持续保管登记

日期：2026-11-28（北京时间）。这是最终集成关闭中间 PR 前的具体来源保管要求，
不代表研究结果晋级或尚未发生的 main 验收。

现有 `scripts/research_registry.py` 在 scheduled live inventory 中，对不在 registry
且没有开放 PR 的 `research/` 来源报 `BLOCK_UNREGISTERED_LIVE_REF`。因此不能在
关闭 #971 或合并 #973 后留下新的未登记源分支。继续使用原规则与原 registry，
不新增清理框架，不删除任何来源。

本次只追加两个记录：

| 分支 | 保管状态 | 身份与含义 |
| --- | --- | --- |
| `research/aec3-platform-20261128` | `ACCEPTED`，两项 GC 标志均 false | 实际重新读取的固定 head `cbddb82cb849e9fa454227f1995efb07ad4a7bf5`；接受为已完成描述性参考的来源锚点，保留实际执行 `819849ee`、成功/失败及无晋级结论 |
| `research/source-simulation-preparation-20261128` | `ACTIVE`，两项 GC 标志均 false | 持续集成来源，`head_sha=null` 明示仍会移动；记录实际观察 `c7baccb8` 和已经执行的 `a058b025`，不假造未来最终 head |

`ACTIVE` 指父研究 #657 和可复验源保管仍有用途，不等于永远存在待合并 PR。
每次实验的确切 source/hash 继续由各自冻结合同与结果记录负责，移动分支名不能替代
这些不可变身份。后续关闭 PR 不授权删除此分支。未来若要终结其保管责任，应另行
核对最后 live SHA、完整依赖和证据留存，再按原生命周期规则处理。

旧 84 个记录、policy、active dependencies 及两个 GC 候选集合均原样保持。
原 registry validator/self-test 和追加前后差异比较通过；只读库存复验在最终合并、
关闭来源 PR 后继续执行。没有改变历史科学判定，也没有提前宣称 protected main 成功。
