# D8 broadside 输出：实现与证据边界

状态：**FOURTH_ATTEMPT_MEASUREMENT_INVALID_ENGINEERING_FIXTURE**。前三次失败及原工件保留在第 8–10 节。性能修正后的第四次执行完成 run、analysis 和 verify 阶段；run 阶段约 146.56 秒，未触及 300 秒上限。但在 negative 阶段因合成 identity fixture 的共享字典别名导致 `D8_NEGATIVE_ACCEPTED:before-dev`，最终仍为 MEASUREMENT_INVALID。第 12 节保留实际日志与工件身份。修正只涉及测试夹具及证据文档，不改生产 guard、科学干预、阈值、预算或 deadline；通过独立 exact-head 复核前不得发布。不能将中间阶段完成当作有效科学结果或质量提升。生产版本、默认配置、API 与生产树不变。

## 1. 冻结合同与单一干预

- 原冻结：14083f84b8ec213d85f10cf31a56e42a774410f5。
- 资源/timeout 的执行前透明修订 R2：1c0c56c8baf1e32bd14a8b1a6f74f20951b38c74。
- 固定四个 supervisor-owned 无 DSP fatal-path fixture 的窄修订 R3：8e3f92af6c4b0d3205a6903e8de31e55c0225a9e。
- 科学定义、原始输入、screen、预算类别与 76 个 negative 类别在修订中未改变。详见同目录 PLAN 与 input-lock。R1/R2 保留在提交历史，不能将后来的实现当作预注册。
- 唯一数学变化是在生成的 candidate research copy 中，将一次
  `const int output_lag = s->fallback_active ? s->fallback_lag : s->lag;`
  换为 `const int output_lag = 0;`。
  另一个 reverse/alias 的 lag 选择不变。FULL tracking=1；tracking、fallback、权重、gain、history/reset 不变。

旧 D7 machinery 的零候选合同不变。新 D8 builder 单独执行数学变换和九项非数学 observer/symbol 变换；每项 exact-one，逆序恢复后逐 byte 比对原文。原 D1 AGC wrapper 的额外定义重命名仅让新 wrapper 在恰好一次原调用前后取得真实 12-byte AGC state。

## 2. 文件职责

- `dualmic_broadside_output_d8_supervise.py`：无 repository import、无 DSP 的外部 supervisor，root deadline、私有 IPC ACK、进程组/PID fallback、非阻塞输出，以及 R3 四个真实 fatal-path fixtures。
- `dualmic_broadside_output_d8_build.py`：冻结 source/helper/production closure，当前实际 compiler、argv、生成 header、精确 CMake flags/Unity forms，四个执行形态，tool environment、byte ledger、逐命令 inventory 与 receipt。
- `dualmic_broadside_output_d8.c`：真实 HPF/BF/AGC 观察与独立 BF/AGC arithmetic controls；不改 pipeline 控制决策。
- `dualmic_broadside_output_d8.py`：原件准入、逐 case 独立执行、先测量比对再 dedup、固定几何 scoring、screen、完整 readback/seal/completion 与有界 stdout projection。
- `test_dualmic_broadside_output_d8.py`：76 项固定 negative 类别、pristine-first/精确拒绝理由，以及 flags/Unity/protocol/budget/数值边界 controls。每项注明 actual evidence、synthetic engineering 或 prospective finalization template，不能将模型 fixture 说成真实 DSP 重算。
- 只在现有 `.github/workflows/frontend-research.yml` 添加 D8 scoped job/selector；从旧 matrix 到 D7 末尾的 job bytes 与 action pins 不变。D8-only 变更不得选择旧 jobs。

## 3. 四形态与原件桥接

顺序按原 input-lock 的 60 cases；每例依次 baseline plain、baseline observed、candidate plain、candidate observed。整个 pipeline 各自独立连续运行，SYNC 及全部后续模块可自然分歧，禁止向 candidate 注入 baseline gates。只在原 render-gap frame300 重置；path change 不重置，window 不重新初始化。

baseline plain/observed 的 PCM/metrics 逐 byte 等于原 A/C；baseline 七个 D1 lane/control 等于原 D1。实际 AGC state 与原 D2 gain.csv 位模式、最终 f32 原值相等。candidate plain/observed 的 PCM/metrics 逐 byte 相等。所有失败立即停止该候选，不能换 compiler flags 或 tolerance。

