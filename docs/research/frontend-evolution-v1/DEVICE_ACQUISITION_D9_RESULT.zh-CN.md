# D9 已知延迟获取与恢复结果

日期：2026-10-10；experiment=`FE_DEVICE_ACQUISITION_D9`。
冻结合同见 [D9 计划](DEVICE_ACQUISITION_D9_PLAN.zh-CN.md)。
结论：`BASELINE_FIXTURE_LIMIT`；`promotion_allowed=false`、`shipping_approved=false`。
D6 基线与 D8 候选在本矩阵中共同暴露短延迟获取缺口；没有满足“基线通过、候选失败”的 mandatory 回归，不能据此批准 D8。
[D8 的选型不确定结论](DEVICE_ROUTE_D8_RESULT.zh-CN.md) 保持原样。

## 实际执行与身份

同一 [公共 API 工程 fixture](../../../tests/validation/frontend_evolution/device_acquisition_d9.c)
分别链接两份既有静态库，严格 C 编译均成功；没有新构建或修改 processor。
每版本运行 100 个固定用例，再各以新进程、新目录重复指定的 16 kHz/seed1/宽带/acquire/7 ms 用例。
共 200 次固定执行与 2 次重复，全部 processor/I/O 返回成功。
100 对实际输入逐字节一致；两次重复各自的输入、输出、metrics 均与对应首次执行逐字节一致。
保存的 200 份逐帧 CSV 已重新计算帧集合、capture 数、首次进入范围帧、末窗、最终延迟和 counters。
进一步读取全部 76 个非双讲用例的实际 S16LE 输入，对 2,736,000 个 mic 样本核验
`mic=truncate(float32(0.4f×已知延迟的实际量化render))`，无历史时核验为零；不匹配数为 0。
这仅核验已知因果输入，不重跑算法，不解释双讲下的可辨识性。

每个版本的 56 个构建相关源码文件（`src`、`include`、`cmake` 及 `CMakeLists.txt`）均匹配对应 D6/D8 receipt。
两份库也分别逐字节匹配对应 receipt；两版本的构建相关源码差异仅为 D8 冻结 patch 的 `src/sync/ap_sync.c` 与 `.h`。
D8 使用既有 strict build，库与其 replay build 相同；两份 CMakeCache 的路径、测试配置不同，分别绑定，不声称 cache 相同。

| 身份 | SHA256 |
| --- | --- |
| 冻结计划 | `74f883bfba41369f5ff0dcad99e2572b940b1acd9e41f6608d947fc19b891d30` |
| C fixture | `7395752ba53b93e701e607b06760af6bfcddc4b6a0243ab059812d26023663a2` |
| D6 库 | `d320534dc4f83b78b3108aa871a4fe197a37265b479b0674769b4145c4de953a` |
| D8 库 | `a04ca88a75c0fd8538f7eb6d3726dfe906b2dfc284cc77c577f2328eb04b23b1` |
| 实际 result.json | `564a2d3d6b6200c728ad09469b455b0595a584286d56ea2c0fd3899e1a9624b6` |
| 原始 binding.json | `5f11e7604040964e7b70e4a5a1972fbe42a96219bcf6561a92cb30bd795feda8` |
| 后续身份核验 identity-validation.json | `d00b6c8fb4fc878ba4e7a8913a780a33f210b3c6fa960dcce910b3502d510c6f` |
| 实际输入核验 input-validation.json | `8aa7b099677561c14c1ec3b99c2779d64eecc821c01fa0f621250dae80c09b6a` |

原始绑定未被覆盖。实际输入、输出、CSV、编译/运行回执与绑定位于
`/tmp/audio-fe-device-acquisition-d9-20261010`；本文件是持久结果摘要，临时目录不是长期归档或跨机器可用性承诺。
临时编排脚本 SHA256=`0007b752a3166efebe7fda4b119b3bb0c32a820321a7c38a9267659422cc3c2e`。

## Mandatory 结果与真实失败

验收保持冻结规则：最后 20 个 capture 帧的估计延迟必须全部位于生成器真值 ±3 ms。
两个采样率、两个 seed、两个 acquire/switch 模式各自完整披露，不增加时长或放宽容差。

| Mandatory 组 | 用例数 | D6 通过 | D8 通过 | 判定 |
| --- | ---: | ---: | ---: | --- |
| 无噪宽带，1 ms | 8 | 0 | 0 | baseline limit |
| 无噪宽带，7 ms | 8 | 0 | 0 | baseline limit |
| 无噪宽带，80 ms | 8 | 8 | 8 | 本矩阵通过 |
| 已通知 capture gap，40→80 ms | 2 | 2 | 2 | 本矩阵通过 |
| 合计 | 26 | 10 | 10 | 16 个共同失败；不晋升 |

全部 16 个短延迟 mandatory 的 `last20_in_band=0`，不是少数末帧遗漏。
多数最终停在约 39–40 ms；16 kHz/seed2/acquire/1 ms 的基线最终为 10 ms、候选为 40 ms，
两者仍均为 0/20。这个不利差异保留，不能用“回归数为零”隐藏它。
基线通过而候选失败的 mandatory 数为 0；该值仅代表本计划定义的相对硬回归，不代表正确获取能力成立。

## 诊断组与缺帧边界

以下末窗计数仅描述本工程数据，不能转换为真实声学成功率或用于候选选型。

| 主矩阵信号组（各 24 例） | D6 末窗达标 | D8 末窗达标 |
| --- | ---: | ---: |
| 宽带 | 8 | 8 |
| 周期双频 | 8 | 8 |
| 低参考 | 8 | 8 |
| 合成双讲 | 0 | 0 |

未通知 capture gap 的两个附加诊断例中，D6 在生成器第 150 帧首次进入 80 ms 范围，
最终 80 ms/20 个末窗帧达标；D8 从未进入目标范围，最终保持 40 ms/0 个末窗帧达标。
该差异不满足冻结 mandatory 回归定义，仍必须披露。
未通知缺帧超出正常 render/capture 配对契约，不能由基线的自动恢复推导规范要求，
也不能把 D8 保持旧估计称为物理对齐正确或恢复成功。
已通知 gap 的两版本均在第 160 帧首次进入范围，最终 80 ms/20 个末窗帧达标。

## 根因边界与下一步

当前已确认的是固定输入下两版本共同失败，尚未确认 tracker 内部根因。
静态实现采用约 2 ms coarse grid；1/7 ms 位于网格之间，而 80 ms 位于网格上。
因此 coarse 选择、局部 refine 与三次确认是后续有限观测方向，不能据此直接归因。
下一单独阶段应冻结少量既有失败例，观察 coarse winner、refined winner、score 与确认状态，
先定位失败阶段，再决定是否需要一个因果明确的修复；不得修改本轮矩阵、门限或历史结论。

本轮数据是已查看的第一方合成 development 工程输入，只有已知生成器延迟；没有 room、真人、
设备物理 render 时轴或独立声学质量资格。产品源码/默认配置未修改，未替换 AISpeech、未 commit/push/设备写。
源码、工程测量、声学、SSC305 资源、HIL、E001 与产品资格保持独立。
Provider 当前 route unresolved；仓内文档仅 reviewing candidate，不声明已正式归档。
最终独立 whole-change 复审与本地 Runtime 结果见 [D9 复审](DEVICE_ACQUISITION_D9_REVIEW.zh-CN.md)。
