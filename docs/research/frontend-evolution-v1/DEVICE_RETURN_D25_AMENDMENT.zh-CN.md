# D25 执行前测量范围与等价投影澄清

日期2026-10-11；原PLAN SHA256 312e95fa166fd0ec6e0671093ef666abb6f512d18559579523fb2d27b7f4594d保持原字节。
独立计划审查QUESTION-1/2仅涉及评分范围和新增字段比较；首次实际编译/DSP前冻结本澄清，未调整信号、时间、算法或评分阈值。

QUESTION-1：shadow只在完整active窗口评分；keep全程无shadow，所有shadow统计null。
shadow策略的whole及[0,2)/[8,10)窗包含inactive，shadow统计null，不将零trace当有效残差；其余完整[10,20)内窗正常统计。
不另加active-only whole，保持窗口明确且防止与完整20秒统计混用。selected及primary全窗口保持原合同。
每窗明确sample_range和samples；near全零才给工程ERLE，混合输出误差仍只报RMS/peak及差值。

QUESTION-2：A/echo原8trace及primary state.csv对D24对应A/ref/policy逐byte一致；selector CSV去掉新增dt列后逐字段和顺序一致，dt全0。
新增near全零、true_echo按D22 A独立构造核；不称12文件全等D24的10文件。
ABA/echo前10秒对D24 switch同policy使用相同原8trace及primary CSV前缀/selector投影，新增truth/near另核。
两QUESTION必须fresh计划复审闭合，实施和工件起止同时绑定PLAN与本澄清。
