# 非真机 V2：真实 CI 源码身份故障定位结果

依据[预先冻结修正合同](DUALMIC_NONDEVICE_V2_CI_SOURCE_ORDER_FIX.zh-CN.md)，已在
原真实 PR synthetic merge `74765cfb8678f41e11166dd37316a66a2f131977` 的独立
checkout 完成单变量定位，不执行任何音频 DSP 或模型。

原 CMake、源码、编译选项完全相同，先 clean 构建真实 build-info，再仅加入一个
未忽略的第一方 `fe-speech/ci-source-order-fixture.json` 并使用新的 build 目录。
实际回读为：

| 工作区状态 | 实际 linked source_revision |
| --- | --- |
| clean | `74765cfb8678f41e11166dd37316a66a2f131977` |
| 仅新增未跟踪 fe-speech fixture | `74765cfb8678f41e11166dd37316a66a2f131977-dirty` |

单个定位阶段共 4.004836 秒，原预算 300 秒；只清理本次创建的 sentinel 后恢复
clean。命令、实际身份、两个 configure/build 日志和退出码见
[定位 receipt](evidence/nondevice-v2-source-order/receipt.json)。这证明了代码中
同一状态产生 source label 不匹配的机制，不伪造原 CI 未保留的 build-info 输出。

workflow 修正只调整 A 构建先后顺序及研究输出的位置：checkout 后先在外部
`/tmp/ap-dualmic-recorded-stage` 保留单测/构建日志，明确检查 clean status、
HEAD==GITHUB_SHA 和实际 build-info 的 source_revision；原 fe-speech 来源与
研究随后照常执行，A 仍消费其原 46 文件，并在外部 stage 做同一 56-case 矩阵。
`CMakeLists.txt`、`.gitignore`、所有 DSP/API、A evaluator 与科学判据未改。
没有 AP_BUILD_SOURCE_REVISION override、删除旧研究输出或跳过 source identity。

## 首次 CI 失败与成功记录分别保留

旧 head `1cf071600bfc396aa478ec31e3109fcb4504836d` 的 A 必须保持 FAIL：
56-case 在链接身份检查处尚未开始。原 failure phase、traceback、失败清单、
artifact transfer 和独立诊断均在本目录；独立 gate 结论为 NOT_QUALIFIED，
其快照时仍有长任务进行中，未将快照伪装成终结状态。

同一旧 synthetic merge 的 B 与 C 真实作业成功，且分别完成独立原件回读。
B 独立重新调用与 CI 同字节的 Opus1.4 6,040 次，包含八次 PLC，全部 PCM 相同；
C 核对 78 文件、六视图和 734 项检查，65.982 秒内完成，双讲负结果未变。
这些成功不能抵消 A 失败，也不能转移给后继 head/main。

为独立解码，从 Ubuntu 官方精确 `libopus0_1.4-1build1_amd64.deb` 取得的实体
SHA256 与 CI 的 `63ddaf057d71c53090607e0467eb308640c3b39b0f189e5b937e9c397be2f676`
一致；没有安装到宿主。首次 Python3.12 tarfile 不支持包内 zstd 数据成员的
提取错误已保留，随后仅在同一 `.deb` 原字节上使用 `dpkg-deb --fsys-tarfile`
恢复并核验选定普通文件，不替换来源、不重跑前端或改质量门槛。

后继提交仍须以新的精确 PR head/base 和自身完整 CI/原件证明修正有效；不得
通过重跑旧 head 消除确定的 workflow 顺序缺陷。保护合并与新 main 的要求保持。
