# 双麦非真机集成：2.3.64 精确源码身份迁移

日期：2026-11-10。基于 PR #927 head
`3a10167568861616f5606796438a5ba33e81313d`，main
`c65777cf4393a67755de99f86654571f9684bb91`。

## 具体故障与范围

Verify `42873621291` 的 `audio-quality / validation-smoke`，job
`130033500119` 在实际 Runtime 身份负例前将新二进制版本 2.3.64 与旧
2.3.63 字面量比较，报 `unexpected source version/module/runtime envelope`。
同一工作流后继中文准备步骤也含相同旧版本假设。原失败、历史合同和既有
2.3.63 结果原样保留；这不是 codec、模型、声学或 DSP 参数故障的通过结论。

本次仅迁移两个 host 集成入口的版本/源码准入。`dualmic_source_identity.py`
读取 SHA256 固定的原 B3 source-lock，以及已独立准入的 R7 / R9
PREREGISTRATION，校验原 56 个公共构建文件，叠加各自 13 个已批准文件的
after 身份。每个文件同时校验长度、SHA256、Git blob、当前执行提交及工作树。
源码版本必须等于实际二进制版本；仅接受 R7 的 2.3.63 和 R9 的 2.3.64。
原 R8 的多一个末尾 LF、只改版本、未知版本、源码增删、未提交或混合源码均拒绝。
不改写 R1–R9 helper、source pin、历史 patch、科学合同或历史执行身份。

该适配只消费已冻结的公共源码元数据，不替代 FE09 的历史对象重放、完整派生
证明或 R9 独立门禁；正常 Verify 仍执行这些原门禁。适配本身只需要当前树，
可用于原 validation-smoke 的 depth-one checkout，不为读取历史对象放宽 CI。
新适配、负例、本文和两份原注册均进入各集成执行的源码绑定。

## 不变的测量合同

对讲仍执行原八场景、八次同步 API 对照、两次固定控制、真实 libopus 和
原 Runtime；配置回读、1023 module mask、fast_math=0、Linux Runtime、
四项 tuning、逐帧完整性、post-PLC/post-volume Render、300 秒预算均不变。
中文仍保留原六视图、原音频/转写/模型锁、预处理、CER/KWS 算法和阈值，
prepare 与 prepared readback 都核验源码身份。没有模型权重或私人语料变动。

2.3.64 必须产生自己实际提交的全新产物，不能继承 2.3.63 的 PASS。
旧报告仍用其原始提交工具重放，不由修改后的 source-bound 工具重新封签。
所有负结果保留，质量仍为描述性/未评估，无真实 WAN、真人听评或物理设备资格。
