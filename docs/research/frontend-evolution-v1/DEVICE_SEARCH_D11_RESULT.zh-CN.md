# D11 搜索几何候选结果：工程获取改善，开发回放拒绝

日期：2026-10-10；experiment=`FE_DEVICE_SEARCH_D11`；[冻结计划](DEVICE_SEARCH_D11_PLAN.zh-CN.md)。
最终决定 **REJECTED_DEVELOPMENT_COUNTER_REGRESSION**；selection=`REJECTED`；
`promotion_allowed=false`、`shipping_approved=false`。
候选修复了本轮固定已知延迟矩阵，但真实开发数据的两个场景出现新增跳变/重置，违反冻结硬门禁。
没有真实延迟标签，不能把新增事件解释为正确对齐，也不能直接证明其物理对齐错误；拒绝依据是预先冻结的稳定性规则。
D9 BASELINE_FIXTURE_LIMIT、D10 工程诊断和 D8 INCONCLUSIVE 均保留，不调整参数或验收洗绿。

## 唯一改动与工程证明

基线为精确 D8 源码，唯一算法改动是 coarse_step 的除数 500→1000。
coarse 网格、refine 半径、uniqueness guard 与确认容差由同一变量派生，同步约 2→1 ms。
原相关门限 0.0324、峰值比 1.01、三次确认、20 ms 大跳界限、D8 40 ms gate、漂移与 AEC 均不改。
[增量研究 patch](../../../.github/research/frontend-evolution-v1/device-search-d11.patch) 仅对精确 D8 独立副本使用，
`git apply --check --unidiff-zero` 与实际独立重放均通过，重放源码逐字节等候选。
实际产品 `src` 未改，候选仅位于 `/tmp/audio-fe-device-search-d11-20261010/source`。

原 strict CTest **14/14**，原 D8 直接 SYNC engineering 与 public recovery 均通过。
[唯一峰 oracle](../../../tests/validation/frontend_evolution/device_search_d11_uniqueness.c)
通过 **21,618** 项全列举对照，最大排除点数为 3。
网格与 guard 同步缩小，使闭区间最多排除三个 coarse 点，原 top4 充分性证明结构保持成立。
这些是工程功能/正确性结果，不是独立声学验收。

## 已知延迟：100 固定用例与一次重复

使用字节不变的 D9 public API fixture，每个候选输入逐字节匹配 D9 保存输入。
100 个 CSV 的 frame 集合、capture 数、first、last20、final 与 counters 已重算一致。
指定 16 kHz/seed1/acquire/7 ms 新进程重复的输入、输出、CSV 均逐字节一致。
原 D8 baseline 不重跑，读取其已锁定结果；验收仍为最终 20 个 capture 帧全部在真值 ±3 ms。

| Mandatory 组 | 数量 | 原 D8 通过 | D11 通过 |
| --- | ---: | ---: | ---: |
| 无噪宽带 1 ms，acquire/switch | 8 | 0 | 8 |
| 无噪宽带 7 ms，acquire/switch | 8 | 0 | 8 |
| 无噪宽带 80 ms，acquire/switch | 8 | 8 | 8 |
| 已通知 capture gap 后恢复 80 ms | 2 | 2 | 2 |
| 合计 | 26 | 10 | 26 |

无缺帧宽带 acquire 在生成器第 39 帧首次进入目标，switch 在第 149 帧；已通知 gap 为第 160 帧。
未通知 gap 两例仍保持 40 ms，0/20，不把超配对契约的保持解释为正确恢复。
诊断主矩阵宽带/周期/低参考各为 24/24，合成双讲仍为 **0/24**；不能外推真实成功率或双讲能力。
固定 1/7/80 ms 是已查看 development 工程输入，不代表任意非网格延迟、room 或独立验证。

## 真实开发回放：触发拒绝

原 tests/audio 119 文件锁、16 例 70 固定臂+2重复实际执行，原 receipt verifier 通过。
适配后的 mic/render、全部配置与 D8 byte-exact 相同；实际构建库与 replay receipt 库也逐字节匹配。
34 个关闭 tracker 的控制臂 PCM/metrics 全部逐字节相同；全部 70 臂中 42 相同、28 改变。
同配置 default/sync-default-control 在候选中逐字节等价。

