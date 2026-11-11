# D8 broadside 输出：实现与证据边界

状态：**FIRST_ATTEMPT_MEASUREMENT_INVALID_BEFORE_BUILD**。首次已审核的 CI 尝试完成了原始 D3 输入准入，但在 D8 合同比较处停止，未进入构建、测试或 D8 DSP。此次失败及其证据保留在第 8 节；修正仍须独立 exact-head 复核后才可发布。生产版本、默认配置、API 与生产树不变。

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

实现准备和修正均只通过 GitHub 连接器写入 detached Git objects。首次经过独立 source review 的 CI 尝试已在构建前失败，详见第 8 节；未产生 D8 科学评分或候选改善结论。所有尚未执行的工程计数、预算与 scientific checks 仍是待验证要求。独立 source review、exact-head required checks、artifact 全闭包读回及新鲜 main 资格检查是不同证据，不能互相替代。本文件不作真实阵列、时钟、校准、ASR、听感或临床结论。

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
