# FE09 T3-S2-B1b-A2-F0：固定前缀退休与独立保留窗口恢复

状态：**供评审的预注册草案 R2，尚未创建 issue、实施源码或执行新实验。** 本次修订只把独立审查意见写成可执行判定合同；不是实验通过记录。
草案日期：2026-10-21（Asia/Shanghai）。父任务：#796 / #791；资源父任务 #767；直接已完成前驱 A0 #803、A1 #809。建议阶段标识 `FE09_T3_S2_B1B_A2_F0_FINITE_PREFIX_RETIREMENT`。

## 1. 唯一研究问题与有限闭环

假设 H：原始第一方 32 个连续 APX3/FBS1 文件在 A0/A1 完整验证、来源静止且调用者独占后，可以将 seq1..16 退休；只保留原始 seq17..32 的 PCM 文件、不可变 A1 FRM2 根及独立 A2 退休检查点，在**外部调用者提供固定检查点身份**的条件下完成 hosted 进程重启后的保留窗口验证和剩余退休操作，且不制造原始 ACK、不放宽旧 A0/A1 合同。

本阶段只进行一次 `1..32 → 17..32` 转换。成功结论是**有限前缀退休与固定窗口恢复**。它不完成长期滚动、seq33 写入、循环槽复用、持续采集期间 GC、源 generation 切换或全机重启自动发现权威根。后续真正滚动阶段仍须独立准入；#796/#791 不随 A2-F0 自动关闭。

明确可单独闭环：所有成功用例都达到完全相同的固定终态，故不必先实现通用滚动才能验证 unlink 顺序与重启恢复。但必须新建独立 A2 reader；不能把“A1 根可见”偷换成“A1 删除后仍有效”。

## 2. 直接源码依据：旧合同必须继续拒绝删除后的目录

已读源文件来自完整提交，不从 PR 候选自己提供的松散文件取得权威：

- `fe09_b2s3_t3s2b1ba0_finite_outboard.c` 的 `inventory()` 从 seq1 遍历到最高序号；缺少任一原始记录即拒绝，`valid_record()` 使用原始 `fe_s2_decode()` / `fe_s2_replay()`。
- `fe09_b2s3_t3s2b1ba1_anchor_root.c` 的 `a1_source_replay()` 调用未修改的 A0 bind，要求 cap=32、committed=32；A1 encode/read/verify 在原始行访问前后重放全部来源。
- A1 FRM2 1376 字节只保存 seq17..32 的行摘要/APX3 摘要、seq16 完整行的 SHA256 和 seq32 完整行 SHA256，**没有提供删除前缀后的独立读取权限或删除清单**。
- A0 的文件命名 API 最大 seq=32，且成功源消费已经结束；不能用该 API 或原 S1 owner 假装接着写 seq33。

因此 seq1 第一次被删除后，旧 A0 bind 与 A1 read/verify 必须依旧拒绝；A2 资格中将其作为必须通过的负向兼容对照。禁止修改旧源码、`#define`、测试、冻结输入清单或临时给旧 reader 提供伪造/隐藏的 seq1..16 文件。

## 3. 已完成前置与新的来源锁

