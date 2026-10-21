# D8固定长窗大跳确认结果

日期：2026-10-10；机械结果：DEVELOPMENT_CANDIDATE_ONLY；选型状态：INCONCLUSIVE_ALIGNMENT_AND_ACOUSTIC_EFFECT。
依据：[冻结计划](DEVICE_ROUTE_D8_PLAN.zh-CN.md)、[失配恢复契约](DEVICE_ROUTE_D8_RECOVERY.zh-CN.md)。
本实验单独实现D7提出的假设，D4拒绝及D5/D7历史测量不改写。
Provider unresolved，仅仓内reviewing候选，未正式归档或批准shipping。

## 结果与取舍

候选在原大跳分支三次确认前加入固定40ms候选相关门限，沿用原0.0324；
不改变大跳范围、原三次确认、small/drift、AEC、产品配置或输入数据角色。
目标rpm480/far-motion tracked1中172ms跳变消失，delay集合由1/2/3/172变为1/2/3ms；
jumps/resets由2/2变0/0，slips由50变48，rail仍0。这是开发稳定性信号，不是ERLE或人声保真。

| 比较项 | 实际结果 |
| --- | --- |
| 16例70固定+2复跑 | 正式receipt契约通过；独立审查者从临时source复验通过 |
| 70固定臂 | 63臂PCM/metrics相同，7臂改变 |
| tracking关闭控制 | 34臂逐字节相同 |
| 新增jump/reset | 全固定臂无新增；既有计数减少不自动表示对齐更准确 |
| 原严格CTest | 14/14通过，包括已知路径恢复和periodic假跳负例 |
| ASAN+UBSAN CTest | 14/14通过，仅Host工程资格 |
| 额外直接SYNC工程集 | 8/16k已知评分、历史/失配拒绝、reset、隔离、禁用、低相关通过 |
| public API失配恢复 | 40ms正常→未通知失配保持40ms→显式CAPTURE_GAP后恢复80ms；jumps=0/0/1 |

必须保留不利观察：rpm240/far-motion default/sync-control阻止原40ms→6–7ms迁移，
rpm480/double-talk-motion default阻止原40ms→7–8ms迁移，保持约39–40ms。
没有独立真实延迟标签，不能断言这些迁移原本正确或错误。
far-motion default原19–21s窗口RMS=-28.7280dBFS，候选=-26.2916dBFS，上升2.4364dB；
double-talk-motion default同窗口由-27.7416变-26.1146dBFS，上升1.6270dB。
目标tracked1同窗口从-27.5394变-29.9147dBFS，下降2.3754dB。
总能量不能区分回声、人声或噪声，这些变化只作诊断，不能据此选型或宣称算法音质收益。
default目标case的slips由23增26，也保留，不当作额外jump/reset回归或确定漂移质量。

因此只保留工程候选：mechanical_decision=DEVELOPMENT_CANDIDATE_ONLY；
selection_status=INCONCLUSIVE_ALIGNMENT_AND_ACOUSTIC_EFFECT；promotion_allowed=false；shipping_approved=false。
不能把comparison的机械通过单独当选型批准，最终须同时读decision.json的风险与限制。

## 资源、恢复与失败保留

候选使用每state160个stride4 floats；真实sizeof为pipeline=78840，基线78192，增加648bytes；
ceiling=80000未放宽，余量1160bytes。无新堆分配/TLS；不是SSC305 CPU/stack/RSS/热功耗资格。
8k40ms=320点，16k40ms=640点；score索引与原stride4一致。
计数失配后不自动恢复评分，必须遵循既有notify_stream_discontinuity/reset契约建立新epoch。
public恢复链路测试通过，但不能当实际XRUN、设备render时轴或元数据接入证据。

补充恢复测试首次strict编译因printf把uint64计数写成%u失败，recovery-build.json保留exit1及原错误。
修正为%llu加显式unsigned long long后recovery-build-v2/recovery-v2通过；候选DSP从未因此修改。
初次sizeof probe缺实际stage宏而编译失败；按原build的真实定义重新测量，未使用失真的精简state结果。

## 制品身份与持久复跑入口

根目录：`/tmp/audio-fe-device-route-d8-20261010`。
候选source只差src/sync/ap_sync.c/h；公共产品源码保持D6基线，无SCM/设备写。

| 证据 | SHA256 |
| --- | --- |
| replay/receipt.json | eb85a87a494d08ce35be0f9cd47ba0030be9336ec85e35ade0322837d10cbedc |
| comparison.json | 3367b128f3269a311b59aad937549d440b6f06732858a5e388757645d3d5d6d7 |
| decision.json | 418029f81ab9a729ad3be41aa6756d16f508b0d7eec7dd3b1204eb7227a82b22 |
| binding.json | eaac4f795ae4378c60ff3bf1a88e1746a00dcbb50beb6cbd6344f83c0376f108 |

binding覆盖source、输入/配置/输出receipt、所有命令日志、库、cache、runner、脚本、冻结计划、
两项工程fixture、原格式错误、ASAN记录和最终decision；独立审查不能只读摘要。
[研究补丁](../../../.github/research/frontend-evolution-v1/device-route-d8.patch) 仅用于D6精确源码的独立副本，
git apply --check通过；实际副本应用后两个源码逐字节等候选，结果绑定在binding。
[直接SYNC fixture](../../../tests/validation/frontend_evolution/device_route_d8_engineering.c) 和
[public恢复fixture](../../../tests/validation/frontend_evolution/device_route_d8_recovery.c) 已原字节持久保存，
不加入产品build/CI默认目标；直接SYNC fixture要求先在独立副本应用研究补丁，不能对shipping源码运行假PASS。

复跑顺序：核D6源码锁和原119输入锁→创建新独立副本→核研究补丁及计划hash→apply到副本→
strict build/原CTest→按engineering-build/recovery-build-v2日志在副本编译持久fixture→
从副本运行原device_replay 70+2→独立verify→比较控制/原counter/所有RMS诊断→完整审查。
不可覆盖失败目录，不把tmp绝对路径当长期发布接口；raw/PCM和二进制不进入Git。

## 下一项需要的证据

本轮已减少指定大跳且保留工程恢复；仍需区分“正确对齐获取被阻止”和“错误候选被拒绝”。
下一项先做已知注入delay、独立宽带/周期/语音/低参考/双讲的获取与恢复矩阵，
以及真实同步render/麦克风标定和人工人声标签。冻结新的数据/评分/算法身份，不能回调本轮门限洗绿。
E001、owner、独立声学、shipping和PQ均保持未验收。本结果不授权AISpeech替换或产品默认修改。
