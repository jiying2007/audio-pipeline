# D42 独立最终审查

2026-10-11，experiment=FE_DEVICE_NOISE_CONDITIONED_PROTECTION_D42，claimant=root，verifier=device_capture_independent_review。fresh whole-change Spec PASS / Quality PASS，Reviewer Independence=independent，unresolved=0。结论覆盖实施、真实执行、独立工程测量与拒绝披露；Candidate=NOISE_CONDITIONED_PROTECTION_DEVELOPMENT_REJECTED，promotion_allowed=false，shipping_approved=false。Runtime最终收口另核，总体native目标“全面推进优化迭代”保持active。

## 冻结契约与实施审查

唯一新算法变化为D41过去帧创新比例扣除原NS上一帧噪声估计N/R，再形成gain下限。旧EMA/count与原NS噪声更新顺序不变；first-party新符号fork，不替换D18原库。原AEC/Activity、ordinary NS、AGC/VAD及frequency_res enable1保持，没有near标签输入、反馈AEC或阈值搜索。N不是背景真值，公式共同缩放测试不扩大成完整NS尺度不变性。

冻结准入保持每candidatearm24near/72no-near fixed及四个明确纯echo whole；near中位<=-3 dB且至少18/24改善，无near和纯echo各例<=1 dB，未放宽。PLAN/PLAN_REVIEW和IMPLEMENTATION/HANDOFF是各自冻结的历史阶段，不覆写其绑定或旧D41 README snapshot。

首次完整执行包审查发现MAJOR1：旧wrapper文本替换污染NS哈希pin。旧writer SHA256=`89a796e769c006a2be1973e624cdfe7f79e5344340962dc86020c17c3920d190`保留，未执行、未产生intent。新v2只修正该pin和操作namespace，源码与门槛不变；fresh独立复审MAJOR1 closed/unresolved0。唯一实际writer SHA256=`7c3ecfe186d3a3c5d888409fbca78f4d7d7d925c5b2bccc8471745b20f121c2e`，七个源码/计划pins当前相同。

## 实际矩阵与独立复算

正式session62543真实terminalexit0，301.3867018017918s，184执行/505944帧。result SHA256=`a2b839fbc635d1f1664d4c98d0406186e481b52aaef0a2a4fd4f4285902f31e2`，binding SHA256=`291d91f48162fa5fcab3f7deff25ec8c9baff77cbe7e39cd78004108f52883f0`。fresh whole审查重新核4520个locked_files和1510个主artifacts当前全部匹配。真实compile/self-test通过；非法argc/frames/mode各exit2、非法gates exit4，sentinel保持。14项unit及strict C known-answer此前真实通过，收口不无意义复跑。

独立audit script SHA256=`b6c9e255188d06ca5fafada572d0fd350ea645a44c37eb3d97934423b34e05b7`，唯一首次session99347 terminalexit0/PASS，retry0，507.73973527830094s。receipt SHA256=`65f1df1812e9817bb5cd5ac8303cf5b044af8487bfde6edc6388a7762e885b4c`，intent SHA256=`78893dfeaf398457e12375e20e3a9b5e628aa13437c44e4110c07d8ef956bebe`。不import测量helper、不执行DSP；184执行/505944帧/552PCM/80951040个AGC输出sample，AGC/VAD binary32exact。960组/2880stage/1296known-near/960个D39差值独立复算，RMS最大误差0 dB、peak exact，6033个合并文件锁起止相等。

92个monitor四原输出复现D39/D41，64个inactive整例控制相同，505944帧ordinary NS统计exact；逐帧D41 count/valid exact、floor_mean单调、92个observer配对除raised_bins外exact；五输出repeat/future前缀与四future null通过。NS FFT、全部实际bin EMA及旧noise逐bin状态未独立全量重算，三覆盖字段false。known-answer、等价与汇总trace不扩大为该覆盖或声学/产品资格。

独立描述审计真实exit0，0.9662440270185471s，80组summary exact、384个near标签按原轨迹核验，receipt SHA256=`ef1b517b79a9814f8a56a26a42cee66f0ea2cb52abaae3fdbe95c54d37e6820d`。root负例session64120 terminalexit0，D30/仓库/D42三个命令各exit2，完整manifest679/2545/1511起止相等，receipt SHA256=`6d5b2fc4f3ce5ef320da559f79c87bb455b986eabbef366bf3cdb0c459a3e0e1`。reviewer回读这些真实回执并核脚本身份，未冒认重跑。历史全仓manifest不能代替后续新文档的当前树身份。

## 决策、文档与本地收口

独立按实际near轨迹复算每arm24/72/4集合和准入，与主结果完全一致。两臂near配对误差中位约-2.18247 dB、20/24改善，但中位不达-3 dB；无near最大+3.70940 dB超过1 dB。纯echo whole最大+.38711/+.54046 dB满足门槛，不能覆盖其他失败。额外独立只读核primary22/72、selected24/72超限，无near中位+.451929389/+.578744592 dB及最坏A-r20-dt/unguarded-shadow [200000,224000)；RESULT披露与实际相同。

near final对bypass误差中位仍约+7.15601 dB，现场99窗final-D39中位约+.45334 dB、51/99增加；现场没有near真值，未写成真人语音收益。两臂拒绝保留，后续先补可辨识性与恢复阶段证据，不扫描相近门槛取得批准。

本次独立核RESULT SHA256=`3cc4cec3f4e0847198b1373472813305213053730cdc616365598b7b02a7cf2a`、README SHA256=`e294333b02a671f5253ffb7313416e8cb66fa4218a1085475d4dbbcfc440576b`。既有用户dirty与D0–D41结果保持。

finalchecks.py SHA256=`f589b587dbfc45c8899153c3862b31fd0743e44e84317868832f2b51cf4ec3d1`、freeze.py SHA256=`c3445687c72269110614c54a1a5d873a0783423abf622bb0d0f26315b1b6007d`、closeout.py SHA256=`d124d54ba5773bb703888e937f1bd2e1f5b74224bcc45b57c952b9f221b05e58`经独立控制审查，当前SHA未变。排他intent、异常真实回执、未知对账不重发、固定task-5818c005663a903e8ab8d8ec与revision2前提保持。

接续顺序：本REVIEW读回→实际docs/diff checks→唯一freeze→独立当前全部锁读回→唯一14项localcloseout→独立终态对账。后续真实终态另写CLOSEOUT，不改snapshot内文件。只完成D42本地里程碑，不调用总体native goal完成；Runtime conformance不替代产品验收。

下游scoped22000 B+D30原71224 B=93224 B满足本实验预算，B0 50000 B仍未满足，不是整SDK/目标板资源资格。Provider route unresolved/知识NEEDS_REVIEW，未声明归档成功。AISpeech固定点/QIVW、真人识别、目标CPU/RAM/功耗/HIL、owner/rights/shipping分别待证。无commit/push/PR/merge/release/设备写。
