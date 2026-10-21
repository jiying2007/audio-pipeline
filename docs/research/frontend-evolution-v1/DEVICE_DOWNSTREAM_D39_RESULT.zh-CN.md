# D39 下游接续实际结果

2026-10-11，FE_DEVICE_DOWNSTREAM_D39。主矩阵和首次独立全量数值审计已通过；整批最终审查与Runtime终态核验尚未完成，不声明实验完成。总体目标“全面推进优化迭代”保持 active。

## 实际执行及身份

正式矩阵仅一次，主回执 `/tmp/audio-device-d39-execute.json` actual exit0，耗时132.67686616443098秒；根 `/tmp/audio-fe-device-downstream-d39-20261011`。46个冻结D30输入分别处理primary和selected，共92次实际C执行、252972帧。AEC与时域RES调用数均0；各臂NS/AGC/VAD实际调用各126486次。两臂各有独立持续下游状态，不重跑AEC、不改变bank选择、不因切换重置下游。

result SHA256=3bf15108885f0b356e0ebcc1f799a2de6178a12665b71aa13ffa79d1774f93fc；binding SHA256=26a53260fcd4662a90bb1a8649dbb47931b2e1474e534b613de80eea83639663；1628个source/input锁起止相同、679个绑定制品。主工具实际旁路byte exact、输出finite/长度与effective gain逐sample检查通过；repeat两臂全部4输出byte exact，future前1247帧及CSV相应前缀byte exact；上述检查已获独立回读确认。

实际下游sizeof：NS9116B、AGC12B、VAD8B、显式帧缓冲2560B，合计11696B；加D30 scoped71224B为82920B，满足冻结局部预算65536B/合计131072B。原B0 50000B不变，不能声称原B0预算满足；未覆盖FFT临时栈、stdio、整线程RSS/CPU/p99/热功耗或目标板。

## 真实窗口和描述性代价

每臂45个whole+195个固定窗口，两臂合计480测量组，其中390个固定窗口。见[计数勘误](DEVICE_DOWNSTREAM_D39_COUNT_ERRATA.zh-CN.md)，原PLAN错误数字保留。固定160点仅作为NS OLA测量坐标，不是物理/端到端延迟资格；整段末160点不评分、没有追加flush。future不评分；重复现场输入包含于统计，不视为独立样本。

以下是固定原窗口的描述统计，来源 `/tmp/audio-device-d39-observations.json`；比较均在同一输入/输出测量坐标，单位dB。known-near error只用于合成已知near工程差值，没有真人干净标签、独立音质或KWS/ASR裁判。

|固定窗口类别|每臂数量|primary中位变化|selected中位变化|含义|
|---|---:|---:|---:|---|
|合成无near：final误差减bypass误差|72|-22.5777|-22.5777|残余能量下降；各臂72/72变化为负|
|合成有near：final误差减bypass误差|24|+9.3418|+9.3418|近端工程误差增加；primary16/24、selected20/24为正|
|现场：NS输出能量减bypass能量|99|-5.6542|-5.5262|只有能量观察，不能推导语音保真|
|现场：final输出能量减bypass能量|99|-4.7138|-4.6014|各臂48/99增加，最大+15.8773；受控AGC允许分支仍可放大|

含near窗口final与NS变化相同，不能把近端代价归给AGC增益。selected相对primary在24个含near窗口的final工程误差中位差约-1.0151e-10dB、最好-2.4093dB，未抵消下游相对bypass的近端代价。无near72窗中selected相对primary的final误差有14窗增加、最大+0.8947dB。不能以整体抑制量覆盖局部退化。

primary/selected实际VAD active为47672/47934帧；频域RES active两臂均64553帧，包含repeat/future。仅为实际活动数量，不是语音准确率。频域门控来自原Activity，不能从合成near标签反向替换门控或据此调参。

另以原合成near窗口的固定output_range回读control.csv，见 `/tmp/audio-device-d39-near-controls.json`。每臂24个near窗口合计3200帧：far=1有3200帧、dt=1为0帧、frequency_active=1有3200帧；primary/selected VAD active为2496/2510帧。这里的near是合成工程标签，窗口按固定测量坐标，不代表真实现场双讲裁判。观察表明这些窗口的原Activity未置dt、频域RES持续启用；这提供下一轮双讲门控遗漏与频域抑制代价的因果诊断方向，尚未隔离二者因果，不据此修改当前门控或shipping算法。

## 保护、审计和决策边界

正式矩阵中的实际compile/self-test/非法argc/frames/mode/gates回执保留。外部目录负路径 `/tmp/audio-device-d39-negative.json` actual complete=true：D30根、仓根、既有D39根各exit2，完整文件manifest起止一致，分别679/2501/680文件。新输出目录不覆盖旧现场证据。

首链接失败及原D18sync shim修复记录见[实施记录](DEVICE_DOWNSTREAM_D39_IMPLEMENTATION.zh-CN.md)，原失败保留；MINOR-1异常回执修复已独立PASS，实际7个定向测试通过。本轮计数MINOR-2用新增勘误解释，原锁定文件不改。

主结果固定 DOWNSTREAM_INTEGRATION_DIAGNOSTIC_NO_PROMOTION，promotion_allowed=false、shipping_approved=false。即便独立数值审计通过，也只说明这次冻结下游接续与工程测量可追溯；含near误差结果阻止把抑制量当成总体语音效果改善。已安装完整SDK、AISpeech固定点产品链路、真人语音效果、QIVW/KWS及目标板资源资格仍分别待证。Provider当前route unresolved、知识NEEDS_REVIEW，没有持久归档成功回执。未commit/push/PR/merge/release/设备写。

首次独立全量审计实际session11957 terminal exit0，耗时191.72062673792243秒、retry0。脚本 `/tmp/audio-device-d39-independent-audit.py` SHA256=3c2c01d3af88e4663765aef5ef6bd9115773f30ca0dd64b57a430a14991c46e8；回执 `/tmp/audio-device-d39-independent-audit.json` SHA256=ac61aabb9d3d43700cebfa759c02a5566ac1e0a5d4c3324aefa3456a7ed8b60a。

独立核验92执行/252972帧/276个PCM trace，40475520个AGC输出样本逐点binary32 exact，AGC与VAD内部float32递推exact；480测量组、1440阶段RMS/peak、648 known-near统计，最大RMS误差0dB、peak exact。合并2308个来源/输入/制品及result/binding路径起止SHA一致。独立实现不import项目measurement helper、不执行C主矩阵。NS FFT未独立重算：核其身份、长度、finite及分支范围，作为AGC/VAD独立递推输入；不宣称NS FFT有独立数值oracle。

另独立描述审计 `/tmp/audio-device-d39-observation-audit.py` SHA256=0a26a47176375a09d2b1f5d4e2e17ac9267d8f7f88cb8c482f2c94fc447f9def；回执SHA256=9b1b1a0d27b39e890bbb07b0fbced97cb7f691ba5ea38ecebc141730d7087868，实际exit0，26组摘要exact、192个原窗口near标志与near trace相符；near控制重叠摘要也已独立只读核验。数值Spec PASS/Quality PASS、Reviewer Independence=independent、unresolved0，MINOR-2勘误可闭合。

下一步：冻结整批审查快照，独立whole review，中文docs与Runtime终态核验。本文件此时为审查中结果记录，Runtime仅代表本地conformance，不能代替产品或总体目标完成。
