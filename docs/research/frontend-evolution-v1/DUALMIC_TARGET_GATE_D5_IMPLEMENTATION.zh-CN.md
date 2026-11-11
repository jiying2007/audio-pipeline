# D5 target gate 实施说明（尚未执行）

执行前科学合同与小索引的原始字节不变：
[冻结合同](DUALMIC_TARGET_GATE_D5_PLAN.zh-CN.md)、[冻结索引](dualmic-target-gate-d5-input-lock.json)，
冻结提交 84a557868a341adbc8e0338034809bd040d5c992；实时追踪 [#938](https://github.com/jiying2007/audio-pipeline/issues/938)。

## 唯一结构与观测

研究构建从已准入原 D2 archive 内取原 C/header，链接封存原静态库作 baseline。
候选仅删除合同指定的一条 target cap 语句并重命名三个导出函数；不加入 D3 零输入 guard。
当前编译器固定 C11/O2/ffp-contract=off/Wall/Wextra/Werror、AGC 构建定义、原头及库、libm；
系统 cc selector 允许正常 alternatives 符号链接：保存 lookup path、直接链接目标、解析后的真实普通文件及其 hash；
实际 argv 使用真实文件路径，读回重建并核验关系/字节。此例外只用于解析编译器，证据文件仍拒绝 symlink。
路径、hash、版本日志、完整 argv、HEAD/tree 均保存。当前宿主 compiler/libc/libm 不声称等于旧环境。

runner 保存实际 baseline/candidate before/after 的四份完整 12-byte state，以及原 allow/reset/数字零标志。
应用 gain 字段由实际 after state 和输入 peak 重建，随后以 Float32 公式验证完整输出字节；
不是内部变量插桩测量。report 每帧的 raw/bounded/effective target、alpha、target/output/peak/clamp
也明确标为同输入 Float32 公式重建，和实际 state/PCM 及原 D2 gain.csv 对照。
baseline 完整 state 与原 gain.csv 的 gain/target/limiter Float32 和输出原件逐字节一致才评分。

第一次机会定义为原输入 !allow 且 bounded target > 1。流开始/reset 后首次机会帧的
before state 仍相等，其 after/output 可以开始分叉；此前所有 state/PCM 必须相同。
全 allow=true 的视图及 near-only/silent-render 全控制必须相等。
candidate allow=0 的应用 gain 不得超过 unity；每样本输出/peak/clamp 均审核。
这测量 target gate 删除的总效应，含同帧及 alpha 分支中介，不是纯延迟历史贡献。

## 准入、闭包与边界

小 D5 JSON 不是完整原件准入锁。driver 显式 pin 原 D3 完整 input-lock/plan、原 admission、
D1/D2/scorer/全部实际 Python 依赖的 Git blobs，复用未修改的原 D3 ZIP/完整 D2 读回准入器。
保存原 D3 admission 和原 D1/D2 报告/manifest，并逐阶段核验原件绑定。
保留依赖包括 device_alignment.py 与 tools/codex_assets/__init__.py；
运行时检查每个仓库内已导入模块属于封存集合。源文件与空目录均须完整闭包，源上限16MiB、
结果上限256MiB，不接受 symlink、额外文件/目录或重封存后的源替换。

C 自测覆盖两 profile、五个合法 gain 初值、allow0/1、zero/signedzero/tiny、
有声和 peak 输入、NaN/Inf 拒绝、原 allow=true 状态方程、无机会历史与 reset。
Python 自测覆盖变换、算术/输出保护及既有目录/回执和 symlink 不可覆盖。
实际负例先完整验证未修改的原证据，再对 PCM、完整state、gain/control、target/alpha、
窗口、漏case、null、源/tree/argv、额外文件目录、失败回执和原输入绑定做预定篡改。
报告与源码部分负例重新封存，只有每项指定拒绝理由才算通过；I/O/timeout/其它异常为 FAIL。

全部60共同跨度/362原固定窗口都使用原 canonical scorer，不搜 lag、不归一化、不选窗。
保留两臂全部 RMS/peak/energy/null 与原电平，far-only/path-change/render-gap/中文不丢失。
32有 clean-near 与28无参考维持原角色；近端 SI-SDR 的符号不决定科学资格。

每阶段含最终写盘300s，每子进程最多30s，总 job20min，不能失败后放宽。
独占 /tmp/ap-dualmic-d5/result；每阶段只能新建自己回执，不修复或覆盖旧成功/失败。
读取验证不重新执行 DSP。负例复制实际原件至一次性隔离目录，原件不改。

## 现有 CI 接线

只在原 Frontend Research workflow 增加一个 scoped D5 job。D5-only 改动逐字节检查旧
D1/D3/D4 job 区域，历史研究 lane 不执行。checkout/upload action 使用原 pinned SHA；
产物在 checkout 外，始终上传首次失败及完整 D5 结果，原 D2 ZIP由固定 artifact 身份独立保存。

命令依次为 driver 的 build/run/analysis/verify，固定 input/result 路径；
最后执行 test_dualmic_target_gate_d5.py 的实际证据负例。
当前文本和源代码是实施候选，不是已构建、已执行或已获得效果结果。
只有独立精确 head 审查后才可打开触发实验的 PR；最终工程资格还需要 exact-head Verify、
保护合并及 fresh-main 全部适用门禁。无 production DSP/default/API/version 变更，
无新模型、私有数据、真实硬件、听评或 ASR/KWS 效果结论。
