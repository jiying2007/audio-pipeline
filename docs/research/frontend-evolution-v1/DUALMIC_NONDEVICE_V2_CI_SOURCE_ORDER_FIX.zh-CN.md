# 非真机 V2：首次远端 A 源码身份失败与构建顺序修正合同

本记录在本次定位复现与修正后的执行之前冻结。旧失败原件保留；没有声学参数、
评分、数据或超时变更，也不覆盖已有本地结果。

## 已观察失败

PR #920 head `1cf071600bfc396aa478ec31e3109fcb4504836d`，base
`2d93c9ddf74355c7e5ac0bc18c9a6fe3ae53cbd3`，实际 synthetic merge
`74765cfb8678f41e11166dd37316a66a2f131977`，tree
`2805a3b7363c53f53b662b70e838a7b887ba749b`。
Verify `42227371302/attempt1` 的 `quality / frontend-speech`
job `127925628653` 在新增回放步骤失败。

新 corpus 的 56 例已经构建/校验，九项方法测试也成功；正式 worker 在
`build_identity()` 抛出 `linked build source does not match --source-revision`，
3.974171 秒后以 FAIL/exit1 正常保存。56 例正式处理尚未开始。
失败 artifact `13506623029` 共 15,296,596 B，ZIP SHA256
`d63cc5c2a32ae7f784e47d304be9d2495d86003a7065d414c0403de73b6b14fb`，
含 144 个文件、完整前置日志、已生成 corpus 及失败 phase/traceback。
该失败是门禁有效拦截，不能把 corpus 完成或其他 job 成功写成 A 通过。

## 代码定位与待复现假设

原 CMake 自动读取 HEAD，并在 `git status --porcelain` 非空时追加 `-dirty`。
新 A configure 排在已有 `fe-speech/effects`、`fir` 等结果生成之后；这些 JSON/
文本未被忽略。新 A 自己预建的 `fe-speech/dualmic-stage` 与 configure 的 tee
日志也会先于 CMake 创建未忽略文件。当前失败 artifact 没有保留失败 binary 的
dump，因此“实际拒绝对象是 SHA-dirty”属于明确代码/目录支持的假设，先做独立
最小配置复现，不冒称已直接取得该字段。

定位复现固定使用上述真实 synthetic merge 的独立 checkout，两次 fresh CMake
默认配置/build-info 构建：先 clean；再仅新增一个第一方
`fe-speech/ci-source-order-fixture.json` 未跟踪文件。其余源码/配置不变。预期首个
dump 为纯 SHA、第二个为同 SHA 加 `-dirty`；保留两个 git status、实际命令、dump、
返回码和时间。单阶段总预算 300 秒；不运行 DSP 音频或模型，不下载新语料。
最后只删除本次明确创建的 sentinel，确认 tracked source 未变。

## 最小修正与验收

将新 A 方法测试与 native configure/build 放到该 job checkout 后、所有研究输出
生成前。新 A stage 与日志整体放在 `/tmp/ap-dualmic-recorded-stage`，避免 tee
本身污染源码工作区；build 仍用原已忽略的 `build-dualmic-recorded/`。
构建前记录并要求 clean git status 和实际 HEAD==GITHUB_SHA；构建后保存真实
build-info dump 并直接要求其中 source_revision==GITHUB_SHA。

后续 A corpus/replay/verify 仍消费原同 job 已准入的 46 来源文件，使用原两 profile、
56 例和空声学阈值。输出路径改为新外部 stage，不改变输入字节、方法或 300 秒
阶段预算。always upload 保留整个外部 stage，包括预构建失败。

不强设 AP_BUILD_SOURCE_REVISION，不忽略新的未知源码，不删除原研究输出来伪造
clean，不放宽 build_identity，不重写 CMake/DSP/API。新提交重新走完整 PR 门禁；
旧 head 的失败和其他成功产物各保持自己的实际身份。受保护合并前仍需精确
head/base、全部适用 checks、required summary App15368 与独立回读。
