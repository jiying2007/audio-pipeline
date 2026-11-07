# D1 首次 Verify 分类失败与精确接线修正

日期：2026-11-07（Asia/Shanghai）。保留原失败，不修改其 run、结论或 D1 原件。

## 实际失败

head `31b949c14d473fe8221a4125adf896a75e785644` 的
[Verify 42318230264 / attempt 1](https://github.com/jiying2007/audio-pipeline/actions/runs/42318230264)
在 impact job `128236092447` 被版本分类拒绝：

`release-bearing change must advance SemVer: base=2.3.63 head=2.3.63`

唯一被列出的路径是 `tools/codex_assets/dualmic_stages_build.py`。因此 fast-gate 和
required summary 失败、下游矩阵跳过，不能称此 head 完整 CI 通过。
同 head 的独立 Frontend Research `42318230362/a1` 已实际成功，D1 完整原件有效；
两种结论不互相代替。

## 最小修正与独立审查

构建 helper 只在隔离副本内生成 host 研究处理器，生产 src/include/examples/cmake
与 4daa7e2 逐 blob 不变；没有 SDK、API/ABI、默认算法或安装物更改。因此按已有
研究 helper 的规则，将这个**精确文件**加入 `DEVICE_RESEARCH_FILES` 的 SemVer-neutral
集合，保持 2.3.63；不使用目录 glob、不豁免其它工具或质量门槛。

新增“该 helper 单独修改也必须 full Verify”的自测初次发现原有通用 tools 分支只
选择 targeted C/performance checks，本地新增断言失败。修正方式是在既有
`tools/runner_preflight.py` 的精确 full 分支中增加本 helper；没有改变通用 tools
或未知路径的默认分类。随后完整 ci_impact 自测 29 项通过。

独立审查把原 HEAD 与修正文件分别载入内存，对全部 tracked paths 及相邻未知
负例共 2,703 路径比较：SemVer 与非 force 的 CI 选择变化都仅限本 helper；forced-main
和 empty-diff 行为完全一致。helper 的 full/audio/quality/resource/extended/ABI/
ARM/composition 均开启；相邻未注册工具仍要求 SemVer，其旧 targeted 行为不改。
未增加算法参数搜索，旧 run_tuning 选择规则保持。

修正 `scripts/ci_impact.py` SHA-256：
`bf12a76ed4dc42c1dbeae5f6072eab8112ede3275d7522d9be835e7c978559b6`。

该修正已获独立静态 PASS；必须由新 head 的真实完整 Verify、required summary、
研究工件及合并后 main 验证收口。它不改变 D1 测量实现、旧输入、声学阈值或预算。
