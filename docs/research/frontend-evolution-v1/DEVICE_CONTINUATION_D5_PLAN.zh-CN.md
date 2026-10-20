# 设备优化接续：D5测量与本地验证闭环

日期：2026-10-10；状态：PHASE_A_B_LOCAL_PASS / PHASE_C_REVIEW_PENDING。
授权：提高预算继续推进；primary=adk-planning-execution-loop。
执行结果见DEVICE_CONTINUATION_D5_RESULT.zh-CN.md；冻结假设/阈值/预算保持原义。
目标：闭合本地工具环境/共享门禁接入，给D4失败补充相关峰证据，保留已拒绝候选。
基线：本地572b0e34a8a8e5663397ce16e378209ba9058d4d + D3source lock；
当前main=39a445d4c21d2f716e6602450a0bf944f248383b，Verify38016025462/Release38017881646成功。
权限：仅本地实施/验证；无SCM写、设备操作、全局工具替换或正式Provider归档。
数据：119文件锁、16轮已查看development；产品DSP/default/API/ABI、E001和历史结论不改。

## Phase A：验证环境和main接入
kind=implementation；scope=既有门禁、A2主线精确第一方文件、接续说明。
保留全部Git fixture断言；Docker离线read-only源挂载验证Git2.47；
临时Git2.43.0来自git/git exact commit564d0252ca632e0264ed670534a51d18a689ef5d，
archive sha256=bec2cd891f2bf0cc992578209cf2d3c966ef4b1917d86291cb8e641ae9917f07；
GPLv2，仅/tmp编译git目标，不make install、不复制入产品、不启用HTTP/SSL。
CVE/发布签名未独立审计，限定离线可信第一方临时fixture，不作生产工具资格。
选择现有Python3.10及临时GitPATH复跑完整docs gate；旧Git失败继续保留。
exit_gate=原有断言通过+整套门禁成功；不能通过改变要求洗绿。
A2只复制当前main精确文件，来源Git blob逐文件核对，不替换用户dirty门禁；
共享gate保留本轮新采集测试和A2入口。HEAD/检出保持原样。

## Phase B：D5观察，不改变算法
kind=measurement；scope=临时第一方源码快照的SYNC stderr trace；shipping_allowed=false。
hypothesis=D4短窗峰唯一性拒绝了既有已知真实路径；先观察coarse/refined/runner-up，而非改阈值。
trace字段：render_total、old/best_delay、best_score、runner-up、unique、候选确认数、raw_jump。
原始ap_sync_track_delay路径和全部状态更新不改，只增加打印，结果与baseline逐点比较。
固定执行：原ap_drift_res_tests（工程已知路径），实际rpm480/far-motion默认/tracked1/fixed1三臂。
预算：1研究build、1既有CTest、3设备回放；不开展参数搜索。
验收：baseline PCM/metrics逐字节相同、真实路径原断言仍通过、trace有限且可关联帧。
exit_gate=上述均通过；若不等价保留失败，不解释为原算法证据。
handoff=新的多帧假设须另冻结，不把measurement与候选互相批准。

## Phase C：机械验证和收口
kind=review；review_mode=whole-diff作者自审，independent reviewer/owner仍待。
required_evidence=源码锁、完整门禁日志、D3复验、D4拒绝结果、D5trace与等价控制。
Provider unresolved只形成reviewing候选；Runtime证据/goal状态与产品资格独立。
retry_budget=同类失败2次后replan；staleness=main变更复核；stop_condition=pass/replan/blocked。
D4结果不可改写，raw只读、失败保留、不清理无关dirty。Runtime总预算10000000/86400秒。
