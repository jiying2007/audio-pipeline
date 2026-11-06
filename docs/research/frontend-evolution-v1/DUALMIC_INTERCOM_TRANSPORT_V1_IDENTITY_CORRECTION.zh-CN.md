# 对讲 V1 配置证据修正：执行前记录

日期：2026-11-06（Asia/Shanghai）。根审查发现以下独立集成证据缺陷；修正后
重新执行相同冻结矩阵，不改变算法、默认参数、八场景、阈值或预算。

原实现 `e7f4b67b24cc26336b8356e8a5bfbd9fc4aa254f` 在 `--identity` 和执行报告中
输出了请求用的 `ap_config_default(AP_PROFILE_CALL)`，随后实际初始化虽然成功，
但没有调用公开 `ap_pipeline_get_config()` / `ap_pipeline_get_tuning()`。
因此原字段是请求值，不能称为初始化后的有效配置回读。原矩阵源代码和产物
不改写：report SHA256
`0c45bad330dc133959e645d834e7142dbf49606c264e4ae0797820b4b917ca95`，
296文件 manifest SHA256
`2bbb7d323dc84e4f3ffff40271ba3cc2dd0c7b2499d7c5f3bb5a7299b469b1d9`。
原实际执行外层耗时8.533989540秒/300秒，原报告内部8.426245588秒不含末尾封存。

唯一修正：两条入口在真实 `ap_pipeline_init()` 后、worker hand-off 前取得
config/tuning 并记录成功标志和阶段；回读错误不能发布有效身份。检查原四个
冻结 tuning 值、完整 tuning mask，且 config/tuning 两份回读一致。负例拒绝
缺失回读标志或 tuning。原 PCM/codec/Runtime 处理和所有判据保持。

原 event_drop 计数也保留：除reopen外每次1，reopen为3；它们不是音频 output_drop。
这些字段是原Runtime诊断，具体发生位置/原因需单独证据，不为抹掉它们修改
生产 Runtime、队列容量、事件阈值或调度。原source结果不足以作为最终“有效配置
已回读”的证据；后继结果必须使用自己实际提交/二进制身份。
