# D30 实际Activity集成与oracle依赖诊断结果

日期2026-10-11；experiment=FE_DEVICE_ACTIVITY_D30；总体native目标继续active。
合同见[PLAN](DEVICE_ACTIVITY_D30_PLAN.zh-CN.md)及[执行前补充](DEVICE_ACTIVITY_D30_AMENDMENT.zh-CN.md)。
主测量有效，decision=ACTIVITY_INTEGRATION_DIAGNOSTIC_NO_PROMOTION；research_algorithm_changed=false、integration_changed=true、shipping_algorithm_changed=false。
实际Activity接入复现设备原轨迹，同时揭示合成双讲oracle保护不能由当前检测替代；promotion_allowed=false、shipping_approved=false。

## 精确身份与实际执行

local HEAD572b0e34a8a8e5663397ce16e378209ba9058d4d及既有dirty保留；冻结时live main373008e89f2ebaabc298d2c9613420b1d4811c78。
只链接原D18实际MDF/Activity库，SHA256=eb5b0c784c316e71d6ed9f58db6cb66f190b631daa00c55a94032168d5a47aa4，不重编或替换原DSP库。
工件根`/tmp/audio-fe-device-activity-d30-20261011`。
result SHA256=e0b74142093d4579615be9ffe047335b4618f46aa1116f0b24941bb921de470d。
binding SHA256=2558d74e0e8377087bcb1a44fc3e13d890c4da9b641b579db9d670e207083956。
主execution回执`/tmp/audio-device-d30-execution.json` SHA256=44a71653b497a2800e2ef494bd2991eb9d16dd69d2e755d92ac627b4e574857a，真实terminal exit0。
绑定655项生成工件；源码、输入及runner起止hash相同。

44主来源（32设备development、12合成/oracle工程）及新进程repeat/future共46次实际C回放。
单路AEC-input/reference上的两套AEC；原Activity每帧按实际输入Float32能量先执行，再驱动AEC/选择/过渡。
C入口只收mic/reference、帧数、通知及模式，没有外部gate/truth参数；原标签仅由回放后对照使用。
shadow通知只复制primary并reset shadow，Activity连续；这不是公共pipeline路径通知的reset语义。
上游BF/SYNC生成的输入仍冻结；未新执行完整BF/SYNC及NS/RES/AGC/VAD/KWS或AISpeech产品链。

| 累计统计 | 数值 |
|---|---:|
| 帧 / 样本时刻 | 126,486 / 20,237,760 |
| primary / shadow调用 | 126,486 / 44,564 |
| shadow完整reset | 30 |
| Activity / selector / transition调用 | 各126,486 |
| SYNC调用 | 0 |
| 实际混合样本时刻 | 89,920 |
| 总事件 | 281：主field243、return12、repeat/future各13 |

8条音频共161,902,080个Float32；state/selector/transition/activity四类CSV各126,486行。
primary state.csv只记录原诊断字段，不能扩大为完整MDF状态转储。

## 设备等价与控制诊断

32field主来源及repeat/future的原11输出全部逐byte复现D29，共374文件比较；实际far/dt与原门控全部一致。
field正常评分、窗口/null及事件保持原结果；不新增设备声学收益，也不改变D28原55个事件梯度增加等代价。
全部实际Activity按Float32能量、EMA、far迟滞、instant ratio及hangover完整回读；selector/transition按实际gate与bank重新核递推。
所有音频finite；mic代数最大绝对误差2.2351741790771484e-08；端点/过渡外精确核验，终态remaining=0。
repeat全部12输出全量同；future通知前12输出前缀同，整段activity.csv与normal逐byte相同。
future仍真实反号mic/ref后执行DSP，独立核实际代数与控制；不评分、不参加候选，不泛化为全部输入的因果证明。

12个return中8个来源的原11输出全量保持；4个dt来源只有mic/reference保持，其余9输出/诊断文件改变。
return原11文件共96个等价、36个改变；这包含真实两AEC演进及控制变化，不能称原bank普遍等价。
所有return的far与原far1一致。4个dt例各有400帧dt disagreement，另8例全部门控一致。
4个dt例的oracle双讲区间是frames[1000,1200)、[1600,1800)，即10–12s、16–18s；实际Activity各2000帧的dt均0。
oracle区间内instant mic/ref能量比跨四例为0.3434752821922302..0.7913883924484253；EMA比为0.36621686816215515..0.6576512455940247。
当前原算法onset要求EMA比>1.5且instant比>1.3499999046325684，hold要求instant比>1.0800000429153442。
本输入在这些区间未达到检测条件；这是冻结算法的门控机制诊断，不据此搜索更低阈值或声称真人检测准确率。

## 近端误差的收益与代价

所有原whole/固定窗/null和评分函数保持，实际结果及相对D29差值完整记录；本轮没有新候选准入门槛。
静态A的r16/r20 dt例whole selected known-near误差相对oracle控制增加约1.151/1.119dB。
ABA的r16/r20 dt例whole该误差反而下降约2.861/2.809dB，且10–12s的原窗口也下降；同时16–18s原窗口显著变差。
不能用whole改善抵消后续near窗口退化，也不能把所有窗口差异都称语音损伤。

