# T1-M3：dEchorate 的历史来源与当前事件范围

## 本提交的有限权限

这是 [#759](https://github.com/jiying2007/audio-pipeline/issues/759) 于
2026-10-20T06:39:12Z 补充登记的第一阶段：只提交未接入工作流的来源验证器和离线
真实 Git 负例。从 `b80d819a486cb973e6a60b4fdf259803d45ec3f0` 开始，三个研究
workflow、原科学脚本、两份原 manifest、科学数据和判定规则均未修改。
既有 docs-gate 只新增本验证器的离线 self-test，不调用公网，不跳过任何科学 job。
Verify 的 fast-docs checkout 补齐 `fetch-depth: 0`，与原 fast-code 一致，确保共享
离线测试取得真实 Git 历史；不把浅克隆中的缺失对象替换为合成历史或省略该测试。

`dechorate_event_source_t1m3.py` 成功时只能给出
`T1_M3_FROZEN_SCIENCE_EVENT_RANGE_QUALIFIED_NO_EXPERIMENT_RESULT`。
`source_range_qualified=true` 表示来源和本次事件范围吻合；所有收据始终保留
`scientific_experiment_executed=false`、`acoustic_pass=false`、
`corpus_materialized_or_verified=false`、`skip_measurement=false`、
`automated_bypass_enabled=false`、`maintenance_push_admitted=false`、
`workflow_hookup_admitted=false`、`m1_m2_prerequisites_closed=false`。
它不产生 `SCIENTIFIC_EXPERIMENT_RUN_AND_VERIFIED`，也不产生任何 push 维护豁免。

## 已复现的具体缺陷

原 `Bind diagnostic to exact source and research-only scope` 同时把
`cb85d2bbffa2e1ac6d6f0a48a66619062b726cc0` 当作历史实验祖先和当前改动范围的起点。
`cb85...HEAD` 因而把此后主干的其他开发也算进一个仅有三个路径的 allowlist。
本地正控制在真实仓库历史上新增了来源策略和一个仅改现有 workflow 的事件：旧比较
实际得到 1,194 个路径并拒绝，而本次 PR base/head 只修改一个 workflow。
测试分别建立真实的两个父提交 PR 合成提交和一个父提交主干 squash；两种当前范围
均通过独立来源检查。此处的 Git 提交和元数据是明确标记的工程 fixture，未伪称
GitHub 上发生了这些事件，未代替原科学实验。

来源检查因此保留两组独立证据：

| 证据 | 固定依据 | 用途 |
|---|---|---|
| 原科学祖先 | `b9ea9e55...` → `cb85d2bb...` → `7e8f26ba...` → 当前 base | 保留 source qualification、原实验及其五个前驱 run 的来源链 |
| 原科学文件 | 原诊断提交 `7e8f26ba6d7330624091291d9e1336e5ff9c09dc` 的三个普通 `100644` Git blobs、SHA256、长度 | 原脚本及两份 manifest 在当前 base/head 都须逐字节相同 |
| 原执行正文 | 原精确 checkout 和六个科学、数据、封存步骤的正文 | 保留源码 checkout、官方代码核验、11 个 SOFA、原依赖版本、诊断与结果形状检查 |
| 完整执行模板 | 原工作流、精确来源修复、来源修复加固定 M2，各自仅有已审旧/新 upload pin 两种正文 | 同时约束权限、job 条件、runner、超时、环境、步骤顺序及 Bind 命令；不能仅凭七段正文相同放行 |
| 当前 PR | 事件的完整 base/head OID，实际 merge 的两个有序父提交及相同 head tree | 只归因本次 PR 的改动；不用浮动 `origin/main` |
| 当前 push | 事件 before/after，after 等于事件 SHA，直接且唯一的父提交等于 before | 只归因本次主干 squash；零 OID、新建、删除、force push 均拒绝 |

机器合同 `dechorate_event_source_t1m3.json` 记录三个原文件的完整散列、原五个
predecessor run、上游官方 revision/blob，以及原 12 个 inventory 对象。
诊断仍取其中原 11 个 SOFA；来源验证器不下载、不读取、不重采样这些数据。
任何材料缺失或散列错误仍须由原 materialize / 诊断步骤拒绝；来源阳性不替代该检查。
原科学文件即使早在当前 base 之前被修改，当前事件只改 workflow，仍会被本验证器拒绝。
修改数据、算法或评分必须另行登记研究合同，不能由维护标签、范围比较或本合同赋权。

独立审查在原 `219414e608465c29afe1b5ebadac0ad632f6c9bb` 复现了五个错误的
来源阳性：只给 diagnostic job 新增写权限、`if: false`、`continue-on-error: true`，
或只在原 Bind 中加入改写科学源码、伪造来源收据的 shell，七段原正文仍相同。
该版本始终未接入科学 workflow、没有产生 skip 或科学 PASS；这些原始失败保留。
本次修复锁定完整可执行模板，五种修改均不再具有来源资格。

## 三个完整模板与有限 pin 变体

`workflow_templates()` 直接从冻结 Git 工作流构造下列三种精确正文，机器合同逐项
登记 SHA256。仅允许正文之前独立的未缩进 ASCII 注释或空行；不能以 YAML 重排、别名、
额外 job、任意 Bind shell、环境覆盖或额外步骤绕过比较。
Unicode NEL/U+2028/U+2029 和其他非 ASCII 控制字符不能被当作注释吞掉，避免
注释归一化与 YAML 行边界解释不一致而隐藏真实配置。

| 模板 | 准确变化 | 接入前置 |
|---|---|---|
| `ORIGINAL_FROZEN_WORKFLOW` | 原工作流正文，包括原 Bind | 原来源与事件规则仍适用；此模板不修复旧比较本身 |
| `EXACT_PROTECTED_SOURCE_BINDING` | 唯一固定 Bind 调用，以及固定 `always()` 来源收据上传步骤 | 本来源验证器与机器合同已在精确 protected base，原科学仍完整执行 |
| `EXACT_SOURCE_BINDING_WITH_DIRECT_PR_M2` | 在前项上只加固定 maintenance job、`needs: maintenance` 与一个准确条件 | 原受审 M2 consumer、M1、T0、当前 witness 四文件的模式、Git blob、长度、SHA256 全部已在 protected event base；hookup 之前另须闭合真实 M1/M2 阶段证据 |

固定 Bind 先保留原 EXPECTED_SHA 检查，再只从真实事件提取完整 base OID，在唯一
RUNNER_TEMP 目录建立该 base 的 worktree，并调用该 worktree 中已受保护的来源
验证器。它没有可编辑的 shell 插槽，不导入 head 的验证器。原始科学步骤随后仍
在精确 head checkout 执行。来源收据保存为
`dechorate-ground-truth-v1-out/source-range.json` 及其 SHA256，单独的固定上传步骤
保留正、负来源结果；来源否定会传播为失败，不能转成科学成功。

固定 M2 job 只在直接 PR 执行，从 protected base 的 `trusted-policy` checkout
调用原 `workflow_pin_pr_consumer.py`。其条件只允许成功的 maintenance job 且
`skip_measurement == 'true'` 时不执行 diagnostic；失败、缺失、跳过或否定都继续
原科学（取消仍为取消）。该原 consumer 在任何 skip 阳性之前必须完成真实 M1
`live_probe`，本来源验证器不会伪造或代替它。普通人类修复 PR 不符合 #714/Bot
身份；main push 的 maintenance job 不执行，两个入口都须完整运行原 corpus。

四文件匹配只证明已审源码存在于受保护 base。收据明确区分
`actual_m1_prerequisite_observed_by_this_helper=false`、
`protected_main_closure_observed_by_this_helper=false` 与源码身份；真实 M2 新主干
Verify/Release、独立 M1 活 bot 阳性仍由既有阶段门禁在 hookup 前另行核验。
这些尚未发生的 run ID 不能根据一个源码 SHA 预造；本模板不新增自动闭合或跳过权限。

每个模板还精确枚举本次 T0 `2026-10-20` 已审 upload 转换后的完整版本：
`043fb46d1a93c77aae656e7c1c64a875d1fc6a0a` →
`cf430e030ddbb5b0abf93d22962f4752f3646cd9`；有 v7 注释的步骤只允许
`v7.0.1` → `v7.0.2`。所有 upload use sites 必须一并转换，不接受部分替换或任意
Action SHA。checkout 和七个原科学步骤不变。因此 #714 完成后，正常来源合格的
人类 PR / main push 可使用已登记的新 pin 模板继续科学执行。dEchorate 原本没有
workflow_dispatch 入口；本提交不新增它，两个 PCR workflow 原有 dispatch 科学
路径仍保持。最终 M3 push 模板由其独立 dormant source tranche 精确登记并保护，
再接通 workflow；本提交没有为未知 push 命令留下通用插槽。

## 事件与保护来源的绑定

执行文件和 JSON 合同必须来自精确事件 base checkout，普通文件模式和逐字节内容
都须等于该 base 的 Git blobs。只能读取候选 head 的 Git 对象，不能导入或执行
候选 head 的验证器。Git 使用固定同仓 URL、完整 OID、有限输出和有限超时；拒绝
浅历史、grafts、调用者重定向 Git 对象/配置的环境，以及路径、模式或对象类型漂移。

当前科学范围仅允许修改已存在的 dEchorate workflow。混合源码、额外 workflow、
新增、删除、重命名、符号链接、可执行模式和 gitlink 都不能通过。本阶段故意不接受
#714 的跨 workflow Actions 更新；后者需要最后独立实现的 M3 push 维护消费者。

实时模式双读当前主干 API 与 Git ref、PR 元数据、Ruleset 21804005 和当前 run。
主干必须仍等于 PR base 或 push after；保护规则必须 active、严格 summary、
GitHub Actions application 15368、squash-only、review threads resolved、无 bypass。
push 还须唯一关联一个已合并的同仓 PR，其 base 等于 before、merge commit 等于
after，真实 PR head tree 等于 after tree。PR 和主干都不以“状态是绿的”代替来源。

run 要匹配准确 ID、attempt、workflow path、event、自己的 head_sha 和 branch，且
仍在执行中。复用调用的 caller context 不可冒充直接 dEchorate 事件，已完成的旧 run
也不能作为当前执行入口。只使用 `run.head_sha`，不使用动态的
`run.pull_requests[].head/base` 充当历史提交证明：旧失败
[38512536044](https://github.com/jiying2007/audio-pipeline/actions/runs/38512536044)
的 `head_sha` 仍是 `3e29c6cc81000741844ecc47962ba43e18e7e502`，但 2026-10-20
再次读取时其关联 PR 数组已显示当前重基后的 `6fc83752...` / `b80d819...`。
原红 run 不会因此变成一次新执行。其余旧红
[38512536268](https://github.com/jiying2007/audio-pipeline/actions/runs/38512536268) 和
[38512536068](https://github.com/jiying2007/audio-pipeline/actions/runs/38512536068) 也继续保留。

## 三个现有入口和后续顺序

在本次 base 的全仓 caller 搜索中，触发关系如下。不能把它们写成“三个主干 push
科学 PASS”。GitHub 的可复用 workflow 继承 caller 的 github context。

| 现有 workflow | 直接入口 | #714 合并后的处置 |
|---|---|---|
| dEchorate diagnostic | PR、main push，均由三个既有路径过滤 | 当前阶段未改。最后 M3 接通后，匹配完整已审维护证明的 push 才能独立显示“未执行科学实验” |
| PCR02 DSP | PR、dispatch；无 push、无 workflow_call 入口 | 直接 PR 使用独立 M2；无新增的主干 push 科学运行。dispatch 保留原科学 |
| PCR02 Real AEC | PR、dispatch、workflow_call；无直接 push | 直接 PR 使用独立 M2；唯一现有 caller 是 PCR02。嵌套调用和 dispatch 保留原科学，不继承 PR-only admission |

具体交付顺序保留 #758/#759 的独立门禁：

1. 保护本来源验证器，完成 exact-head Verify。另行完成受保护 M1 源策略的新 main
   Verify/Release 与最新真实 bot 树阳性，以及受保护 M2 消费者源码资格。
2. 三个 M2 workflow 分别整合。对 dEchorate 只改现有 workflow：用本次事件范围和
   原冻源证明修复旧范围比较，并接第三个 direct-PR-only M2 消费者。普通修复 PR
   不是 #714，必须完整实际运行原固定 corpus；其新 main 也运行原诊断、Verify 和
   匹配 Release。来源检查阳性只允许继续原科学步骤，不能直接作为科学 job 的成功。
   本步骤不增加任何非 PR 的维护跳过。
3. 最终 M3 push 消费者与其精确工作流模板先在独立源码 PR 登记和保护；三个 M2
   独立闭合、最新 bot 树再次资格后，才在另一个 workflow-only PR 接通。它须
   使用 before 中已受保护的策略，验证真实已合并 #714、不可变
   Dependabot actor ID 49699333、before/base、after/merge、唯一父链和实际 bot tree；
   重新从 before 的全部实际 workflow use sites 推导完整已审三种 pin 转换。原
   55/108、55/125 或后续观察计数都不是未来 diff 的硬编码通行证。
4. push 维护消费者必须独立读回三个 direct M2 收据：`maintenance.json`，各不超过
   16,000 B，artifact 名为 `workflow-pin-maintenance-<workflow-stem>-<run_id>`。
   绑定准确 run 的 `head_sha`、path、event、attempt，实时 artifact ID/长度/digest、
   原 ZIP 散列，以及收据中的 base/head、M1/T0/witness/consumer 散列与 before Git
   blobs。PCR02 caller 内的 Real AEC 收据不算第三个 direct run。不能只消费 JSON
   自述、API success 或 M1 的 open-PR live_probe；PR 合并后来源协议已经不同。
5. 新 #714 PR 收据明确是非测量维护。独立 CodeQL、Actions 版本来源、artifact 下载
   读回、严格 expected-head squash 和新的主干 Verify/Release 仍是独立要求。
   push job 不等待自己尚未完成的新主干 Verify/Release，避免依赖死锁；这些在外部
   governed merge/release 链中完成。任何缺失证据都不获得科学或产品 PASS。

## 离线复核与将来的调用接口

```sh
python3 .github/program/test_dechorate_event_source_t1m3.py --self-test
python3 .github/program/test_dechorate_event_source_t1m3.py --output /tmp/t1-m3-source-review.json
```

离线测试先通过真实 PR / squash 两种正控制，再分别扰动事件、祖先、文件、模式、
原科学步骤、完整执行模板、当前 main/PR/run/ruleset 和封存边界，最后再次通过未修改控制。
只替换网络读取；实际 Git 对象检查不会被 mock。测试不生成可信 runner、corpus、
M1/M2 admission 或科学结果。完整复核报告与工作流消费用的小收据是不同材料。
M2 模板的源码正控制只复制已冻结的真实 Git blobs 进入明确的工程 fixture，不把
该 fixture 称为真实受保护主干或 M1/M2 资格闭合。固定 Bind 的集成反例还实际创建
base worktree、调用真实 CLI，并在任何网络读取前由错误仓库事件得到已封存的否定。

后续受保护 consumer 的接口仅为：从精确 base checkout 执行
`python3 .github/program/dechorate_event_source_t1m3.py --event-file "$GITHUB_EVENT_PATH" --receipt <new-file>`。
checkout 必须完整取历史并关闭持久化凭据，head 只作为 Git 数据读取。未来科学 job
仍须精确 checkout head，保留原 EXPECTED_SHA 检查和全部原科学步骤。这里不添加该
consumer。本程序没有 GitHub skip output；来源否定退出 1，写收据失败退出 2。
每次正、负结果都写独立 JSON 和 SHA256；已有收据拒绝覆盖。整个源收据最多 16,000 B，
不输出凭据、原事件正文或临时下载 URL。

原始依据：

- https://github.com/jiying2007/audio-pipeline/issues/758
- https://github.com/jiying2007/audio-pipeline/issues/759
- https://github.com/jiying2007/audio-pipeline/commit/7e8f26ba6d7330624091291d9e1336e5ff9c09dc
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
- https://docs.github.com/en/actions/reference/workflows-and-actions/reusing-workflow-configurations

所有阶段都不改变 I025–I040、RealMAN 源时钟、SSC305/HIL 或公开 ABI 的权限。