每个 observed frame 记录真实 472-byte HPF/BF record（16-byte header、四份 24-byte HPF、两份 180-byte BF）与真实 24-byte AGC before/after。布局、offset、endianness、IEEE f32、record 数和 reset/continuity 都需检查。两臂的实际 HPF/BF trace 与四个实际 HPF lane 必须先逐 byte 比较，然后才允许共享 lane storage；两份 state trace 都保留。baseline BF 按真实 effective lag、candidate BF 按零 lag，分别独立逐 sample/f32-bit 重建。

near-only/silent-render 的所有已记录 stream、PCM、metrics、control，以及**观察到的 HPF/BF/AGC state**逐 byte 不变。不宣称完整 SYNC/AEC/NS 内部状态被直接观察。

## 4. 保留映射与闭包

每例保留 42 个实际临时输出的 descriptor，写入 retention proof 后才执行 move/discard。proof 包含每个源的实测 byte count/SHA256、明确 destination/equal-to、操作类别与 identity。缺测量、伪 dedup、错误 source pointer、额外文件/目录/symlink 均拒绝。

- baseline 的原 A/C、D1 输出仅在本轮真实比对后引用原件，不将假设原值当本轮观察。
- 四个 HPF lane 在两臂真实相等后保留一次。
- candidate 保留 BF、reference、echo、AEC residual、NS output、AGC output 六种唯一内容；absent-AEC 空 lane 的语义显式保留。
- D1 AEC input 可指向实测 BF；NS input 可指向实测 AEC residual 或 capture-only BF。不得制造数据来满足 identity。
- 两臂 HPF/BF 和 AGC trace、candidate PCM、metrics/control、实际 observer receipt 与 retention proof 均保留。
- source archive、四个生成形态的 source/build provenance 与实际 compile recipe 有界保留；所有 repository runtime imports 都属于冻结 closure。
- 完整 tool inventory 每次命令后重新测量；相同状态经实际 descriptor/bytes 相等检查后只存一次完整 inventory，command receipt 使用有界 descriptor 引用。科学 command receipt 的 64 KiB 上限不是依赖平均值。

retirement 仅在四个 child quiescent、42-source proof 已写入且没有 writer reservation 后进入。入口对整个结果树实测一次，事务内只准按 proof 的固定序列执行同文件系统 move/逐 byte 证明相等的 unlink，不准启动 child、写入新文件或新 reservation；每步保持实测路径/大小/category ledger，并在 rename 前检查 destination 类别。成功出口再次完整实测并核对 exact map。普通失败先清除 ledger，再由正常失败路径计量实际前缀；期限已到不做补测或补写。此局部优化把每例 retirement 的63次全树遍历变成2次，其他检查不取消，也不预先宣称能在300秒内完成。

analysis seal 闭合全部当时 core evidence；verify 从实际保留内容重新分析并比较 report。negative 完成后，finalizer 检查全部七个 phase PASS、精确文件/目录集合、negative fixture descriptors、seals、summary 与 completion 自身 byte accounting。completion 必须存在并经读回，才能发 FINISH ACK。stdout 是有界 compact projection，不复制巨大逐 frame JSON；完整报告与二进制 trace 仍在 artifact 中。

## 5. 固定评价与保守 veto

最终送出的 S16 PCM 除以 32768，使用冻结 D1 `measure_lane/si_sdr_span` 的固定 160-sample offset；不能调用 ±3ms lag-search evaluator。全 32 near-reference common 与 input-defined 可评分 windows 均报告，包括所有负值；原 clean energy 为零的 windows 保留 null 原因，不依据 candidate output 决定适用性。

16 个 nominal/weak × profile × pair 的 common ΔSI-SDR 每个须 ≥1.0 dB；全部可评分 near common/window Δ≥0。1 dB 是有限研究预算的保守 continuation hurdle，不是听感阈值或统计显著性。16 views 来自相关的 4 对原始输入。

同一适用 near span/window 的 projection gain，两臂均须 finite、严格 >−120 dB，且 candidate≥baseline。common 使用完整 raw S16 和 delay160；window 使用固定 clean[a:b]/output[a+160:b+160] 与 delay0。无 epsilon/四舍五入比较。None 或 finite≤−120 是 NO_ADVANCE；NaN/Inf 是 MEASUREMENT_INVALID。

24 个 far/path/gap 与 4 个 C 的 common/window/native-whole RMS 与 peak 不增加；60 个 case 的 S16 clip count 与从实际 NS output/AGC state 重建、f32-bit 验证的 terminal-clamp count 不增加。保持 ERLE 完整固定曲线、尾部水平/能量和原 helper 自身尾部相对语义；24 项 convergence、16 项 event recovery 必须有 finite 值且不变差。缺失必要值是 continuation veto，不能填零。far-only event recovery 继续 null/N/A。

