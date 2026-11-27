# WebRTC AEC3 参考工程 CI 与可迁移 bundle

本入口把[固定源码准入](WEBRTC_AEC3_SOURCE.zh-CN.md)和
[独立适配器工程测试](WEBRTC_AEC3_ADAPTER.zh-CN.md)接入既有
`.github/workflows/frontend-research.yml` 的单独 `webrtc-aec3-engineering` job。
**实现与小型回归本身不构成真实工程执行证据。实际状态统一见[平台运行手册](LONG_TERM_RESEARCH_PLATFORM.zh-CN.md)及其中的原始结果入口。**
实际结果以该 job 的精确提交、原始日志、`ci-receipt.json` 和 bundle 为准。
六例已披露语音对照由独立冻结合同在合格 bundle 上另行执行，不包含在这个 job 中。

## 历史实验隔离

新 AEC3 selector 放在原 D8 selector 前。AEC3 被选中时，明确输出
`d1/d3/d3_execute/d4/d5/d6/d7/d8/d8_archive=false` 并直接退出原选择逻辑。
混入历史实验、DSP 或其他未列明路径的改动会失败，不落入 D5/D6/D8 的旧执行分支。
手动选项只追加 `webrtc-aec3-engineering`，原选项和默认值保留。

入口覆盖新 `webrtc_*` / `test_webrtc_*` 文件、AEC3 源/实验 JSON、`WEBRTC_AEC3*`
文档、现有目录中的 `webrtc` 条目及新增 job。共享 `sources.json` 只允许改 `webrtc`
条目；Verify 只允许新增三个指定 tiny test 命令。运行手册的确切路径可随本工作包
集成，但它单独变更不会触发大型构建。既有 frontend README 只允许在顶端加入
确定的运行手册单行链接，不能借导航改动修改历史结论。

小型回归真实读取 Git 基线 `21448956f65916577d13082e9dc58f275f8fbb70`：

- 去除这次显式新增的接线与末尾 job 后，旧 workflow 全部字节保持一致，SHA256
  `d5dc866941cd9ca3cbae5a6dc5297b97115e903ca59573dd0a5a6c790a9e313f`。
- 从原 `matrix:` 到原文件末尾的全部 jobs 保持一致，SHA256
  `d1a75d946a6b3d7707f9943c075dfa0fb23dca33798bd06992c213c689611849`。
- 实际运行 scope 的 manual D8 选择器，只得到 `d8_archive=true`；全部 DSP 选择为
  false。该回归不执行任何 workflow 科学作业或 DSP。

## 受限工程流水线

`webrtc_aec3_ci.py run` 仅接受真实 GitHub Actions Linux / Ubuntu 24.04 / x86_64
环境，并要求指定的 40 位提交等于实际 HEAD，编排器、runner 和 fixture 与提交一致。
本地小型测试验证拒绝本地大型构建，不通过伪造 Actions 环境执行编译。

1. 从源锁 URL 显式下载三份源码归档，按固定大小限制读取并验证 SHA256，之后才调用
   唯一权威 `webrtc_aec3_source.preflight`。
2. 建临时 venv；按源锁的两份确切 wheel 版本及 SHA256 使用
   `pip download --require-hashes --no-deps --only-binary=:all:`。核对完整 wheel 文件集合、
   大小和哈希后，使用 `pip install --no-index --no-deps --require-hashes` 安装。
3. 只调用原 `webrtc_aec3_source.build` 构建参考库；保留其全部准入、无下载 wrap、
   源码前后复验和已提交控制文件检查。
4. 消费构建 receipt 的实际 C++ 编译器及 pkg-config flags，使用 C++17、`-Wall
   -Wextra -Werror` 编译自己的 runner。仅将第三方头路径的 `-I` 转为 `-isystem`，
   保留自己代码的严格告警；不改上游源文件。
5. 使用 `$ORIGIN/lib` 链接 runner。解析实际动态依赖，把构建目录内的 WebRTC/Abseil
   研究共享库按 SONAME 拷为普通文件。使用 `readelf` 拒绝绝对 RPATH/RUNPATH，
   移走原构建目录，再以 bundle 的 `bin/lib` 重新解析和运行真实工程 fixture。
6. 核验全部实际工程状态、音频/墙钟预算、源码、二进制、动态库和 runtime identity，
   然后创建文件级清单与保留执行权限的 tar.gz。

| 资源边界 | 固定上限 |
| --- | ---: |
| Actions job | 20 分钟 |
| 外层进程监督 | 1110 秒，超限 KILL |
| 编排内部总预算 | 1050 秒，包含打包终检 |
| 参考库构建 | 600 秒，parallel 2 |
| 自有 runner 编译 | 90 秒 |
| 工程 fixture | capture 音频合计 ≤10 秒，每条 ≤1 秒，实际报告墙钟 ≤120 秒 |

