# D8：固定40ms证据参与大跳确认

日期：2026-10-10；状态：FROZEN_CANDIDATE_PLAN。
用户授权继续上一轮明确的下一项算法实验；primary=adk-planning-execution-loop。
范围为临时第一方研究构建，产品源码/default/API不改，无SCM/设备写。
基线=D6 source identity，receipt=d2e4c5fb82c2ca795d576f42618b8204e47ae16b7f96c232fdc161d542bf4b36；
D7测量=result 770b2ac5f6b8472176eb050fc96459d676d1641ab1aa424e84342c72d6e17410，非算法批准。
live main=f05eecb69ab5ac1a0968381f109510c939b53e50，tracker#657 OPEN，其他PR独立。
Provider route unresolved，本计划仅仓内reviewing候选；D4拒绝保留不改。

## Phase A：单因果候选与资源契约

kind=implementation；hypothesis=短窗假大跳的相关不能在40ms完整历史保持，已知路径能保持。
唯一因果：原raw_jump>sample_rate/50的大跳分支，在原三次确认之前增加完整40ms候选分数检查。
长窗score低于现有AP_SYNC_MIN_CORRELATION_SQUARED=0.0324，或历史不完整时，清大跳确认并拒绝本次观测；
否则按原候选容差/三次确认/route apply继续。原小跳、漂移、相关门限、确认次数和max delay不改。
不加D4短窗唯一性条件，不计算/选择长窗最优delay，不搜索阈值/窗口，不改变AEC系数或reset契约。

资源：基线完整state=78192，ceiling=80000（实际编译定义下sizeof），不放宽上限。
40ms历史按原stride=4保存，160 floats覆盖16kHz640点；8kHz为320点80份评分样本。
候选history是每个state独立、固定容量、无malloc/TLS/全局slot；init/reset按既有memset清空。
mic累计完整样本计数与render_total一致、window+maxdelay历史可用且未超ring时才计分。
适用8/16kHz，帧80/160且按4对齐。其他输入或历史不足拒绝大跳，不能猜测/补零。
候选仅改临时src/sync/ap_sync.c/h；公共头和真实产品源码保持原字节。
exit_gate=严格构建且公共resident ceiling原断言通过；失败即保留并停止，不扩大资源门限。

## Phase B：固定工程验证与负例

kind=validation；固定14CTest全部必须通过，包括原已知640→1280路径恢复和periodic假跳负例。
额外直接SYNC工程测试：8/16kHz长窗延迟数学已知答案；历史不足/累计不一致/低相关拒绝；
reset清除历史及确认；两个state交错无串扰；禁用tracking不改变delay/事件。
负例只作工程契约，不替代人声或声学资格。任何硬回归即REJECTED，禁止调参数或重写旧测试洗绿。
在全构建下报告实际sizeof、无新堆分配；Host资源数不升级SSC305 CPU/stack/RSS资格。

## Phase C：固定development回放和决定

kind=research；使用原119文件锁/16轮development，不将已查看样本升级blind。
沿用D3 70fixed+2repeat原配置/数据/metric契约，仅processor identity不同。
本批矩阵选择诊断作用不等于独立保真验证，所有失败/负结果保留。
fixed1和tracking关闭的隔离臂必须PCM/metrics逐字节等基线；禁用drift臂只有tracker大跳影响可不同。
default/sync-default-control及重复控制仍逐点相同；零参考quiet必须无新增跳变/重置。
指定rpm480/far-motion tracked1的172ms大跳必须消失，同时原工程恢复必须通过；
任意其他case新增jump/reset即拒绝，无新增不保证声学无回归。
不以总能量选择候选，不设/改ERLE、FAR、FPR或人声保真阈值。
若新臂出现未解释counter/output差异，记录diagnostic/inconclusive，不claim候选通过。

## Phase D：独立审查与闭环

kind=review；goal_statement=作出固定D8候选接受/拒绝/不确定决定；claimant=root；verifier=独立审查者。
required_evidence=冻结计划、全部source/build/config/input/output绑定、14CTest及新增负例、回放、独立whole-change审查。
retry_budget=同类失败2次replan；staleness=源码/规则变化重锁；heartbeat=阶段完成；stop_condition=pass/replan/blocked。
attestation_readback=hash/JSON回读；scope_write=新D8文档、临时source/runner/test输出，sharedcontract串行。
执行预算=1候选strictbuild、1既有CTest、1新增工程集、1固定70+2矩阵及复验，无参数搜索；
若工程硬失败即停止矩阵，保留REJECTED结果。Host sanitizer若候选工程通过才补1构建，非DUT证据。
decision=REJECTED/INCONCLUSIVE/DEVELOPMENT_CANDIDATE_ONLY；任何结果都不能更改shipping或E001。
剩余独立声学/人工标签/render时轴/设备制品/owner/产品资格另验收。