A1 已通过 [PR #818](https://github.com/jiying2007/audio-pipeline/pull/818) 合并到 `c416a5f8e44b36a6af5be4dc53c71456dd6ba5ef`。该精确主线的 [Verify 39435091890](https://github.com/jiying2007/audio-pipeline/actions/runs/39435091890) 有 79 success、1 expected skip，required summary 成功；同 SHA [Release 39440540096](https://github.com/jiying2007/audio-pipeline/actions/runs/39440540096) 的 release/convergence 均成功。[#809](https://github.com/jiying2007/audio-pipeline/issues/809) 已 CLOSED completed，并登记原始 A1 Artifact 12272245576 的独立 ZIP/四成员读回。此草案核验了 live issue/run/job/Artifact 元数据，没有重复下载该 ZIP 或执行 A1 实验。

本草案的 `source-lock.json` 冻结 **81 个原始输入**：A1 既有冻结清单的 75 个输入加 A1 自身六文件。每个输入记录完整 Git blob SHA-1、SHA256、字节数。所有 81 个文件都与 c416 字节相同，并与本次审查快照 `01479d6b441f54ea1d68588155dc9742eaa96fbc` 的真实 Git blob 逐一比较相同。

新清单 SHA256：`df0801d5b32a9629bb54ce5f6db027039ea0f2101600a9ca8a1f7b1752ace73c`。原 A1 清单 SHA256 `babeac353b527cf2b342fa386f550c6ffcd542c47d32e44bc56b263a6dd10f08` 原样保留；A0 资格主线仍为 `e3672ffe16e4c9d42a100e7712b9bbd3d8338545`。

实施前还必须重新读取 then-current protected main 和 applicable full Verify/Release；将实际实现起点及原始检查证据登记后才能建实现分支。若 81 个冻结输入变化，停止并独立重新审查；不得自动重写 hash。01479 仅为本次源码审查快照，不在此声称它已经完成自身的主线门禁。

## 4. 数据、源 owner 与执行范围

仅使用现有第一方、已披露的确定性工程输入。固定 48 个 profile：C1、C2-ULA、C4-ULA、C4-UCA × 16/32/48 kHz × Render owner disabled/enabled × K1/K2。实际 slot map、source ID/generation、depth、PCM 公式和 PRESENT/ABSENT 交替方式来自已冻结 B0/A1 fixture，不按新结果选择。

每 profile 恰好 32 个源文件。复用原始 APX3 writer、S1 drain、A0 sink 的真实调用链及原始 FBS1 行；source role 为 `first-party-synthetic-disclosed-engineering-fixture`。现有 feeder 不等同于新跑 BF producer、真实 ADC 或真实声学实验，结果不得扩大成这些证据。

A2 进入时，来源已停止，S1 head=tail=32，无 producer、worker、sink 回调或继续消费/ACK/写入的旧 owner。head/tail 与原 owner 的检查只发生在 P0；fresh recovery 不接收旧 owner 来重做该检查。数据目录、原 A1 根目录、A2 检查点目录均由同一调用者独占，限定同一host文件系统，三个 inode 必须不同。A2 成功/失败都不更改 S1 head/tail、原始 source generation/epoch、BF 状态或已发生 ACK。调用者在 A2 接管后不再恢复旧 A0/A1 的业务生命周期。

资格测试唯一例外是正常 transaction worker 保存 P0 实际绑定成功的旧 A0/A1 只读快照，仅用来在退休后证明旧 API 拒绝缺前缀，再关闭/清除并退出。这个负向对照不能授予 A2 权限，也不是 A2 API 的依赖；fresh recovery 不继承它。不得用伪造的未绑定 owner 拒绝来替代这个对照。

允许新增：独立非安装 C/H、对应 deterministic fixture、独立资格入口、A2 说明和新输入锁；在既有 `quality.yml` 增加一个受 required summary 约束的 A2 job，并接入既有 docs 自测入口。禁止新增独立 workflow 控制器、公共 ABI、产品 `src/`/`include/`/CMake 变更、其他研究算法/阈值变更或收费资源。

## 5. 独立退休检查点 FPR1：保留来源证明，不保留已退休 PCM

建议冻结独立私有 FPR1 v1；**不扩展/重解释** FRM1、FRM2、FBS1 或 APX3。FPR1 固定 4768 字节：192 字节头 + 原始 FRM2 精确 1376 字节 + 原始 seq1..16 FBS1 精确 16×200 字节。退休行是只读复制的原始字节，不重建 FBS1，不保存退休 APX3/PCM。

| 偏移 | 大小 | 字段与固定值 |
|---|---:|---|
| 0 / 4 / 8 / 12 | 各 4 | magic `0x31525046`（FPR1）、version=1、header=192、total=4768 |
| 16 / 20 / 24 / 28 | 各 4 | embedded_root_bytes=1376、retired_count=16、retained_count=16、original_count=32 |
| 32 / 36 / 40 | 4 / 4 / 8 | capture_id、input_hz、source_generation；与 FRM2/原始行一致 |
| 48 / 56 / 64 / 72 / 80 | 各 8 | retired_first=1、retired_last=16、retained_first=17、retained_last=32、original_high_water=32 |
| 88..119 | 32 | SHA256（原始完整 FRM2 的 1376 字节）；不是 FRM2 的自摘要字段 |
| 120..151 | 32 | FPR1 自摘要：完整 4768 字节，将本字段置零后求 SHA256 |
| 152 / 160 / 168 | 各 8 | original、retained、retired 的原始 FBS1+APX3 逻辑字节总量；original=retained+retired |
| 176..191 | 16 | reserved，全零 |
| 192..1567 | 1376 | 原始 FRM2 逐字节原件 |
| 1568..4767 | 3200 | 原始 seq1..16 的完整 FBS1 行，严格顺序 |

全部整数 little-endian，拒绝短、长、非规范 reserved、溢出、乱序及重复。最终文件名固定 `fpr1-<capture_id:8hex>-<generation:16hex>-<self_digest:64hex>.bin`。对实际完整文件另算 `checkpoint_file_sha256=SHA256(4768 原字节)`，与“自摘要字段置零后计算”的值明确区分。

FPR1 的 retired FBS1 rows 可以重建每个允许删除的**原始规范文件名**及长度/SHA，并证明 seq1 零 prior → seq16 完整行 → FRM2 非零左锚点 → retained seq17..32 的行链。它保留的是元数据来源链；删除后不能再次读取或证明退休 PCM 字节仍在本地存在。

## 6. 恢复权威：禁止磁盘自授权

FPR1/FRM2 的自哈希不是签名，也不是先前 `fsync()` 成功的证明。任何磁盘文件和自身重算出的摘要都不能自行授予 unlink 权限。

最小 A2-F0 接口必须从可信调用者接收一个固定 expected anchor：`capture_id`、`source_generation`、原始数据/A1 root/A2 control 目录的设备及 inode 身份、`checkpoint_file_sha256`。首次完整来源验证并生成 FPR1 后，先把该身份返回给上层；只有上层显式把同一身份交回，才能发布检查点及退休文件。

本阶段进程重启实验使用**存活的未插桩 Python 父协调器**保有该 expected anchor，重新 exec 目标子进程并传入；不是父进程自身重启。新子进程不得继承旧 A0/A1/A2 owner、source/root/control fd、退休 PCM 或未验证内存。父只保有 expected anchor、摘要、元数据与当次进程控制句柄。缺失、全零、错误目录身份的 anchor 一律拒绝；当前已经绑定的 A2 owner 还必须拒绝之后传入的不同 anchor，且不能覆盖既有绑定（N004）。fresh child 不能凭空判断父未提供的历史 anchor，故不作该承诺。资格日志记录 anchor 在删除前交回确认的顺序。

expected anchor 是应用层准入条件；真实 `unlinkat()` 仍只使用现有调用 UID 对 caller-owned 目录的既有权限，不提权。该 anchor 没有保存每个文件的原 inode，故跨 exec 只保证三个目录身份、规范文件名、内容摘要、owner/mode/nlink 等元数据条件；不能识别子进程不运行期间同名同字节文件被替换为新 inode。操作内读取前后的可观察身份变化仍必须拒绝，不扩展成跨进程单文件 inode 连续性证明。

若未来产品要求整机断电后从同一可变目录自举出权威根，必须另行定义可信持久化锚点/目录权限与根选择协议；本阶段不解决它。单个 same-UID 恶意并发写入者破坏独占目录契约，也不在本阶段保证范围内；能观察到的目录/文件替换必须拒绝，不能宣称普通 POSIX 校验消除了任意 TOCTOU。

## 7. 必须保持的事务与恢复状态机

### P0：完整源准入，尚不删除

使用未修改的 A0 bind/replay 验证全部 32 文件；使用未修改 A1 publish/read/verify 建立原始 FRM2 根。读取原始 retired rows 前后再次做完整源验证。资格驱动在构建前逐项验证全部 81 个源码身份，C runtime 不读取源码仓库。runtime 验证源配置、所有行链、文件摘要与原始 codec replay 后生成新 FPR1。此阶段任何错误都保证零删除。

### P1：独立检查点先持久化

调用者 anchor 已交回确认后，使用第三个目录执行：`O_EXCL .part → 完整有界写 → file fsync → linkat no-clobber → unlink 临时名 → control directory fsync → 独立重开读回`。随后重新打开/核对 A1 根原件并执行本次 A1 file/directory fsync；这些步骤全部完成后才到 P08。禁止 rename 覆盖既有根。

进入第一次数据 unlink 前，FPR1/A1 根必须按 expected anchor 独立验证，原始数据目录仍是全部 32 文件，所有目录身份/权限仍一致。只看根文件存在、或从旧进程继承 `committed=true` 都不够。孤立/半写 `.part`、额外 root、不同 bytes 或同一操作内可观察的 inode 变化均拒绝；不自动清理不明现场。相同字节文件跨 exec 的 inode 连续性不在本合同内。

### P2：固定升序退休 1..16

每个 unlink 前独立枚举数据目录并验证唯一允许集合 `k+1..32`，其中 `k` 是已经缺失的连续前缀长度，0≤k≤16。所有 retained seq17..32 都必须存在且完整通过原始 codec/行链/摘要验证；所有仍存在 retired files 必须与 FPR1 原始 rows/规范文件名/长度/摘要一致。缺口只能是连续退休前缀；中间缺失、外来文件、重复路径或 retained 缺失一律拒绝。

只对下一项确切 seq=k+1 执行 `unlinkat`，随后 `fsync(data_dir)`，再次枚举并校验。文件必须为 caller-owned mode0600、nlink=1 regular file；拒绝 symlink、hardlink、FIFO、device、外来 uid、路径/目录别名及可观察到的 inode 替换。不删除 A1 根、FPR1、任何 retained file 或不在退休列表的名字。

若 unlink 成功而随后的目录 fsync 失败，必须返回 `PARTIAL_RETIREMENT_NOT_COMMITTED`，保留已经发生的缺失及诊断；**不能声称失败无副作用、不能重造旧文件或伪造回滚**。该状态不允许生成终态成功收据。失败收据只报告当次确已验证或自身成功操作可推出的观察；若 inventory/stat/read 尚未完成，`observed_prefix_known=false`，不能猜测 k。测试父协调器在故障后独立枚举真实缺失集合，用于核对副作用，不把该外部观察伪装成失败 C 调用已经知道的状态。

### P3：新进程 read / explicit resume

恢复的 `read` 只验证 expected anchor、两个不可变 root 和数据目录目前集合，报告 k；不自动删除，不认定旧进程执行过持久化屏障，不创建 ACK。

显式 `resume` 先对已验证 root/control/data 目录执行本次所需 fsync/reopen/readback，再按 P2 退休剩余前缀。即使 k=16，也要完成本次目录 fsync 和 retained replay 才可签发本次 hosted 终态。root 丢失、无法匹配 expected anchor 或 retained 文件不全时拒绝；不得从部分来源重新生成替代 root。

### P4：有限成功终态

数据目录恰好只含原始 seq17..32，16 个 APX3/FBS1 内容与删除前的原始见证一致；A1 root 与 FPR1 原件字节不变；退休前缀 APX3/PCM 不在任何被测数据/隐藏旁路备份目录中。父协调进程只可保有 expected anchor、摘要和元数据，不能在恢复时供应退休 PCM。旧 A0/A1 API 对该目录拒绝，独立 A2 reader 成功。

成功字段包含 `finite_prefix_retirement_completed=true`、`retained_original_files=16`、`retired_original_files=16`、`original_ack_created=false`、`retired_pcm_reverified_after_delete=false`、`continuous_rolling_qualified=false`、`cold_system_boot_authority_qualified=false`、`physical_powerloss_qualified=false`。记录实际逻辑字节退休量及文件系统观测值，不能把逻辑长度减小称为 NAND 实际空间/寿命收益。

## 8. 原始 codec 复用与独立验证

APX3 创建、CRC、decode、replay 必须调用冻结的 `fe_s2_writer_*`、`fe_s2_decode()`、`fe_s2_replay()`；SHA 使用原始 `fe_b1s1_sha256()`；原始文件名调用未修改 `fe_t3b1ba0_name()`。不重新实现 CRC/APX3 serializer/parser，不复制 DSP 或另造 evaluator。

A2 新代码只解析自身 FPR1、既有 FRM2/FBS1 元数据和目录协议，读取 FBS1 原始字节、检查自身行摘要与完整行 prior 链；它绝不写回或修补 FBS1。原 A0 的 `valid_record()` 是 private static、不能在删除后通过 A0 bind 间接复用；新 retained reader 必须明确保留全部原始 owner/slot/Render/global-local/CRC/PCM-FNV 约束，并在删除前用全部 48 profile 与未修改的原 A0 replay 做等价交叉检查。不能为了“复用”放开 static、增加模式开关或修改原 frozen 输入。

以下约束逐项保留，不用“codec 已通过”代替 owner 约束：

| 层 | 必须检查的固定条件 |
|---|---|
| source config | depth=2/4；mics=1/2/4；rate=16/32/48 kHz；Render enabled=0/1；capture ID>0；generation>0且非UINT64_MAX；enabled时Render ID非0且不同于capture，disabled时为0；active slots构成双射，inactive slots为UINT32_MAX |
| 原始FBS1 | magic/version/event；capture epoch=1；Render epoch在enabled时非0，否则0；ABSENT reason恰为FE_B1S0_ABSENT_SOURCE_REPORTED，其余0；global seq来自固定原始序号，local seq=1、frames=1；APX长度1..5120且文件长度恰200+n；无实际Render时Render FNV=0；前168B自摘要和完整200B行链摘要明确区分 |
| 原始APX3 decode/replay | 原codec检查format/CRC和exact total；rate/mics/实际Render/source IDs/epoch映射与原行一致；未知clock authority=0、timestamp validity=0；callback index=0、local seq=1、seen恰1、**capture_flags=0且render_flags=0**；Capture/Render字节数分别rate×mics/50、rate×实际Render/50；Capture及PRESENT Render的PCM-FNV分别与原行一致；无Render时指针为NULL且FNV=0 |
| 独立FRM2 reader | magic/version/header224/member72/total1376/count16/original32；全部source配置；first17/last32/high32；depth2/4、frame_ms10、frames1、rowbytes200、original32；212..223 reserved=0；自摘要将160..191清零；16 members严格17..32且行/APX摘要匹配；left=原row16完整200B SHA且非零，last=原row32完整行SHA |
| FPR1 totals | 从16个retired原行记载的长度和实际16个retained文件长度重新计算original/retained/retired三值及checked addition；只验证header的original=retained+retired不够 |

`fe_t3b1ba1_name()` 只做部分格式检查，不是独立 FRM2 validator。global seq17..32 不能从 APX3 local seq1 推断。原codec允许有语义的非零flags，因此专门冻结 N161/N162：分别只变一种XRUN flag及使原codec合法所需的对应frame epoch；原codec成功而原A0/新A2在零flags约束拒绝。完整受控重封的负例元数据不作真实来源资格，且不修改81个冻结源码输入。

## 9. 固定正向、负向与故障矩阵

**正向矩阵：**全部 48 profile，各32原始帧 → 原 A0/A1准入 → FPR1 → 正常顺序退休 → 新进程 read+显式 resume → 16保留文件逐帧 original replay。每目标完整跑两次，固定source身份、FPR1 raw digest、原始内容摘要及语义状态/计数逐字节一致。实际目录/文件dev/ino、fd编号、包含这些身份的anchor实例、PID、路径、elapsed/RSS等归主机观测，不要求新建fixture之间相等；每个case内部仍严格绑定同一父固定的实际anchor。正常 transaction worker 对仍存在的真实旧 source owner 做调用前后 ACK/head/tail 快照。fresh recovery 已没有该 owner，只记录父保有的先前见证、未接收/重造 source owner、未调用源 producer/ACK API、没有新 ACK 权限；它的 live head/tail 观测必须为空，不能把父传入的历史数值当作恢复后的实测。

**故障代表 profile：**C1/16k/Render disabled/K1 与 C4-UCA/48k/Render enabled/K2 两端，固定在看结果之前。对两个 profile 分别覆盖9个 root事务边界，以及16个unlink各自的“inventory完整验证后、成功后未dirsync、dirsync后”共48个边界，合计每profile57个进程终止点。它们是57个控制流注入点，部分具有相同盘面，不称57种独立盘面或统计独立观测。只模拟进程终止与 syscall 故障，不模拟断电。

机器合同为每个 P-ID 固定 root条目、size、nlink、数据缺失序号、read结果和resume副作用。共同要求：child到达指定点后报告ID并阻塞，父核对标记后发SIGKILL，等待真实signal退出并回收，才启动fresh recovery；通知后继续执行、普通返回错误或只有marker没有wait证据都不算进程终止资格。

| 控制流点 | SIGKILL后应观察的A2 control盘面与k | fresh read / explicit resume |
|---|---|---|
| P01：完整P0准入且父已交回确认anchor，temp尚未创建 | 空；k=0 | 两者拒绝，零unlink，不再生成root |
| P02：temp创建；P03：完整写；P04：file fsync | 只有part；长度分别0/4768/4768，nlink=1；k=0 | 两者拒绝，保留现场，零unlink |
| P05：linkat之后、temp unlink之前 | part与final同inode、各nlink=2、4768B；k=0 | 两者拒绝，不自动删part或修改现场 |
| P06：temp unlink；P07：control dirsync；P08：两root重开验证及本次A1 sync；P09：retirement entry、首次inventory之前 | final-only，nlink=1；k=0 | read只观察且commit=false；resume完成本次sync/reopen/readback后到k=16 |
| 第j次unlink的三点，j=1..16 | final-only；k依次j−1/j/j | read不删除、不推断旧fsync；resume做本次屏障并仅删剩余16−k项 |
| P57：seq16 dirsync之后 | final-only；k=16 | resume新增unlink恰0，仍做本次sync与retained replay才可成功 |

P09 是首次 retirement inventory 之前；P10 是首次 inventory 已完整验证之后、seq1 unlink之前。两点控制流不同、盘面相同。P01–P05的read拒绝后，只允许父明确发起独立重绑定的resume拒绝探测，不能继续发布/修复root。这些盘面期望只适用于同一存活host文件系统上的进程SIGKILL；不推断断电后的落盘状态。

**164个具有独立ID的负向控制**在 `test-contract.json` 逐项固定，其中157个属于目标C，5个属于Python收据读回，2个属于Python源码锁检查。另有15个独立E-ID，落实原已承诺的artifact来源/执行完整性拒绝要求。该文件是未执行的输入/判定合同，不是测试代码或通过记录。不能看到结果后删减类别或仅修改计数来满足门槛：

| ID 范围 | 数量 | 固定故障族 |
|---|---:|---|
| N001–N024 | 24 | 缺失/零/错误/变化expected anchor；重封装FPR1/FRM2仍不匹配固定外部身份；长度、版本、magic、计数、范围、保留位、摘要类型混淆、加法溢出等独立字段 |
| N025–N056 | 32 | 对16个retired序号分别执行“首次完整准入前缺失”与“原始内容改变/规范身份不符”两类负例；不能提前接受旧前缀已经被不明删除的输入 |
| N057–N088 | 32 | 对16个retained序号分别执行缺失与篡改；包含CRC重算但固定源SHA/FNV不符，任何时候都不得删下一项 |
| N089–N104 | 16 | source ID/generation/rate/mics/Render owner/event/epoch/reason/slots、global-local sequence、whole-row左锚点及末行、高水位/反向范围漂移 |
| N105–N120 | 16 | 数据/根/控制目录别名或替换、foreign inode/uid/mode、symbolic/hard links、extra files、多根、非连续缺失前缀、未知临时文件、特殊文件 |
| N121–N144 | 24 | root/create/write/read/link/unlink/file-sync/dir-sync与data/open/read/stat/unlink/dir-sync中的有界EIO/EROFS/ENOSPC/短读写/关闭失败；保留真实部分副作用 |
| N145–N160 | 16 | 无quiescence/有未ACK源、请求seq0/33或窗口变化、原A0/A1删除后拒绝、不允许第二次新窗口、无外部anchor的“恢复”、谎称删除后复验旧PCM、恢复自动生成ACK或权限字段漂移 |
| N161–N162 | 2 | capture_flags / render_flags各自非零但原codec合法；受控重封后原A0与新A2必须命中各自零flags拒绝 |
| N163–N164 | 2 | APX3与PCM不变，仅改Capture / PRESENT Render的FBS1 FNV；受控重封后原A0与新A2必须命中各自PCM-FNV callback拒绝 |

每例冻结layer/phase、profile、initial k、mutation字段偏移或syscall occurrence、outer hash策略、命中的拒绝类、父独立观察的缺失集合、允许新增unlink数及前后快照。`retained_bytes_unchanged` 对比故障注入完成后的调用前快照；另外保留注入前原始摘要证明变异命中，避免故意删改retained的用例与“未变”断言矛盾。失败C调用无法完整观察时应报告unknown；父的独立盘面事实不替它制造known k。

结构负例明确修复非目标外层hash、受控expected digest和规范文件名，让内层validator实际执行；N020保留故意错误的self字段，N021修复外层但故意错误的embedded raw hash。它们是明确标注的解析测试输入，不是可信来源。N024则保留原caller anchor，重封装后必须先在外部raw digest层拒绝。元数据语义负例同时用原A0对完整来源的拒绝作对照，不能让旧文件名/旧hash的早期拒绝冒充目标分支。

N161/N162保持k=0、全部32文件在场。N161用C1/Render disabled的seq17，经原writer产生capture XRUN=8、该frame capture epoch=2，header capture epoch仍1；N162用C4-UCA/Render enabled的seq17（PRESENT），只将render XRUN=8及该frame render epoch=2，header render epoch仍1。两例分别完整更新APX摘要、FBS1自身/后续整行链、规范文件名、FRM2成员/末锚/self及FPR1各层hash和受控anchor；原codec decode/宽容visitor replay必须成功，原A0及A2独立reader分别在零flags约束拒绝、零unlink。不能先经P0的原A0拒绝就声称新A2已检查该分支，也不能使用要求双流成对reset的CLOCK_RESET来混入其他故障。

N163/N164同样保持k=0及完整32文件，只将seq17的FBS1 Capture FNV（+72）或PRESENT Render FNV（+80）分别XOR1，原APX3/PCM及所有flags保持原样。完整重封同一元数据链与受控anchor后，原codec成功，原A0与独立A2分别在对应PCM-FNV callback拒绝，零unlink。N073–N088的原root SHA拒绝以及N104的无Render零FNV规则不能代替这两个分支。

N108跨设备与N114 foreign UID用新A2的可审计stat seam仅改变指定观察字段；不要求root、mount或chown。N121–N144明确实际syscall是否发生、path/phase/ordinal和注入errno；N124是先真实写2384B再EIO，N130是先真实读2384B再EOF，不能把普通短读写当必失败。N131/N138先真实close一次再返回EIO，fd已关闭，禁止重试close。N141从k=8真实unlink seq9成功后注入dirsync EIO，终态k=9、零seq10删除且PARTIAL_RETIREMENT_NOT_COMMITTED。EMFILE不靠耗尽runner资源；FIFO负例必须在读取前拒绝，不得阻塞。注入errno不能称真实设备故障。

N121–N128的调用前control为空，允许的部分发布现场逐项固定；N129–N133则在setup已经发布final-only之后，只调用登记的独立readback/本次A1屏障操作，故其失败操作必须保持调用前namespace不变。不能把从空目录开始的整个publication误算作这几个“未变”用例。

N154–157/N160的5项收据控制、N158/N159的2项源码锁控制只在隔离副本上重封装，不能伪称目标C执行。E01–E15分别检查错误source commit、替换原codec/source闭包、缺target、缺第二轮、关闭sanitizer编译/链接/环境、QEMU或ELF替换、rebind冒exec、无SIGKILL wait、错误P盘面、缺恢复阶段、隐藏重试、越预算和重复ID掩盖缺项。全部按外部可信CI/run与独立原始ZIP核验；自哈希包不能认证自身执行来源。

同样源码必须在 Native、ASan+UBSan+LSan、ARM32/QEMU、native TSan 四目标真实构建并执行，每目标两次完整suite。每suite逻辑目标实例为48正向+114进程终止+157目标C负例=319，八suite合计2552；Python的7项N-ID与15项E-ID每完整evidence bundle另计，不乘四目标冒充目标覆盖。

### 9.1 fresh exec的最小工程模型

每个正向/进程终止case恰用两个目标进程。第一个transaction worker完成准入，等父交回anchor确认后工作，正常退出或在指定点被SIGKILL。第二个fresh recovery worker先read并把只读报告交给父；父核对没有副作用后，通过当次IPC明确要求resume或预登记的拒绝探测。恢复者必须先关闭read的全部fd、清空owner/暂存字节，再重新打开并独立验证同一固定anchor，不能复用read状态充当已提交权限。read与resume之间不要求第三次exec。

Python使用 `close_fds=True`，仅显式传递当次标准流/控制IPC，不传数据/root fd。native、sanitized、TSan各自启动对应已构建ELF；ARM每次明确启动 `qemu-arm -L /usr/arm-linux-gnueabihf <同一arm.elf>`，不依赖binfmt。目标C不从已运行的sanitizer进程fork、自exec或恢复旧内存。157个目标C负例在一个目标进程中串行、每例重新建立专属fixture。因此每suite计划启动(48+114)×2+1=325个目标进程，八suite2600次；这是启动数，不是逻辑用例数。

负例batch也有逐例IPC屏障：子进程在候选调用返回后报告case ID、结果、known/unknown状态及fixture位置，随后阻塞；父独立枚举核对盘面与副作用后明确回复，子才可清理这个fixture并推进下一例。不新增进程，也不允许父尚未观察就删除现场；等待时间计入同一suite/collect截止。

每target只编译/链接一次，同一ELF覆盖两suite；纯解析/metadata/IO负例批处理以减少TSan/QEMU启动成本。TSan等启动失败不自动重试，不关闭ASLR/检测器或加ignore来凑成功；所有启动、等待和清理计入原suite截止时间。正常退出的sanitized事务/恢复/负例进程检查LSan；被SIGKILL进程不能执行正常退出的泄漏检查，不声称其获得LSan终止后证明。每次编译、启动、marker、SIGKILL/wait、read、父resume命令、重新打开、观察和退出都保留有界原始证据，不能只复用上一轮hash。

## 10. 预先固定预算

| 项目 | 冻结上限与解释 |
|---|---|
| 单一fixture源文件 | 32个；每个≤200+5120=5320B，合计≤170240B。正常终态16个；不保留退休PCM备份 |
| 新检查点 | FPR1精确4768B；原FRM2精确1376B。发布临时副本单份；按inode和路径分别计数硬链接阶段 |
| 同时活动fixture盘面 | ≤1MiB（源、两个root、临时/故障现场）；用例串行，离开故障前先保存元数据证据再清理测试专属目录 |
| A2状态与工作缓冲 | 显式列出caller-owned状态、局部scratch和持久buffer；新增A2的静态/工作字节总额≤64KiB，不缓存32份PCM。原fixture、旧模块栈和进程RSS另行实测，不隐入该数 |
| 时间截止 | 单次编译/工具命令120秒；每target每轮**完整suite聚合**540秒，包含全部child startup/IPC/crash/recovery/清理；collect含四target编译与八suite的全局monotonic截止1500秒，job硬上限1800秒，余300秒留给读回/上传等步骤。child有效截止取suite及collect剩余时间的较小者，不因exec/故障重置 |
| 最终小证据包 | `receipt.json`≤4MiB、`collect.log`≤16MiB、`verify.log`≤1MiB，四成员ZIP≤32MiB，retention 30天；禁入原始PCM或整份测试目录 |
| 费用与新依赖 | 现有免费/自有资源、现有镜像和工具；C/Python stdlib，不新增paid服务或大语料下载 |

8×540=4320秒，故540秒单项上限本身并不证明30分钟能完成。全局截止负责限制资源，并不预先保证所有测试能通过；首次实测仍未知。任何目标、第二suite或case未完成都判失败，保留有界部分证据，终止/回收自有进程组；禁止动态skip、隐藏重试或扩大预算。单child stdout/stderr各≤64KiB且全局collect.log≤16MiB，流式读取同时受两者约束；溢出只保留标记清楚的失败前缀，不截断成成功日志。

这些是本有限host研究的保护预算，不是SSC305全机或实时预算。触顶后只能独立说明原因并重新登记。TSan/ASan虚拟地址空间不以64KiB或普通进程RLIMIT_AS伪装成目标内存；64KiB只约束清楚列出的新增A2状态/工作区。

## 11. 证据、准入与终态判定

在任何实现提交之前登记该范围、81输入锁、确定性profile与负例机器清单。新实施基线须为当时已完成自身主线门禁的protected main。旧81输入逐项不变、实际编译闭包和A2新增输入归属于执行checkout，source_commit绑定真实PR merge SHA或push SHA，不替换成历史c416。

复用既有 `SHA256SUMS / receipt.json / collect.log / verify.log` 四成员形式：保留每个实际编译/ELF/两次运行/进程终止点及恢复命令、源身份和失败；同运行上传下载后原件读回，再做不修改原件的重新封装负例。PR和distinct main各自取得原始ZIP，并独立计算ZIP与三个内部文件SHA256。

合并需要完整适用PR检查、required summary、live expected head/base、strict Ruleset 21804005、零未解决讨论、受保护expected-head squash；之后distinct main full Verify、same-SHA governed Release/convergence与原始A2 Artifact独立读回成功。该research阶段release-neutral，不制造新版本，不迁移E001。

唯一成功decision建议 `FE09_A2F0_FINITE_PREFIX_RETIREMENT_AND_ANCHORED_HOSTED_PROCESS_RECOVERY_ONLY`。若需要修改旧reader、从磁盘自身选择权威根、丢失retained bytes、依赖退休PCM备份、恢复造ACK或在预算内无法取得四目标证据，判 `FE09_A2F0_NOT_ADMITTED` 并保留失败。

可关闭的只有A2-F0 child。#796/#791/#767/#733及#58保留各自剩余工作。所有hardware/physical-powerloss/cold-system-boot/continuous-rolling/public-SDK/whole-device-memory/10ms-product资格字段保持false；已完成有限unlink这一事实可如实为true。

## 12. 登记前设计裁决与实施边界

1. 当前模型明确为存活Python父协调器保有可信anchor，目标子进程fresh exec/restart；整机重启仍须另开持久可信锚点设计。
2. FPR1保留3200B原始retired rows足以形成可独立检查的删除清单与完整seq16左锚点，并保持原行逐字节原件、有界、无旧PCM；不声称已证明绝对最小编码。
3. 新reader必须保留第8节完整元数据/FNV/零flags约束与FRM2逐字段验证；源锁、164个N-ID、57个P-ID及15个E-ID在登记前冻结。任何字节hash变化只允许发生于尚未登记/未实施的本草案修订，不得实施后看结果改合同。

此草案仍须差异复核并登记；当前授权只包括草案修订，尚未授权实现或新实验。最小实现文件和驱动复用边界另列于 `REVIEW_NOTES.md`，不改变本有限研究范围。
