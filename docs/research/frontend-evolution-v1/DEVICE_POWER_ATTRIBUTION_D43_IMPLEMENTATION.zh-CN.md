# D43 功率归因测量实施进度

2026-10-11，experiment=FE_DEVICE_POWER_ATTRIBUTION_D43。本文件记录实施阶段的真实进展，不是正式矩阵结果、整体审查 PASS 或产品资格。PLAN、AMENDMENT、PLAN_REVIEW 和原 HANDOFF 保持冻结；总体目标继续 active。

## 已实施的测量链路

新增 C 执行器、只读 NS observer、Python 读取/执行工具及异常输入测试。原 D42 guard/header 和原 NS 算术顺序保持。observer 捕获更新前的旧 E/R/Cr/Ci、原旧噪声估计 N，另记录当前 FFT 和原 target/gain；新增 power.csv 逐帧汇总以及固定稀疏帧 bins.csv 全257bin快照。未来正式执行必须证明五个原输出逐字节等于冻结 D42；自测不能替代该矩阵证据。

当前源文件 SHA256：

| 文件 | SHA256 |
| --- | --- |
| device_power_attribution_d43.c | 154fed956a90aebb2bed0da3ab44021eab2e433cfc2cfa36509e6ee4d858b90a |
| device_power_attribution_d43.h | 6314f819a5ad050794688d7c82f4f8b789a6ce5198c06ff4e18864d3524e6fd1 |
| device_power_ns_d43.c | ef8c287b005aa1c1f672425ee825a27628394b2b8048b1334dced29cc5c463d0 |
| device_power_attribution.py | d96dd725784415c1389b98590f896de82abcaf7de5c3b271433a9c7d2baaa5df |
| test_device_power_attribution.py | c55aaf160717726ea419e24fb41c5ecdca5a18384d95b9f5a2fc70676e2f5ae0 |

Python 正式执行逻辑已写入，尚未执行：46来源×两臂×两模式184次/505944帧，原五输出和960组旧 observation 保持 D42 exact；七文件重复/future前缀、双模式统计、源工件起止锁和资源/磁盘预算均设置拒绝条件。异常 argc/frames/mode/gates 在正式矩阵中验证七文件哨兵；独立审计不使用该 helper 批准自己。

## 已执行的定向验证

- 严格 C v2 编译 exit0，实际墙时0.561047331430018秒；原 D18 unity archive/defines/include、C11/O2/严格 warnings/ffp-contract=off。回执 `/tmp/command-d43-preflight-v2-build.json` SHA256=c44b900ac05fcdfebca643d124d94388987ecd6f5a256fc4bc78c917b18098e7。
- v2真实自测 exit0，墙时0.07684218417853117秒，回执 `/tmp/command-d43-preflight-v2-self-test.json` SHA256=25de43a31fa00c102b259c1fc8dff4f0edc25adc4769dfdafdbb8202e8f24917。保留原 D42 known answers；新增浮点宿主前提、33/44固定选帧，以及40帧 observed/NULL 的 NS/guard/result/输出 byteexact、更新前噪声/旧E、warmup/inactive 检查。
- 12项 Python unit 实际 exit0。覆盖非有限/负N、重复/缺失/多余bin、非法schema/行宽、gate/count、monitor抬升、inactive gain、空汇总、双模式过去状态篡改、既有root与单工件预算拒绝，另含active→inactive的旧计数边界。
- 非仓 cwd=/tmp help exit0；deepdry session44160 terminal exit0，46cases/6040locks，writes=false/dsp_executed=false，但它发生在下述计数修复之前。早期 session90202 6039locks只对应增加历史snapshot锁之前的工具字节。当前修复字节的定向回执脚本 `/tmp/audio-device-d43-targeted-v1.py` session30362已实际terminal exit0，unit/help/dry/docs/diff五命令全部exit0。当前deepdry实际46cases/6040locks、writes=false/dsp_executed=false，墙时43.63389462418854秒；五份 `/tmp/command-d43-targeted-v1-{unit,help,dry,docs,diff}.json` 和对应intent均保留。
- git diff --check 实际 exit0；本文件初版文档一致性 session83934 terminal0/PASS，后续文档更新需复核。

独立部分审查发现MAJOR-1：原读取器在inactive帧要求count_before=0，但冻结NS保留reset之前的旧计数，只有count_after清0。这会在active→inactive时误拒绝合法数据。已最小修复为无条件验证count_before==previous_count、再按当前active更新/清零；新增12帧边界测试验证旧count10合法而伪造0拒绝，实际12unit PASS。未改NS或D42guard。

fresh独立部分复审已完成：Spec PASS、Quality PASS、Reviewer Independence=independent、unresolved0。reviewer从/tmp独立执行当前12tests实际exit0，并逐行核封存D42全部505944帧的count生命周期，其中564个inactive首帧保留非零count_before，与修复一致。起止五源身份已核；C/observer及当前读取/矩阵逻辑未发现新增可验证缺陷。该结论只覆盖当前部分实现文件，不放行正式matrix，不替代整轮audit/writer/negative及文档审查；未重跑DSP或独立重建全FFT/EMA/noise历史。

严格自测的观察范围仅40帧；未独立全量重建FFT/EMA/noise历史。正式矩阵独立审计仅对冻结选帧验证全bin公式，不得将其升级为全部帧历史重建。原 D42 拒绝、近端合成角色、field无真值及无产品放行保持。

## 当前恢复状态与剩余工作

恢复时实际核得 D43 native intent/accepted/compact 三回执存在，request_ms=1791713247271，终态仍是 ACCEPTED_COMPLETION_UNVERIFIED，观察墙时120.41944728512317秒。原请求已受理，不重发、不改成 completion_verified；fresh Runtime snapshot maintenance.required=false/recommended_action=continue，故继续业务实施。心跳首次写受沙箱只读文件系统拒绝，随后经正式升级执行成功；不把失败或心跳当作DSP进展。

fresh main=d3f89e54beed483fcc0f8ce59e74b28533ed19b5；API现有79条check_runs，required summary completed/success。openPR721/717/714/708/695，#657 OPEN/updated2026-10-10T11:33:28Z；最新制品11698628825来自该main、未过期。这些远端证据不验证本地 D43。Provider validation query零命中且route unresolved，知识NEEDS_REVIEW，未声明归档成功。

正式 `/tmp/audio-fe-device-power-attribution-d43-20261011` root 当前不存在；没有正式执行 intent/receipt、RESULT/整体REVIEW/CLOSEOUT。当前部分源独立审查完成；该审查不能批准完整阶段。

下一步按原计划：闭合当前源审查；补齐独立诊断数值审计、三个既有root完整manifest负例和唯一正式writer；冻结实施/控制身份并完成独立实施审查；fresh Runtime允许后执行一次正式矩阵，观察同handle不盲重放；独立核所有五输出、固定快照数值和全部固定窗口描述；真实RESULT/REVIEW/freeze及本地Runtime收口。推进检查点应从当前实际revision读回，不能沿用原HANDOFF预期的最终revision3。

无commit/push/PR/merge/release/设备写；AISpeech固定点产品链路、真人语音效果、目标板和E001/HIL/shipping分别待证。