identity/arithmetic/source/continuity/closure/budget 失败为 MEASUREMENT_INVALID；有效但任一 screen 失败为 NO_ADVANCE；全部通过仅为 REVIEW_FOR_INDEPENDENT_CONFIRMATION_NO_PROMOTION。不得自动再开变体、调参或生产提升。

## 6. 资源、deadline 与诚实限制

结果闭包保留 512 MiB 上限，原有类别 caps 与科学 one-case scratch 保留。固定加变量接受金额 535454336 bytes，低于 536870912，所有自有写入（含失败前缀、header/newline、receipt/seal/completion）都先预检。科学 CLI 的固定文件数、每帧 row 上界及 RLIMIT_FSIZE 证明 one-case 最坏 24491008 bytes 在 24 MiB 内；不能以运行后库存代替这一证明。

R2 明确将 opaque build-tool 临时文件放在 `/tmp/ap-dualmic-d8/toolchain`：进程/单文件/时间 limits 加事后完整 inventory，128 MiB 是事后接受 cap，**不是逐写 aggregate quota、瞬时峰值或累计写入硬保证**。HOME/TMPDIR/XDG 环境采用明确 allowlist，Git identity 使用只读 options；全部环境记录。禁用 bytecode，防止 repository imports 写 .pyc。路径和 rlimits 约束已知工具，不宣称 syscall confinement。没有 sudo、mount、ptrace、quota、prctl/subreaper、额外权限或网络资源。

外部 supervisor 在实验 I/O 前记录单调时钟，root1200秒不可重置。单一主实验 worker 是显式长寿命例外，不是新增 300 秒 DSP child。它建新 session，验证 PID=PGID 后才收到开始 ACK；普通 git/compiler/CMake/CLI 子进程继承该组，min(30秒, phase剩余, root剩余)。每 phase≤300秒，命令期限覆盖 pipe draining、receipt 和 finalizer；未验证 descendants 全部消失不能解除 deadline。IPC 不能泄露给外部子进程。

首次观察到 deadline/故障即 SIGKILL 整组并用 actual PID fallback，不能通过 TimeoutError 让 D3 finally 写 admission。不会在过期后启动 inventory、hash、receipt 修复或清理。supervisor 自身 SIGKILL/OOM 和内核调度/不可中断系统调用不可能被 Python 保证瞬间处理，合同明确不声称即时物理终止。GitHub job 外层20分钟限制可能更早中止，并不延长研究预算。artifact upload 是之后的平台保全步骤，不重新运行分析或补写成功 evidence。

R3 的四个固定无 DSP fixtures 由 supervisor 创建，一个 group 同时活跃：startup-before-group、child-tree、try/except/finally、bounded-pipe。每个2秒lease，固定 body-ready barrier，先注册 PID/PGID/descendant再释放；pipe必须实际输出完整两份65536 bytes。 intentional expiry 只杀该 fixture，但真实期限/异常杀全部注册 group/PID。保留四个固定目录的 pending/stdout/stderr/receipt，检查 except/finally marker 不存在、PIDs 消失；zombie 依赖 runner reaping，不消失则 fail。逻辑581632 bytes 在既有报告类别的1 MiB reservation内。不把这些 fixture 说成已实际触发全局 root1200 expiry。

## 7. 运行与结论仍待独立复核

实现准备和修正均只通过 GitHub 连接器写入 detached Git objects。两次经过独立 source review 的 CI 尝试分别在合同比较和 tool discovery 处失败，详见第 8、9 节；未产生 D8 科学评分或候选改善结论。所有尚未执行的工程计数、预算与 scientific checks 仍是待验证要求。独立 source review、exact-head required checks、artifact 全闭包读回及新鲜 main 资格检查是不同证据，不能互相替代。本文件不作真实阵列、时钟、校准、ASR、听感或临床结论。

## 8. 首次尝试：完整保留的构建前失败

