# WebRTC AEC3 固定分发源码准入与构建

本入口落实 [#968](https://github.com/jiying2007/audio-pipeline/issues/968) 的外部参考工程：
**freedesktop `webrtc-audio-processing` 2.1，继承 M131 的 AudioProcessing 分发包**。
它提供 AEC3/APM 参考所需的固定源码、五类权利登记、无隐式下载构建和回读，
不代表最新原版 WebRTC，不产生语音效果、SSC305 性能、训练或产品结论。

## 身份与准入

上游项目为 [WebRTC](https://webrtc.googlesource.com/src/)，实际采用
[freedesktop 分发库](https://gitlab.freedesktop.org/pulseaudio/webrtc-audio-processing)。
分发 tag `v2.1` 的 commit 为 `846fe90a289f58b7c9303a635142aa2c7caa93e5`，
tree 为 `704db84e4285c0006ac8204dad2497fca3d27791`。
包内 `NEWS` 指明 2.0 更新至 M131，2.1 补充构建、头文件及 Windows 修补；
`UPDATING.md` 说明该包选择复制上游文件并维护手工改动。
因此不将分发 commit 写成 WebRTC 原版 commit，也不推定某个未核实的原版 M131 SHA。

源锁 [webrtc-aec3-source-lock.json](../../../.github/research/frontend-evolution-v1/webrtc-aec3-source-lock.json)
记录完整归档字节、文件清单摘要、Git tree、许可文件及补丁摘要。
[webrtc-aec3-admission.json](../../../.github/research/frontend-evolution-v1/webrtc-aec3-admission.json)
与现有 `sources.json` 的 `webrtc` 条目共用 `contracts.admit_execution`；
准入 scope 覆盖此固定分发版的离线参考构建、有界合成工程测试，以及另有执行前
exact-byte/权利/角色/预算合同的已披露参考语料。它不允许任意数据、参数搜索或效果晋升。
源码许可准入不替代真实语料的来源、权利、独立划分或声学实验合同。

| 本地输入归档 | 字节数 | SHA256 |
| --- | ---: | --- |
| `webrtc-audio-processing-2.1.tar.xz` | 604192 | `ae9302824b2038d394f10213cab05312c564a038434269f11dbf68f511f9f9fe` |
| `abseil-cpp-20240722.0.tar.gz` | 2242861 | `f50e5ac311a81382da7fa75b97310e4b9006474f9560ac46f54a9967f07d4ae3` |
| `abseil-cpp_20240722.0-3_patch.zip` | 5929 | `12dd8df1488a314c53e3751abd2750cf233b830651d168b6a9f15e7d0cf71f7b` |

下载地址以源锁为准。两个 Abseil 地址和哈希来自固定分发包的
`subprojects/abseil-cpp.wrap`，不跟随默认分支或 WrapDB 更新。
本地审查逐字比较了分发 tar 的全部 663 文件与分发 Git commit，文件集合和执行位一致；
从归档重建 Git tree 也一致。Abseil tar 的 1538 文件独立重建 tree 为
`7d7c3f8f2c41ec3a809d9f7985116f485da48c5d`；官方 GitHub API 将 `20240722.0`
解析到 `4447c7562e3bc702ade25105912dce503f0c4010`，这里只声明此 tag 观察和归档树，
不声称另做了 Abseil Git clone 的独立全树比对。

## 分开审阅的五类权利

| 类别 | 登记 | 本入口的具体范围 |
| --- | --- | --- |
| code | ALLOWED | 固定包 `COPYING`、`webrtc/LICENSE` 的 BSD 风格条款；保留 notices。`webrtc/PATENTS` 是有范围和终止条件的实现专属专利授权。 |
| dependencies | ALLOWED | 包内 rnnoise、pffft、ooura、spl_sqrt_floor、fft notices；Abseil `LICENSE` 为 Apache-2.0，官方 wrap 的 `LICENSE.build` 为 MIT。宿主 C/C++、libm、threads、可选 librt/libatomic 记录实际工具链。 |
| weights | ALLOWED | 仅包内 `rnnoise/src/rnn_vad_weights.cc/.h` 的编译期参数及其 `COPYING`。没有另行获取权重，不能扩大为任意模型的许可。 |
| data | NOT_APPLICABLE | 没有准入语音训练集或真实评测语料；源包内依赖测试文件不是音频语料授权。 |
| redistribution | ALLOWED | 保留源锁列出的许可证、版权、专利声明，遵守 Apache-2.0 的 notices/改动说明和 MIT 条件；不授予背书或产品发布权。 |

准备器保留全部 notice 文件。研究证据包若携带源码或二进制，应随附这些通知；
不能只带单个 `COPYING` 就省略嵌入依赖的条件。构建工具的 Meson 1.5.2 和
Ninja Python 包 1.11.1.1 独立安装于临时虚拟环境，其 wheel 身份写入源锁，
不是新增产品运行依赖；Meson COPYING 与 Ninja 所附 Apache-2.0 文本已核对。

分发包的 `patches/` 原样保存以下七份补丁，**不重新应用**：

- `0001-AECM-MIPS-Use-uintptr_t-for-pointer-arithmetic.patch`
- `0001-Add-support-for-BSD-systems.patch`
- `0001-Allow-disabling-inline-SSE.patch`
- `0001-Fix-up-XMM-intrinsics-usage-on-MSVC.patch`
- `0001-Some-fixes-for-MinGW.patch`
- `0001-common_audio-Add-MIPS_DSP_R1_LE-guard-for-vector-sca.patch`
- `0001-meson-Fixes-for-MSVC-build.patch`

官方 Abseil wrap patch 只添加 `LICENSE.build` 和 `meson.build`，不覆盖已有文件。
准备后的 source 含 2203 文件、14541954 字节，按路径、大小、Git 执行位、SHA256、
Git blob SHA1 构成的规范 JSON 清单 SHA256 为
`b353d20bbe718987c22d3aa338a3e1ee49af654b840259954680b2377c9b89fc`。
这不是 tar 的哈希，不能互换。

## 准备、回读与构建

先由显式下载步骤准备三份原始归档，使用源锁 URL、大小及 SHA256 检查。
工具本身只读取本地归档，拒绝符号/硬链接、特殊文件、穿越/重复路径、错误根目录、
超界成员、文件覆盖、错误清单和错误 tree。全部归档验证通过后才写入全新输出。
归档目录、准备目录及构建目录互不包含，构建目录还须在项目 checkout 外。

以下变量指向操作者选定的临时工作区；必须使用尚不存在的准备/构建目录。

```sh
python3 tests/validation/frontend_evolution/webrtc_aec3_source.py preflight \
  --archives-dir "$archive_dir" --output "$prepared_dir"
python3 tests/validation/frontend_evolution/webrtc_aec3_source.py verify \
  --prepared "$prepared_dir"
```

输出 `source/`、`files.json` 和 `source-receipt.json`。成功状态
`SOURCE_BYTES_VERIFIED_NOT_BUILT` 仅证明固定源码字节可回读。
verify 对完整文件集合、大小、执行位和内容重新计算，不信任可修改 receipt 的自述。

在执行 Meson 前先提交源码锁、admission、catalog、构建器和现有 contracts helper；`build` 要求这些路径
与当前 Git HEAD 的原字节相同并记录该 commit/tree，未提交的准入不能运行构建。
Meson 需要 1.5.2，Ninja Python wheel 为 1.11.1.1，其二进制版本输出为
`1.11.1.git.kitware.jobserver-1`。只在临时 venv 安装，禁止全局安装。
CI 可先以 `pip download --require-hashes --no-deps --only-binary=:all:` 按源锁下载
固定 wheel，再以 `pip install --no-index --no-deps` 从已验证 wheel 安装；
不要在配置或编译阶段安装依赖。

```sh
python3 tests/validation/frontend_evolution/webrtc_aec3_source.py build-plan \
  --prepared "$prepared_dir" --build-dir "$build_dir" \
  --meson "$tool_env/bin/meson"
python3 tests/validation/frontend_evolution/webrtc_aec3_source.py build \
  --prepared "$prepared_dir" --build-dir "$build_dir" \
  --meson "$tool_env/bin/meson" --ninja "$tool_env/bin/ninja"
```

固定 setup 使用 `--wrap-mode=nodownload --force-fallback-for=abseil-cpp`，
强制使用已验证 Abseil，阻止意外采用宿主 absl 或网络 fallback。
其他固定选项为 Ninja backend、release、shared、C++17。
只编译 `webrtc-audio-processing-2` 目标；不执行上游 `run-offline` 或任何音频。
总墙钟预算 600 秒，编译并行数 2，超时终止整个构建进程组，失败日志保留。
该预算是参考工程资源限制，不是语音质量阈值。宿主构建不构成 SSC305 兼容或性能证据。

`build-receipt.json` 保留源码 receipt、已提交控制文件、真实工具版本/哈希、
setup/compile 命令与退出码、耗时、日志摘要和成功后的链接信息。
build 完成后重新核验准备源树；意外源码写入会使构建失败。
成功状态 `BUILT_FIXED_REFERENCE_NO_ACOUSTIC_MEASUREMENT` 不改变原源码 receipt
的 `NOT_BUILT` 历史语义。失败保持 `BUILD_FAILED`，不生成音质 PASS。

适配器编译应消费 receipt 中的 `link.pkgconfig_dir`、`pkgconfig_module`、`cflags`、
`libs`、源头文件/Abseil 路径和真实共享库身份；优先使用 Meson 自动生成的 uninstalled
pkg-config 文件，不安装到系统。适配器自身、10 ms 配置、通道映射、时间/延迟语义及
synthetic tinyfixture 由独立合同与文件承担，不能由此构建结果推导 AEC3 效果。

## 小型回归与现状

```sh
python3 tests/validation/frontend_evolution/test_webrtc_aec3_source.py
python3 tests/validation/frontend_evolution/test_contracts.py
```

小型测试只使用临时合成归档，覆盖 hash/大小/tree、危险路径、重复、链接/特殊文件、
覆盖、源漂移、准入记录、缺字段和构建路径边界；不伪造第三方实验、原始录音或真机结果。
首轮源码准入先冻结为 commit `14ccc75a8131e3a593b4211173ac01a14b5ac23d`，随后实际
执行仅 configure：Meson 1.5.2、Ninja `1.11.1.git.kitware.jobserver-1`、GNU C/C++ 14.2.0，
成功退出 0，耗时 1.216694498 秒，完整源树复验通过，compile 和 acoustic 均为 NOT_RUN。
此观测保存在 [configure receipt](WEBRTC_AEC3_SOURCE_CONFIGURE_20261128.json)。
确认自动生成的 uninstalled pkg-config 名为 `webrtc-audio-processing-2-uninstalled`，
共享库目标位于 `meson/webrtc/modules/audio_processing/libwebrtc-audio-processing-2.so.1`。
configure 包含编译器能力探针，不是整个库编译、运行 AEC3 或质量评测。

后继源码准入将 scope 增补为另有冻结合同的已披露参考语料，并将现有 `contracts.py`
加入执行控制文件身份。这不会改变三份归档及 2203 文件清单；旧 configure receipt
仍对应原 commit/源锁。新源锁 SHA 不接受旧 prepared receipt，须 fresh preflight，
不得改写旧 receipt 的 SHA 来复用。

上述源码准入与 configure-only 回执本身不证明大规模 C++ 构建或声学处理。实际 CI 构建和后续适配器
回放必须各自保存精确提交、失败、日志与结果；不能把计划状态改写成实际结果。

Meson 参数语义见官方 [Subprojects](https://mesonbuild.com/Subprojects.html)
与 [Commands](https://mesonbuild.com/Commands.html)。依赖许可和分发声明以本次冻结的
源文件为权威，后续 upstream README 或许可证变化不自动重判既有冻结版本。

实际执行状态统一见[长期平台运行手册的本轮结果入口](LONG_TERM_RESEARCH_PLATFORM.zh-CN.md)。
