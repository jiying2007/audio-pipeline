# FE09 A2-F0：固定前缀退休与外部锚定的 hosted 进程恢复

## 登记、范围与当前状态

本阶段由 [#825](https://github.com/jiying2007/audio-pipeline/issues/825) 登记。
实现之前的完整审查原件保存在提交
`f90f6bd73c13c997b0bb85decf1545c632878982` 的
`docs/research/frontend-evolution-v1/FE09_A2_F0_PREREGISTRATION_20261021/`。
该 checkpoint 的父提交、已完成自身 Verify/Release 的实现起点为
`01479d6b441f54ea1d68588155dc9742eaa96fbc`。
后续整合主线仍须分别取得适用 PR 检查和 distinct-main 验证，不能继承旧提交的通过状态。

这是新候选的实施说明，不是执行成功收据。正式结果以对应精确执行提交的原始
`receipt.json / collect.log / verify.log / SHA256SUMS`、实际 CI 和独立 ZIP 读回为准。
四份原件中的草案时点措辞由 #825 和 registration.json 的登记状态补充；技术合同原字节保持。

唯一研究转换是原始来源停止、调用者独占后的 **1..32 → 17..32**。
独立 FPR1 检查点保留原始 FRM2 及退休 FBS1 元数据，外部可信调用者保存 expected anchor，
新启动的目标进程验证保留窗口并显式继续剩余退休。原 A0/A1 缺少前缀后必须继续拒绝。
不包括 seq33、连续滚动、槽复用、并发 producer、整机冷启动、物理断电、设备资源资格、
真实 NAND 收益、公共 C4 SDK 或 SSC305。父任务 #796、#791、#767 的其他工作保持开放。

## 冻结原件

| 原件 | 字节数 | SHA256 |
|---|---:|---|
| PREREGISTRATION.md | 33986 | `1acb4be8295a9154e50a2f7912e59d47648c5972fc68acc9f8d8f59d06072e0f` |
| source-lock.json | 21705 | `df0801d5b32a9629bb54ce5f6db027039ea0f2101600a9ca8a1f7b1752ace73c` |
| test-contract.json | 585779 | `a0a957394425a3b2bf9d79c8762204e496867b8c386efe894e7e85a3af6dd67e` |
| REVIEW_NOTES.md | 9457 | `a58d69bb28c74708af854a0ecee669c45752ff08297b259d04a7bb96f0936568` |

本目录中的 `fe09_b2s3_t3s2b1ba2_frozen_inputs.json` 与
`fe09_b2s3_t3s2b1ba2_test_contract.json` 分别是上述两份 JSON 的逐字节副本。
源码锁的 81 个原始输入均保持原 Git blob、长度和 SHA256；新增 A2 源码身份另外绑定真实执行
checkout，不把候选源码伪装成旧锁的批准输入，也不自动更新原锁。

## 私有实现与验证职责

新的 C/H 仅负责独立 FPR1、FRM2/FBS1 元数据、原 codec callback 约束、目录协议和有界状态。
原 APX3 writer/decode/replay、CRC、SHA 与规范命名函数来自冻结源码。
不会放开旧 static validator、改变旧 owner 或给旧 reader 增加删除后模式。
该研究代码不安装，不改公共 ABI、产品 src/include 或 shipping 默认。

C fixture 使用原第一方 32 帧来源，提供 transaction、recovery 和 negative-batch 三种工作者。
Python 父协调器保有 expected anchor，只传当次控制 IPC、摘要和元数据，使用 fresh exec 和
`close_fds=True` 启动对应目标。ARM 每次明确通过 QEMU 启动同一个已构建 ARM ELF。
恢复者没有旧 owner、源 fd 或退休 PCM，live source head/tail 必须为空；父保存的历史观测
不能当作恢复进程重新测得的值。

`read` 只报告当前已验证状态。父独立检查无副作用并发出 resume 指令后，工作者须关闭读取 fd、
清空 owner 并重新打开、验证同一外部 anchor，执行本次屏障和剩余 unlink。
负例在候选调用后阻塞，父实际枚举和验证盘面以后才允许清理并进入下一例。
故障注入的 UID/device/errno 只经过明确的新 A2 seam，不提权或耗尽真实 runner 资源。

FPR1 固定为 4768 B；原始退休行只证明元数据链，删除后的退休 PCM 不再可读。
首次根发布和本次 fsync/readback 完成后，数据按 1..16 升序逐项 unlink/fsync/重新核验。
unlink 已发生而后续 fsync 失败必须保留真实部分副作用，返回未提交；不伪造回滚或删除前状态。

## 实施前的错误标签映射裁决

N003 与 N024 都要求独立 reader 在外部完整文件 SHA256 比较处拒绝。
模块仅凭当前 FPR1 字节和 caller digest，无法证明历史上究竟哪一方改变。
因此保留真实运行错误 `EXTERNAL_CHECKPOINT_RAW_DIGEST_MISMATCH`，并对 N003 登记标签
`WRONG_EXTERNAL_FILE_DIGEST` 允许一个精确、显式的语义映射。

这个映射不改变输入、门槛、拒绝层或副作用判定，也不允许按 case ID 伪造运行错误。
trace 同时保留注册的 expected rejection、实际 runtime error 和变异来源证据：

- N003：FPR1 原件不变，仅 caller expected digest 的 byte0 XOR1；父独立核对原件和参数见证。
- N024：原 caller anchor 不变，FPR1 reserved byte 被受控改写并重新封装；完整 raw digest
  实际变化，必须先命中外部 raw digest 比较，不能先在内部 reserved 校验拒绝。

两者都要求零新 unlink、盘面不变和无成功/ACK 声明。其他标签不自动获得别名。
该裁决在实现测试执行前登记，冻结机器合同本身没有重写。

## 完整矩阵与预算

48 个 profile 覆盖 C1/C2-ULA/C4-ULA/C4-UCA、16/32/48 kHz、Render 开/关和 K1/K2。
两个固定代表 profile 各执行 57 个进程终止点；父在目标 barrier 阻塞后真实 SIGKILL，
等待目标信号退出后才启动恢复。P01–P05 保留不完整根现场并拒绝；P06 起的完整根允许观察，
resume 仍要本次屏障。P57 新增 unlink 恰为零。

164 个 N-ID 中 157 个由目标 C 执行，5 个检查 Python receipt，2 个检查 source lock。
另有 15 个 E-ID 检查 Artifact 和执行来源。每目标每轮 319 个逻辑目标实例；
四目标各两轮合计 2552 个实例、2600 次目标进程启动，两个计数口径分别报告。

| 资源 | 已登记上限 |
|---|---:|
| 新 A2 显式状态与工作区 | 64 KiB |
| 同时活动 fixture | 1 MiB |
| 单次编译或工具调用 | 120 s |
| 每目标每轮完整 suite，含子进程启动、IPC、恢复和清理 | 540 s |
| collect 全局，含全部构建与八轮 suite | 1500 s |
| 整个 CI job | 1800 s |
| 单个子进程 stdout / stderr，各自 | 64 KiB |
| collect.log / receipt.json / verify.log | 16 MiB / 4 MiB / 1 MiB |
| 原始四成员 ZIP | 32 MiB |

共同 monotonic remaining deadline 不随新子进程或故障用例重置。超限、缺目标、缺第二轮、
sanitizer 错误或未完成用例都必须失败；没有隐藏重试、skip、关闭检测器或动态扩时。
SIGKILL 进程不能执行 LSan 正常退出检查，不能声称它拥有该检查的终止后证明。
64 KiB 是新增 A2 明确工作区，不是全进程 RSS、sanitizer 虚拟地址空间或设备全机预算。

资源账本分别列出 caller-owned workspace、owner、receipt、局部栈保留量和只读数据保留量。
四个目标的实际编译器 stack-usage/callgraph 和对象 section 报告用于核对这些保留量，
不能只复述 C 常量作为实测。Native/ARM 的功能数据与 sanitizer 自动生成的元数据分别列明；
旧模块栈、原 fixture 和实际进程 RSS 另列，不计作新增 A2 的功能工作区，也不隐去。
目标进程的 hosted 高水位 RSS 来自父进程对自己启动的确切 PID 执行 `wait4` 所返回的
`rusage`，同时绑定退出码或真实终止信号；它包含 fork/exec 瞬态，不能解释为设备常驻内存。
不能按 `/proc/<Popen.pid>` 采样推断进程归属，因为 PID namespace 与挂载的 procfs 可能不同。

## 操作入口与原始证据

在仓库根执行元数据自测：

```sh
python3 tests/validation/frontend_evolution/fe09_b2s3_t3s2b1ba2_finite_retirement_qualification.py --self-test
```

正式完整资格需要已声明的 Native、sanitized、ARM32/QEMU 和 TSan 工具链。以真实 checkout
提交绑定来源，输出目录必须是新的，不能覆盖原件：

```sh
python3 tests/validation/frontend_evolution/fe09_b2s3_t3s2b1ba2_finite_retirement_qualification.py \
  --collect --output fe09-t3s2b1ba2 --execution-source "$GITHUB_SHA"
python3 tests/validation/frontend_evolution/fe09_b2s3_t3s2b1ba2_finite_retirement_qualification.py \
  --verify --output fe09-t3s2b1ba2 --execution-source "$GITHUB_SHA"
```

既有 quality workflow 的新 stage job 上传四成员原件，下载绑定本次 upload 返回的唯一 Artifact ID，
然后验证文件集合、内部 SHA256、执行提交、完整 raw trace、全部计数和权限边界。
`--negative-readback` 在隔离副本上重封装负例，不改变下载的原件。
人工独立原 ZIP 读回还须绑定实际 run/event/attempt/head、Artifact ID、API digest 和上传日志。

本实现的固定证据传输采用 `zlib-rfc1950-base64-v1` 无损编码。
`collect.log` 的每行是连续编号的 `trace_block`，其 payload 包含 codec、原始字节数、
SHA256 和 zlib level 9 的 base64 数据。解压内容为保序 canonical JSONL 事件：stdout/stderr
事件的 `raw_b64` 保留实际原字节，父观察事件保留完整 metadata 和 digest 对象。
普通块的目标大小是 65536 B；单事件和单块展开均不超过 1 MiB，全部展开不超过 256 MiB。
回读使用有界解压并重算完整 trace，拒绝缺号、重号、乱序、多余压缩流和超量展开，
不以摘要替代原记录。resource 事件中的 `.su` / `.ci` 保留完整 UTF-8 原文及其原始字节数、
SHA256；回读严格重新编码并核对原件，不进行内层压缩。包含全部报告、JSON 转义和对象身份的
整个 resource 事件仍须不超过同一 1 MiB，所有原文自然计入同一 256 MiB 总展开预算。
`.su` 原始读取继续受 256 KiB 限制；`.ci` 预读以同一 1 MiB 封顶，并由完整事件上限进一步约束。
不删除 sanitizer 节点或边，不修改原调用图分析与 A2 状态、栈、只读数据验收条件。

PR #829 的首轮 A2 job `119669225692` 在原 Native 两轮完成后，以
`MISSING_OR_OVERSIZED_sanitized-20.ci` 拒绝；原四成员失败包为 Artifact `12405353437`。
拒绝发生在新增驱动对整份调用图的 256 KiB 额外读取限制处；本地保留原参数的单 core 诊断
复现了超出该限制的完整报告，不能将其大小当作未上传的远端报告实测值。
冻结 #825 原件未规定此单报告上限。
修正为上述单层传输后，必须对新的完整源码身份重新运行四目标资格，首轮失败不改写为成功。

child 的 stdout/stderr 限额各按未压缩的 64 KiB 计算；实际编码后的 `collect.log` 仍受
16 MiB 上限约束，四成员 ZIP 的上限也不变。超限后不切换格式、删除既有记录或截断为成功。
失败先保留已经完成的块，再以末尾 `failure_prefix` 明示原件不完整；成功 verifier 必须拒绝它。

唯一成功 decision 为
`FE09_A2F0_FINITE_PREFIX_RETIREMENT_AND_ANCHORED_HOSTED_PROCESS_RECOVERY_ONLY`。
失败 decision 为 `FE09_A2F0_NOT_ADMITTED`，失败原件和部分结果保留。
`finite_prefix_retirement_completed=true` 仅指本有限窗口；所有物理、冷启动、连续滚动、
全机内存、10 ms 产品和公共 SDK 权限仍为 false。

受保护合并还要求精确 PR head/base、适用检查、summary/App15368、零未解决讨论及
strict Ruleset21804005。合并后该新主线的 full Verify、同 SHA governed Release/convergence
和原始 A2 Artifact 读回分别取得。该研究是 release-neutral，不创建新版本、不迁移 E001。
