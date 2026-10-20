# D37 归一化无效字段的执行前补充

2026-10-11；原PLAN SHA256=ab15bccb2657bfc6dc010dac2f26d0d34820125b1bc7e2fb8843a3f993aaf8be保持，D37未实现或测量。
独立计划QUESTION-1：model_valid=1但当前residual_energy=0时，normalized_valid=0已有明确含义，但innovation_ratio/explained_fraction的导出值尚未明确。

冻结补充：任意normalized_valid=0时，innovation_ratio=explained_fraction=-1；按normalized_valid判断null，不能因explained_fraction真实可为-1而推断无效。model_valid和真实beta/fit/prediction/innovation能量保持，不删当前rr=0的有效模型。held_cos2继续保留D36自身有效性。
known-answer在当前rr=0时须同时断言model_valid=1、normalized_valid=0、两归一化字段exact -1，以及真实prediction/innovation能量。

不改模型公式、窗口、容差、数据角色、数值失败停止条件或NO_PROMOTION；原问题保留。fresh独立计划复审及上下文维护解除后才实现。
