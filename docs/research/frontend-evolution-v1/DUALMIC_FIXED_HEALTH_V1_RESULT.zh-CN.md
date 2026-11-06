# FE-C2-FIXED-DIRECTION-HEALTH-V1：双麦固定方向保护结果

日期：2026-11-06。算法/测试源码提交：`4f2a1c63455736c42ce72f8c7103b35b3b0f9893`。原始基线：`438fe09d79ff768306c00573849517bcd91cbc6e`。

**结论：固定方向 BF 的狭义 hard-contamination 保护已经实现，默认与关闭方向跟踪的宿主构建均通过定向验证；始终开启方向跟踪的 PCM 与旧状态逐字节不变。** 此结果不包括真人 KWS、对讲听感或物理 SSC305 性能。HPF 级联的原 raw→恢复32帧断言实际失败，保留为33帧恢复边界；另有一个低资源既有通用合同测试问题已在原始基线复现。

实施与测量身份分别见 [实施冻结](DUALMIC_FIXED_HEALTH_V1_IMPLEMENTATION.zh-CN.md)、[恢复测量起点勘误](DUALMIC_FIXED_HEALTH_V1_MEASUREMENT_ERRATA.zh-CN.md)及[模式生命周期补充](DUALMIC_FIXED_HEALTH_V1_MODE_EPOCH.zh-CN.md)。机器结果和原始日志索引为 [summary.json](evidence/dualmic-fixed-health-v1/summary.json)。这些材料不改写原计划或历史 I007 结论。

## 实际改变

`track_direction=false` 不再每帧清除已确认的保护状态。每四帧仅观察当前固定 lag；维持既有能量比、coherence、roughness 阈值，两次同目标有效证据才选择较弱可信麦。两路高于1 LSB RMS 才有观察资格，八次连续有效恢复证据才回等权混合。

静音清未完成计数而保留已确认路由。固定与跟踪模式切换也清未完成确认/恢复计数，不丢已确认的 hard 目标及冻结lag；唯一新增计数器用3表示非fixed、4..7表示fixed相位，避免跨模式借用证据和长时间无界递增。

未确认的 soft fallback 不带入固定模式。没有新增全 lag 搜索、soft wind 选择器、crossfade、增益调参、堆分配、I/O或额外PCM缓冲。既有 true 分支内部搜索、阈值、节拍和输出公式不变；模式边界的证据失效单独定义。

`track=false` 表示保持当前lag，未必重置为broadside；SSC305-low从reset开始的lag仍为0。SAFE仍直接取mic0，不执行这一保护。编译关闭方向跟踪时，standalone非零track请求仍原子返回AP_ESTATE。

## 定向结果和独立对照

GCC 14.2.0，`x86_64-linux-gnu`，Release默认构建。所有信号为实施前固定的第一方工程数据，属于开发/回归。

| 检查 | 结果 |
|---|---|
| 同一最终测试编译到精确base | 实际exit 1；fixed不进入hard、模式切换丢hard、公共LITE输出失去保护 |
| 候选24个hard工程正例 | 8k/16k × BF-only/HPF→BF × 左右污染 × lag -1/0/+1，全部选对可信通道 |
| 216条负例轨迹 | 同相、增益差、弱通道、离轴、转向、噪声、静音及已声明形状的未覆盖故障，全部维持原固定混合 |
| 连续确认、恢复、静音、reset | 符合冻结判据；一次观察不足，左右候选交替不确认，静音中断恢复计数 |
| 模式epoch | 一帧tracking无观察、四帧tracking含健康观察、同目标/换目标、异常私有相位重建全部通过 |
| 公共pipeline CALL/ASSISTANT | BF-only配置下FULL/LITE/SAFE、帧计数、输出及有限指标通过；不是完整双用途音质判定 |
| exact候选head的现有module/contract/realtime及新BF测试 | 4/4通过 |
| low-host方向跟踪OFF | 新BF及现有module/realtime通过；通用contract的既有60ms上限问题另列 |
| ASan+UBSan | 禁用本环境不可运行的LeakSanitizer后4/4通过 |

候选最终检查计数为5,766,658，失败0；这是样点/状态断言数，**不是独立声学样本数**。原始base最终失败21,850个断言，同样不是独立场景数量。

始终track=true的2880帧对照包含健康、左右污染、恢复、弱通道、离轴/转向、噪声、静音及HPF，记录每帧PCM和原176B状态。基线与候选的1,935,360字节完全一致，SHA-256均为：

```text
f0effc06bc7ce5f22ef46a5f6c26268f29167cc7bfd540ebeecdf5851c1f6426
```

公共ABI probe输出也逐字节一致。此证明限于已执行的同编译器宿主对照，不是其他ISA的已测字节承诺。

## HPF恢复与对讲路由边界

污染从frame20开始，所有24例在frame24进入hard。raw输入从frame80切回clean；每帧10ms，以下计数含首尾已消费输入帧，不含设备/系统队列延迟。

