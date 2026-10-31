# F1-R2-T1：当前维护源码上的只构建接入

## 范围与前置

本项承接已合入的 F1-R2-T0（PR #874），对应 #845 评论 6542112186。
T0 的主线是 `f4ad623e30998f95d5066d3b55c210131df08148`，独立
Verify `41188493747` 和 Release `41190840827` 已完成。它只证明历史与当前
96 份依赖的关系，没有执行 F1 的进程 RSS 实验。

T1 将最新归档 `9ac5a209b16210c7e514d57711f22c9b27354cb8` 的三份 C 文件
及原私有 CMake 配方逐字节接入当前非安装研究目录。归档 Python qualifier、
R1 合同和源码锁不复制、不导入、不改写；既有 F0/B3 配方与产品源码不回退。
C 文件内部保留原 R1 名称与未执行说明，不将名称替换冒充新实验结果。

| 文件 | 原归档 Git blob |
| --- | --- |
| `fe09_t3s3_f1_rss_launcher.c` | `7059add3eb99d00ff0575c3e6e6cd4f1debf9ae8` |
| `fe09_t3s3_f1_rss_observer.c` | `e03c8f711ae2af0a1c3f8d9401e28cf097ea38cf` |
| `fe09_t3s3_f1_rss_fixture.c` | `ad994d6f7d15902c22aee76d4019e003b8e4f8cf` |
| `fe09_t3s3_f1_build/CMakeLists.txt` | `95d9b43f634ed40520b537da71efc0aa25399e9b` |

## 实际接入

新增 `tests/validation/frontend_evolution/fe09_f1_r2_build.py` 在导入受保护 T0
之前检查其固定 blob，并直接编译已校验字节，避免加载陈旧字节码。
T0 原检查仍验证 96 份历史依赖、9 份已审查维护文件和87份未变文件。
随后核对当前三份 C 和私有 CMake 与归档的 regular Git mode、blob 和正文一致。
结束后再次检查完整源码证明，源码变化拒绝构建通过。

| 构建 | 目标 | 静态检查 |
| --- | --- | --- |
| native | 原 plain、resource probe、launcher、fixture | ELF64/x86-64、编译单元和符号 |
| sanitized | 原 plain、resource probe | ASan/UBSan 编译选项、ELF64/x86-64、符号 |
| arm32 | 原 plain、resource probe | Cortex-A32/hard-float 编译、ELF32/ARM、符号 |

总计八个生成映像。编译数据库逐目标检查实际源码集合、重复/缺失成员、数值和警告
选项及 sanitizer 区别；launcher/fixture 只在 native 编译。对原两个目标要求链接
`main` 和 `__wrap_main`，对两个 helper 不要求包装入口。ELF 检查和 nm 是静态
检查，不运行生成程序。CMake 使用 `CMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY`。
脚本不调用 ctest、QEMU、launcher、fixture 或生成的 DSP 二进制；不联网或读取
provider 凭据。编译器、链接器及 CMake 本身必然执行，这不是零工具进程的声明。

## 运行与有界证据

需要完整、干净、包含所有历史对象的已提交 Git checkout；工具包括 CMake、GCC、
nm、`arm-linux-gnueabihf-gcc` 和 `arm-linux-gnueabihf-nm`。仓库既有固定摘要的 CI
镜像提供这些工具。正常 Verify 的既有 docs gate 在三种 Python 模式下运行离线
测试；只有 pinned-container `fast-code` 作业运行实际构建，不增加工作流或研究作业。

```sh
python3 tests/validation/frontend_evolution/test_fe09_f1_r2_build.py
python3 -O tests/validation/frontend_evolution/test_fe09_f1_r2_build.py
python3 -OO tests/validation/frontend_evolution/test_fe09_f1_r2_build.py
python3 tests/validation/frontend_evolution/fe09_f1_r2_build.py \
  --output /trusted/evidence/f1-r2-t1-new-build
```

输出父目录须已存在且由调用方控制；输出目录必须在源码树外，使用新的0700目录。
已有文件/目录不覆盖。工具环境不继承 token、编译选项、编译启动器或动态加载覆盖。
每条工具命令最多60秒（含0.5秒清理预留），合并stdout/stderr最多1MiB；进程组归
本次调用所有，失败时清理，不重试。构建工具阶段总预算480秒；原T0源码检查继续
使用其原有读取预算，不假装它包含在新工具阶段内。这些不是正式F1实验的时间预算。

工具版本日志、configure/build日志、实际compile_commands及nm输出保留在输出目录；
`receipt.json` 记录源码、工具文件/版本哈希、编译数据库、逐目标源码路径和ELF/符号
哈希，`receipt.json.sha256`核对回执字节。成功时同一回执写入CI日志；失败时写出拒绝回执及每份日志最多8KiB的诊断尾部，
最多19份，尾部不冒充完整日志。工作目录只在
该runner生命周期内存在，并非独立长期artifact。失败保留已产生文件及拒绝回执
（输出本身失败时可能不完整），不把缺失回执或旧目录当通过；构建错误不会自动重跑。
仅完整退出0及完整回执/校验文件才能认定该次构建检查成功。

## 不能据此宣布的完成

唯一正向状态为 `F1_R2_T1_BUILD_ONLY_NO_EXECUTION`。生成目标执行次数为0；
F1执行、provider授权、RSS测量、正式控制清单、完整未来F1源码闭包、shipping和
SSC305 HIL资格均为false。静态符号存在不证明运行时握手、故障清理或RSS正确。
编译器文件身份不等于完整sysroot/SKU资格；未遍历全部动态库或系统头依赖闭包。
原C实现的运行时审查和失败注入仍需完整后续控制，不因能编译而授予执行资格。

本地测试用合成编译数据库/ELF和普通临时子进程验证工程控制，不是八个真实F1映像
编译结果。实际三架构构建以精确PR及独立主线CI为准。后续R2 collector、完整接线、
178项规定控制、外部freeze、36进程/21600帧正式实验及原始证据回读仍未完成。
#845、#657及相关父项保持开放；#714、A3、公共四麦SDK和物理#58互不代替。

## English contract

T1 integrates four exact archived C/build files into a noninstalled current-source
build. The pinned T0 bridge proves source identity before and after compilation.
Native, ASan/UBSan and ARM32 modes produce eight images, with compile-unit,
flags, ELF and static-symbol checks. None of those generated images is executed.
This is not the formal F1 cohort, RSS evidence, runtime correctness, full future
source closure, SDK publication or device qualification. Missing tools/objects,
source drift, compile/link failure and incomplete evidence reject visibly.
