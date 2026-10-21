# D38 精确求和执行记录

2026-10-11；experiment=FE_DEVICE_CAUSAL_RESIDUAL_MODEL_D38；主测量和独立全量数值审计 PASS，整批文档/收口审查尚待完成。

原 D37 保持 NUMERICAL_CONTRACT_FAILED_REPLAN，其源码/输出/失败回执/REVIEW 身份锁定。D38 PLAN 独立 Spec/Quality PASS，SHA256=9e4927fefd2cc8b207b2e026b4ada38aefa12423f3d2912869e48edf5171df08；新实施独立 Spec/Quality PASS / independent / unresolved0。工具 SHA256=6974a6ea99c0d5ccedc820aa7eff57c9c4ba076da0fbf385fd464ba2326b2c04，测试 SHA256=223cc30ad6c1d747e74012bf6fd97543a618c459c62d2ac1430b05078f9c597a。

唯一数值变化为六类 binary64 项求和→math.fsum；逐点乘法、prediction、innovation、前帧lag与拟合、beta/ratio除法和原统计保持。13 known-answer 实际 PASS，包含 D37 真实失败帧 Decimal 回放、160 项正负抵消与顺序、最大有限/最小次正规数以及39601比例不clamp。测试继承原九项，未将旧测试重复计数。

首次非仓 cwd wrapper session22816 terminal exit0；help/deep dry-run/13tests/main各exit0，main44.47986630629748秒。原46例126486帧240窗、repeat全CSV/future通知前1247帧exact、future measurement=null；起止身份一致，AEC/lag搜索执行均0。

输出 /tmp/audio-fe-device-causal-residual-model-d38-20261011；result SHA256=4cb3d3273391a3a6b9e34348a060bb4a423e2184a2d8f5e42b097e711d6946c4，binding SHA256=4c51efdd4cfa863fdac15dc58b2f2849fa62114d93c485fbd0ef87614ebe08c8。

negative session13038 terminal exit0，旧D37根/仓根/已有D38根命令各exit2，48/2483/48文件完整manifest前后相等，2.930051377043128秒。root执行、独立审查者核回执，未独立重跑。回执 SHA256=0410153c564430020555e840d64fceff5d3eae4acf2bc88218c1e2df9ef4977f。

独立 audit /tmp/audio-device-d38-independent-audit.py SHA256=62ed98c89e6232f6d575bc75438147487f6fcad4f14b02bfc8062fbe02045eb1，session50618首次实际执行中。它不import项目/helper、不使用fsum作裁判；Decimal.from_float精确接收各binary64项，2200精度与Inexact/Rounded traps反向求和，float一次舍入。1385位保守上界、极值/次正规数/负beta/当前rr0内存检查通过；全量尚待真实终态，禁止推断PASS。

随后同 session50618 真实 terminal exit0，首次 audit PASS，用时130.04858053382486秒，retry0。回执 /tmp/audio-device-d38-independent-audit.json SHA256=e4ccc8e4e4e857266b74cd4f0e36d0308ba6452f15a6ad0b68601a80ceb0ad16。全46例126486帧240窗1897290次字段exact断言通过；3953项起止来源锁保持，repeat全量/future1247前缀通过。独立Decimal与导出浮点全部exact，不使用D37容差换PASS。

全执行集合model/normalized valid均66724，reason0/1/2为66724/46/59716，ratio>1为32698（包含repeat/future，不能当成仅主矩阵统计）。实际residual全零帧为0，相关边界由known-answer覆盖。数值资格不包含目标CPU或声学验证。

纯echo四来源A-r16/A-r20/ABA-r16/ABA-r20的explained_fraction p50为0.43796394/0.41539107/0.44335405/0.43751445。混合ABA首near的innovation_ratio p50为0.83560545/0.83779769，200帧中ratio>1仅22/21；混合A首near为1.07837478/1.07759480，ratio>1为192/193。求和优化未消除near/echo混合问题；过去模型解释部分残差，但创新不是near truth，不能据此批准阈值/保护器。后续结构实验需独立冻结新假设与数据资格。

fresh main仍d3f89e54beed483fcc0f8ce59e74b28533ed19b5，77completed/76success/1skip；#657仍OPEN，PR721/717/714/708/695 head保持，最近3非过期artifact仍属f495801f1d5782d8ace8b67abb0f18ec2b53cd36，不批准本地D38。Provider route unresolved/current为空、zero-hit，知识线NEEDS_REVIEW；不采用不同AISpeech reviewing v27作为本研究事实。

Runtime ensure dry-run实际exit2，已有D37 active目标冲突。随后按真实数值失败replan：只终止Runtime本地D37任务（非native总体目标），新ensure/PLAN evidence/progress/checkpoint/heartbeat六命令均exit0。新localgoal task-f549a2d7016352e32a8c0c60 active/open3，checkpoint1 verified；原native目标active且无token上限，不以D38预算替代。无成功改判D37。

NO_PROMOTION / promotion_allowed=false / shipping_approved=false。数值诊断不等于真人near识别、降能量声学收益或产品资格；AISpeech整链、真人KWS/near、SSC305资源/热/功耗、HIL/E001/PQ、rights/owner仍分别验收。README接续追加后旧D36 README snapshot仅保留历史身份，旧专属源码/工件保持。
