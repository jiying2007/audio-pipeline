# D42 实施和执行准备

2026-10-11，experiment=FE_DEVICE_NOISE_CONDITIONED_PROTECTION_D42。计划独立Spec PASS / Quality PASS、unresolved0后实施。本记录仅报告已完成源码及预验证，正式184矩阵和候选效果尚未执行；总体native优化目标active。

唯一算法变化：D41过去EMA coherence保护floor改为sqrt(max(0,1-q-N/R))，N取原noise_tracker.estimate[k]的旧binary32值并转double，在当前bin原noise_tracker_update之前读取。N finite非负、q/count/energy valid保持，非法值拒绝；原噪声更新、NS/AGC/VAD、AEC/Activity和gain attack/release不变。不新增估计器或标签，不回读当前噪声，不反馈AEC。

新增first-party源分别派生D41，原D41及D18库不改：

| 新文件 | SHA256 |
| --- | --- |
| device_noise_conditioned_protection_d42.h | 33efa7a43ff6945faa7ad8858ee7852da97cdd84c8176f2d7a4886a4056fda41 |
| device_noise_conditioned_ns_d42.c | 09aaa1d9f4a6e5e9d865355f88b480b546568279d56a1fec090313cefe8bf35d |
| device_noise_conditioned_protection_d42.c | f72a38f29d3a92821d0f7bbb73e4d8812c863dd28e458ed92ba2f067da0ac07c |
| device_noise_conditioned_protection.py | a6c5b230836bd2e9cd2a14562b7eeffed4abb3c849318a0540364f325239001e |
| test_device_noise_conditioned_protection.py | 04383cb675dd42cf8c9367d66ca439299c464c5b4cd7763ee74d00ab5f2c5adc |

工具继承D30/D39/D40/D18完整锁，新增D41完整locked_files/artifacts、result/binding和finalsnapshot身份；旧D41拒绝/data role必须保持。四输出monitor与D39/D41 byteexact及ordinary NS统计要求保留，protection逐帧count/valid与D41相同且floor_mean<=D41，两个mode observer除raised_bins exact。仍为每candidatearm24/72/四枚举whole原准入、184执行/505944帧/960测量组；非法测量固定MEASUREMENT_INVALID_REPLAN，不宽门槛。

实际预验证：14项Python contract/admission tests真实exit0（0.012s）；非仓cwdhelp exit0；deepdry唯一session51744 terminalexit0，46cases/4520locks/writesFalse。strict C编译与实际self-test wrapper `/tmp/audio-device-d42-build-v1.py` terminalexit0，两回执 `/tmp/command-d42-preflight-v1-{build,self-test}.json`及对应intent保留，原D18 FLAGS/defs/includes/lib、ffp-contractoff不变。

C实际known-answer除原AGC/complexcross/warmup/inactive外，新增N=0回退、正交R1/N.75 floor.5、N>=innovation归零、公式输入共同缩放4/4/3 floor.5、负N/NaN/Inf拒绝。N/R单位相容不等于统计量或真实背景噪声相同；缩放测试不扩大为包含NS正则及启动分支的整链性质。全部实际bin EMA/NSFFT/旧noise状态未独立全量重算。

正式根 `/tmp/audio-fe-device-noise-conditioned-protection-d42-20261011`；修复后的唯一wrapper `/tmp/audio-device-d42-execute-v2.py`在写intent前核七个计划/源码pin及fresh policy固定task active、maintenancefalse，排他root/intent/receipt，单主预算1800s，超时保留真实partial/null exit不重放。

首次完整实施审查：算法源码和测量工具Spec PASS / Quality PASS；执行包因MAJOR1（wrapper NS pin仍是旧值，命名替换还改变hash中的d41片段）FAIL/unresolved1。旧wrapper原字节/SHA89a796e769c006a2be1973e624cdfe7f79e5344340962dc86020c17c3920d190保留，未执行或产生intent/矩阵；新v2身份仅修正NS pin为本轮实际09aaa1d9...及新v2intent/receipt路径，不修改DSP或门槛。七项pin及新writer待fresh控制复审，不能提前声明闭合或正式执行。独立reviewer在/tmp复跑14项Python测试真实exit0/0.014s，回读原C编译/自测真实回执，未冒称重跑DSP。

上述首次审查之后，独立fresh复审已完成：Spec PASS / Quality PASS，Reviewer Independence=independent，MAJOR1 closed、unresolved0。v2 writer SHA256=7c3ecfe186d3a3c5d888409fbca78f4d7d7d925c5b2bccc8471745b20f121c2e，七项pin全部当前匹配；旧writer未改，mainroot/v2intent/v2receipt均不存在。该PASS仅证明执行准备与实施审查完成，仍须fresh maintenancefalse才能唯一运行正式矩阵。

本地Runtime已实际注册task-5818c005663a903e8ab8d8ec，open3/implementation；request SHA256=1c4ce3362daf45e3e82c2510685c2814d3593006b6bc04dd43e86b0bb0f30df9，routing5818c005663a903e8ab8d8ec1fc0f9cfce81856304879c70a3268c1a996fcd06，attestationcca01eb713cddbcf85c0ba0e46d3d941b87ae89cb17296a09ca1d2e371d38124。fresh policy09:17:35.935898Z维护requiredtrue，正式矩阵前先接力/维护并即时复核；不把宿主维护当业务效果证据。

Provider route unresolved/知识NEEDS_REVIEW，未声明归档成功。promotion_allowed=false、shipping_approved=false；AISpeech固定点/QIVW、真人效果、完整SDK/目标CPU/RAM/功耗/HIL和owner/rights/shipping分别待证。既有用户dirty、原D0–D41失败保留；无commit/push/PR/merge/release/设备写。
