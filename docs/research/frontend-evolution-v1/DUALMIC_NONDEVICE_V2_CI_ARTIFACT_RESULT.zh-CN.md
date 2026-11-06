# 非真机 V2：下载原件完整性失败与最小上传修正

依据[预先冻结合同](DUALMIC_NONDEVICE_V2_CI_ARTIFACT_FIX.zh-CN.md)，对实际
artifact `13510677983` 做只读逐成员比对。root 定位阶段 0.034283 秒 / 300，
第二审查者也独立确认：result 650 个预期文件仅有 648 个，无多余成员；
两个缺失路径正好也是 manifest 的全部隐藏路径。已存在 647 个 manifest
成员的大小与摘要一致，另一个文件是 manifest 本身。

| 缺失公开来源文件 | 字节 | 原 manifest 与精确 checkout 共同 SHA256 |
| --- | ---: | --- |
| speech-admission-v1.json | 1219 | `a9768d0cf83c7d9875d73a54b8dda7f59540346b3d60a2fd72336071914bbc9f` |
| speech-spatial-v1.json | 1498 | `9cf0253c3e04e48ed98643c1bd39dcc94c9e8ac0bb0265fd90f5e645a13dc8da` |

路径前缀均为 `source-tree/.github/research/frontend-evolution-v1/`。原件保持
缺失状态，未补文件、重封 ZIP 或重新运行 DSP。完整独立阶段仍是 **FAIL**；
原件完整性拒绝发生在 canonical 全回读和独立声学重算之前。

此次源码顺序修复已经由真实原件证明：prebuild status 为 0 字节，checkout、
实际 linked build-info 和报告均为 `5e5b70fb1f009b6f88b251040268bfc0956f85bc`。
这项成功与上传失败分别记录，不能彼此抵扣。相同 head 的 B/C 原件已各自
独立回读，但整个 head 仍为 **NOT_QUALIFIED**。

代码变化只有 A 现有受控上传步骤的 `include-hidden-files: true`。路径仍为
`/tmp/ap-dualmic-recorded-stage/`；来源清单、650 个结果成员、795 个完整
stage 成员、所有验证代码、300 秒预算和原质量门禁保持。新 PR 与 main 均须
取得自己的完整原件，待新实际结果确认后才能记录通过。

原始独立失败、固定 action 来源摘要、两方缺失比对及真实 ZIP transfer
见 [保留证据目录](evidence/nondevice-v2-hidden-upload/)。此前源码身份故障、
早期审查预算失败及所有负向科学观测继续保留。
