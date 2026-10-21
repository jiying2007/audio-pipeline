# A2-F0 R2：独立审查后的登记候选与最小工程划分

本目录只是尚未登记的预注册草案。此次只读源码/合同审查及元数据修订没有实施C/Python资格驱动、编译、运行新实验、创建issue、发送评论或修改远程。81个冻结原始输入不变；不改变原A0/A1完整来源依赖。以下工程文件只是后续授权后的最小计划，不是已经创建的实现。

## 本轮收敛决定

固定一次32→16退休可以在通用滚动之前单独验收。源停止、调用者独占、可信expected anchor由存活Python父协调器保有，范围仍只有hosted子进程恢复。原A0/A1缺prefix后继续拒绝；新A2 reader不依赖旧owner或退休PCM。目录dev/ino得到外部绑定，单文件inode跨exec连续性没有得到绑定，不能宣称已证明。

完整机器合同现在包含164个N-ID：157个目标C控制、5个Python receipt控制、2个Python source-lock控制；57个P-ID在两个固定profile执行；另有15个Python artifact完整性E-ID。每target每轮48+114+157=319个逻辑目标实例，四target两轮共2552。两进程协议加单独负例batch的计划启动数为325/suite、2600总启动，不与逻辑实例混算。所有数字都是预登记计划，尚无通过结果。

P01–P05固定为k0、空/part/同inode双链接状态，read与独立resume探测均拒绝；P06–P09固定final-only/k0，read不commit，resume做本次屏障再完成k16；第j次unlink三点k=j−1/j/j，P57不得新增unlink。P09在首次inventory前，P10在首次inventory完整验证后，控制流不同但盘面相同。SIGKILL由父在worker报告且阻塞后发出，等待真实signal退出后才能恢复。

新增四个有实质必要的callback控制：N161/N162只变一种原codec允许的XRUN flag及所需frame epoch；N163/N164只变Capture/PRESENT Render的FBS1 FNV。四例都保持完整32文件/k0，受控重封完整链和测试anchor，让原codec成功、旧A0与新A2分别命中相应callback约束拒绝；不允许用外层旧SHA或P0的旧A0早拒绝来替代新reader覆盖。

## 最小实现文件列表

相对路径基准是tests/validation/frontend_evolution/；原81文件原字节不动。

| 新文件 | 唯一责任 |
|---|---|
| fe09_b2s3_t3s2b1ba2_finite_retirement.h | 私有非安装A2状态、外部anchor、bounded workspace、独立prepare/read/resume接口和明确结果；无公共ABI |
| fe09_b2s3_t3s2b1ba2_finite_retirement.c | FPR1、独立FRM2/FBS1/retained验证、根先于unlink/本次fsync协议、新A2局部syscall/stat seam；复用冻结原codec与SHA/name API |
| fe09_b2s3_t3s2b1ba2_finite_retirement_test.c | 原第一方32帧fixture、transaction/recovery/negative-batch CLI、IPC barrier、真实namespace见证、测试专属清理；所有四target编译同一test TU |
| fe09_b2s3_t3s2b1ba2_finite_retirement_qualification.py | source/build身份、surviving coordinator、fresh exec、单调截止/流式日志限制、完整trace重算、四成员证据与隔离重封读回 |
| fe09_b2s3_t3s2b1ba2_frozen_inputs.json | 原81输入锁的逐字节候选；实施时还绑定实际checkout与新增A2输入身份 |
| fe09_b2s3_t3s2b1ba2_test_contract.json | 已登记的N/P/E机器合同，不能见结果后改 |
| FE09_T3S2B1B_A2_F0_FINITE_RETIREMENT.md | 已登记范围、冻结合同身份、限制和实际结果入口 |

只需修改两个既有接入点：.github/workflows/quality.yml增加同类受required summary约束的A2 job；.github/scripts/verify-docs-gate.sh增加新资格入口的metadata self-test。当前scripts/ci_impact.py:605–643已将tests/和.github/变更归入full路径；verify.yml:288–291复用quality，319以后summary依赖quality，无需新增workflow或为此放宽impact/summary。此判断来自只读代码，不是已运行的gate。

## 依赖和可复用结构

旧A1资格入口的identity/pins、严格JSON和SHA256/blob规则、compile flags、实际compiler/QEMU身份以及四成员读回结构可以复用。其SOURCES=(*a0.SOURCES[:-1], A1_SOURCE_C, A1_TEST)是已有闭包；新stage在明确列出的冻结闭包上仅加A2 C并替换最终test TU，不复制旧codec或改旧模块全局变量。保持两项已存在的旧文件warning例外边界，不扩散成全局警告关闭。

旧A1 `compile_plan()`在184–217行给出四target真实命令，ARM使用qemu-arm -L /usr/arm-linux-gnueabihf；`run()`在220–240行只是subprocess.run(capture_output=True)，只处理一个直接child且没有完整进程组收尾。它的`verify_execution_log()`在241–309行要求每target恰两次返回0的单JSON执行，不能直接用于A2多child与预期SIGKILL。新stage需要独立trace schema、Popen/IPC、流式输出上限及自有process group清理；保留其严格原件读回思想，不伪造旧validator已经支持fresh exec。