2026-11-11 的 [Frontend Research run43115604725](https://github.com/jiying2007/audio-pipeline/actions/runs/43115604725)，attempt1，head `e4d0b8dfb30169e5628ee2bd31ed8df54f7d65e3`，D8 job `130842741497` 已完成，结论 failure。scope job 成功，历史 D1/D3/D4/D5/D6/D7 jobs 全部 skipped；D8 failure-evidence upload 成功。此记录不覆盖独立的 Verify gate。

原 D3 准入报告 `INPUT_ADMITTED_NO_DSP_EXECUTION`、`original_D2_readback_exact=true`，用时44.84039957秒；原件474165229 bytes、3551 members、861385743 extracted bytes、60 cases/35916 frames/5746560 samples 均按原合同验证。之后 D8 停于 `MEASUREMENT_INVALID / D8_FULL_ORIGINAL_LOCK`，未开始 D8 build、tests、四形态 replay 或科学 scoring。这是实现 guard 失败，不是有效实验的 NO_ADVANCE，也不能据此判断候选质量。

具体原因：冻结的 D8 `original_admission` 比原 D3 lock 多三个明确 metadata annotations：
`admission_freeze`、`fresh_full_original_D2_readback_required`、`required_status`。
首次实现只验证/移除了前两个，就把仍带 `required_status` 的对象与原 D3 对象做全对象 equality，因此必然拒绝。
通过连接器重新比较冻结 JSON，`required_status="INPUT_ADMITTED_NO_DSP_EXECUTION"` 是唯一差异；完整嵌套 D2 case/input lock 没有差异。
修正明确验证并移除第三 annotation，然后仍比较每一个原始字段及完整嵌套 D2 对象，不改合同、不改数据、不放宽比较、不改候选参数。补充 focused engineering controls 覆盖 pristine、wrong/missing status、altered/missing original field 及 nested D2 drift，保持既有76个 fixed negative 类别。

[失败 artifact13897369988](https://github.com/jiying2007/audio-pipeline/actions/runs/43115604725/artifacts/13897369988)：
- name：`frontend-research-dualmic-broadside-output-d8-43115604725-attempt-1`
- uploaded ZIP：473258336 bytes；SHA256 `87d7f34796b1a97cc626dd39d73b30576dd29cb4e9cba8dc1278520f46d7fa1d`
- upload log 报告8 files；API 读取时 unexpired，expires_at `2027-02-09T22:54:23Z`。
- 完整 decoded job log 按连接器返回文本的 UTF-8（含其 BOM）计31980 bytes，SHA256 `2627e0b1344b926ed2efc5040967fa694c816eecb803dfd895acae0528624e37`。这不是 GitHub 压缩 log archive 的 hash。

上述 artifact 身份/上传成功来自实际 job log 与 artifact API；没有把 metadata 查询说成独立打开或重算了 artifact 的8个 members。首败不能被后续修正或重试覆盖；新的发布/运行须有新的 exact-head 复核，并保留本次记录。

## 9. 第二次尝试：tool discovery 失败与封闭 PATH 修正

[Frontend Research run43118580272](https://github.com/jiying2007/audio-pipeline/actions/runs/43118580272)，attempt1，head `a1c69806143e96c585ce65568d0a5c5d03139a0f`，D8 job `130852950835` 已完成，结论 failure。scope 成功，历史研究 jobs 全部 skipped，failure-evidence upload 成功。原 D3 admission 成功，用时37.049105113秒，`original_D2_readback_exact=true`；修正后的 original-lock guard 已通过。此后在 build 的 tool discovery 处以 `MEASUREMENT_INVALID / D8_TOOL_MISSING` 停止，未进入 compiler-version/configure/compile、四形态 replay、D8 tests 或科学 scoring。

当前实际 runner 日志标识 image `ubuntu24/20261101.360`。本次泛化错误没有写出失败的 lookup 名称；上传 artifact 的内部成员未独立打开，因此不能宣称已经从实际 failure receipt 读到“cmake missing”。
但是源码把 discovery PATH 固定为 `/usr/bin:/bin`；同一官方 image 的
[install-cmake.sh](https://api.github.com/repos/actions/runner-images/contents/images/ubuntu/scripts/build/install-cmake.sh?ref=add4380b0d6685806e9192c33c37359ee0aa4023)
使用 `--prefix=/usr/local`，
[软件清单](https://api.github.com/repos/actions/runner-images/contents/images/ubuntu/Ubuntu2404-Readme.md?ref=add4380b0d6685806e9192c33c37359ee0aa4023)
列 CMake3.31.6；该 image tag 经 Git data 解析到 immutable commit `add4380b0d6685806e9192c33c37359ee0aa4023`。遗漏 `/usr/local/bin` 是有公开来源依据的 CMake-path 原因推断，不是本次二进制/version receipt 的直接观测。旧 D7 的 lookup 使用 ambient PATH，不能据此假定新的封闭 PATH 等价。

修正将封闭 allowlist 改为 **`/usr/bin:/bin:/usr/local/bin`**，仅在原两个目录之后追加官方安装目录，保持原系统工具优先级；不继承 ambient PATH、不安装工具、不更改系统设置或权限。实际 lookup path、symlink target、resolved executable、文件 hash 与版本检查继续保留。missing-tool 失败必须给出明确工具名与封闭 PATH；synthetic lookup controls 覆盖原目录优先级、local fallback、missing tool 和忽略未注册/ambient 路径。它们不冒充对 runner 文件系统实际工具位置的检查，也不代表新 compile 已通过。

同一 immutable image source 的其余工具兼容性审查如下（[toolset](https://github.com/actions/runner-images/blob/add4380b0d6685806e9192c33c37359ee0aa4023/images/ubuntu/toolsets/toolset-2404.json)、[Git installer](https://github.com/actions/runner-images/blob/add4380b0d6685806e9192c33c37359ee0aa4023/images/ubuntu/scripts/build/install-git.sh)、同 commit README）：
- 显式 `tool_identity` lookup 只有 cc/cmake；新 PATH 保留原 cc 选择优先级。Git 由 apt 安装，源码 source_identity 的 Git 命令位于失败 lookup 之前，bare Git argv 仍只使用 sealed environment。
- Unix Makefiles 使用 make 和 /bin/sh。toolset 包含 make/gcc/g++，README 列 make4.3 与 GCC packages；标准 package 位置由原 /usr/bin:/bin 覆盖。CMake 实际生成的工具路径仍须保留核验，不预先假定。
- GCC 私有 cc1/collect2 由实际 compiler installation prefix 查找；as/ld/ar/ranlib 来自 image 的 binutils package（README2.42）。没有增加 private/toolcache PATH。
- ap_build_info_dump、observer self-tests 与科学 replay 全部使用明确绝对路径。workflow 的 Python 在 sealed child environment 前启动，supervisor 用 sys.executable exec 主 worker；不需扩大 Python lookup。该 recipe 不选择 Ninja、ALSA 或外部 test runner。
这只是官方 source/package 兼容性审查，没有发现另一个已知 PATH 缺口；不是本次每个 child 可执行文件路径/版本的实测证明或运行成功保证。所有原 identity、argv、flags、baseline byte bridges、resource/deadline guards 继续强制。

[失败 artifact13900090732](https://github.com/jiying2007/audio-pipeline/actions/runs/43118580272/artifacts/13900090732)：
- name：`frontend-research-dualmic-broadside-output-d8-43118580272-attempt-1`
- uploaded ZIP：473324911 bytes；SHA256 `d3baf9609ba2f0e9b3b2edb0b02f887694676014bb9fbac228bbf91e2f87e03a`
- upload log 报告65 files；API读取时 unexpired，expires_at `2027-02-09T23:16:45Z`。
- 完整 decoded job log 的 UTF-8（含 BOM）31995 bytes，SHA256 `5bae5b7ee07c855965203f40ebe152bd125e72bd105a1c83d5235b1a0e33dd2b`；不是压缩 log archive 的 hash。

第一次 run43115604725/artifact13897369988 的失败记录不变。本次仍是 engineering MEASUREMENT_INVALID，不是有效实验的 NO_ADVANCE，也没有候选质量、实际 compiler/CMake 版本或独立 artifact-content audit 结论。

## 10. 第三次执行失败及固定旧工件的只读诊断

第三次 [Research run43121241713](https://github.com/jiying2007/audio-pipeline/actions/runs/43121241713)，attempt1，head `4a86ad099010ae1aead149414091b88be73c7f3e`，D8 job130862020659，以退出码124结束。监督步骤从2026-11-11T23:37:45.4700590Z至23:45:35.3108263Z。这个退出码对应外部 supervisor 的 `D8_SUPERVISOR_TIMEOUT`，但原日志本身没有阶段定位；不能仅按总时长或文件数猜测发生位置。

原[artifact13900578432](https://github.com/jiying2007/audio-pipeline/actions/runs/43121241713/artifacts/13900578432)完整保留：
- 名称 `frontend-research-dualmic-broadside-output-d8-43121241713-attempt-1`。
- ZIP 543037811 bytes，SHA256 `d2744826ec842956b55610a7f33e905c1a17483f9d0c2b52fef7987356737ca5`。
- 上传1842文件，API读取时未过期，到期2027-02-09T23:37:28Z。
- 完整 decoded job log 的UTF-8（含BOM）31409 bytes，SHA256 `8998ef1cd4577d052f0b6636b426710c48aeeedc74d3ed48529a24d7bef4ba62`，不是压缩日志包哈希。

为了只读原失败收据而不重跑D8，独立审核的诊断提交 `f007e5192eb0c1e408701f288afa9d1b6d3e903e` 在单独的非main分支运行：[diagnostic run43126999200](https://github.com/jiying2007/audio-pipeline/actions/runs/43126999200)，job130881515035，attempt1。该诊断没有checkout、仓库代码导入、编译、测试、DSP或模型执行，只验证完整旧ZIP的下载及落盘重读哈希、ZIP元数据安全，并读取固定JSON收据。它没有修改PR #948或原工件。诊断成功不是科学尝试成功。

诊断核验1842个普通条目、中央目录209071 bytes、声明解压总量625011944 bytes，没有解压原语料、打开嵌套original.zip、读取音频/状态/构建二进制。142个命令收据均解析且模式有效，无损坏收据；日志投影和完整报告均保留每个被读收据的原始长度和SHA256。

实际最后持久化证据：
- admission phase记录PASS，elapsed_seconds=60.77153061800001。
- baseline-build记录PASS，elapsed_seconds=71.216371988；31个命令均terminal PASS。
- candidate-build记录PASS，elapsed_seconds=37.09195158；7个命令均terminal PASS。
- run phase的deadline=493.06856282，root_started=23.265672033，root_deadline=1223.265672033。阶段从monotonic193.06856282起计300秒。
- run有104个命令收据：103个terminal PASS、最后1个PENDING；phase.commands只持久化到第103个命令 `025-candidate-plain`。
- 最后的 `025-candidate-observed.command.json`（原长度4112，SHA256 `86b135cdfe6b2026f6694dfdaa72d5418be2323b2f8c57b56966a54d3b630e17`）为PENDING、returncode=null、初始status=FAIL、timed_out=false。其deadline与run phase相同，timeout_seconds=0.9795940239999936，按原deadline-timeout推得开始时刻492.088968796。
- 前一个 `025-candidate-plain` 为terminal PASS/returncode0，elapsed_seconds=1.4262467130000118。索引25在原冻结顺序对应 `A/pair-1-path-change-assistant`。
- analysis、verify、negative phase均不存在；run-index、report、seal、readback、negative-tests、summary、completion均不存在。first-failure不存在符合deadline fail-stop不补写终态收据的设计。

这支持“run phase预算耗尽，最后处于案例25 candidate-observed的未完成生命周期”，不证明该子进程具体在哪个函数或系统调用被杀。PENDING/初始FAIL不是算法失败；terminal command PASS写在COMMAND_END ACK之前，phase PASS写在finalizer/PHASE_END前。后续阶段的出现提供顺序佐证，但收据不是独立原始PCM/state二进制重算审计。没有完整矩阵或最终科学screen，结论仍为工程性MEASUREMENT_INVALID，不是NO_ADVANCE或质量提升。

逐行按原始monotonic字段复算的工程耗时：
- 103个成功科学命令收据的elapsed合计115.34253306899987秒。
- 78个同案例相邻命令之间，从前一收据的start+elapsed到后一start，合计98.42424527600005秒。
- 25个跨案例间隔同样计算，合计84.43524673400009秒。
这些区间包含不同的receipt/ACK、准备、inventory、预算检查，以及跨案例的原件/状态/算术/保留核验，不能当作纯DSP耗时或单独inventory profiling。

最新被实际读取且内容寻址身份一致的tool inventory为138300 bytes，SHA256 `b35d1f27e8081cafa943e8180f12ade3ed367d3597db5b6861727096be605def`，包含799个文件、233个目录、14241102个逻辑数据字节。原Phase.run在每次调用中执行3遍完整tool inventory，其中前两遍之间只有free-space只读查询；这是一项明确的相邻重复工作，但不能由此保证单独删除一遍就能让全60案例进入300秒。

诊断[artifact13903289018](https://github.com/jiying2007/audio-pipeline/actions/runs/43126999200/artifacts/13903289018)只含完成的报告：
- artifact ZIP31316 bytes，SHA256 `49b9cc95b731280e02876bbb85cc246e67a8bac39f815c191af2354235fff8d7`，expires_at2027-02-10T00:24:07Z。
- `report.json` 577819 bytes，SHA256 `c19429628302361b5255a5f10c0fc0a95f6a08e8eae24f0a1c75a212a21e52fb`。
- 完整decoded诊断job log 167069 UTF-8 bytes，SHA256 `17c31c446357c562c25c7b05705f7152f7fbfa88c58ea9dfa2ab5c4a877634a5`。
- 状态 `DIAGNOSTIC_RECEIPTS_ONLY_NO_DSP`；这不是候选算法的通过状态。

所有前两次失败、第三次原失败前缀、完整诊断来源以及科学范围限制保持不变。后续只允许独立审核的工程性能修正，不得换数据、减少病例/窗口、缓存掉实际变化、放松身份/预算核验、改阈值或延长300秒。

## 11. 不改科学定义的工程性能修正

此次修正由第10节实际失败触发，只解决受监督测量过程的重复文件遍历、路径分类和可观测性；不变更BF数学干预、C observer、四形态pipeline、Float32重构、原件桥接、评分/窗口/null规则、screen或候选数量。所有phase仍为300秒、普通child仍为min(30,remaining)、root仍为1200秒。未获得一次完整成功运行前，不承诺全60例能够完成。

- 每次inventory仍是新的实际测量，不维护跨调用的文件内容或元数据缓存。根及子目录通过dir-fd、O_DIRECTORY/O_NOFOLLOW/O_CLOEXEC逐层打开，内容模式的文件使用不阻塞的no-follow打开，再核对命名对象与opened/after fstat及实际读取字节数、SHA256。目录的成员相关元数据及命名绑定在成功返回前复核；这是封闭writer条件下的新鲜测量，不声称对任意恶意并发改写提供原子快照。根的祖先只检查绑定身份，不把无关/tmp活动引起的祖先时间变化误判为本树写入。
- metadata-only预算遍历保持实际no-follow stat、大小、类型、nlink检查；不为普通文件新增无用的打开或哈希。内容inventory仍逐文件读实际bytes/hash。两者不混同证据范围。目录迭代器在递归前关闭；绝对根与相对树合计最多48个目录分量（包含 / 根目录），使用原NOFILE限制，不能调高较严的继承限制。
- 返回路径顺序保持旧Path分量顺序；不是简单字符串排序。严格目标路径验证与原desc逻辑保留。实际before/after内容inventory、完整closure、原始输入、源和byte预算核验不能省略。
- 唯一删除的完整扫描是Phase.run中紧邻的重复：prepare_tool_environment已经完成并返回实际inventory，原代码丢弃后只查询free-space又扫描一次。改为使用该返回值，独立post-child扫描不变；有child、source写入或任何其他writer隔开的扫描均保留。完整科学矩阵因此由720遍减少到480遍。以最后观察到的14241102-byte树作条件示例，少读3417864480个逻辑字节；不是实测磁盘I/O或耗时预测。
- 静态分类只把冻结的60个两分量case key及合法tail建立精确查找，避免每个已测文件重复扫描60个字符串前缀；不缓存测量。路径前缀、未知tail、大小类别、scratch/ancillary预留和retirement语义保持一致。
- 命令receipt新增最多2048-byte、10个固定阶段、有界且可验证的累计monotonic子阶段计时；只描述准备/inventory、lease ACK、receipt、child与pipe、quiescence及预算核验等复合区间。它们不是纯DSP计时，且明确不包括最终receipt/phase重写、返回stdout读取及COMMAND_END ACK。科学receipt原65536-byte上限和总报告预算不变。
- 主Python worker只增加unbuffered输出，使既有准入输出及时可见；不改科学可执行文件、compiler flags、CMake recipe或任何PCM/metrics格式。supervisor只在现有最早截止仍有效时，将小型phase/临近截止标记送入已有非阻塞队列；phase转换后也包含transport_deadline。标记每行最多512 bytes、总量最多16 KiB，计入已有4 MiB合并输出上限及已有headroom。不得阻塞ACK、等待输出、延长期限或在fatal分支补写；调度不保证每个预警都能被发送。
- 新回归控制与固定76项科学negative类别分开标识。真实小型普通文件/目录变化验证新鲜哈希、大小、名称、类型和顺序；共享pure kind/identity/depth守卫验证合成的symlink/special/hardlink政策。generic inventory原有普通hardlink语义与budget nlink=1语义分开保留。不得为本次修正新增真实symlink/hardlink/FIFO的创建与失败清理例外。

这些是拟合并实现的边界，仍须完成精确源码审核及原门禁。其动机是减少已确认重复工作，不是把部分结果变成有效科学实验；第10节的失败与全部原工件继续保留。

## 12. 第四次执行：工程夹具别名错误，科学结果仍无效

第四次 [Research run43133029682](https://github.com/jiying2007/audio-pipeline/actions/runs/43133029682)，attempt1，head `a462a4edafbeda710184930413448ac80c173be4`，D8 job130901613906，实际最终结论failure。scope成功、历史研究jobs全部skipped、失败证据上传成功；没有在此把独立Verify workflow的状态混为科学通过。

新日志直接包含lease-live阶段标记，不必再按工件大小猜测进度。以下差值来自标记中保留六位小数的monotonic elapsed字段，属于受监督阶段的复合墙钟时间，不是单独DSP、哈希或compiler耗时，也不是完整命令receipt子计时的独立读取：
- admission：PHASE_BEGIN0.156314，PHASE_END34.833745，差值约34.677431秒。原D3 admission输出仍为 `INPUT_ADMITTED_NO_DSP_EXECUTION`、`original_D2_readback_exact=true`，其自身计时32.309167257秒，口径不同。
- baseline-build：34.842380至58.175624，约23.333244秒。
- candidate-build：58.184334至68.184192，约9.999858秒。
- run：68.192746至214.757478，约146.564732秒；PHASE_END时仍余153.435264秒。
- analysis：214.766298至279.232821，约64.466523秒。
- verify：279.241060至350.525433，约71.284373秒。
- negative从350.534125开始，没有成功的PHASE_END/FINISH。2026-11-12T01:21:35.2818692Z输出 `MEASUREMENT_INVALID`、reason `D8_NEGATIVE_ACCEPTED:before-dev`、type `ValueError`；随后退出125。

这些直接标记和实际控制流支持run、analysis、verify已结束，工程性能修正使本次run阶段在原300秒内完成；不保证其他机器/运行具有同样速度，也不代表整套验证完成。negative尚未通过，最终结果仍无效，不能发布NO_ADVANCE或提升结论。没有独立读取或重算本次artifact内的PCM、state、完整quality报告或命令子计时。

根因是测试夹具对象图，而不是实际identity guard放松：`engineering_inventory_validators`把pristine的before/opened/after/named四个字段都指向同一个 `actual` 字典。Python `copy.deepcopy`保留同一对象的别名关系，因此原拟定的 `before-dev` 单目标变化实际上同时改变四个row的dev，四者仍相等。production `check_inventory_identity`正确接受这组相等描述符；测试期望拒绝，遂报告 `D8_NEGATIVE_ACCEPTED`。这是源码语义与实际错误标签相符的诊断，不冒充已打开保存的mutant成员。

窄修正要求每个pristine row有独立字典，并对每个隔离mutant在持久化前及读回后核对精确、类型敏感的目标差异；对明确设计的all-negative-size多字段例外单独声明。旧共享别名形状作为有界回归夹具，必须被fixture隔离检查拒绝。审查其余新增工程controls及相似别名用法，不允许靠修改production guard、少测类别、隐藏mutation、放宽预算或改变science使测试通过。源码侧兼容性审查覆盖六组新增工程控制：真实目录/文件freshness及byte/path accounting、kind/depth/identity政策、1320个合法与480个非法category路径、timing前缀/finite/order/实际receipt绑定、marker期限/rounding/共享cap，以及AST重复/陈旧/写入边界控制。除已确认的identity别名外，未发现另一个具体的guard API、预期reason或fixture closure不一致；这不等于执行通过或保证negative阶段能在300秒内完成。此次修正仍须独立源码复核，所有新增或修正控制在再次运行前均为NOT_RUN。

原[artifact13906123706](https://github.com/jiying2007/audio-pipeline/actions/runs/43133029682/artifacts/13906123706)保留：
- 名称 `frontend-research-dualmic-broadside-output-d8-43133029682-attempt-1`。
- ZIP628448675 bytes，SHA256 `0fc87634747e586f49063c207f590bf6016fe6144cd49e25bcccffcda246c5db`。
- 上传日志报告3418文件，API读取时unexpired，到期2027-02-10T01:13:44Z。
- 完整decoded job log的UTF-8（含BOM）36211 bytes，SHA256 `16596e753c38ecb227a04f114c8df9c17b936385544d9b80463444334e361923`；不是压缩log archive的hash。
- artifact身份、大小、上传成功及文件数来自实际API/日志；本次没有独立member读取或原始二进制审计。

前三次失败、只读诊断以及本次无效结果不能被后续修正覆盖。原两臂四形态recipe、全部60例/窗口/原件桥接、科学screen、76个固定negative类别、R3合同、512MiB结果闭包、300/30/1200秒上限均保持不变。
