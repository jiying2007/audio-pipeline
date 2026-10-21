# D35 历史参考相关性诊断冻结计划

日期2026-10-11；experiment=FE_DEVICE_REFERENCE_COHERENCE_D35；primary=adk-planning-execution-loop。
goal_statement=全面推进优化迭代；claimant=root；verifier=device_capture_independent_review；总体native目标active。
上一轮D34为progress：完整三臂诊断证明未反馈臂仍有初始误触发，单独隔离观测不足；本轮处理可辨识观测，不能用新测量批准算法。

## P1 授权、精确来源与假设

kind=bounded first-party causal feature diagnostic；implementation_permission=新D35 C测量程序/Python工具/tests/PLAN/RESULT/REVIEW和README追加。
local HEAD=572b0e34a8a8e5663397ce16e378209ba9058d4d；旧dirty、D0-D34专属源码/数据/工件不改。
fresh live main=d3f89e54beed483fcc0f8ce59e74b28533ed19b5；77checks完成、76success/1skipped，summary/release/convergence成功。
#657 OPEN updated2026-10-10T11:33:28Z；PR721/717/714/708/695仍独立open，三个最新nonexpired远端artifact=11693386608/11693380927/11693361221、head b797e4706eba9f6fe088c2e1e6853f447224be4f；不借其结果批准本地实验。
Provider debug route unresolved/current为空，知识线NEEDS_REVIEW，无正式归档；记忆仅用作研究/产品分层方法，非当前制品事实。
D34 result/binding=902de3247ac3179082481f28c07b471b8dd2eabd0834562da7416b3a657b9acd / edf842ff61d6d9fd0ac4ccdb05bc408c8f2500f692db00b5edf64eabb2df0d09；D34 REVIEW=329de75f38d4000fedf0784ceed63c862b589f8e95abfbd80c3026bf18c65dfb。
D34 binding递归封存D30/D32/D33依赖；本轮首先核全部source/input/artifact当前字节，再消费D30未保护primary残差与实际reference。
question=同帧残差与旧估计回声的相关性会混淆路径失配/near，带固定AEC尾长范围内历史延迟的参考相关性是否提供额外可辨识信息？
hypothesis=路径失配残差仍含可由历史render参考解释的成分，独立near更弱相关；短帧、多重反射、有限样本和搜索最大值偏差可能导致重叠，必须保留。
数据=32已查看field development+12合成return+repeat/future，共46例126486帧；adaptive reuse明确，无新的validation/blind或真人资格。
不使用path/near真值选择lag、window或参数，不复制第三方源/模型，不改权威声学评分器。

## P2 唯一新增观测合同

仅对D30实际reference与primary_residual做诊断，不重新运行AEC/Activity/选择/过渡，也不改变旧guard或任何反馈。
window固定原native帧160 samples/10ms，无均值扣除、归一化、补零、重采样或未来参考。
lag固定0..1535 samples，来自原AEC tail1536；每帧起点a，只测试lag<=a的完整历史窗口，因此startup tested_lags=min(1536,a+1)。不足历史不补造样本。
每lag计算double顺序累加 rr=sum(residual²)、xx=sum(reference[t-lag]²)、rx=sum(residual*reference[t-lag])，cos2=rx²/(rr*xx)。
rr或xx为0时该lag无效；全部无效输出max=-1、chosen=-1、lag=-1、valid_lags=0，Python统计为null，不伪装0相干。
记录frame、tested_lags、valid_lags、residual_energy、max_cos2、chosen_lag、chosen_cos2、zero_lag_cos2。
先求全有效lag最大值，再按固定1e-12数值容差从小到大选择首个cos2>=max-1e-12的lag；max与chosen_cos2分别记录，容差只作数值确定性规则，不是检测阈值。
特征在本帧处理完成后可用；若未来用于保护，最早下一帧使用。本轮不回填当前gate、不拟合分类器、不挑阈值、不生成候选接受规则。
每例全部逐帧输出；非future原whole/windows内完整160点帧分别报告valid/null/min/max/p10/p50/p90与chosen_lag分布，保留窗口边界丢弃样本。
合成return near事后由原near文件重建，在两个原near区间及其余无near帧报告分布；有near来源的其他时段不当独立pureecho实例。
额外固定按D32 monitor的原guard触发帧选取上一帧特征，报告触发证据分布；这只是解释旧误触发，不用它选择最优lag/阈值。
field无near标签；零参考不可辨识单列，不将其null当检测成功；future只核前缀，不汇总未来段、不评分或选型。
decision固定REFERENCE_COHERENCE_DIAGNOSTIC_NO_PROMOTION；promotion_allowed/shipping_approved=false；统计可揭示重叠，不认证路径真值、真人保护或声学收益。