| 原窗口示例 | D29 oracle控制error RMS dBFS | D30实际Activity error RMS dBFS | delta dB | near_present |
|---|---:|---:|---:|---|
| A-r20 dt，10–10.5s | -74.16484304555188 | -45.25329040135259 | +28.91155264419929 | true |
| A-r20 dt，10.5–12s | -74.20499669263964 | -41.73988740147366 | +32.46510929116598 | true |
| ABA-r20 dt，16–18s | -92.70297756449978 | -41.751913252916026 | +50.95106431158375 | true |
| ABA-r20 dt，18–20s | -96.36791152804442 | -45.72645483576026 | +50.64145669228416 | false |

上述error=residual减去已知合成near；不是输出音量、真人录音、设备ERLE或唤醒率。
大dB差值必须连同原低误差基准及绝对误差披露；近端停止后的窗口也有适应污染/恢复代价，不能称所有增量发生在人声期间。
输入near是独立合成noise/oracle工程真值，不是独立真人声学验证；当前仅证明原oracle保护对该工程对照的重要性。
return事件由原8增至12；ABA两dt来源各新增2次切换，静态A两dt来源仍0，设备243保持。
只读派生诊断脚本/回执`/tmp/audio-device-d30-gate-diagnostic.py/.json`记录原gate区间、能量比和原窗口绝对误差，不增加裁判或选型。
其SHA256=06b7a14d9569636c3ce8ff15c11d92e2fa6ac7ec0ca421fcca1aae8f319850aa / 09737fd0d6e666ca3ab4be10af33d0e1185428d039ac1de575871952f0c8f761。

## 独立实际审计

独立audit/六负例均首次执行真实terminal exit0、retry0，不导入新测量器、不运行C/AEC/Activity。
独立核46case、368trace、161,902,080个Float32；四CSV各126,486行。
34field执行的374个原输出文件全byteeqD29，102,486个field帧的实际gate与原gate相同；return far差0、dt差1,600帧。
独立复算476个原窗（本轮normal+repeat240及D29对照236）、1,133有效channel/295null；240个delta和108个known-near delta。
RMS/peak/delta、Activity Float32能量与完整递推误差均0；代数及所有实际calls/资源/281事件独立一致。
最大return窗口绝对error与near_present已独立复核，是上述16–18s合成近端窗；不是-240dB floor裁切造成，不推导真人损害。
audit脚本/回执`/tmp/audio-device-d30-independent-audit.py/.json` SHA256=6c5b317a872ed100d27e454639a47a353e2ddd6f04fd6c420e11f0ce378fad3d / 9daf5ad297eefb83616f0e21937f6f3cfa261d789c6228abde189e4ceb9160d7。
六工具拒绝均exit2；旧D29的675文件、新D30的659文件完整manifest起止同；仓根仅工具潜在measurement-invalid路径0文件，不锁全dirty。
negative脚本/回执SHA256=5d2d1a91d20d217f1bdc335e4c332b2b41460e69ecb9ee4821dce786a353e717 / 8829a32e5bec93324a197fa60600c8c856bd9a7db3964badc26ce700c1149774。
全部源/结果/失败与检查由review-snapshot-v1.json绑定；whole-change fresh review及REVIEW后复验另见[REVIEW](DEVICE_ACTIVITY_D30_REVIEW.zh-CN.md)。

## 资源、失败与边界

实际sizeof(Activity)=28B；两AEC66,040B、selector20B、transition16B、8帧缓冲5,120B，局部合计71,224B。
满足本轮128KiB局部预算，B0 50,000B不改，两AEC状态自身仍超限；不包含其它局部变量/stdio/库/完整栈或进程总资源。
没有DUT CPU/RSS/热/功耗、完整前端链或产品部署资格。
预编译第0次真实exit1，嵌套D29 runner的main宏重定义；仅改新D30包含方式及显式组合自测，原依赖和警告不变。
原失败回执SHA256=b2061a33c1d477c1988c1c816dc47f70984bbc28c464c623e12f55011d9b516b。
原源码base64/hash快照SHA256=67cb91a32a1ca25ff403c990530cbfd3f62dade6deb987fab91d2629de93c2e9，能还原失败源码。
第1次严格编译、自测及4项Python tests通过；预编译retry1，主46次DSP重跑0，不称整轮零失败。
主严格编译/自测/argc与4完整非法参数拒绝通过，12输出sentinel保持且AEC/Activity调用0。
非仓cwd help/dry-run/4tests均terminal exit0，dry-run未建输出根。
Provider route unresolved/current为空，知识线NEEDS_REVIEW；仓内reviewing candidate，不声明正式归档。
原D0-D29源/工件与用户dirty保留，无commit/push/PR/merge/发布/设备写；总体目标保持active。
下一阶段优先near保护的可辨识观测和完整前后处理影响，独立冻结新假设；不依据本轮差值直接扫阈值。
AISpeech产品调用链、真人独立检测、owner/E001/PQ、目标资源及API/default分别未闭合。
