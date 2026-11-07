# 双麦 D2：真实执行、失败保全与增益分解结果

日期：2026-11-07（Asia/Shanghai）。任务 #922，PR #923。
本记录对应 [执行前合同](DUALMIC_GAIN_D2_PLAN.zh-CN.md) 和冻结 input-lock；
合同 commit `6c5aa1ba924ba6ab7f72db3e376703e24e1f459a`，不得用后续结果修改其条件。

## 首次执行：编译失败，D2 没有音频结果

实际 source `d2a917a0311ec6d2bdc3414bc78b2d0bc2b7b49a` / tree
`d411092c0752fb3497d45ad33e467f27c78ff61e` 的
[Frontend Research 42321336440 / attempt 1](https://github.com/jiying2007/audio-pipeline/actions/runs/42321336440)
在 job `128246347231` 失败。完整 D1 60 例 run 与 verify 已成功；D2 在 build 阶段失败，
尚未进入 AGC run，没有 D2 波形、分数或质量结论。

完整保留工件 [13552927522](https://github.com/jiying2007/audio-pipeline/actions/runs/42321336440/artifacts/13552927522)：
ZIP 404994669 bytes、2870 members、解压 757296686 bytes；SHA256
`2954e524b95176c83f4be33a1650ab8765b6feee5c09440b7e5a9c5b625f3e49`。
原件下载后按完整大小/hash和安全目录成员核验，10.854325 秒，未重建或替换原件。

`gain-d2/compile/stderr.txt` 的首个真实错误：

```text
dualmic_gain_d2.c:337:66: error: expected ')' before '{' token
```

`main` 的参数校验条件漏了外层 `if` 的一个闭合括号；后续 unused 报错是语法失败
级联。实际 compiler exit=1，0.063826 秒；完整 build phase 为 FAILED，1.869667 秒。
原静态审查未识别该语法缺陷，不能把静态 PASS 当作真实构建 PASS。

修复仅补一个 `)`。原 C 算术、状态与事件处理、四视图、Python scorer/读回、输入锁、
300 秒单阶段和20分钟总预算全部不变；由新 source 重新在 Actions 构建/执行。
这次失败不重标为成功，也不被解释为算法拒绝。

## 修复后的首次有效执行

真实 source `cc853616685b9faf7880e6d8f8f1a89d187d342a` / tree
`bfc59f0c8b5129e336859df30393f888a4dd423f` 的
[Frontend Research 42321833898 / attempt 1](https://github.com/jiying2007/audio-pipeline/actions/runs/42321833898)
在 job `128247951171` 成功。完整 [artifact 13553232106](https://github.com/jiying2007/audio-pipeline/actions/runs/42321833898/artifacts/13553232106)
为474165229 bytes、3551 members、解压861385743 bytes；ZIP SHA256
`a3ab7823fdcd7586c3b72eb214b5536dcfb7531fdf0b1611d49e1575a29b2c3d`。
实际原件下载、完整大小/hash及安全解包核验13.873595秒。

修复C为18426 bytes，SHA256
`3dd63fc0f7f1c29e4b849af6a63bb737f186b77a4bb09ee39aa014e14eff8cd5`。
Python `8e415aea38e952901223d9461136a47db1832b0e3585008b12587e21828f6363`、
negative test `40ed8f39aee04e8b1ab8879bfb17642788a7cb56213e02a7490577997058f8da`
与首次失败source相同。没有修改D1核心11个依赖、输入、参数或评分规则。

实际60例、35916帧、5746560样点、8次原discontinuity reset全部完成。每帧真实
AGC只调用一次；原before/after状态、最终Float32及原D1端点评分全部精确复现。
15项结构/保存字段篡改负例在Actions首步再次通过。D2结论为
**`GAIN_DECOMPOSITION_VALID_NO_PROMOTION`**，并非算法候选获准。

| 实际完整阶段 | 秒 | 冻结预算 |
|---|---:|---:|
| fresh D1 run | 5.574804 | 300 |
| fresh D1 analysis及封存 | 20.429546 | 300 |
| fresh D1 verify | 20.356123 | 300 |
| D2 build | 1.717396 | 300 |
| D2 run | 2.218119 | 300 |
| D2 analysis及封存 | 29.035757 | 300 |
| D2 verify | 29.073099 | 300 |

原job20分钟总预算未增加。C/DSP实际执行在Actions，独立审计只读原件，无模型重跑。

## 首次独立原件审计

同一fresh D1使用既有独立checker
`f9c2b57d62041e61e85f2ef5566b067d7a2a381f32a461e75c73f8e896dca67b`：
7401419 checks、11386 numeric comparisons，25.954930秒/300，首次PASS；
最大数值绝对差2.291500322826323e-12。回执SHA256
`4bc39c8e05b46dea291d6cd02037a64a407cd6f525b0db332186e172353fd980`。

D2使用新独立checker
`a352a46492692261ba90f223a41658435d520c3d615be82bde584e5f4359c9a7`，
不导入D1/D2 runner，绑定上述fresh父回执，独立核读全部原tap、控制、状态、四视图、
Float32运算、编译依赖/argv、Git原始源码及保存分数。首次PASS，无审计重试：
1146398 checks、10522 numeric comparisons，30.516287秒/300；最大数值绝对差
1.5116796703296131e-12。回执SHA256
`d3c163fe38f5199d0c5a03c3728dd2bde5db5964f7d6e651da4885093a7830e0`。
原ZIP到解包D1/D2关键文件的独立绑定另通过，回执SHA256
`c5d6408f212f4888237ceb876fff1cdc3545ef0e876cdc4724e5fa491d4a852f`。

数值1e-8仅用于冻结canonical/D19结果的一致性审计，不是新声学门槛；状态、波形、
原端点及源文件使用精确字节比较。审计不执行DSP或模型，不建立第二评分权威。

| 实际保存对象 | SHA256 |
|---|---|
| D2 report.json | `f259693095d73e8cca74e15cc60f0c4e1e157cfecab32706bee35926f2fca9ea` |
| D2 artifact-manifest.json | `e43fa150e38d65ecb43020f19a403547fce9634736735b0367512040b9c58a63` |
| fresh D1 report.json | `472e050dd155973c0a49fca1fb17c8204e240411ca37d99e3a81c1b777d8e958` |
| fresh D1 artifact-manifest.json | `84c6884037fc61aeee222033cf0b5a6f06c644114ffdeee1349ed61e6c2e86cf` |

## 核心结果：最终clamp没有改变样本

统计覆盖完整执行流，不只包含评分窗。60例是既有4组英文配对的场景/profile视图
加固定中文单句视图，不能解释为60条独立语料或60名说话者。

| 实际控制/算子 | A56 | C4 | 合计 |
|---|---:|---:|---:|
| 帧数 | 33600 | 2316 | 35916 |
| target被原allow cap的帧数 | 16367 | 1102 | 17469 |
| 输出gain被unity gate cap的帧数 | 15837 | 1102 | 16939 |
| 整帧peak ceiling生效的帧数 | 33 | 0 | 33 |
| peak view到最终clamp改变的样本数 | 0 | 0 | 0 |

全部60例的 `peak_capped` 与 `replay_final` 逐字节相同。因此，本轮AGC最终
逐样本clamp不可能解释观察到的分数变化；不能把整帧乘法限幅笼统称为硬削波。
这个结论仅约束这批实际输入和这个AGC级，不排除其它输入或上游的削波。

33个peak帧改变5280个样本。峰值限制的有无与状态增益变化是不同证据；不能
因为触发次数少，就推导对听感没有影响或允许移除保护。

## 固定公共跨度的有序变化

全部视图保持160样点偏移，物理跨度为`[0,N-160)`；没有重新搜lag或裁窗重置。
下表每格是对同profile/场景的4组配对分别计算的描述性中位数，单位dB。**不同列的中位数不能
相加当作总贡献**；有序差值也不是独立适应的因果干预。`state_only`的真实状态
已包含原allow对target历史的作用。

| 场景/profile | pre→state | state→output gate | gate→peak | peak→final |
|---|---:|---:|---:|---:|
| near-only / CALL | -3.191004 | 0 | +0.247070 | 0 |
| near-only / ASSISTANT | -2.525405 | 0 | +0.256563 | 0 |
| nominal双讲 / CALL | -0.356604 | +0.027108 | 0 | 0 |
| nominal双讲 / ASSISTANT | -0.327962 | +0.022714 | 0 | 0 |
| weak双讲 / CALL | +1.480561 | +0.071700 | 0 | 0 |
| weak双讲 / ASSISTANT | +1.900572 | +0.068614 | 0 | 0 |

原关注的pair0 nominal双讲可逐例相加，不使用聚合中位数：

| profile | pre→state | state→gate | gate→peak | peak→final | pre→final |
|---|---:|---:|---:|---:|---:|
| CALL | -4.924776489 | +0.014643873 | 0 | 0 | -4.910132616 |
| ASSISTANT | -4.688021945 | +0.011606574 | +0.029721124 | 0 | -4.646694247 |

显著下降已经出现在真实状态增益的时变作用；本例输出gate和peak没有造成其
主要负差值。near-only全程allow=true，同样有状态级变化；pair0 near-only的
peak级反而分别改善0.806454794/1.090535253 dB。但另有弱双讲例状态级为正，
因此不能将AGC全局解释为有害。

实际CSV还给出一个后继结构假设的可核查线索：pair0 near-only两profile的原生
frame0–193输入峰值都精确为0、allow都为1，target被限制为8，alpha为原Float32
0.015；状态从1升至frame193后的7.6269846。frame194才出现约7.3e-9量级的非零
输入。这证明数字零期间状态预充确实发生，不是人类VAD标注，也未证明它单独造成
整句分数变化；本轮没有干预状态更新时机或据此批准修复。

SI-SDR只消去一个全局尺度，时变增益可能因改变包络而降低它；AGC本来承担电平
控制。这个测量定位不足以证明识别/听感损伤，也不支持直接删除AGC、回扫旧增益
系数，或用输出全局归一化掩盖实际电平行为。静音预充和attack/release的独立作用
还没有被这四个视图分别干预，不能把它们称为已确证根因。

## 中文交互负结果继续单独保留

C clean的pre→state共同跨度RMS增加CALL 7.931050520、ASSISTANT 9.355652752 dB；
无输出gate/peak/clamp改变。C duplex两profile各551帧同时发生target和输出gate cap，
peak与clamp均零。pre→state RMS分别+0.001215263/+0.003100076 dB，随后gate给出
等量负变化，最终共同跨度RMS与pre相同到现有计算精度；这仍不代表Float32逐字节相同。
原D1已确认pre/final首差在CALL sample89013、ASSISTANT sample88960，均为frame556。

C没有准入clean-near阶段真值，本轮只报告实际能量和控制；不能从上述结果推导
近端被AEC/NS抹除、DTD false-negative rate，或把英文状态级观察套用为中文CER原因。
原固定中文单句clean CER=0/12、duplex CALL/ASSISTANT CER=3/12以及duplex KWS未命中
保持原判定；D1最终PCM与历史相同，不重跑模型，不将本轮诊断当作中文识别改善。

## 本轮决策与闭环边界

1. D1的16个英文nominal/weak双讲NS联合级公共跨度增量全正，旧NS/RES-off优先假设
   不进入候选执行；这不证明NS/RES在其它数据上无损。
2. D2排除了本组最后clamp造成分数下降的解释，并把原显著英文负差值定位到状态
   增益作用；不把原target-gate历史、初始静音、release或音质损伤单独归因为已证实。
3. 对讲继续需要电平、峰值和双讲约束，识别交互继续需要真实ASR/KWS证据；不得只
   优化SI-SDR就晋升两用途公共默认。旧paired target/limiter、global cap和adaptive
   release拒绝不重开。独立结构干预或新增数据必须另冻结，不能由D2方法自证候选。
4. 生产src/include/examples/cmake及默认参数保持4daa7e2，SDK版本2.3.63；测量代码、
   失败、输入锁、负例与实际构建/全部输出均已接入可重复的既有Actions入口。

本文固定首个有效D2测量source。最终PR head、保护合并及新main各自的完整Verify、
required summary、fresh D1/D2和独立原件回执，另在 [#922](https://github.com/jiying2007/audio-pipeline/issues/922)
按实际身份登记；不得借用cc853或旧31b的CI资格。没有真机、真实WAN、MOS、
泛化质量晋升、商业发布或tag声明。