## P3 实际执行与独立复算

PLAN独立审查PASS后实现；fresh实施PASS后启动实际测量。
C standalone仅libc/libm，不链接DSP库；strict C11/O2/Wall/Wextra/Werror/Wconversion/Wshadow/pedantic/ffp-contract=off。
C自检固定延迟正例/反相cos2/零分母/数值tie/startup完整lag，CLI非法帧数/参数在打开输入输出前拒绝，既有sentinel保持。
Python进入tools.codex_assets；Python3.8兼容；非仓cwd help/deep dry-run/tests后运行46次C测量，独立记录每次command/exit/elapsed与runner/source起止身份。
输出只fresh direct /tmp/audio-fe-device-reference-coherence-d35-20261011；主执行父wrapper不设置整体超时，单例timeout120；retry_budget2，源/输入漂移立即replan。
拒绝旧D34根/仓根/已有输出根，分别完整manifest前后相等；新证据保留全部失败，不覆盖重跑。
verifier不得import新tool/helper；独立C采用反向样本累加、全lag全frame重算，逐行比较有效/无效计数、max/chosen/zero特征、lag选择容差；不重新执行AEC/DSP。
近tie可导致chosen lag存在数值不确定性：若独立反向累加的容差边界跨越，以完整lag证据保留差异并replan，不借宽松放行或临时改tie规则。
独立Python stdlib复算原窗口/near/旧guard上一帧统计、repeat/future与全部源起止锁；max/余弦abs<=1e-12，energy相对<=1e-12（零值要求精确0），其他整数/null精确相等。
实际数值新观察者不作为旧guard候选自证；whole-change fresh、REVIEW后docs/git diff复验、本地Runtime final分层收口。

## P4 生命周期、预算与接力

资源矩阵=主C测量→输出负例→独立C/统计audit串行；独立审核脚本可准备，执行不争用主输出。
staleness_threshold=120s无输出时观察同一真实live handle，不因poll超时重启；heartbeat=真实handle/Runtime；attestation_readback=起止source/input/runner锁。
Host测量CPU开销与observer局部内存实际记录，不当SSC305 CPU/RSS/栈/热/功耗资格；旧研究128KiB/B0 50000B预算不改，本轮无部署状态新增。
open_items3；plan_completeness=P1/P2/P3/P4；logical_task_open=true；milestone_close仅观测/诊断证据；session_handoff_required=PLAN/RESULT/REVIEW与回执。
required_evidence=独立计划/实施/全数值/whole-change审查、实际主回执/负例/文档复验/锁；completion_claim尚未成立。
stop_condition=pass/replan/blocked/abort；漂移、近tie差异、两次未知失败或无信息增量须replan，不扫描窗口/阈值追绿。
rollback_path=停用D35诊断，旧库/数据/算法/拒绝记录及用户dirty保留；handoff_target=依据可分布重叠决定下一单因果保护结构，不能把max相关性当自动near分类器。
AISpeech整链/真人KWS/目标HIL/E001/PQ/第三方权利与owner资格分别未闭合；无commit/push/PR/merge/发布/设备写。
