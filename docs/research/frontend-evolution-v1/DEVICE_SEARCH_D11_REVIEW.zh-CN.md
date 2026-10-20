# D11 独立复审：执行记录通过，候选拒绝

日期：2026-10-10；reviewer=`device_capture_independent_review`；independence=`independent`。
whole-change：**Spec PASS / Quality PASS（执行、测量与拒绝记录）**。
未发现 blocker、major 或 minor。候选决定独立保持 **REJECTED_DEVELOPMENT_COUNTER_REGRESSION**，
selection=`REJECTED`；`promotion_allowed=false`、`shipping_approved=false`。
审查通过不能批准已触发冻结失败条件的算法候选。

## 冻结对象与身份

对象：[冻结计划](DEVICE_SEARCH_D11_PLAN.zh-CN.md)、[结果](DEVICE_SEARCH_D11_RESULT.zh-CN.md)、
README、增量 patch、唯一峰 fixture 与五份实际工件。
快照 `/tmp/audio-fe-device-search-d11-20261010/review-snapshot-v1.json`，
SHA256=`0938b856a5d98443fff5d6e85ce4c8226f70fb0066caef3c9e86ce1d19ee8c79`。
独立审查起始与结束核验的五个文件、五个工件 hash 全部匹配，未 stale。
本复审记录由根代理在收到最终独立结论后补写，不属于该快照的被审文件。

## 独立核验结果

| 核验 | 证据结论 |
| --- | --- |
| 唯一算法参数与 patch 重放 | coarse_step 除数 500→1000；实际重放源码逐字节等候选 |
| 原工程门禁 | Strict CTest 14/14，原 D8 engineering/recovery 均通过 |
| Top4 oracle | 21,618 项通过；最大排除点数 3；网格与 guard 同步缩小保持证明前提 |
| 固定已知延迟矩阵 | 100 份 CSV 重算一致；mandatory 26/26；输入和指定新进程重复逐字节匹配 |
| 原开发回放 | 独立 receipt verify 通过；16 例、70 固定臂、2 次复跑 |
| 对照及差异 | 34 个关闭 tracker 控制相同；42/70 臂相同，28 改变；变化窗口 RMS 从实际 PCM 重算 |
| 新增 jump/reset | 六个 counter 条目对应三个执行臂、两个采集场景；触发冻结拒绝条件 |
| 状态与资源 | state 78,840；ELF text/data/bss=58,936/176/0 bytes；四组静态调用上界与结果一致 |

rpm240/far-motion 的 default 与同配置 sync-default-control，
以及 rpm480/double-talk-motion 的 default，其 jumps/resets 均由 0/0→1/1。
同配置重复控制没有被算为独立场景。缺物理延迟真值，无法判断新增事件的对齐正确性；
稳定性硬门禁已经失败，足够拒绝候选，不以 RMS 下降抵消失败。

已知延迟 26/26 只证明固定 development 工程用例改善；诊断双讲仍为 0/24，
未通知 gap 两例仍保持 40 ms。目标 tracked1 的 slips、delay 集合及 RMS 变化如实披露，
没有推导 ERLE、人声保真或真实声学收益。D8 INCONCLUSIVE、D9 baseline limit、D10 有限诊断均保留。

资源核验区分 100 ms 冻结验收与 180 ms 静态诊断；两版本另最多执行一次既有长窗评分。
调用次数与 ELF 体积不是 CPU、p99、RSS、stack、热、功耗或 SSC305 部署证据。
独立审查只读，未修改文件、提交、spawn 或访问设备。

## 定向检查与收口边界

根代理实际执行 Python 3.10 `scripts/docs_consistency.py --self-test`：exit 0/OK；
实际 `scripts/docs_consistency.py`：exit 0/PASS；`git diff --check`：exit 0。
Runtime 绑定与 final 门禁另行执行，其结果不由本审查推导。
产品源码、默认配置、API、AISpeech 和 E001 未修改，无 commit/push/设备写。
Provider route unresolved，仓内文档为 reviewing candidate，未正式归档。

恢复入口：先读 RESULT 与绑定工件，对两个现场新增事件作有限时序和候选证据鉴别，
独立获取实际对齐真值及人声标签后再冻结新实验。不得改本轮门限、时长或失败结果来洗绿。
本地主机、main CI、Runtime conformance 不能替代 SSC305、独立声学、HIL、E001、
owner、shipping、PQ 或 Provider 资格。
