# 噪声估计器 clamp 内联：不改变生产代码

基线6bc79ae。独立有界实验将噪声估计器跨编译单元clamp调用替换为同表达式局部内联，未改变状态、参数、浮点运算或默认算法。EMA/MCRA各872,000次输出与完整状态逐字节相同；72条固定主机微基准观察的几何平均耗时比0.74898645，局部耗时降低25.101%，初筛仅REVIEW_ONLY。

继续集成发现默认pipeline采用unity编译。按相同顺序编译完整NS、tracker、window与FFT后，两种模式各3,600帧输出/完整状态/结果逐字节相同，且两臂完整对象反汇编除文件名头外完全一致：基线clamp已被编译器内联。因此局部25.1%不能推广成默认pipeline性能提升，最终NO_PRODUCTION_CHANGE，不为无实际收益的代码改动开生产PR。

两种模式ASan/UBSan（关闭LSan）通过；原噪声/window单测四项通过；错误clamp负对照均拒绝。初次严格编译错误、缺window依赖失败均保留。CMake缺失且安装被环境批准机制拒绝，没有绕过；完整CMake/CTest、端到端pipeline和SSC305仍未验证。未重复性能测量挑选结果。

[原始结果](ns-clamp-inline-v1/RESULT.md)、[集成适用性](ns-clamp-inline-v1/integration/RESULT.md)、[冻结合同](ns-clamp-inline-v1/PLAN.json)、[证据传输说明](ns-clamp-inline-v1/TRANSPORT.md)保留完整边界。仅归档研究证据，不改生产、CI门槛或历史结果。
