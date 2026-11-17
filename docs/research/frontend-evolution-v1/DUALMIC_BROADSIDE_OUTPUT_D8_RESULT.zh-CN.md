# D8 broadside 输出：有效结果与关闭记录

## 结论

**NO_ADVANCE；measurement_valid=true；promotion_allowed=false。**

首个完整有效执行为 [Research run43135999005](https://github.com/jiying2007/audio-pipeline/actions/runs/43135999005)，attempt1，job130911420512。科学执行提交固定为 `0fe59e3c852f2150f717ee9dbb92ace517f2816b`，tree `82b482bbdaffd333774ac06efef77fbfeb0f8217`；合同为冻结R3 `8e3f92af6c4b0d3205a6903e8de31e55c0225a9e`。后续归档文档或CI提交不是新的科学执行SHA。

全60视图、35,916帧、5,746,560样本、362固定窗口与8次原始reset完成。全部16个primary common-span结果均未达到预注册的+1dB研究继续门槛，还有近端不回退、projection不下降、控制能量与恢复时间否决项。此单一候选关闭，不提升生产/default/API/version，不启动下一种lag或参数扫描。

该实验只测试生成研究副本中一次BF输出采样lag设为0的总效应；FULL tracking、状态更新、fallback、权重/gain/history/reset及独立下游pipeline保留。四个原始recorded pairs派生出相关视图，不能当作16个独立样本。+1dB是有限研究预算的保守继续筛选，不是听感阈值、临床标准或统计显著性。结果不证明D7关联就是因果损害，也不消除实际阵列、clock、校准和truth缺口。

## 完整归档与证据边界

- [完整终态导出](dualmic-broadside-output-d8-result-export.json)：保留日志中整条JSON及恢复的单个LF，未改写数值、未删负例/null/window/curve。967,201 bytes，SHA256 `095a7e4b27e04d53b9316872a633f5a569477031aedf4c744fe06e5cc6bde8c2`，Git blob `e7a6c475fc952cecaa937071ffe2a67a9a651797`。
- [终态身份清单](dualmic-broadside-output-d8-terminal-lock.json)绑定原run/job/head/tree/artifact及console-reported文件描述符。
- [原完整artifact13907504634](https://github.com/jiying2007/audio-pipeline/actions/runs/43135999005/artifacts/13907504634)：629,265,247 bytes，SHA256 `ed302fc060dba6ee29c62de6583c579c678da984497f3cfe1c10d5efb08f5057`；上传日志报告3,832文件，到期2027-02-10T01:39:29Z。ZIP包含原original.zip，其压缩总大小不是512MiB结果逻辑字节cap的实测值。
- 完整decoded job log为1,003,432 UTF-8 bytes（含BOM），SHA256 `9fde04b745095cd27b293b13f6dbd8b675d11265a432ae020fd6962aec5a0130`。这不是压缩GitHub日志包hash。

console中的描述符：
- report.json：16,809,218 bytes，SHA256 `441e56d739bd5473c0d58be6cbc4191aed6f03a40081f9809412deb25ed7d32a`。
- negative-tests.json：459,310 bytes，SHA256 `d30286fda74c3ba36b85e2efbc65216b472018b9cc783087b8843851b83b55b9`。
- completion.json：595,883 bytes，SHA256 `b27b658abb280e884b745b7cd877d25d119ca8784182392a77639849c178112b`。

成功的mandatory源码门禁、FINISH和job success支持本次完成76项targeted negatives、1,958项新增工程controls及既有controls、4个fatal fixtures，并完成原件/源/状态/算术/closure/预算核验。上述文件描述符从实际console读取；本归档作者与结果审核没有另行打开这些ZIP成员、PCM/state或full report，也没有独立取得最大child用时、实际预算类别总量或完整negative/completion收据字段。不能把归档检查称为独立raw-binary重算、实验复现或重新执行科学门禁。

## Primary最终S16结果

端点为最终交付S16/32768，固定physical[0,N−160)对output[160,N)，canonical `si_sdr_span`，无±3ms lag搜索。以下为原JSON的数值表示；决策基于完整精度，未用四舍五入或epsilon。

| 视图 | baseline SI-SDR dB | candidate SI-SDR dB | ΔdB |
| --- | ---: | ---: | ---: |
| A/pair-0-doubletalk-nominal-call | 5.842548751518564 | 5.780888355168406 | -0.06166039635015785 |
| A/pair-0-doubletalk-nominal-assistant | 6.162696711148463 | 6.102202115844068 | -0.06049459530439538 |
| A/pair-0-doubletalk-weak-call | 5.740570219117071 | 5.736360161544772 | -0.004210057572299419 |
| A/pair-0-doubletalk-weak-assistant | 5.721682508002308 | 5.713397825671143 | -0.008284682331165527 |
| A/pair-1-doubletalk-nominal-call | 0.9261313359314955 | 0.9603252667556503 | 0.03419393082415478 |
| A/pair-1-doubletalk-nominal-assistant | 0.8568674963936662 | 0.9119512118458019 | 0.05508371545213564 |
| A/pair-1-doubletalk-weak-call | -3.167779050092769 | -3.0305348456787606 | 0.1372442044140083 |
| A/pair-1-doubletalk-weak-assistant | -3.4772010989621633 | -3.232968753592829 | 0.24423234536933425 |
| A/pair-2-doubletalk-nominal-call | 7.593853894468818 | 7.5857410423493015 | -0.008112852119516845 |
| A/pair-2-doubletalk-nominal-assistant | 7.51920098441208 | 7.505140024128782 | -0.01406096028329884 |
| A/pair-2-doubletalk-weak-call | 5.907809896234167 | 5.89597310461992 | -0.011836791614246778 |
| A/pair-2-doubletalk-weak-assistant | 5.465948710817676 | 5.438773431197941 | -0.027175279619735093 |
| A/pair-3-doubletalk-nominal-call | 3.2862442144614885 | 3.3772958294055124 | 0.09105161494402392 |
| A/pair-3-doubletalk-nominal-assistant | 2.8233022609583793 | 2.907348775958435 | 0.08404651500005578 |
| A/pair-3-doubletalk-weak-call | -0.7807866110053351 | -0.6842861405915256 | 0.09650047041380949 |
| A/pair-3-doubletalk-weak-assistant | -1.3383047252425884 | -1.2079678676787846 | 0.13033685756380375 |

16项中8负、8正；范围−0.06166039635015785至+0.24423234536933425dB，0/16达到+1dB。不得挑选局部正值替代预注册的每项门槛。

## 全部筛选与null保留

独立text/result review逐项重算导出值对应的1,012个strict谓词，与归档中的checks/vetoes一致；这只审核导出值之间的一致性，不是从音频重新计算指标。

| 检查 | 失败/总数 | 说明 |
| --- | ---: | --- |
| primary common-span +1dB | 16/16 | 全部未达到 |
| near不回退 | 44/192 | 8个common、36个scored windows；15个视图至少一项失败 |
| projection不下降及anti-collapse | 56/192 | 9个common、47个windows；没有null/nonfinite或≤−120dB失败，失败来自candidate projection下降 |
| 控制RMS/peak不增加 | 87/452 | 19/28控制视图；A far-only28项、path-change24项、render-gap14项，C duplex21项 |
| convergence/recovery不变慢 | 1/40 | A/pair-0-path-change-call的post-event recovery由540增至550ms |
| S16 clip与actual AGC terminal clamps | 0/120 | 两臂全部60视图的两类计数均为0 |

32个near common-span中8负、16相同、8正。160个实际scored windows中36负、80相同、44正。全部28个无clean-near common-span与202/362个null windows原样保留，未伪造为0分。16个near-only/silent-render对照的exact标记全部true。C仍无准入clean-near参考，能量风险门槛不是语音质量证明。总体35/60视图至少一项veto；25个视图通过各自局部检查不改变整项NO_ADVANCE。

恢复指标保留原 `_window_erle`/`_settling_ms`、完整曲线和own-tail-relative语义。540→550ms是该定义下的比较；不能把own-tail-relative时间当成绝对质量。全部原窗口和scored/null规则继续使用原合同，不按候选输出选择适用性。

## 实际时间边界

以下是日志中六位小数monotonic标记差值，属于复合墙钟区间；不是完整command receipt的sub-timing读取或纯DSP profiling。

| 阶段 | 秒 |
| --- | ---: |
| admission | 49.808230 |
| baseline-build | 38.463569 |
| candidate-build | 17.112713 |
| run | 270.290268 |
| analysis | 122.441890 |
| verify | 128.305289 |
| negative至FINISH | 270.958624 |

FINISH在897.737564秒；root仍余302.262436秒、negative仍余29.041364秒。正常supervisor成功退出还要求finished protocol、worker exit0、无后代、pipes/responses排空及最终deadline仍有效。此次满足冻结上限，不保证以后同类运行的速度。本候选已关闭，不为了性能比较再跑科学实验。

## 所有先前失败继续保留

| 尝试 | 原执行SHA | run / artifact | 实际结论 |
| --- | --- | --- | --- |
| 1 | e4d0b8dfb30169e5628ee2bd31ed8df54f7d65e3 | [43115604725](https://github.com/jiying2007/audio-pipeline/actions/runs/43115604725) / 13897369988 | MEASUREMENT_INVALID；D8_FULL_ORIGINAL_LOCK，漏验证移除第三个metadata annotation |
| 2 | a1c69806143e96c585ce65568d0a5c5d03139a0f | [43118580272](https://github.com/jiying2007/audio-pipeline/actions/runs/43118580272) / 13900090732 | MEASUREMENT_INVALID；D8_TOOL_MISSING，泛化日志未标明工具名，CMake路径只作源码依据推断 |
| 3 | 4a86ad099010ae1aead149414091b88be73c7f3e | [43121241713](https://github.com/jiying2007/audio-pipeline/actions/runs/43121241713) / 13900578432 | MEASUREMENT_INVALID；run phase300秒到期，最后持久化至case25 candidate-observed PENDING |
| 4 | a462a4edafbeda710184930413448ac80c173be4 | [43133029682](https://github.com/jiying2007/audio-pipeline/actions/runs/43133029682) / 13906123706 | MEASUREMENT_INVALID；合成identity fixture字典共享别名，D8_NEGATIVE_ACCEPTED:before-dev |
| 5 | 0fe59e3c852f2150f717ee9dbb92ace517f2816b | [43135999005](https://github.com/jiying2007/audio-pipeline/actions/runs/43135999005) / 13907504634 | 完整有效NO_ADVANCE |

第3次失败的额外[只读诊断run43126999200](https://github.com/jiying2007/audio-pipeline/actions/runs/43126999200)、artifact13903289018只读取固定旧收据，没有重跑科学实验。各失败的完整hash/size、原证据边界与修正过程见[实现记录第8–12节](DUALMIC_BROADSIDE_OUTPUT_D8_IMPLEMENTATION.zh-CN.md)。后来的成功没有覆盖或重新标记先前无效结果。

## 关闭后的CI与重开边界

关闭路由将当前D8的PR、main push和manual选择导向明确命名的archived-evidence-validation，只验证上述不可变归档、schema、counts、printed-value decision consistency及未变的科学源/合同绑定。它不下载原artifact、不编译、不DSP、不重跑原76项科学negatives。输出 `ARCHIVED_EVIDENCE_VALIDATED_NO_DSP`仅代表归档校验，不代表在新的CI SHA上复现原实验。

归档checker独立固定旧execution SHA/tree与export SHA/size，不以可变清单自证身份。它在固定120秒外部SIGKILL监督下，只读既有checkout、固定归档和Git对象；采用lower-only资源限制和有界pipe/stdout，无仓库模块导入、安装、网络下载或新文件写入。该代码只读性来自明确操作集合，FSIZE=0本身不是文件系统隔离证明。普通调度、Python信号交付和内核延迟仍存在，不宣称瞬时物理终止。

为兼容既有protected squash策略，运行时不依赖旧execution commit仍在本地Git ancestry中。原execution SHA/tree在归档审核时固定；新CI只读取当前HEAD，用独立固定的原始tree指纹检查六个允许归档路径之外的Git条目，并实际核验107个源文件及10个production root对象。旧workflow由严格inverse/forward变换及原blob身份约束，D1–D7和dormant科学job不变。这是当前源码对固定证据的等价性检查，不是runtime ancestry证明。

归档缺失、损坏或源/依赖漂移必须fail closed，不能回退到原科学job。既有path filters不扩大；单独且不匹配D8的依赖变更沿用原工作流策略，不声称持续重验所有未来变更。D1–D7既有selector/job保持原样。原D8科学job保留为dormant历史能力；明确的新用户请求及独立审核后的source/routing变更才可重开，现有manual D8选项不会隐式重跑。本结果不授权任何后续sweep、promotion、生产/default/API/version变更。
