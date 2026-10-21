# D7多帧相关测量结果

日期：2026-10-10；测量状态：MEASUREMENT_PASS / NO_PROMOTION。
依据：[冻结计划](DEVICE_MULTIFRAME_D7_PLAN.zh-CN.md) 和 [观测存储修订](DEVICE_MULTIFRAME_D7_AMENDMENT.zh-CN.md)。
Provider route unresolved，本记录仅为仓内reviewing候选。独立审查结果另附，不能由本测量自批算法候选。

## 结论和限制

在两个已定位事件上，40/100ms历史提供了10ms单帧没有的区分信息：设备误跳候选的
平方归一化相关显著下降，已知路径工程恢复候选仍保持高相关。
这支持进一步冻结多帧确认假设，尚不能证明任何通用门限、故障率或产品声学收益。
测量仅发生在原tracker达到既有最低相关门限的观测点，不能推出全时段检测率或误报率。
fixed16是观察本批数据后的固定诊断延迟，不是独立真值；最长窗本身也可能受双讲、路径切换混窗影响。

| 事件 | 候选samples | 10ms候选score | 40ms候选score | 100ms候选score |
| --- | ---: | ---: | ---: | ---: |
| tracked1误跳接受前，render_total=306880 | 2752 | 0.723276794 | 0.00750771305 | 0.0000277537292 |
| 已知路径工程恢复接受前，render_total=204800 | 1284 | 1.000000600 | 0.967872620 | 0.975764811 |

误跳事件40ms最优delay=264、score=0.0261534899；100ms最优delay=1380、score=0.0050892178，
都不是可靠真实延迟证据。已知恢复40/100ms最优delay=1280，score约1，与其注入80ms路径一致。
浮点score略大于1原样保留。render_total按回放样本时间解释，不能作为设备AO时间戳。

## 实际执行和等价

首次在临时pipeline state内加历史导致公共resident ceiling静态断言拒绝，build exit2已保留。
修订后只在临时ap_sync.c内增加Host线程局部16槽旁路历史；原pipeline state/header和上限不变。
旁路只读评分，不回写原决策；init清slot，历史不完整或render/mic累计不一致时eligible=false。
线程局部历史、日志I/O和额外评分都有开销，本实验不作为资源或线程迁移资格。

严格build-v2成功；CTest在实际构建cwd运行，明确14/14通过。
原ap_drift_res_tests通过；known-route=393、default=238、tracked1=238个观测，三个窗口均历史完整。
fixed1禁用tracking，无trace为预期。所有评分有限；160点候选score与原score误差不超过1e-6。
rpm480/far-motion default/tracked1/fixed1三臂六份PCM/metrics与D6逐字节等价。
仅执行该固定集合，没有参数搜索、阈值调整、silent padding或声学标签升级。

## 可追溯身份

根目录：`/tmp/audio-fe-device-multiframe-d7-20261010`。
编排：`/tmp/audio-device-d7-run.py`，其SHA绑定在binding.json。
初始configure.json/build.json保留；成功日志使用-v2.json，新build-v2不覆盖初始build。

| 证据 | SHA256 |
| --- | --- |
| result.json | 770b2ac5f6b8472176eb050fc96459d676d1641ab1aa424e84342c72d6e17410 |
| binding.json | c940389361abbaa0eef4c7d14f5a828b9727011bdadc99bb3cd978a369a06993 |
| ctest-v2.json | 19a34c9a35b55281d3eaf5e9d9d7094c7dc6d75f6c3ee4b840025c45fbfb7e99 |
| D6 baseline receipt | d2e4c5fb82c2ca795d576f42618b8204e47ae16b7f96c232fdc161d542bf4b36 |

binding绑定原/临时全部DSP源码hash，唯一差异=src/sync/ap_sync.c；同时绑定临时库、runner、
CMake cache、计划/修订、全部命令日志和六份PCM/metrics。不是shipping SDK或device制品。

## 下一阶段边界

D4拒绝不变。下一候选可单独研究“原大跳确认增加固定长窗证据”，须另冻算法/测量身份，
验收原真实路径工程恢复、噪声/双讲/低参考/突发切换的负例，以及完整开发矩阵。
不能由两个事件反推通用阈值，不能以能量下降作近端保真证明。
设备位置/render时轴/制品、人工标签、独立声学、owner/shipping/E001/PQ仍待外部证据。
无SCM写、设备写或产品DSP/default/API改变。D6独立软件审查通过不被改写；D7新结论独立验收。
