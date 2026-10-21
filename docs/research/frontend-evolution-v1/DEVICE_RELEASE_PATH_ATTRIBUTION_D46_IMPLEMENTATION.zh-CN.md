# D46 时序归因工具实施与定向验证

2026-10-12，experiment=FE_DEVICE_RELEASE_PATH_ATTRIBUTION_D46。新task-f972a6cb6470af7431f4e9e1实际active/open3，CP1verified、progress1、events728。批准PLAN/PLAN_REVIEW与HANDOFF保持原字节。工具及测试已经实施，独立实施Spec/Quality/Reviewer Independence PASS、unresolved0；正式writer控制审查、CP2及唯一formal/独立全量复算尚待，不提前声明结果。

| 新源码 | SHA256 |
| --- | --- |
| tools/codex_assets/device_release_path_attribution.py | `fe23488cef390b597e0a9c97aec9e455059503897f529d036835e03bf06c3aec` |
| tests/validation/frontend_evolution/test_device_release_path_attribution.py | `ff5a31e93736a55ed25927eb88a7635feeec8a49ca06e6d6269a553b14c4ca0a` |

## 实际实现和覆盖

纯标准库直接读取D45冻结NS/final PCM与power，不import旧测量helper，不执行DSP。固定24对/7阶段、160点对齐与尾160点截断，168 pair-segment/336 stage另48 stage-whole直接统计。float32le显式解码，float64顺序左折叠能量、差异及peak，strict zero与null诊断dB保持；分段能量与whole按原冻结容差核验，peak exact。分段统计不替代D45原准入或声学结论。

96 PCM+48 power输入按D45 artifact SHA绑定；D45 snapshot原47文件、来源及计划/工具/测试一并起止核，共199项锁。读取器核18列/2000顺序frame、合法数值、原count递推/warmup/inactive/空有效集零、mode仅actual raised差异、candidate actual=post_would/monitor0。power与波形坐标分别保存，不宣称逐帧因果一一对应。

固定新/tmp根、既有/外部/own-parent symlink在preflight前拒绝；创建后排他intent/result/binding，任何测量错误保存measurement-invalid及partial，不重放。启动free>=512 MiB、输入/输出单文件<=4 MiB、root<=16 MiB、formal180 s内部deadline保持。宿主限制不证明目标板资源。

## 定向验证与发现闭合

主首次11unit真实exit0（chunk3a037d）；非仓cwd help实际0（e947aa）、dry-run实际0（dcf63c），writes=false/dsp0/24对144消费文件199锁。独立发现MINOR-1：finite但非法q/floor/能量及计数记录被读取器接受，临时反例actualexit0（f8e3cf）。输入SHA降低真实误消费风险但不替代合法性验证；正式root尚未创建，无formal失败副作用。

已最小补齐原D45合法性：q/floor[0,1]、全部汇总非负、innovation/excess原1e-12界限、counts<=valid、past count递推、warmup/inactive有效集和empty strict0；保留inactive旧count非零的合法生命周期。统计、坐标、预算及准入未改，旧D45源和冻结文档未动。

主修正后12unit实际exit0、.040 s（93cc96），新增十类finite-invalid及empty非零1e-30反例；dry-run实际0（410e76）仍199锁且无写。独立12unit实际0、.035 s（513b4d）；原组合反例现ValueError拒绝，另真实11帧fixture末inactive count_before10/emptyzero被合法接受（2cc7e8 actual0），MINOR-1 closed。

主对真实48份power和24配对mode投影作只读定向核验，session31841 terminal0（e6c189），输出D46_ACTUAL_POWER_VALID 24 96000 NO_DSP_NO_FORMAL。这不是新的波形评分或正式D46。docs consistency实际0（f825f5），git diff --check实际0。验证为真实工具输出和review回读，不冒称所有主检查具有额外独立subprocess回执。

## 下一步与边界

源码现可供正式writer独立审查；CP2须绑定本IMPLEMENTATION后再唯一formal。正式root=/tmp/audio-fe-device-release-path-attribution-d46-20261012，独立复算须不import新helper、覆盖全部24对/168段/336stage及whole、严格输入/坐标/零/容差/起止锁。任何未知回执先对账，不重新执行。实施静态PASS不代表formal测量或审计终态。

D45 DEVELOPMENT_REJECTED及原全部门槛保留，D46 measurement-only/algorithm_changed=false/promotion_allowed=false/shipping_approved=false。结果只可为时序归因，不能批准近端识别、算法候选、真人/目标板/HIL/PQ或产品。Provider route unresolved/NEEDS_REVIEW，无归档成功；无commit/push/PR/merge/release/设备写，总体native目标active。