| 分组 | 首个有效恢复观察 | 第八次观察/退出 | raw→退出 | 最大进入附加采样变化 | 最大退出附加采样变化 |
|---|---:|---:|---:|---:|---:|
| BF-only，12例 | 80 | 108 | 29帧 / 290ms | 0.118757799 | 0.0329557471 |
| HPF→BF，12例 | 84 | 112 | **33帧 / 330ms** | 0.074432075 | 0.0349931195 |

“附加采样变化”是切换帧首样本与同一输入若继续旧路由的首样本之差，单位为normalized float，不是dB。相邻帧实际边界最大绝对变化分别为BF-only进入0.152603671/退出0.0659114942、HPF→BF进入0.115100063/退出0.0699862391。它包含信号本身的相邻样本变化，不能与附加路由变化混用。

HPF尾迹使frame80不满足原恢复条件；独立双精度输入检查固定断言frame84首次有效，再检查八次连续计数和frame112退出。没有根据候选退出时刻动态生成期望，也没有改BF阈值。原12个raw起点断言失败保留，不能将这一测量勘误写成原始32帧目标通过。

没有crossfade，所以这些非零路由边界是真实保留的对讲风险；有限输出、无丢帧与数值通过不等于无点击或真人听感改善。

## 状态、资源和ABI

| 宿主测量 | base | 候选 | 增量 |
|---|---:|---:|---:|
| BF私有状态 | 176 B | 180 B | 4 B |
| standalone BF module | 184 B | 188 B | 4 B |
| 默认完整pipeline | 78,192 B | 78,200 B | 8 B，对齐后 |
| low-host pipeline | 38,832 B | 38,840 B | 8 B |
| low-host runtime | 6,456 B | 6,456 B | 0 B |
| low-host两arena合计 | 45,288 B | 45,296 B | 8 B |

low-host使用16k输入/内部、双麦、60ms delay、64ms AEC tail、queue depth4和tracking OFF，**SIMD/ISA仍是宿主SCALAR**；它不是SSC305 NEON preset执行。保守50,000 B arena门槛未修改。`nm -u`未发现核心库对malloc/calloc/realloc/free的直接引用；这不是整个进程的分配计数或LeakSanitizer结果。

没有公开结构、函数、枚举或capability含义变化。opaque module最低内存查询由184变为188 B；调用方仍应查询state size或使用既有公共最大arena。ROM 40,960 B及其他门槛均未提高，但本地配置的Arm交叉编译器/QEMU命令不可用，AArch32 ROM、QEMU和物理CPU/热/功耗未执行，须由后续精确集成门禁/实际设备测量分别报告。

## 保留失败与环境限制

- 初版公共BF-only测试遗漏关闭SYNC flags，四个配置被API拒绝。修正测试配置后重新测base，真实BF失败仍在；两日志都保留。
- 第一候选的HPF raw恢复断言12次失败，保留原样，按已审查的起点勘误复测。
- 独立复审发现未完成fixed证据跨tracking间隔继承，24次失败保留。源码`1dae740`保留修正前候选，`4f2a1c6`修正模式epoch；没有新阈值。
- low-host原`ap_contract_tests`在`tests/test_contracts.c:328`把100ms timestamp差当作合法，超过该构建60ms cap；base和候选均失败。本BF工作包未改该既有测试，也不把它报告为PASS。
- 首次四个sanitizer测试都被LeakSanitizer的ptrace环境限制终止。原日志保留，后续仅设置`ASAN_OPTIONS=detect_leaks=0`运行ASan+UBSan；LeakSanitizer本身仍是未在受支持环境执行。

## 复现入口

默认构建与本地定向检查：

```sh
cmake -S . -B build/fixed-health -DCMAKE_BUILD_TYPE=Release -DAP_STRICT_WARNINGS=ON -DAP_BUILD_BENCH=OFF -DAP_BUILD_EXAMPLES=OFF
cmake --build build/fixed-health --target ap_beamformer_health_tests ap_module_tests ap_contract_tests ap_realtime_tests --parallel 4
ctest --test-dir build/fixed-health --output-on-failure -R '^(ap_beamformer_health_tests|ap_module_tests|ap_contract_tests|ap_realtime_tests)$'
build/fixed-health/ap_beamformer_health_tests --legacy-trace candidate-tracking.bin
build/fixed-health/ap_beamformer_health_tests --mode-epoch
```

精确base的库在独立checkout构建，再用候选的同一个`tests/test_beamformer_health.c`、base的`src/include/generated`头和base库链接测试；该文件对旧状态兼容，不依靠编译失败充当缺陷证据。对两端`--legacy-trace`文件做完整字节比较。单次构建/定向运行都遵守300秒预算。

本工作包完成的是可回归的双麦软件修复。数字断流/rail/反相的通用分类、SAFE坏mic0处理、真实中文KWS FAR/FRR、真人对讲与物理SSC305资格没有被此结果替代；共同版本2.3.62、CHANGELOG和完整exact-head门禁由总集成处理。
