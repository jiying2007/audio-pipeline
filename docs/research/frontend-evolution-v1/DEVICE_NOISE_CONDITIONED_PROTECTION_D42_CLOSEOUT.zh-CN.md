# D42 本地里程碑收口

2026-10-11，experiment=FE_DEVICE_NOISE_CONDITIONED_PROTECTION_D42。本轮主测量、首次独立全量审计、fresh whole-change审查、最终文档检查及本地Runtime操作均真实完成。候选 NOISE_CONDITIONED_PROTECTION_DEVELOPMENT_REJECTED 保持；测量与本地conformance通过不代表算法准入、产品资格或总体目标完成。

## 执行和拒绝证据

唯一正式矩阵session62543 terminalexit0，184执行/505944帧，301.3867018017918s；result/binding SHA256分别为 `a2b839fbc635d1f1664d4c98d0406186e481b52aaef0a2a4fd4f4285902f31e2` / `291d91f48162fa5fcab3f7deff25ec8c9baff77cbe7e39cd78004108f52883f0`。旧错误writer未执行，v2仅修正pin/操作身份，原字节保留。

独立全量session99347 terminalexit0/PASS，507.73973527830094s，retry0；receipt SHA256=`65f1df1812e9817bb5cd5ac8303cf5b044af8487bfde6edc6388a7762e885b4c`。184执行/505944帧/552PCM/80951040个AGC输出sample、960测量组/2880stage/1296known-near、6033合并文件锁起止相等；AGC/VAD binary32 exact、RMS最大误差0 dB。NS FFT、全部bin EMA及旧noise内部状态未独立全量重算，覆盖边界保持。

两candidatearm near配对误差中位约-2.18247 dB、各20/24改善，未达-3 dB；无near固定窗最大+3.70940 dB，primary22/72、selected24/72超过冻结1 dB。纯echo整例最大+.38711/+.54046 dB满足限制，不能覆盖其他失败。独立准入精确复现拒绝；门槛和失败未改判，promotion_allowed=false、shipping_approved=false。

## 实际最终检查和文件冻结

REVIEW SHA256=`b8ea54355c319f62741c2dd574ec09779c7cb538267b88ef3d4efeb077183c34`，记录独立whole-change Spec PASS / Quality PASS、independent、unresolved0。RESULT SHA256=`3cc4cec3f4e0847198b1373472813305213053730cdc616365598b7b02a7cf2a`；README SHA256=`e294333b02a671f5253ffb7313416e8cb66fa4218a1085475d4dbbcfc440576b`。

finalchecks session35342 terminalexit0，docs consistency PASS、git diff --check exit0；双intent/receipt均绑定当前REVIEW。唯一freeze实际exit0，`/tmp/audio-device-d42-review-snapshot.json`包含40文件，SHA256=`3faf06d95b908ea2debe20fb3048cfe06c8d4bf991a7c855dece1e50a144a892`。独立reviewer核40文件起止hash全部相同。

本CLOSEOUT在冻结快照之后新增，独立接受追加文档审查；不覆写快照或其中任何文件。原IMPLEMENTATION/HANDOFF、D0–D41结果及旧README身份继续作为各自历史证据。

## Runtime终态与维护事实

冻结回读时fresh steady09:47:48.410699Z因heartbeat-stale 933.091s报告fail/replan；不是测量失败或最终PASS。依据已真实完成的主运行与独立审计，root实际执行一次必要heartbeat；fresh09:48:34.203875Z恢复active/reasons[]，独立09:48:51.865704Z读回恢复正常后放行唯一localcloseout。未重做测量、审计、finalchecks或freeze，也未把heartbeat当测量进展。

已审writer `/tmp/audio-device-d42-closeout.py` SHA256=`d124d54ba5773bb703888e937f1bd2e1f5b74224bcc45b57c952b9f221b05e58`，唯一session67814真实terminalexit0。14项操作0..13全部exit0；每项intent/receipt保存writer、snapshot、review和实际命令身份。操作仅登记本轮证据/制品、progress3、checkpoint3 verified、heartbeat、local open0、local complete、final gate及status读回。

local task=`task-5818c005663a903e8ab8d8ec` completed/open_items0，progress3/checkpoint3 verified。final gate09:49:08.981193Z为pass、reasons[]、missing_evidence[]、completion_allowed=true；第12项final receipt SHA256=`b08a31709ac5ed1a5acff083b57ff828cb8abeaa99111fd6daeeb04f10f1f319`，第13项status receipt SHA256=`a6ac562917409b53768d8064a7751ab811c3beaebb83a3c717448b62d9591805`。这仅证明D42本地Runtime conformance。

宿主自动压缩后fresh维护requiredfalse，直接执行已审矩阵；D42新native compact请求未发送，三request路径均不存在。旧D41请求的只读受理后观察和原回执保持，不能把自动压缩因果归为未发送的新请求。

总体native目标“全面推进优化迭代”实际仍active，remainingTokens=null；未调用总体完成。D42本地16M记账配置不是总体目标token上限。

## 下一步和独立待证边界

本轮证据支持先核原噪声估计与创新量的可辨识性、near结束后的保护恢复过程，再冻结新的单因果研究；不要继续用整例平均掩盖固定窗超限或扫描相近阈值。本轮算法不直接替换AISpeech固定点/QIVW产品链路。

下游scoped22000 B+D30原71224 B=93224 B满足本实验预算，B0 50000 B仍未满足，不是整SDK/目标板资源验收。真人混合/音质/识别、AISpeech集成、目标CPU/RAM/功耗/热/HIL、rights/owner/shipping分别待证。Provider route unresolved、知识NEEDS_REVIEW，未声明归档成功。无commit/push/PR/merge/release/设备写。