fixture 外层最多留 125 秒用于失败收尾，超过其 120 秒合同不能判工程 PASS。
不在超时后另换实现、改预算、跳过失败项或生成备用成功状态。

## Bundle 与真实运行环境

成功 archive 名为 `webrtc-aec3-engineering-bundle.tar.gz`，解到全新目录后根下即为
`bundle.json`、`bin/`、`prepared/`、`build/` 和 `engineering/`。
Actions 也保存对应原始 `bundle/` 目录、CI 日志和首次失败前缀。

| `bundle.paths` 字段 | 相对路径 |
| --- | --- |
| runner | `bin/webrtc-aec3-runner` |
| prepared | `prepared` |
| build_receipt | `build/build-receipt.json` |
| adapter_build | `build/runner-build.json` |
| engineering | `engineering/engineering.json` |

`bundle.json` 的 `files` 绑定所有其他普通文件的相对路径和 SHA256；清单不递归包含
自身。所有 bundle 文件都不能是符号链接或硬链接。源码 notices 保留在完整
`prepared/source` 中；原 source receipt 与 build receipt 保留各自阶段语义。

`runner-build.json` 绑定 `BUILT_ADAPTER`、code revision、runner/编排器源码、
实际 binary、source build receipt、编译器与命令数组，并将
`runtime_libraries` 记录为 `{ "bin/lib/SONAME": "sha256" }`。
实际工程报告再绑定 binary、fixture、共享 runtime helper 源码、source build receipt
和 code revision。开始及结束都读取同一套 runtime helper，变化即失败。

这是**在 Ubuntu 24.04 构建并实际测试、脱离原构建目录的研究 bundle**。
系统 libc、libm、libstdc++、libgcc、动态 loader 不复制；它们的实际路径、哈希及
宿主 system/machine/kernel/os-release 身份另行记录，不宣称跨发行版兼容。
`runtime_identity` 由共享的只读 helper 生成：

```text
system, machine, release, os_release_sha256
libraries: {resolved_absolute_path: sha256}
library_names: {SONAME: resolved_absolute_path}
```

迁移至另一 Linux 宿主后，先在 `LD_LIBRARY_PATH=<bundle>/bin/lib` 环境下对同一
binary 运行冻结 fixture，并记录该宿主自己的工程 receipt。只有实际成功且源码、
二进制、库及语料合同仍匹配，才可按另行冻结的合同开展语音对照。
CI 宿主的计时不移用为另一宿主的性能。

## 成功、失败与审计入口

只有实际 fixture 全部通过、最后源码/二进制/动态库复验和打包预算检查也通过，
才保留 `PASS_ENGINEERING_ONLY` bundle。后段打包失败或超时会撤销临时成功清单、
删除成功 archive 路径，保留 FAIL receipt 和实际诊断目录。
`always()` 使用现有固定 SHA 的 upload-artifact v7 保存结果或失败前缀。
编译成功、工程成功、真实语音描述性结果与算法效果晋升是独立证据，不相互替代。

普通 Verify fast-code 只运行：

```sh
python3 -B tests/validation/frontend_evolution/test_webrtc_aec3_source.py
python3 -B tests/validation/frontend_evolution/test_webrtc_aec3_ci.py
python3 -B tests/validation/frontend_evolution/test_webrtc_aec3_reference.py
```

这些是来源、selector、传输、复制/打包和失败边界测试，不下载/编译外部参考库，
不执行语音 DSP，也不生成真实 binary 的工程 PASS。
重编仅通过新增 Actions job；六例语音对照不接入本 job，也不因 workflow 修改重跑历史候选。

## 首次实际 CI 的共享库枚举失败

[run 46043193599](https://github.com/jiying2007/audio-pipeline/actions/runs/46043193599)
对应 head `1f5b6d0e0cbf18c10471a8629f26baa712e38199`。scope 成功，只有 AEC3 job
执行，全部历史 DSP 与 D8 archive jobs 均跳过。工程步骤在收集共享库身份时失败：
原 `*.so*` 枚举把 Meson 的 `libwebrtc-audio-processing-2.so.1.p/` 对象目录纳入文件
读取，触发 `IsADirectoryError`；失败前缀保存在 artifact `15220518270`。
该轮没有工程 PASS，也没有开始六例语音对照。

后继修复只要求枚举项同时为普通文件且不是符号链接，保留实际版本共享库并排除
对象目录。tiny 回归复现该目录形态以及仅有对象目录时的拒绝路径；不改源码归档、
编译/音频预算、算法配置或工程验收标准。修复后的实际结果仍须由新 head 的 Actions 产生。
