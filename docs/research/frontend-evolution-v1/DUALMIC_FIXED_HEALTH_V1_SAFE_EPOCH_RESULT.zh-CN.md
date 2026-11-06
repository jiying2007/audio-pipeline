# 双麦固定方向健康保护：SAFE 观察边界修复结果

日期：2026-11-06。实际测量源码：`88003920f952af69dd7f88fea969122ba726e706`。
集成前基线：`9ec381e4f4fa6e6ecd1c9016d3b0711c79343a75`。
独立补充冻结：`a72e056`，见
[SAFE 边界合同](DUALMIC_FIXED_HEALTH_V1_SAFE_EPOCH_FREEZE.zh-CN.md)。

**公开 API 反例已修复；相同新增测试从288个失败断言变为0，tracking-ON/OFF
两种完整宿主CTest均63/63通过。** 这是一项观察状态生命周期修复，不是新增故障分类、
阈值优化或真人对讲声学结论。原4f2a1c6结果和所有首次失败记录保持原身份。

## 反例与唯一生产变化

LITE的四个输入帧只产生一次hard待确认观察，随后SAFE旁路BF。
SAFE期间输入已变健康或切到另一污染通道，再回LITE时，原候选仍可能把暂停前arm
算作连续证据，在首个新观察就直接选麦。先前的fixed↔tracking epoch修复无法看到
这个完全旁路区间。

补充公开测试覆盖16个CALL组合：8k/16k、SAFE一帧/四帧、SAFE健康/对侧污染、
返回原目标/换目标。原目标的8例实际提前确认，输出距应有等权混合最大
4635–5021 S16；换目标的8例由原目标一致性规则正确重新计数。

另有八条CALL/ASSISTANT恢复轨迹证明：七次恢复观察也会越过SAFE，在返回的第一个
新恢复观察就退出hard。原输出距应保留的可靠单通道最大270 S16（8k）或293 S16（16k）。

生产改动只在 `src/core/ap_pipeline.c:ap_pipeline_set_quality()` 增加10行：
当参数合法、BF stage启用、quality实际发生变化且进入或离开SAFE时，清除
`fallback_hard_arm_count`、`fallback_recovery_count`，并将
`fixed_health_counter`置3。保留active/hard、目标通道、lag、gain及历史。
重复设置同一quality不触发失效；非法quality在此前原子返回AP_EINVAL。

该逻辑受 `AP_BUILD_STAGE_BF` 编译guard保护。无新增状态、公开API、缓冲、分配或
crossfade；原两次确认、八次恢复、四帧节拍、hard/roughness阈值、输出增益均未变化。
SAFE本身仍使用mic0，不能据此宣称SAFE具有坏麦保护。

## 真实执行与保留证据

原字节日志、执行命令、返回码、源码与二进制哈希见
[summary.json](evidence/dualmic-fixed-health-safe-v1/summary.json)。
before/after使用同一份新增测试源码，其SHA-256为：

```text
f4ef1f12699a0d34abc548c58849a794feda613541c737e8fa76df9e8dd92f6e
```

| 检查 | 修复前 | 精确8800392候选 |
|---|---|---|
| 公开SAFE边界定向测试 | exit1，5024 checks / 288 failures | ON/OFF均exit0，5024 / 0 |
| 16条pending确认轨迹 | 8条原目标提前确认 | 首次新观察等权，第五帧第二次观察才确认 |
| 8条pending恢复轨迹 | 第一次返回观察提前退出 | 第七次保留hard，第八次新观察退出 |
| 8条已确认hard轨迹 | 保留 | 经SAFE回LITE/FULL仍保留，最大路由误差0 S16 |
| 重复quality与非法quality | 作为共同回归执行 | 重复调用不打断确认/恢复；非法调用整个opaque状态不变 |
| 完整tracking-ON CTest | 本补充不重跑基线完整集 | **63/63 PASS** |
| 完整tracking-OFF CTest | 本补充不重跑基线完整集 | **63/63 PASS** |
| 完整pipeline状态 | 78,224 B | ON/OFF均78,224 B，新增0 B |

5024是断言数，不是独立声学样本数。全部信号来自先前冻结的第一方工程生成器，
没有新增seed或搜索；仅为已曝光开发/回归数据。新增测试仅追加到既有
`tests/test_beamformer_health.c`，原测试完整保留。

候选ON/OFF分别重新生成2880帧始终track=true的私有BF兼容轨迹，逐字节比较原始
438fe09基线的PCM和旧176 B状态，1,935,360 B全部相同：

```text
f0effc06bc7ce5f22ef46a5f6c26268f29167cc7bfd540ebeecdf5851c1f6426
```

该私有兼容轨迹不表示tracking-OFF公开入口允许track请求；公开module仍由既有
能力测试验证非零track原子返回AP_ESTATE。宿主工具链为GNU14.2.0、x86_64、
Release、SCALAR。此ON/OFF对照仅改变方向跟踪开关，不是SSC305低资源NEON配置。
所有本次配置、构建与测试都在每次300秒预算内完成；完整CTest各约1.4秒，
这不是音频RTF或目标CPU性能测量。

## 复现入口

先检出精确源码8800392，再执行以下两种配置。输出目录应为独立构建目录。

```sh
cmake -S . -B build/safe-on -DCMAKE_BUILD_TYPE=Release \
  -DAP_BUILD_BENCH=OFF -DAP_STRICT_WARNINGS=ON \
  -DAP_ENABLE_BF_DIRECTION_TRACKING=ON \
  -DAP_BUILD_SOURCE_REVISION=88003920f952af69dd7f88fea969122ba726e706
cmake --build build/safe-on --parallel 4
ctest --test-dir build/safe-on --output-on-failure
build/safe-on/ap_beamformer_health_tests --safe-epoch

cmake -S . -B build/safe-off -DCMAKE_BUILD_TYPE=Release \
  -DAP_BUILD_BENCH=OFF -DAP_STRICT_WARNINGS=ON \
  -DAP_ENABLE_BF_DIRECTION_TRACKING=OFF \
  -DAP_BUILD_SOURCE_REVISION=88003920f952af69dd7f88fea969122ba726e706
cmake --build build/safe-off --parallel 4
ctest --test-dir build/safe-off --output-on-failure
build/safe-off/ap_beamformer_health_tests --safe-epoch
```

修复前反例使用9ec381e的生产库和上述同一份测试源码，不能用旧测试缺失或编译失败
代替行为反例。`before-safe-epoch.json`记录生产文件、测试文件和实际可执行文件身份；
`on/off-execution.json`记录最终精确提交的完整命令、返回码与时间。

本补充没有再运行真人KWS、主观对讲或物理SSC305实验，也不将宿主CTest当远程CI。
原HPF raw恢复33帧边界、无crossfade的路由采样变化仍成立。根工作包负责公共文档、
R6源码准入、整合42-case回放和精确远程门禁；源码恢复续包单独捕获本结果提交，
其自身另行提交，不宣称包含自身。
