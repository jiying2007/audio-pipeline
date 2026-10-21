# D45 合成增益后保护实施冻结

2026-10-11，experiment=FE_DEVICE_POST_NS_PROTECTION_D45。状态为 IMPLEMENTED_TARGETED_VERIFIED，正式矩阵尚未执行。本文冻结当前实现及实际定向证据；不声明声学准入、产品批准或发布。原 PLAN 与 PLAN_REVIEW 字节保持。

唯一算法变化已实现：同一 D44 floor 不再抬 RES target，而在原 ordinary NS × 原平滑 RES 增益及既有 SAFE 分支之后应用 max。原 RES 状态、噪声 tracker、EMA、FFT、OLA、AGC/VAD 算法保持。新 observer 在 D43 bin 外增加三个 float，不进入算法历史；power 18 列、bins 25 列保留旧前缀。

## 冻结源码

| 仓内路径 | SHA256 |
|---|---|
| tests/validation/frontend_evolution/device_post_ns_protection_d45.h | 82458adbab6fb83708ab89f3cd24b99ccde02f83df1680933b455f74594d570d |
| tests/validation/frontend_evolution/device_post_ns_d45.c | ba6c427a2ea01d0a540bc21a14e6ce6a7c172ed278120b9ae1359ae27ff07724 |
| tests/validation/frontend_evolution/device_post_ns_protection_d45.c | 101ba4441794d8845b82904a8c524db4ea88fea746f29b9d0cb08b967baa048a |
| tests/validation/frontend_evolution/test_device_post_ns_protection.py | 3f6ca5da374fec4afafbc77dd7f44198bf7d79b1241e20bd12bbc08b038bbca0 |
| tools/codex_assets/device_post_ns_protection.py | 84ae3a41685e46a71769017e17b0ab277c1ef68e3c28e9bd722c5f9872831c17 |

PLAN=15e94e9f589aa6ceb9933f8193cbbf4b10bbfc34d57bf05c794c6213fd2c24ce；PLAN_REVIEW=4694589c1c59b9d6bc4da81621648c6a108a873d3ab6b0fbce2ba0053fb66558。原 D42 observe/development_admission 不改；原 D44 helper/hash/binding/CLOSEOUT 作为冻结来源锁，未重跑或修改历史实验。

## 实际定向验证

严格 C11/O2/Wall/Wextra/Werror/Wconversion/Wshadow/pedantic、ffp-contract=off，使用 D18 exact archive、原 build defines/includes；真实 compile exit0（chunk463c42）。定向 runner=/tmp/audio-device-d45-targeted-runner-v1，SHA256=780ffd2db218b98253f43477cb4d48a8ba0d6f17865f12a59016c536ff96667d。

首次 self-test exit0（chunkb0c4bc），包含原严格 2N 等 known answers、40 帧 observer/NULL 状态与输出 exact、新 max 的小于/等于/大于/floor0/monitor/inactive，以及受控弱 NS×RES 下 candidate 抬最终增益而原 RES/noise/result 保持 monitor exact。

排他定向控制 /tmp/audio-device-d45-targeted-v1.py 实际 session59938 terminal exit0，14 操作、1.8906677616760135秒；receipt=/tmp/audio-device-d45-targeted-v1.json，SHA256=8324198907634ab47e086d023ca4b06e05954db89e8434988f05dc8cf02f4f26。9 项 D45 单测及 54 项继承单测全部通过（D44 5、D43 12、D42 14、D41 14、D40 9）。非法 argc/frames/mode exit2，长度/NaN/Infinity/gates exit4，七输出 sentinel 及输入 manifest 保持；source/runner 起止 hash 相同。该控制仅定向 known answers 和负例，formal_dsp_executions=0。

非仓 cwd /tmp 的 help 真实 exit0（chunk5f1fc9）。非仓 deep dry-run 实际 session89322 terminal exit0（chunk00c395）：46 cases、9829 locked_files、writes=false、dsp_executed=false。此 dry-run 只核冻结来源，不是正式测量或独立声学评分。

## 独立实施审查

device_capture_independent_review fresh 回读五源及计划：Spec PASS、Quality PASS、Reviewer Independence PASS、unresolved0。独立 /tmp 单测实际 9 tests/0.033秒/exit0（chunk187c9f）。首次漏 PYTHONPATH 的独立调用 exit1/ModuleNotFoundError tools（chunk2b990a），仅补测试环境重试，未改源。独立代理未执行 C DSP；主编译/self-test不冒称独立执行。

审查确认唯一映射、无 RES/noise 状态反馈、observer NULL、旧列及新计数语义、原 NS/RES control 投影、原评分入口、来源锁、根与父 symlink 拒绝和预算。正式唯一 writer 控制仍须独立审查。

## 执行前条件与范围

2026-10-11 fresh main 仍 ef1fb54cdd326c280c30889646a3592c17c10d50，其 check-runs 此次已含 required summary success、frontend-spatial success；所有返回 check completed，仅 fast-docs 预期 skipped。PR717/714/708/695 heads 与 PLAN 同；#657 OPEN/updated2026-10-11T13:56:54Z，其 body 的 main70aeb4为历史。最近 artifacts11706755896/11706750311/11706720893均未过期并绑定PR714头，不作 D45 证据。

D45 native 请求1791732510507实际已受理，compact receipt 状态 ACCEPTED_COMPLETION_UNVERIFIED/120.39899717830122秒，保留旧回执。恢复 fresh snapshot2026-10-11T15:32:37.289497Z required=false/recommended continue，允许业务继续，不将自动压缩因果归入该请求、不重复发送。

正式 root=/tmp/audio-fe-device-post-ns-protection-d45-20261011，当前不存在。待冻结控制审查和 CP2 verified 后才唯一正式执行。仍184次/505944帧，候选输出按原入口真实重算全部960组；monitor四输出与D44monitor exact、candidate bypass exact、两模式原状态 exact、repeat/future、资源/数字和独立全量审计均待实际执行。原准入不改，promotion_allowed=false、shipping_approved=false。

Provider 知识 NEEDS_REVIEW，未声明归档成功。无 commit/push/PR/merge/release/设备写；总体目标保持 active。
