# D41 准入集合补充

2026-10-11，仅澄清原PLAN的whole准入集合，不调整算法、阈值、数据角色或预算。原PLAN字节保留。

每个candidate arm分别评分：12个非future return来源各8个fixed窗口，共96fixed；其中原near轨迹对应24个near_present=true、72个near_present=false。near24与no-near72仅来自这12个来源，不包含field/repeat/future。标签仅用于执行后的测量分类及开发准入，不传入DSP或保护函数。

无nearwhole准入只包含四个完整near轨迹全零的来源：return-A-r16-echo-shadow、return-A-r20-echo-shadow、return-ABA-r16-echo-shadow、return-ABA-r20-echo-shadow。每arm四whole，各final energy相对D39增加<=1dB。含near的dt/unguarded来源whole不参与该纯echowhole准入，但仍完整保留并披露whole与全部fixed测量。

因此每arm准入为：24个nearfixed的配对final known-near error中位<=-3dB且至少18个严格改善；72个no-nearfixed和4个纯echowhole各自final energy配对增加<=1dB，全部同时满足。两arm分别满足，不跨arm平均。共8个纯echowhole准入；完整四组合960组测量不因准入子集减少。

repeat仅作为一致性控制，其现场fixed窗口计入field描述99/arm；不是独立采集样本，不进入near24/no-near72/纯echowhole准入。future仅前缀因果检查，measurement/differences=null，不评分。
