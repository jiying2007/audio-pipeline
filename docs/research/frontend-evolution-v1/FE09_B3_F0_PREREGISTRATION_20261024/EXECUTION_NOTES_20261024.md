# B3-F0 执行记录与编译器路径修正

本页在首次执行之后新增，不改写冻结合同、输入真值、来源锁或旧结果。
固定研究身份仍为 `FE09-B3-F0-C4-16K-RENDER-PAP-V1`。

## 首次本地执行

源码 `d0d3c8a2bee898e02833e61ea9aa529d34628ad6` 的显式 native/sanitized
部分矩阵在 13.032151 秒终止，原总判为
`FE09_B3_F0_COMPOSITION_REJECTED_WITH_EVIDENCE`，qualification=false。
Native 完成 11×600=6,600 帧；sanitized 构建完成，但 fixture-only 在 DSP
初始化前因本机 LeakSanitizer 无法读取 /proc task / ptrace 环境错误退出 -6。
未关闭 LSan，也未重跑该本地矩阵。

原 receipt SHA256 为
`f631c54b66b1cfe0eed50d5d94f3a518f5dd1c54188b3cf6d3b211f62f7ee344`。
71 个封存成员及完整成员集合由 root 和独立审查者分别回读。

## 首次托管 PR 执行

[PR838 的 Verify40057529621 attempt1](https://github.com/jiying2007/audio-pipeline/actions/runs/40057529621)
使用实际 synthetic merge `64f783ad5a333798339786625ecacba49cce69d1`，
父提交为 f430 基线与 d0d3 候选。frontend-reference job120764078418 的 B3
步骤失败，原件上传成功；原总判仍是 REJECTED，qualification=false。

Native 与 sanitized 各完成 11×600=6,600 帧，共 13,200 帧、32 项 API 负控和
10 次单列 setup；独立回读重新核验了固定门控覆盖、direct/repeat/observer 比较、
前240帧未来控制及8项重封语义负控。Arm 在配置阶段失败，Arm DSP=0。
这些完成部分不能替代三目标完整资格。

原 job 的实际起点为 2026-10-24T03:17:05Z，B3 有效预算为246.419856秒，
实际耗时22.769323秒；失败不是超时，原15分钟 deadline 没有重置。

[原 artifact12546565951](https://github.com/jiying2007/audio-pipeline/actions/runs/40057529621/artifacts/12546565951)
为2,520,768字节、118个ZIP成员、117项内部seal，ZIP SHA256 为
`9a7523a97358fdab83be07dbfd761699db39bfef0a11fb890ab0b476ea1f8a61`。
原 receipt SHA256 为
`3625b4f34794cff48c83061c1a96b11187136f2664673a8e8798aac75ae48bbb`。

## 已定位的构建问题与最小修正

原 `arm-linux-gnueabihf-gcc --version` 成功，但 CMake 随后把裸名称解析为
不存在的 `/__w/audio-pipeline/audio-pipeline/arm-linux-gnueabihf-gcc`。
运行器用未注明类型的 `-DCMAKE_C_COMPILER=name` 传参；冻结 toolchain 的
`CACHE FILEPATH` 将这个相对值按当前工作目录转换为绝对路径。
这是 [CMake set 的既定行为](https://cmake.org/cmake/help/v3.28/command/set.html)。

修正仅在私有 qualifier 中保存一次 `shutil.which` 的实际结果，再用
`Path.absolute()` 生成绝对路径，供版本记录与 CMake 同时使用。保留命中的
symlink/编译器 wrapper 别名，不用 `resolve()` 改变其 argv0 语义。
原 toolchain、66项编译依赖、C flags、优化级别、输入、调度、判据和预算不变。

本地真实 native cc 的最小 configure-only 对照复现了裸名称失败、绝对路径成功；
随后单独确认保留 `/usr/bin/cc` 别名的绝对路径也成功。额外 DSP 帧数为0，
没有把该本地检查称作 Arm 执行。最初对照脚本在两个配置完成后，误把最终 cache
类型断言为 FILEPATH；实际 CMake 写回 STRING。该审计断言失败和原日志一并保留，
只按实际 cache 值修正回读，没有重跑前两项配置。

修正后的新源码仍须独立完成首次 hosted 三目标矩阵、适用 PR 门禁及后续新 main
门禁。此前两个总判保持拒绝，不能由构建修正或13,200帧完成部分推导完整资格。
