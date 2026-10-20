# D46 时序归因计划独立审查

2026-10-12，experiment=FE_DEVICE_RELEASE_PATH_ATTRIBUTION_D46。claimant=root；verifier=device_capture_independent_review；Reviewer Independence=independent。Review Target 为新 PLAN 的当前工作树字节及其明确消费的 D45/D25 冻结来源，不是 D46 实施或执行验收。

PLAN SHA256=`b442e58a8cbe0a31a5b4c67fa14e5d20c98951641db667978c41b7f519e97366`。本轮只读审查除本新增 PLAN_REVIEW 外未修改仓库；没有执行 DSP、D46 正式测量或旧全量审计。原 dirty 与历史工件保持。

## 结论

Spec PASS；Quality PASS；Reviewer Independence PASS；blocker=0、major=0、minor=0、question=0，unresolved=0。计划具备可实施、可独立复算的输入集合、坐标、数值规则、数据角色、预算与失败保存合同。此结论允许后续登记新任务并准备实现，不能声明正式测量通过、完整根因成立或 D45 候选获准。

## 实际计划核验

独立读回 D45 result 的 return 集合：12 个 source_case × primary/selected 两臂，共24个配对；monitor/candidate 两模式共48条 case 记录，全部2000帧。集合包含 A/ABA、r16/r20、echo/dt/unguarded，明确排除 field、repeat 和 future。由这些记录派生实际96份NS/final PCM及48份power.csv，共144个不同输入；逐文件SHA与D45 binding.artifacts相同，最大文件1280000字节，满足每输入4 MiB预算。实际只读检查 tool chunk=`ac7ef5`，exit0；这是输入身份核验，不是D46正式统计或DSP执行。

D45 result/binding pins与计划一致。历史47项snapshot SHA=`a19d6269921530b6d8890dfa4eded1340a7d9e86c1991376f9ba035a6eae21cc`及其全部当前文件字节独立回读匹配；只核这份既有快照，不重新运行D45测量。此时新D46正式root不存在。

冻结D25 C SHA=`079c0bc34b605d855ce728cceeb8656204cbf86192bdeaa48724454a9e4eaeab`、Python SHA=`26f28c5cf83fe5882d18bd2b86c7c2670b26494c20131c98556cb7c9567e02a0`实际匹配。C与Python均明确ABA仅在样本[160000,192000)使用B路径，其余使用A；near非echo条件只在帧[1000,1200)及[1600,1800)开启。A形状没有路径切换，同样保留这些固定时段；echo条件没有near，不能将阶段标签误写为实际近端检测输出。

上述集合、源身份及坐标检查 tool chunk=`669743`，exit0；D25条件源码读取chunks=`2a9c9b`、`23f7ee`。当前HEAD独立只读为`572b0e34a8a8e5663397ce16e378209ba9058d4d`；本审查未重新查询远端CI或Provider，不把主代理的远端恢复记录扩大为独立外部核验。

## 坐标、数值与可复算性

七个原frame段连续、不重叠，合计[0,2000)。按固定160点延迟分别映射为output[160,160160)、[160160,192160)、[192160,193760)、[193760,256160)、[256160,288160)、[288160,289760)、[289760,320000)。实际可评分样本合计319840；最后段实际input结束于319840，截去末160样本，不评分output首160，不flush或补样本。24对×7段=168 pair-segment；NS/final两stage共336分段测量，另有whole直接重算。

float32LE长度与finite、float64顺序左折叠能量/差异能量、peak、energy_delta、严格零/null，以及分段sum对whole的固定容差已明示。实施与独立审计应分别使用实际读取的同一冻结范围，保留原始input与截断后input、output和tail计数，不引入epsilon能量或新评分阈值。

power18字段按原frame坐标计数，与延迟对齐的波形坐标分别呈现。两模式仅raised允许差异；candidate raised=post_would_raise、monitor raised=0，旧统计与门控投影保持。固定分段统计可解释差异分布，但FFT/OLA以及过去统计意味着它不能证明逐帧一一因果关系。全部24对和全部阶段应报告，不能只选纯echo ABA或既有最坏窗。

## 生命周期、预算与后续门禁

新namespace和output root、已有root/外部root/own及parent symlink提前拒绝、intent先于操作、异常/partial保存和未知不重放已写入合同。正式180秒、独立180秒、root16 MiB、单输出4 MiB、free512 MiB为新离线诊断预算；不得借此改旧DSP或审计预算。对应实现及one-shot控制仍须独立审查，非仓help/dry-run、known-answer/negative与实际完整测量仍未执行。

纯标准库、不import测量helper、不重跑AEC/NS/AGC/VAD可避免用原测量器自证。144输入及明确result/binding/snapshot/CLOSEOUT/D25 pins起止锁可建立消费身份；独立审计必须自行计算336分段和whole，不以已有intake probe代替新正式结果。

data_role保持development-and-synthetic-engineering；measurement_only=true、algorithm_changed=false、promotion_allowed=false、shipping_approved=false。固定阶段不是blind数据或验证级标签，不能选择新候选、改D45原准入或推出唯一根因。全部FFT、完整EMA/noise历史、真人近端识别、目标板/HIL/PQ仍不在本诊断覆盖内。

计划审查完成时D46未实施、未正式运行，也未收口。原intake probe只是主代理只读探索，本轮没有独立重算其全部数值或把它升级为正式D46。D45 DEVELOPMENT_REJECTED保持；知识Provider unresolved/NEEDS_REVIEW，无归档成功；总体native目标active不由本PLAN PASS完成。下一步是主代理登记、实现和独立实施审查，之后才允许唯一正式测量。