旧A1 C测试的339–360和402–404行只是同进程重新bind owner，没有fork/exec。A2必须由Python父重新启动目标；ARM每次显式启动qemu+同一ARM ELF，native TSan每次启动同一TSan ELF，不在TSan进程内fork后复用runtime。`close_fds=True`，仅允许当前标准流/控制IPC。恢复worker先read交报告，父明确发resume后关闭所有read fd、清空owner，再独立重开校验；不要求第三个进程。157个C负例一个进程串行新fixture；每例候选调用结束后IPC阻塞，父独立枚举/核对并明确确认后子才可清理并推进，进程数不变。Python的7+15项另计。

A1原fixture可借用确定性生成和setup辅助函数，但`teardown_a1()`在144–151行要求全部原始源未删，不能在A2退休后调用。A2需要自己的测试专属清理，发生于所有测量/receipt后、与候选unlink计数分离。正常transaction保留实际P0-bound旧owner快照只为旧reader拒绝对照；恢复进程不继承，不能伪造未绑定owner来凑拒绝。

## 30分钟/540秒预算的实际含义

每target只构建一次、同一ELF两轮，四target串行控制峰值内存。两轮只比较固定FPR1 raw digest/source身份/语义状态；实际dev/ino、fd、路径、PID及含这些值的anchor实例等归主机观测，每case内部仍绑定其原定anchor。每suite全部启动/等待/恢复/负例/清理共用540秒monotonic截止；collect含构建和八suite另有1500秒总截止，job硬1800秒，余300秒供读回/上传等步骤。每编译/工具命令上限120秒，child还受suite与collect剩余时间限制。因为8×540>1800，不能宣称单项timeout保证总完成；首次实际耗时仍未知。启动失败零自动retry，无隐藏skip/扩时；任何目标/第二轮不完整即NOT_ADMITTED并保留有界失败。

所有child stdout/stderr各≤64KiB、聚合collect.log≤16MiB同时流式限制；receipt≤4MiB、verify.log≤1MiB、ZIP≤32MiB。不能把无界capture_output后再检查称预算控制。对自有进程组超时清理并wait回收，预期SIGKILL和实际timeout/sanitizer错误分别记录。SIGKILL不会执行LSan正常退出检查；仅正常结束的sanitized workers获得该退出检查，不扩大声明。TSan虚拟映射不以64KiB或RLIMIT_AS错误代替显式A2 workspace测量。

## 注入与观察不能偷换

N108/N114只在新A2 seam把真实stat的st_dev/st_uid改为指定测试值，明确synthetic；不sudo/mount/chown。ENOSPC/EROFS/EMFILE不填满盘或耗尽runner fd。N131/N138先真实close一次，再注入EIO，fd已关闭不得retry；Linux close文档说明晚期错误仍可能已释放fd，重试有关闭复用fd的危险（https://man7.org/linux/man-pages/man2/close.2.html）。普通短读写正常循环，负例是明确partial+EIO/EOF。N141先真实删seq9再注入dirsync错误，必须保留k9/部分未提交。

失败C调用只报告自己实际知道的状态。N142初始扫描失败时runtime prefix未知，父仍独立核验真实k8和零新unlink。parent snapshot不是runtime knowledge。只有transaction真实旧owner存在时才测live ACK/head/tail；fresh recovery把父先前见证明确标为历史，live head/tail=null，并证明未接收/重造source owner、没有producer/ACK API调用和ACK权限。

## 实际阻塞与当前状态

无需新增物理设备即可实施这个有限host软件阶段；当前尚未授权开跑，先完成差异复核、登记精确合同和当时已经完成自身Verify/Release的protected main身份。预算能否完成四target真实执行仍待未来实验，不能预先承诺。整机冷启动权威、持续seq33/滚动复用、并发producer、same-UID恶意并发、实际NAND/UBIFS掉电是独立未解决事项，不应混入本child。

本轮检查只包括源码/合同阅读、JSON元数据一致性、N/P/E的唯一ID与count、FPR1字节/offset算术、81冻结输入的身份及whitespace；没有执行候选研究。历史A1独立ZIP读回来自已核验的#809 closeout，本次没有重复下载或重跑。

## 候选文件身份

- PREREGISTRATION.md SHA256: 1acb4be8295a9154e50a2f7912e59d47648c5972fc68acc9f8d8f59d06072e0f
- source-lock.json SHA256: df0801d5b32a9629bb54ce5f6db027039ea0f2101600a9ca8a1f7b1752ace73c
- test-contract.json SHA256: a0a957394425a3b2bf9d79c8762204e496867b8c386efe894e7e85a3af6dd67e

source-lock保持原字节；另外两件合同hash只在这次尚未登记、尚未实施的草案阶段改变。REVIEW_NOTES自身hash由交付消息给出，不在本文件中自引用。
