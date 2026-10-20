# D17 参考坐标诊断结果：20点采集偏置与1ms回放不等价

日期2026-10-11；experiment=`FE_DEVICE_ALIGNMENT_D17`；[冻结计划](DEVICE_ALIGNMENT_D17_PLAN.zh-CN.md)。
实际结果 **ALIGNMENT_CONTRACT_DIAGNOSTIC_NO_PROMOTION**；`promotion_allowed=false`、`shipping_approved=false`。
总体目标active；本轮没有算法候选，不改变D8/D11/D14/D16原结果。

## 实际数据关系

原119文件锁完整通过；16场景原生输出共 **7,715,328 samples**。
全部session报告ref_delay_samples=20，原used逐样本满足：

```text
used[j] = 0                        当 j < 20
used[j] = raw.channel0[j - 20]      当 j >= 20
```

独立队列模拟初始20个零，每次append128点、每累计256点mic消费256点ref，
完整输出与直接索引、实际ref_used数据逐点及S16LE hash相同，跨hop没有多加128或256点延迟。
该关系说明捕获序列间的确定性偏置，不说明声学路径真值或设备实时端到端延迟。

原D16 adapted mic/render全部匹配：render为raw.channel0、mic保留两通道interleaved，
相同16 kHz、没有重采样，取配对native前缀后再取完整160点帧，无尾部补零。
9场景留下128点未配对input，总1152点；9场景各移除32点native尾，总288点；
最终replay前缀共 **7,715,040 samples**。两个尾部角色不同，不把未配对input冒充输出。

## 固定坐标对照

以下只比较原used与固定延迟序列的字节，不处理DSP、不搜索lag、不评价音质。
8个far/double-talk/far-motion/double-talk-motion场景可辨识，
8个quiet/near/motion/near-motion场景的播放参考为零，对所有固定移位均不可辨识。
静音byte-equal不能证明参数正确。

| 固定诊断 | 相对raw的延迟 | 可辨识场景 | 全16前缀不相同samples |
| --- | ---: | ---: | ---: |
| 原delay减1点 | 19 | 8/16 | 2,991,368 |
| 原delay加1点 | 21 | 8/16 | 2,991,368 |
| 原1ms回放初值 | 16 | 8/16 | 2,999,496 |
| 默认40ms初值 | 640 | 8/16 | 3,017,279 |
| used再加原20点偏置 | 40 | 8/16 | 2,999,984 |

20/16000=1.25ms，1ms初始化为16点，少4点/0.25ms。
原tracked1/fixed1是已冻结的1ms诊断臂，不是精确复制设备20点参考；旧结果不因此失效或被改写。
差异计数没有质量排序意义，不能从数值大小选择新的delay。
used再加20点展示重复补偿后raw总偏置40点；这是负例，不是当前adapter已经重复补偿的证据。

## 当前源码契约及边界

HDI input callback发生在ref缓冲之前，采raw两路；当前默认ref队列预留20个零，
只读取raw第0路。SEVC_API_FeedPlanar和output callback使用同一缓冲ref指针。
该源码支持上述模型；hdi HEAD=d83d52838d6be20ff36ff8ba266969cd819bb7c4且有既有staged改动，
app_audio_test HEAD=c81084935638f3d3771f7c3226db0314c078d800且clean。
本轮绑定当前文件hash/实际Git状态，不推定这些就是采集时设备binary。

SDK初始化为initial_delay_ms×internal_rate/1000；本轮内部率16k，默认40ms=640点。
SYNC reference取数起点=render_total-frame_samples-delay_samples，正delay读取更早raw。
render先push一帧再process同坐标mic，没有因160点重组自动新增整帧偏置。
漂移启用时还存在drift_credit分数插值，故固定样本比较不是完整自适应reference回放。
metrics显示delay_samples×1000/rate的整数商：16–31点都可能显示1ms，20点也显示1ms。
不能从estimated_delay_ms=1推定内部16点或物理正确；1ms配置值与1ms显示值语义不同。

真实DSP还涉及float输入、HPF/BF、AEC自适应与后续处理。adapter字节匹配不是完整产品同算法等价。
20点是已知捕获参考偏置；默认40ms是SDK先验。二者差异不是40ms默认有缺陷或真实路径应20点的证明。
raw坐标与used坐标必须在后续实验显式选择；禁止自动相加或按每个场景最优相关对齐。

## 执行证据与恢复

新增[研究工具](../../../tools/codex_assets/device_alignment.py)仅stdout，不写数据/输出文件。
实际命令均在/tmp cwd执行并保存command-0..3.json：

| 命令 | exit | 证据 |
| --- | ---: | --- |
| test_device_alignment.py | 0 | 5项测试，12组长度/延迟子例，边界方向、固定负例及非法参数 |
| device_alignment.py --help | 0 | 非仓库cwd CLI smoke |
| device_alignment.py --root 原tests/audio --receipt 原D16 --dry-run | 0 | 全16逐样本重建及起止input回读 |
| 同命令但receipt换成D3计划 | 2 | D16身份漂移拒绝，未测量新数据 |

已知答案queue子例为4长度×3delay=12组；另负例覆盖19/21/16/640、重复补偿与静音。
表中测试总数为5个unittest方法，不能把子例数当独立声学场景数。
工件根`/tmp/audio-fe-device-alignment-d17-20261011`，未复跑70臂DSP。
result.json SHA256=`8d587b8975abb7311b480fa5688f04901af582b02e0e919e07f71dbd9e50bb06`；
binding.json SHA256=`400b7963fe0d16485496405ededaa1ede4f41e6c6d9874ab7dc4819f9924cb8e`。
binding包含16个source/plan/tool/script文件的起止hash与外部仓状态、命令回执/result。
独立复审和文档snapshot另绑定；tmp失效须先恢复核hash，不能仅凭本文认定证据新鲜。
Provider route unresolved知识线NEEDS_REVIEW，当前只形成仓内reviewing candidate，未正式归档。

## 下一动作

下轮可独立预注册“精确捕获参考”集成诊断：使用used作为render、initial0、固定关闭跟踪/漂移，
先证明送入AEC前的样本坐标等价，再与原raw+fixed1比较。这个臂只重现参考消费坐标，
不是把20点当声学最优值；不能直接修改默认或豁免旧新增jump/reset。
若需自适应路径比较，必须明确raw/used坐标和已知偏置，冻结初始化、计数及真值资格后另做候选实验。
真人clean target、独立标签/下游唤醒ASR、物理校准/目标板资源/HIL仍待真实证据；总目标不关闭。
