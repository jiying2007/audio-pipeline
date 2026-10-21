# D43 独立计划审查

2026-10-11，experiment=FE_DEVICE_POWER_ATTRIBUTION_D43，claimant=root，verifier=device_capture_independent_review。PLAN与AMENDMENT fresh独立复审：Spec PASS / Quality PASS，Reviewer Independence=independent，QUESTION-1 closed，unresolved=0。该PASS只放行有界测量实施与后续实施审查，不声明源码、编译、矩阵、观测结果或效果已完成。

PLAN SHA256=`67cc799ccfc9d012694c717a1e96b66643d457be90840ecbb70b89b47b0288e1`保持；AMENDMENT SHA256=`cf9f9a8af23cddeee5c1d9f7909c55b2173d4a6355b536c89f4e800f6228a664`。首审NEEDS_CLARIFICATION/QUESTION-1为三个功率sum的过去/当前时间语义及多bin累加/独立误差规则未冻结。新增修订明确active-valid旧E/R/N之和，当前FFT功率另列；ascending-bin普通binary64左折叠及计算括号，独立fsum容差max(1e-24,1e-12*abs(expected))、expected零严格零；整数/集合exact，单bin floor/target/resgain binary32 bit exact，以及D42原五输出byteexact和实际floor_mean binary64exact不放宽。原计划不覆写，未用效果结果选择数值合同。

只读observer捕获在当前guard/noise更新之前，原D42算术和状态顺序保持。原184执行/505944帧全部五输出对D42 exact，固定稀疏选帧不事后挑选；independent按保存快照核内部公式与选帧汇总，不能扩大成全部FFT/EMA/oldnoise历史状态重建。两模式old_gain/applied/resgain/实际raised可不同，其他来源统计相同。既有D42拒绝、future不评分、repeat非新增独立样本、field无near真值保持。

reviewer独立核固定快照计数：2000帧33快照/8481bin行；3003–3024帧44快照/11308bin行。实际文件<=4MiB、root<=1536MiB、启动可用空间>=3GiB及含observer资源预算仍须在实施/执行中真实验证，不因计划可行就声明达到。

注册控制 `/tmp/audio-device-d43-register.py` SHA256=`9b555961a5db40dd2d98cbe49411b935fb07e5e76792fdca5ca89b3b52cdbcb7`与checkpoint SHA256=`4b2de1bc1f70157e8968ab0fef68e700bd871b73e8a608d500cb345b5633fb05`独立静态PASS；固定thread、新namespace、排他intent/receipt、异常null/partial保存和未知对账不重发正确。request SHA256=`16bab6bb7944f0d2b2e3159d5c47ad02449096bf92d7baddeeea3781bccfa400`；本地64M/86400记账配置与总体native无token上限分开。脚本仍待root实际顺序执行，未提前声明Runtime登记完成。

只接受POWER_ATTRIBUTION_DIAGNOSTIC_NO_PROMOTION；测量失败保留MEASUREMENT_INVALID_REPLAN，以新身份修复。计划审查不批准D42或新的声学/产品候选，AISpeech固定点/QIVW、真人/外部独立数据、目标板/HIL、owner/rights/shipping分别待证。Provider route unresolved/知识NEEDS_REVIEW，未声明归档成功。无commit/push/PR/merge/release/设备写；总体native目标继续active。
