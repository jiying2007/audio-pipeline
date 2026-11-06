# 非真机 V2：隐藏来源文件上传完整性修正合同

本合同在修改上传设置前冻结。只修正实际远端原件缺失，不运行新算法候选、
不调整科学判据、预算或来源角色；此前失败全部保留。

## 精确失败身份与原因

- PR #920 head `083ecc5b1d709124bf90f4a2a4f6131928956197`，base
  `2d93c9ddf74355c7e5ac0bc18c9a6fe3ae53cbd3`，实际 checkout
  `5e5b70fb1f009b6f88b251040268bfc0956f85bc`，tree
  `e2e2cbf0d36e3d922bd571a37f2eb758637dd14c`；本地同 tree 为 `dfec1b0`。
- Verify `42230060500/attempt1`、A job `127942327744` 的生产者步骤成功，
  实际 clean/build/source 身份已正确；正式 56-case 执行 41.915841 秒，
  CI 内预上传回读报告 650 个结果文件。
- Artifact `13510677983` 的真实 ZIP 为 45,180,260 字节，SHA256
  `8f0da48068e1af0c02d7ccab0d63a6b9c7aabdb6a7dbdfd21c7bf29fe5a66a5e`。
  ZIP 实际 793 文件，result 实际 648；原 manifest 要求 result 共 650。
- 缺失仅为 `source-tree/.github/research/frontend-evolution-v1/` 下的
  `speech-admission-v1.json` 与 `speech-spatial-v1.json`。它们是已承诺的
  公开来源准入记录，不能拿 checkout 补进旧原件后重封为成功。
- 既有独立 checker 在 0.105994 秒、8276 项已执行检查后以
  `650-file exact manifest mismatch` 拒绝；外层阶段 0.166509 秒 / 300。
  本份原件的声学指标独立重算及 canonical 全回读尚未启动。
- 实际固定 action `actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a`
  的 [action.yml](https://raw.githubusercontent.com/actions/upload-artifact/043fb46d1a93c77aae656e7c1c64a875d1fc6a0a/action.yml)
  声明 `include-hidden-files` 默认 `false`；官方实体 3603 字节，SHA256
  `c5979822866a72362e609844b6ebe77d4b7e759af68cc1c2c425dcf51481fab4`。

因此该 head 为 **NOT_QUALIFIED**，即使其后完整 CI summary 成功也不能覆盖
独立原件完整性失败。此前源码顺序失败和更早独立审查超预算均不改写。

## 唯一实现变化

仅在 `quality.yml` 的 `Preserve complete dual-mic recorded-speech diagnostics`
上传步骤增加 `include-hidden-files: true`。上传范围仍精确限定在
`/tmp/ap-dualmic-recorded-stage/`；必须核对其来源复制只使用冻结清单，
没有 `.git`、凭据或任意用户目录。其他上传、DSP、模型、evaluator、预算、
源码身份和质量门槛全部保持。结果文档与原失败回执可随同保存。

## 有界验证与合入条件

1. 只读诊断阶段预算 300 秒：比较原 ZIP 与 manifest、核对两个已承诺的
   文件路径及 committed source 摘要、核对固定 action 默认值；不运行音频。
2. 检查 YAML 只有该上传输入改变，A stage 所有受控来源路径可解释，B/C
   既有独立精确原件检查不发生覆盖缺失；不新增镜像实现的单元测试。
3. 新精确提交必须重新产生自己的全部适用 CI 及新 A/B/C 原件。新 A ZIP
   必须包含上述两个原 manifest 成员、result 精确 650 文件和完整 stage
   795 文件，并通过同一独立 checker 的原 300 秒合同。禁止修改旧 ZIP。
4. 所有适用检查、required summary 实际 JSON、精确 head/base、原件审查与
   review threads 均独立合格后，才受保护 squash；新 main 必须另取完整
   检查和自己的 A/B/C 原件。不给旧成功结果换执行身份。
