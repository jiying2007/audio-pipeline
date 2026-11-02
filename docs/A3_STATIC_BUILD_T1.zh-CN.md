# FE09 A3-R2-T1：归档 C 源码对象级编译接入

**阶段目标：原始 A3 C 源码在当前主线的静态可编译性。不是运行资格或实验结果。**

前置独立来源核验为 [PR #878](https://github.com/jiying2007/audio-pipeline/pull/878)，
合并主线 `61f178ba681620e1c6a1f6403aedbd3905c14cf4`，
原始 88 份历史源码逐一验证 Git blob、size、SHA-256，当前 88 份相同。
当前完整 Git tree 不等于历史 Git tree；禁止用 88/88 推导全仓源码等同。
此次 T1 只读调用并固定 T0 的代码身份，不改变 T0 或原 R1 文件。

## 固定的非安装原始源码

原始归档：`c4e9cb92af2fe42f09f09bcac0d0a814a511aab8`

| 文件 | 原归档 Git blob |
| --- | --- |
| `fe09_a3_f0_live_roll.c` | `3b79ca0681afd77e48d85fa0646ccea4fa744d62` |
| `fe09_a3_f0_live_roll.h` | `dff07def1aabcd2c1e3361e3f55f4050e4676cc1` |
| `fe09_a3_f0_original_validator.c` | `3d9af35bd4323716e43bc6d82e552a267a5905af` |

以 exact archived Git blob 直接复制文件，不改 C/h 正文。这里的 A3 源码仍处于
**非安装研究**路径。归档原始 `fe09_a3_f0_source_admission.py` 只是 T0 核验的数据，
不导入或执行；不存在 provider 授权、外部冻结、原 117 控制准入。

A3-T1 使用受保护的 A3-T0 核验器 Git blob
`d0dba25e0b01821577d21f02cb892336dd479548` 和
F1 已验收的有界工具进程清理器 Git blob
`a4f20160d024109ebc7cb1af7371c00f8acff82e`。
导入前验证原始字节，避免使用陈旧编译缓存或被修改的运行器。
编译前后独立重复 T0 全部历史源核对及当前三份 C/h 的 archive/worktree 字节检查。

## 对象级编译（没有链接、执行）

已有固定 CI 编译器镜像的 `fast-code` 执行四种构建，每种仅编译
两份 C translation units：native GCC、native Clang、GCC ASan/UBSan、
ARM32 Cortex-A32 hard-float，共 **8 个 ET_REL 对象文件**。
其中 original_validator C 原样包含锁定的 A0 `.c`；不能再单独把该 A0 编译一遍，
避免重复制同一翻译单元。所有命令都使用
`-c -std=c11 -O2 -fno-fast-math -ffp-contract=off -fno-lto
-fstack-usage -fno-common -Wall -Wextra -Wpedantic -Werror`，
固定包含当前 checkout 的 `src`、`include` 搜索路径，与原 B3-F0 非安装私有构建一致；不从外部参数接受头文件路径。
实际编译依赖的 `audio_pipeline/audio_pipeline_build.h` 是主仓 CMake `configure_file`
在构建目录 `generated/audio_pipeline/` 中生成的，不能手写伪造。每一种模式先
在新的临时 SDK 配置目录调用原始 `cmake -S root -B ...`，关闭测试／benchmark／
examples／Linux runtime，并用 `CMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY`
避免在编译器资格探测时运行生成程序。按照当前主仓 CMake 原规则保留
`AP_BUILD_MAX_MIC_CHANNELS=2`、fast-math OFF；这只约束公共 SDK 的配置头，
**并不声称原始私有 A3 四麦来源获得公开 SDK 资格**。验证真实生成头中的
`v2.3.61`、编译配置、fast-math 与模式字段，记录 SHA-256，随后把该目录加入
`-I` 编译选项。CMake 配置本身可能运行 CMake/编译器及编译静态探测对象，
不会运行或链接 A3 目标。
无链接、无运行输出文件、无 `ctest` / QEMU / A3 worker / 原始 DSP 程序。
ARM 编译仅证明交叉编译接受源码，不证明实际 SSC305 的资源占用或设备运行。

对象文件只在已有 runner 的临时目录生成，使用新建 0700 输出目录，
不覆盖旧证据。读取 ELF 的 ET_REL/type/class/machine、精确字节 SHA-256、
编译器原文件/版本 SHA、编译选项及工具原始日志。工具调用按固定 60 秒及整个
420 秒预算清理进程组，不携带 GH_TOKEN 或其它 credential。真实失败
输出拒绝回执和每个最多 4096 字节诊断尾部；尾部不是完整日志，也不能作为通过证据。
一个成功的 T1 receipt 仍将全部实验、外部 source、RSS、SDK、HIL、shipping 资格置 `false`。

## 执行及退出

```sh
python3 tests/validation/frontend_evolution/test_fe09_a3_r2_static_build.py
python3 -O tests/validation/frontend_evolution/test_fe09_a3_r2_static_build.py
python3 -OO tests/validation/frontend_evolution/test_fe09_a3_r2_static_build.py
python3 tests/validation/frontend_evolution/fe09_a3_r2_static_build.py \
  --output /trusted/existing-parent/a3-t1-new-object-build
```

第四条要求真实 checkout、已存在且有权限的输出父目录和既有固定编译器；
在当前 Verify 中只由 `fast-code` 执行，普通 docs gate 运行离线测试。
离线单元夹具仅合成 ELF/object，不执行任何 A3 C；不能代替真正 CI 编译。

成功状态应为 `A3_R2_T1_STATIC_OBJECTS_ONLY_NO_EXECUTION`。
后续 T2 必须单独审查 A3 运行时原协议与缺失的 driver、collector、来源导入，
在具备原 R1 external PRE/POST freeze 后才能启动实际 33–49 滚动实验，
不因八个编译目标存在而关闭 #847 / #657。#845 F1、#714 M2/M3、
#511 发布凭据和 #58 实机准入仍独立。

## English contract

T1 imports the three exact archived A3 C/header Git blobs and compiles
two C translation units to eight **unlinked, unexecuted ET_REL objects**.
Protected T0 original-source audit and worktree/archive byte identity are
required before and after compilation. Outputs prove only compiler acceptance,
not runtime function, memory/RSS measurement, scientific control completion,
external provider/freezing authority, public API/ABI or shipping qualification.
