# D49 新 C 实现与私有自检记录

2026-10-15，experiment=FE_DEVICE_MAGNITUDE_LOWER_BOUND_D49。承接原 PLAN=e8ffa4a9db2165b80f036c4791fdf1af6b7ca5215a7cc2daec47d8e8d2cbb119、AMENDMENT=9e7ddaa0e82d434f3d2addc631d878562c35719a21bb03e98dcf7a810ec87a65 与独立计划审查=772cfe8f5328eee065fcb47ccf0d13b19c750c0ca9eb262d68569e8576d0d06d。本记录仅覆盖新 C 分支和私有自检，不是完整 IMPLEMENTATION 冻结，不放行正式矩阵或声学候选。

## 已落地范围

新增 `device_magnitude_lower_bound_d49.c/.h` 和 `device_magnitude_lower_bound_ns_d49.c`，原 D47 三文件保持。NS 逐字对照确认除预期 include、函数命名与 floor 调用变更外完全一致。原 raw P/J 及有限检查保持；新的 L 使用 double sqrt(P)、hypot(pr,pi)、有符号差，差<=0 时直接正零，仅正差平方。严格 L>2N 与 L/P 共同采用同一保护量。预测操作数按原顺序重算，增加的 double 计算开销尚无目标板性能证据。

原噪声/EMA/count/reset、NS/RES 及 post-NS max 位置不变；power21列、bins25列、current_innovation_sum 原 J 和 overshoot 诊断保持。新增 known answers 覆盖等幅反相/正负虚相位、过预测、P0/J正、确定幅度差、严格2N及相邻double、warmup/退化和非有限输入。observer-vs-NULL、pre-update noise、post max、快照计划等原研究自检保留在新分支中执行。

新增 `tools.codex_assets.device_magnitude_lower_bound` 私有入口及两个阶段共四项定向边界测试。当前入口只提供 help、只读 dry-run、一次固定私有根 compile/selftest/invalid-argc；未实现正式矩阵。私有根 `/tmp/audio-device-d49-c-selftest-v1` 与正式根 `/tmp/audio-fe-device-magnitude-lower-bound-d49-20261015` 严格分离。

## 审查修复与实际验证

独立 reviewer=device_capture_independent_review 先确认核心公式和单因果范围，发现1项执行前 MINOR：子命令启动失败/超时时，旧草稿只保存总错误，丢失本次尝试的子命令证据。未运行有缺陷草稿的 C 验证。修复后每次尝试均先保存 command/cwd/PID/started/exit/terminal/stdout/stderr，再判断；独立 session/process group，超时 SIGKILL 及剩余预算内回收，未观察到终态保持 unknown。单命令总预算120秒包含最多5秒回收余量，没有增加预算。

实际验证记录：

- 非仓库 cwd=/tmp help 与 dry-run 均 exit0；dry-run 只读、不创建私有或正式根。该 dry-run 先于异常证据修复，不冒称是最终 tool 的全量验证。
- 原两项根边界/排他写保护单测：ced138，exit0，2 tests。新增启动失败和真实进程组超时回收两项单测：da66d6，exit0，2 tests，0.306秒。原成功测试未重跑。
- 修复后 fresh 独立复审 Spec/Quality/Independence PASS，MINOR closed，unresolved0，仅放行一次私有 compile+selftest/invalid-argc。
- 唯一私有实际执行 eac53b，外层exit0；receipt 内总耗时0.8531126631423831秒；compile PID3637000 exit0，selftest PID3637008 exit0且实际 D49_SELF_TEST_PASS，invalid-argc PID3637010 exit2；三者 terminal=true、timed_out=false。source_end_verified=true，起止身份相等。

私有 intent `/tmp/audio-device-d49-c-selftest-v1/intent.json` SHA256=9e0f47e10d0aaefade22d011dad684ce6a38664f9e970be7d8db742c7d9ee538；receipt 同根 `receipt.json` SHA256=930ff37d927d11862411d8a2739d00611a9c5b1224a0584e8341319d2a916019；runner SHA256=053b5201657075098d2814d7559c72b8fbf36b466ae9b9f5a0722d7c313bed1e。实际回执独立回读另行附核，不以静态审查替代。

后续实际附核已返回：独立 reviewer 只读检查 intent/receipt/runner，核三命令/cwd/实际0/0/2、终态、11项来源起止及当前SHA一致；限定范围 Spec/Quality/Independence PASS，unresolved0，未重跑任何命令。该附核仍不批准正式矩阵或声学准入。

当前执行源身份：

| 新文件 | SHA256 |
|---|---|
| C | fbcb151d7543fdb3e2d006aa9670ffc8233cb331d0da75c2d6aa1da10fae0dd9 |
| header | 727c80d5474ad1d73504a4ae71ac8249ad2e8707d01a8cdd4ec6d25f83d0e4e4 |
| NS | 92d142c7a409412937f5bf5266e1b9c495460ae7079754377f56889d0bad5618 |
| tool | 7d2845003b3a107e41b3a582d0ab77648508b8b6cd06f77dde5d1d68c2b74a1e |
| tests | af1318f929adbed5a44ff52d007c4524396889cce8eab78e90831e600647637b |

## 继续工作与保留边界

下一步新增正式矩阵控制，literal pin D48 tool/test、D47 C/NS/header及真实结果/closeout链，完整合并原11744输入、1884工件与13671最终快照，冲突拒绝。冻结 D48 observe 和原 D42 development_admission，原184路/505944帧、960组、24near/72no-near/4pureecho准入及各预算不变；完整实施、负例和控制审查后才唯一创建正式根。之后独立全量审计、whole、最终快照和本地收口仍未执行。

本轮私有自检不是全依赖图正式 preflight、完整声学回放、目标板 CPU/实时性、AISpeech/QIVW、真人 ASR/KWS、HIL/E001 或至少72小时 PQ 证据。promotion_allowed=false、shipping_approved=false；D49任务及总体目标继续active，result/review证据仍缺。

恢复时确认上次 native request1792077322464 已发送并受理，120.42749704886228秒内未证实完成，实际精确进程列表为空；旧 receipt 保持 ACCEPTED_COMPLETION_UNVERIFIED。三文件 SHA：intent=1a26cdd030f451b0751d36de521bb16c0104adb51cc62b7a72c6d56bf054680c、accepted=90e61f9f88639d8db70e40fbe04439530e9ac282a0c52e3e5aed12bf36ec7b57、compact=0f114b04a78970d8aaa5be3a7b9eb0d9ab4716337cb89390837ce0d3e95e92c2。最新策略 required=false、recommended_action=continue，已恢复业务，不重发或循环轮询。

fresh main仍6fafcc868c5d3a0c4aa328e3d6ab54109cf5a741，67success+1skip；新增open研究PR763/head95b7c2cdedf8221ba436ef0d7cc0b510d6cc7e15，714/695继续open；最新制品11985117017/11985047143属于PR763而非D49。#657继续OPEN。Provider再次返回WORKSPACE_UNBOUND/route unresolved、execution_subject=null，因此知识NEEDS_REVIEW、未归档成功；不采用无绑定的 discovery 条目。本地原5项tracked dirty保留，无commit/push/PR/merge/release或设备写。
