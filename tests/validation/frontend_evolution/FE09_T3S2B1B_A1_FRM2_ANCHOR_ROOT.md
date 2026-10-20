# FE09 T3-S2-B1b-A1：FRM2 原始来源左锚点根（不删除）

## 预先固定的假设与边界

预注册 [#809](https://github.com/jiying2007/audio-pipeline/issues/809) 的启动条件
已由 A0 #803 于 `2026-10-20T05:09:00Z` Closed/Completed 满足。直接来源固定为
`e3672ffe16e4c9d42a100e7712b9bbd3d8338545`，Verify `39274232480`，同 SHA
Release/Convergence `39284587954`，原始 A0 Artifact `12197835183`。
此处引用 A0 的已完成记录；本文件不制造 A1 的远程执行或合并回执。

在任何 A1 C 代码之前，`fe09_b2s3_t3s2b1ba1_frozen_inputs.json` 固定了
75 个原始输入的完整 Git blob、SHA256 和字节数，包括 A0 的冻结前驱和实际
编译源的本地头文件闭包。清单 SHA256 为
`babeac353b527cf2b342fa386f550c6ffcd542c47d32e44bc56b263a6dd10f08`。

假设：A0 的 32 个连续、不可变原始 APX3/FBS1 文件可以支持一个独立、不可覆写的
逻辑窗口 `17..32` 检查点，其左锚点是 **整个原始 seq16 的 200 字节 FBS1**
的 SHA256。根中保留 seq17..32 的原始完整行及 APX3 摘要；每次读取先、后调用
未修改的 A0 bind/inventory/S2 replay，且物理 seq1..32 始终存在。

这是独立的、非安装的 Linux hosted 研究代码。固定 B0/B1a FRM1 的零左锚点规则、
S1/S2/S2-A/A0 的代码与 APX3 codec、`src/`、`include/` 和 CMake 均不修改。
调用者只在 A0 完成 32 次原始 S1 ACK 后、来源停止追加时串行使用 A1；目录与 fd
仍由调用者独占。A1 不接管或推进 S1 tail，不创建 ACK，不删除原始来源文件。

## 固定的 FRM2 v2 窗口与事务

本阶段只接受 A0 cap=32、实际 high-water=32 的窗口 `17..32`；不是通用滚动
格式，也不允许不同窗口、根替换或多根竞争。格式是独立 FRM2 v2，所有数值显式
little-endian，固定 224 字节头及 16 个 72 字节成员，共 1376 字节。
头包含长度、source owner/generation、速率/麦克风/Render owner/slot、first/last/
high-water、非零 seq16 完整行 SHA、seq32 完整行 SHA、根 SHA 和严格保留字段。
根 SHA 覆盖整个 envelope，自身 32 字节字段计算时为零。成员按原始全局序号排列，
包含序号、完整原始行 SHA 和原始 APX3 SHA，不另造 FBS1 或 APX3 编解码器。

根目录使用独立的调用者 `O_DIRECTORY|O_NOFOLLOW` fd，并检查设备/inode、owner
和权限；拒绝来源目录别名。首次发布遵循 `O_EXCL .part -> 完整有界写 -> file
fsync -> linkat no-clobber -> unlink 临时名 -> directory fsync -> 独立重开读回`。
只允许删除本次根目录内的临时链接；禁止删除 A0 文件。失败保留已经发生的字节与
链接，不尝试掩盖半事务。任何孤立 `.part`、额外文件、硬链接或不同根均拒绝。

可见且字节正确的重启根只证明读取与来源对应，不证明旧发布执行过持久化屏障，
更不证明原始 ACK。读回回执必须把 `hosted_checkpoint_committed` 保持为 false。
显式重试同一根时重新 file/directory fsync 并独立读回，才可给出本次 hosted 根
检查点回执；仍不声明根与 S1 ACK 原子提交。发布后但目录尚未同步的故障必须
没有成功回执。Hosted fsync 不是 NAND/UBIFS 掉电资格。

## 预定验证与判定

固定 48 个来源场景：C1/C2-ULA/C4-ULA/C4-UCA × 16/32/48 kHz × Render owner
启用/禁用 × K1/K2；启用者在原始 32 帧内交替 PRESENT/ABSENT。所有场景都使用
原始第一方 writer、S1 drain、A0 sink、S2 CRC/replay/FNV 与完整行哈希链。
每次 A1 调用前后验证原始 S1 ACK/tail 未变化；原始文件计数与字节摘要保持一致。

强负例超过 100 个，包含伪造/零左锚点、seq16/17 与更早原始记录损坏或缺失、
身份/slot/Render/generation/epoch、重复/倒退/竞争根、schema/version/digest、
符号/硬链接、fd 被替换、孤立/短/额外字节和 ENOSPC/EROFS/EIO/短读写/fsync
阶段故障。故障只在本研究接口注入，不更改系统、原始模块或成功判定阈值。

Native、ASan+UBSan+LSan、ARM32/QEMU 与 TSan 每个真实 ELF 执行两次，科学
来源见证必须完全相同。工具缺失或环境失败不能被删去、抑制或计为通过。主机
资源实测单独归因，不与跨 ISA 的确定性科学字段混合，也不证明 SSC305 的
192 KiB、10 ms、真实 ADC/Render 时钟或 HIL。A1 原始四成员证据仍须独立完成
同运行上传读回、ZIP 和三个内部文件 SHA256 核验，以及精确 PR/main 的
Verify summary、Release/Convergence 后，才允许关闭 #809。A2 删除/滚动另行预注册。

## 源码检查点与当前执行状态

预先固定的格式和接受规则保持不变。新 C/H、原始来源 fixture 以及资格入口已实现；
首次严格 Native 编译实际执行了 48 个来源场景、462 个失败拒绝、51 次重启校验、
10 个独立事务故障。另一个负例用原始 APX3 writer 更改未保留的 row1，重新连接
全部 32 行且由未修改的 A0 bind 接受；A1 仍因固定的原始 source high-water 行
变化而拒绝。该次 Native 执行只是本地诊断，四目标资格尚未完成。

新 `collect.log` 使用 JSONL 原始调用记录。独立读回从日志逐条核对每个目标的
21 个原始 C 编译单元、链接命令、实际 ELF SHA256、两次成功执行的原始 stdout
及 stderr；重新计算 stdout SHA，并与逐场景结果和主机观测对应。仅在收据里
填写两条相同散列不能通过。编译器/ELF/QEMU 身份及已完成的执行在取得时立即
进入失败可保留的收据，后续目标失败不删除此前证据。

2026-10-20 本机现有系统工具为 ArmHF GCC 13.3、QEMU 8.2 和 binutils 2.42。
主矩阵沿用 A0 的 `-march=armv7-a -mfpu=neon-vfpv4 -mfloat-abi=hard`；QEMU
执行属于通用 AArch32 用户态仿真。每次收据记录实际命令、版本和工具文件 SHA；
这些名称或版本本身不构成 Cortex-A32 或 SSC305 目标硬件资格。
