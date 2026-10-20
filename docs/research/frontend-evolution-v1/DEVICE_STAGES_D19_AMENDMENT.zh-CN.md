# D19 测量实现修正与失败保留

日期2026-10-11；对应[冻结计划](DEVICE_STAGES_D19_PLAN.zh-CN.md)。本修正保持数据、DSP函数体、参数、窗口和验收规则。

首次工件根`/tmp/audio-fe-device-stages-d19-20261011`完成库构建，但严格runner编译失败，尚未执行DSP回放。
内部头需要与冻结库一致的AEC backend及stage宏；runner最初未取得这些宏。完整失败stderr保存在
`command-compile.json`，终态`measurement-invalid.json`保留，不删除、不解释为通过。
修正版从实际生成`CMakeFiles/audio_pipeline.dir/flags.make`取得`C_DEFINES`，直接传给独立C编译，
不猜测内部类型布局，不修改冻结源或生成头。新工件根为`/tmp/audio-fe-device-stages-d19-r1-20261011`。

独立实现审查发现MAJOR-1：创建前拒绝已有输出根时，异常处理可能写入该已有目录。
修复为只有本次`mkdir`成功且登记归属后才允许保存失败回执；创建前拒绝只返回exit2。
负例覆盖既有目录、创建后受控失败，以及短trace/NaN/Inf和RMS已知答案。
这些负例是测量实现验证，不能替代实际32臂阶段观测及独立审计。

本次为第一次测量修正，消耗retry_budget中的1次；不改变验收阈值，不搜索算法，不抹去历史失败。
整体目标仍active，测量有效性与声学、AISpeech产品接入及物理资格分别验收。
