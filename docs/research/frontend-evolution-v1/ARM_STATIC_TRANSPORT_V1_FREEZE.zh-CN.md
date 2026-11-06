# ARM 静态证据无损传输修复：冻结合同 V1

冻结日期：2026-11-06。基线为失败 candidate
`ce5d3f460c3fdb371c8ce9182b4443b2c262fb79`；受保护 base 为
`a920beed8e2c66ea9d90442d31af9632f5c75a23`。

## 已复现根因与保留的失败

[PR #917 的 Verify 42185156796](https://github.com/jiying2007/audio-pipeline/actions/runs/42185156796)
在 impact 阶段被受保护 base 的 immutable whitespace checker 拒绝。
独立调用该原 checker 的隔离 Git object 检查，只产生两条诊断：

```text
validation/research/evidence/dualmic-arm-static-9a9202e/original/base-size.log:30: new blank line at EOF.
validation/research/evidence/dualmic-arm-static-9a9202e/original/candidate-size.log:30: new blank line at EOF.
```

二者是原测量日志的真实末尾空行，不应删改。现有 checker 的例外必须事先存在于
受保护 base，且 policy/checker 在导入两端逐字节一致；本次不得内联登记例外、
修改 checker/policy、增加审批路径或再次准备规则 PR。

## 唯一传输候选

仅将上述两个原文件以单行标准 base64 加一个 LF 保存为同路径 `.b64` 文件。
解码后字节数和 SHA-256 必须完全等于原 artifact manifest；不得清理原文 whitespace。
原 `artifact-manifest.json` 逐字节归档。其 24 个逻辑成员中，另外 22 个文件
（包括旧 README、原 report、resource receipt 和 source bundle）保持原路径和字节。

新增 TRANSPORT 说明和显式解码/校验脚本；更新外层 physical artifact manifest
描述当前实际存储文件；研究入口只改链接到 TRANSPORT 说明。旧 README 保留为
可重建原快照的一员，不把它静默改为新的测量结果。
保留原失败 run、job、base/head、真实 merge checkout 身份与下载日志文本身份。
若原 CI 日志本身带 whitespace，亦用 base64 保存，避免改写原日志。

## 预先固定的验收与预算

1. 解码并在新外部目录重建原 manifest 的全部 24 个成员；每个成员的 SHA-256、
   字节数和 `git show ce5d3f4:<path>` 原字节必须一致，原 manifest 本身也必须一致。
2. 受保护 base 原 checker 对原 candidate 仍按原样 FAIL；对修复提交必须
   `STRICT_PASS`，exceptions 为 0。不得依赖当前工作树属性或 Git config 绕过检查。
3. 两个运输负例必须拒绝：改动 encoded 内容；改动保持原路径的原成员。
4. 最终验证 DSP、CMake、workflow、checker/policy 与失败 candidate 逐字节不变。
5. 不运行编译、DSP/声学回放、训练、安装或完整矩阵。修复只改变证据运输容器，
   原 ARM 资源数值、原任务总预算失败及未运行项保持不变。

从隔离工作树建立到封存验收的执行窗口上限 **300 秒**，计入传输、证据整理、
校验与提交，不以配置/编码 CPU 时间代替总墙钟时间。超时保留 FAIL，不增加预算。
