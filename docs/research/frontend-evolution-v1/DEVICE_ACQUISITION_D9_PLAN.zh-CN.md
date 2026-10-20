# D9已知延迟获取与恢复矩阵

日期：2026-10-10；状态：FROZEN_ENGINEERING_MEASUREMENT_PLAN。
授权：用户继续推进D8后明确的下一研究；primary=adk-planning-execution-loop。
目标=判断D8保守gate是否阻止已知正确延迟获取。算法不改、D8选型不确定不改写。
基线=D6 receipt d2e4c5fb82c2ca795d576f42618b8204e47ae16b7f96c232fdc161d542bf4b36；
候选=D8 receipt eb85a87a494d08ce35be0f9cd47ba0030be9336ec85e35ade0322837d10cbedc及其冻结研究patch。
live main=f05eecb69ab5ac1a0968381f109510c939b53e50，tracker#657 OPEN，其他PR独立。
Provider route unresolved，仓内仅reviewing候选；无SCM/设备写、无产品默认改变。

## Phase A：冻结数据与测量实现

kind=measurement；数据为第一方合成、已公开development工程数据，不是真人、room或blind。
同一新C fixture使用公共API，分别链接原D6和D8精确静态库，不改两边processor或既有回放测量。
隔离SYNC stages=AP_STAGE_SYNC，mic1，initial40ms/max100ms，delay/drift均启用，其他默认配置相同。
rate=8000/16000；seed=1/2；true_delay=1/7/80ms；regime=acquire/switch。
每例300个10ms帧；acquire从第0帧使用true_delay；switch前120帧40ms，之后true_delay。
四类信号：宽带低通PRNG（因果2ms滑动平均）；双频733/1187Hz周期；
低参考（同宽带render幅度0.03，常规0.30）；双讲（宽带echo + 独立seed的近端低通PRNG，幅度0.42）。
mic echo=0.4×实际量化render的已知延迟信号；delay前无历史时为真实生成器起始零，不补算法尾。
全部生成S16LE实际mic/render，保留每例输入字节及逐帧metrics，两processor输入必须逐字节相同。
周期/双讲的延迟标签是生成器真值，不证明可辨识性或实际声学标签。

96主例=2rates×2seeds×3delays×2regimes×4signals；
4附加例=2rates×capture-gap已通知/未通知，宽带seed1，前120帧40ms，之后80ms。
gap例第120帧仅push render不process capture，notify例立刻通知CAPTURE_GAP；未通知例明确超出正常配对契约，
仅观察fail-closed，不把baseline自动获取当作正确处理gap的规范。
总固定执行=每processor100例，共200；另每processor复跑16k/seed1/宽带/acquire/7ms一例，共2。
新fixture不加入shipping构建/CI默认目标；source/config/输入/库/输出hash必须绑定。

## Phase B：验收与负例

kind=validation；指标=逐帧estimated_delay_ms/counter、首次进入目标±3ms帧及最终20个capture帧在范围数量。
mandatory集合仅无噪宽带96中的24例：每processor最终20帧必须20/20在生成器目标±3ms；
若baseline先失败，记BASELINE_FIXTURE_LIMIT，不把candidate优势当通用资格。
baseline通过而candidate失败，D8记REJECTED_KNOWN_DELAY_ACQUISITION_REGRESSION；不调整帧数、误差或门限洗绿。
双讲/周期/低参考均完整披露，不能凭diagnostic通过率选型；gap已通知恢复目标最终20帧必须20/20。
不能用jump较少替代获取正确性；未通知gap只记录保持/拒绝，非自动恢复要求。
严格C编译、输入范围/finite/帧数/类型检查；指定重复输入、输出和metrics逐字节等价。
任何I/O或processor错误为测量失败，不伪造目标/runner/实际输入。
重算summary必须基于保存metrics，源代码判定与Python回读相互核验。

## Phase C：决定与独立审查

kind=review；claimant=root；verifier=已授权独立审查者；whole-change。
required_evidence=冻结计划、fixture、两processorsource/库/配置、实际输入/输出/trace、重复控制、负/不利结果及独立核验。
预算=两次fixture编译、200固定+2重复，不新构建算法、不搜索参数；必要测量实现bug修复保留失败用新目录。
retry_budget=同类错误2次重规划；staleness=任何fixture/规则变化重锁；heartbeat=阶段完成；stop_condition=pass/replan/blocked。
goal_statement=得到D8已知获取风险决定；open_items=fixture/执行/审查三项；attestation_readback=hash/JSON及实际metrics重算。
可能结论=REJECTED/INCONCLUSIVE/ENGINEERING_ONLY，任何结论不批准shipping、AISpeech替换、E001或PQ。
物理render时轴、独立声学、人工标签、owner及SSC305资源另验收。