| 新增事件场景 | 执行臂 | D8 jumps/resets | D11 jumps/resets |
| --- | --- | --- | --- |
| rpm240/far-motion，run-2908630469-2466 | default | 0/0 | 1/1 |
| 同一场景、同配置重复控制 | sync-default-control | 0/0 | 1/1 |
| rpm480/double-talk-motion，run-4874838670-2672 | default | 0/0 | 1/1 |

comparison 的 6 个 counter 条目对应 **3 个执行臂、2 个采集场景**，不是六个独立场景。
这已足够触发 REJECTED；未根据新增延迟接近合成真值而放宽现场门禁。
所有固定臂的最终 counters、delay 集合及变化臂窗口 RMS 均已从实际文件独立重算。

指定 rpm480/far-motion tracked1 仍没有 172 ms 跳变，jumps/resets 仍为 0/0，
delay 集合由 D8 的 1/2/3 ms 变为 0/1 ms，slips 从 48→29。
19–21 s 输出 RMS 为 -29.914745→-31.743109 dBFS，变化 -1.828365 dB。
触发拒绝的 rpm240 far-motion default 同窗口变化 -6.037657 dB，
rpm480 double-talk-motion default 变化 -3.708599 dB。
RMS 下降无法区分残回、人声与噪声，不能覆盖新增 jump/reset，也不能宣称 ERLE 或人声保真收益。

## 资源与实际身份

完整 state=**78,840 bytes**，与 D8 相同；原 ceiling=80,000，余量 1,160；无新增状态成员、malloc 或 TLS。
Host 静态库各对象合计 ELF text=58,936、data=176、bss=0 bytes，与 D8 相同；库字节不同。

| rate / max delay | 原短窗 coarse+refine score 次数上界 | D11 上界 | 比率 |
| --- | ---: | ---: | ---: |
| 8 kHz / 100 ms，冻结验收 | 84 | 118 | 1.405 |
| 16 kHz / 100 ms，冻结验收 | 116 | 134 | 1.155 |
| 8 kHz / 180 ms，额外静态诊断 | 124 | 198 | 1.597 |
| 16 kHz / 180 ms，真实回放默认配置 | 156 | 214 | 1.372 |

两版本在合格的大跳分支另最多调用一次既有 40 ms history score，stride4 对应 8/16 kHz 的 80/160 个评分点。
以上仅为静态调用上界，调用成本不同，不是 Host 实测 CPU，更不是 SSC305 p99、RSS、stack、热或功耗资格。
未用体积不变推导运行代价不变。

| 证据 | SHA256 |
| --- | --- |
| 冻结计划 | `4009c6bebc9ee1680b83c41170b1152e340492b3a12d2fba94c2dcd170a8bca6` |
| 增量 patch | `3a10fc32923b977526ac1f86245fb4284979323fab244f1ccba269badae65eab` |
| 唯一峰 fixture | `5af46731c035eb04bfbaca8248850f68941078318866be31e476ca5e8e09ddb7` |
| 工程 result | `6214598616548154d1782bd83b70a4c912375979a7233d5174bae4d4790c4706` |
| 工程 binding | `0970bf49ac67fa22e5ebb895007152c938fe6e853f99714bcb017d085aba7545` |
| 实际候选库 | `ead75733d45f5b78c086bed9122082d410847eea0ed6b21f8bafab102a1cb0ac` |
| 真实回放 receipt | `e5ddd8ccd8b56dfa33aa7f8ddf6a63185e55a6f1973fe2fc15dc67e5acb4c0b3` |
| 真实 comparison | `c7200d891a539ecff3566ebfa9129d65fe254edbae8eb6590432a951de3e7db5` |
| 最终执行 binding | `6e17559d027df08f29c7a38e9194488811a09d4a8725d463752cb146d1d9eb5c` |
| 后续静态资源补充 | `bdd99e436199e4c6d33b7e515f040a19a29424c407adb8de748235808ccb84d6` |

上述实际工件位于 `/tmp/audio-fe-device-search-d11-20261010`，原工程/最终执行 binding 均未覆盖。
本文件为持久摘要，临时工件可用性不代表长期归档。原 first-party replay 工具未修改，不建立第二声学评估器。
下一阶段先对两次现场新增事件作有限时序/候选证据鉴别，真实对齐真值和人声标签另行采集；
没有这些证据，不放宽本轮稳定性条件或宣称更细网格可部署。
产品源码/default/API、AISpeech、E001 不改变，无 commit/push/设备写。
Provider route unresolved，记录为 reviewing candidate，未正式归档；独立审查见 [D11 复审](DEVICE_SEARCH_D11_REVIEW.zh-CN.md)。
