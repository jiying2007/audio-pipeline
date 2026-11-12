# D8 第三次失败工件：只读收据诊断

## 目的与边界

第三次 D8 Research 运行 [43121241713](https://github.com/jiying2007/audio-pipeline/actions/runs/43121241713)，任务 130862020659，在源提交 `4a86ad099010ae1aead149414091b88be73c7f3e` 的 attempt 1 上以退出码 124 结束。监督步骤从 2026-11-11T23:37:45.4700590Z 到 2026-11-11T23:45:35.3108263Z。完整解码任务日志为 31,409 字节（UTF-8，包含 BOM），SHA256 为 `8998ef1cd4577d052f0b6636b426710c48aeeedc74d3ed48529a24d7bef4ba62`。这不是压缩日志包的哈希。

监督器的退出码映射表明触发了 `D8_SUPERVISOR_TIMEOUT`。日志没有阶段或命令定位信息。不能用约 470 秒总耗时、1,842 个上传文件或工件压缩大小推断实际停止阶段、执行过多少科学样本，或任何音质结果。标准输出可能仍在被杀工作进程的 Python 缓冲区中。

本次只读取已有失败工件中的 JSON 收据，不再执行 D8，不构建，不运行测试，不加载 PCM、状态或可执行文件，不重放原始输入，不修改 D8 的科学合同、源、屏幕、预算或 PR #948。诊断结束只表示收据读取结果，不表示原科学运行通过、完成、改进或获得晋级资格。

## 固定身份

- 仓库：`jiying2007/audio-pipeline`。
- 原运行：`43121241713`，attempt `1`，原源提交如上。
- 原工件：`13900578432`。
- 名称：`frontend-research-dualmic-broadside-output-d8-43121241713-attempt-1`。
- ZIP：恰好 `543037811` 字节，SHA256 `d2744826ec842956b55610a7f33e905c1a17483f9d0c2b52fef7987356737ca5`。
- 上传日志记录 1,842 个普通文件；API 到期时间为 2027-02-09T23:37:28Z。
- 原工件保留在 [Actions 工件页](https://github.com/jiying2007/audio-pipeline/actions/runs/43121241713/artifacts/13900578432)，不得重写、删除或重复上传。
- 诊断代码基于未改变的 `main = 1b5b01e0f2580ec9e05dfacff2ee1d292c438172`，树 `db25581db2ad683499ec2c7b2e22686787d39db2`。

## 隔离触发

新工作流只监听 `diagnostic/d8-attempt-43121241713` 分支的 push，并只匹配该诊断的三个文件。不提供 pull_request、workflow_dispatch、schedule、workflow_run 或 create 触发。工作步骤再次核对仓库、事件和完整分支引用。

发布由父任务在独立精确提交审核后完成：先在上述 main 建立专用分支，再将其一次前进到审核过的诊断提交。第一次建立分支时还没有新工作流；第二次更新产生 push。不得打开诊断 PR，以免启动通用 Verify 构建；不得更新 PR #948 的研究分支。

GitHub 官方事件文档明确 push 可以运行尚未合入默认分支的工作流，GITHUB_SHA 为被推送的尖端提交，GITHUB_REF 为被更新引用；create 是单独的引用创建事件。来源：[github/docs 固定提交 2b4f2c7398e04ee8d02adca7440e4286d20c78b9](https://github.com/github/docs/blob/2b4f2c7398e04ee8d02adca7440e4286d20c78b9/content/actions/reference/workflows-and-actions/events-that-trigger-workflows.md#push)。实际是否触发仍须通过 Actions API 验证，不重复盲目发布。

逐一读取上述 main 的全部 70 个现存工作流入口：24 个包含 push，均限定 main；0 个包含 create。其余入口为 pull_request、workflow_dispatch、schedule 或 workflow_call，且没有由该新诊断名称触发的 workflow_run。此专用非 main push 与 70 个既有入口均不匹配。此次不改变任何既有工作流。发布前须重新确认 main 和专用分支的实际 SHA。

## 读取与资源合同

工作流没有 checkout、安装、仓库代码导入、构建或 DSP 步骤。独立 Python 脚本原文逐字嵌入工作流 heredoc；审核时证明两份字节相等。只使用 Ubuntu 24.04 的绝对路径 `/usr/bin/timeout`、`/usr/bin/python3 -I -B` 和 Python 标准库。

诊断计算具有独立的 300 秒外部 SIGKILL 截止，覆盖元数据、一次下载、验证、完整报告写入与读回以及最终控制台输出。平台任务上限 10 分钟不是额外分析时间。资源限制只向下收紧，不申请新权限：AS 256 MiB、NOFILE 32、CORE 0、FSIZE 543037811 字节。无超时后清理、重试或续期。

唯一新目录 `/tmp/ap-d8-receipt-inspection` 必须不存在。仅容许两个排他创建的文件：
1. `archive.zip`，恰好 543037811 字节，每次写之前检查总量，流式哈希与关闭后独立重读已写 ZIP 的完整 SHA256 均一致后才读取 ZIP。
2. `report.json`，不超过 25165824 字节（24 MiB），完整序列化与检查后才写入，并在截止前关闭、读回验证。

两个文件联合自有写入上限为 568203635 字节。没有把这声称为操作系统全局写入配额。下载与诊断本身不重试；固定上传动作的传输实现仍受平台任务上限约束。只上传成功完成、读回一致的 `report.json`；上传是已完成诊断的传输，不能继续分析。使用已在研究工作流使用的固定 upload-artifact 提交，绝不上传原 ZIP 或未完成报告。

仅向固定 GitHub API 请求原运行和工件元数据，每个响应最多 1 MiB。验证原运行、提交、attempt、仓库、工件 ID、名称、大小、哈希和未过期状态后，只下载一次。禁用代理和自动重定向；授权头仅送往 api.github.com。签名下载地址只接受固定官方 Azure 工件主机规则、HTTPS 默认端口、无 userinfo/fragment，且不携带授权头；不记录令牌、签名地址、原始网络异常或响应正文。

在构造 ZipFile 之前，将 EOCD/ZIP64 所声明的中央目录限制为 4 MiB。ZIP 元数据先检查路径、重复条目、类型、加密、压缩方法、数量、长度、本地头与数据描述符重叠；最多 4096 条目、恰好 1842 个普通文件、总解压声明不超过 1 GiB。只读已选 JSON 成员到内存，绝不全量解压、不打开嵌套 original.zip、PCM、状态、构建二进制或任意 stdout/stderr。

## 收据与解释

固定读取 7 个阶段 JSON、input/admission.json、first-failure.json 与 run-index.json（存在时），以及所有安全命名的阶段命令 JSON，而不是只信 phase.commands。命令最多 512 个；每个 JSON 最多 1 MiB，run 科学命令最多 65536 字节；全部选中 JSON 读取合计最多 16 MiB。只按原始有限数值 deadline - timeout_seconds 推导命令开始时刻，缺失、重复或相同时刻都保留歧义，不用 ZIP 时间或文件名猜时序。

对每个成员保存路径、原始长度、SHA256、解析/模式状态，以及通过已知非敏感 D8 模式检查的完整解析值。被 SIGKILL 截断的 JSON、重复键、非有限数、未知字段或损坏模式应明确记录，继续查看其他有界收据；不得伪装为缺失或丢弃整份诊断。ZIP 结构或外层身份错误则整体关闭读取。

只读取最新相关命令收据明确引用、路径/长度/哈希相符的内容寻址 tool-inventory JSON；仍受 1 MiB 单成员和 16 MiB 总量限制。仅报告真实文件数量与字节量摘要，不打开其指向的文件。超限或不可用明确报告，不扩大边界。

控制台投影在写出前整体计算，最多 512 KiB，保留全部阶段/命令生命周期与截止值、原始返回码及明确的存在/缺失/无效状态；完整合格值与原始成员哈希在 report.json 中。没有静默截断或删掉不利记录。

解释必须始终写为“最后持久化证据”：
- 初始 phase FAIL 且 first_failure=null 是待完成值，不是已记录的终态失败。
- 命令 PENDING 写在 Popen 前，但 absence of effective_limits 或空日志不证明孩子未运行。
- 命令 PASS/TERMINAL 写在 COMMAND_END/传输 ACK 前；阶段 PASS 写在 finalizer/PHASE_END/FINISH 前。记录 PASS 不等于整个生命周期完成。
- retention.json 写在 42 个保留操作前，不能单凭它证明该案例已保留完成。
- run-index.json 只在全部 60 案例循环完成后写出；缺失不等于零案例执行。
- 缺失最终记录、文件数量、压缩大小均不是科学结果。

## 后续

本诊断只补充第三次失败的定位证据，不修改前两次失败或任何历史原始工件。任何工程修正须有独立精确提交审核与父任务的发布决定；不能据此自动重新运行 D8、改变时限、放松准入或晋级。未来若改进日志，应在现有租约仍有效时发出有界非阻塞阶段/命令标记；不得在超时捕获分支先写日志再杀死工作组，以免违背无截止后写入的合同。
