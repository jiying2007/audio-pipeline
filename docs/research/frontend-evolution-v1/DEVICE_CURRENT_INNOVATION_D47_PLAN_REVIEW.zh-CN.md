# D47 当前创新映射计划独立审查

2026-10-13，experiment=FE_DEVICE_CURRENT_INNOVATION_D47。claimant=root；verifier=device_capture_independent_review；Reviewer Independence=independent。Review Target为新PLAN+执行前AMENDMENT当前字节及明确引用的冻结D45源，不是实施或正式结果验收。只新增本PLAN_REVIEW，未修改其他源、旧结果或裁判；未执行DSP、正式测量或旧全量审计。

| 合同 | SHA256 |
| --- | --- |
| PLAN | `20906d11069584db58c5ba13855b6d1d36f798361fae690d5dab142b3b23cfc0` |
| AMENDMENT | `0645bf01701fcdd6ef1f13aafbf8d8a60adc57620f0875b95c4cd7309a6f3f5b` |

## 最终计划结论与发现历史

Spec PASS；Quality PASS；Reviewer Independence PASS；unresolved=0。初审未发现MAJOR；MINOR-1统计组计数、MINOR-2审计预算来源文案经执行前AMENDMENT最小澄清并独立fresh复审闭合。原PLAN字节保持，未登记、未实施、未正式执行；此结论仅允许后续新任务登记和实现准备，不批准假设收益、算法候选或产品。

MINOR-1：原“240窗口”应为每mode/arm的45 whole+195 fixed，共240组，四种组合960组；不是240 fixed。独立只读已有D45 result字段检查四组合均为45/195，tool chunk c7ee0e实际exit0。没有重算旧波形或改变原评分集合。

MINOR-2：D45实际冻结独立audit为1200秒；D47独立audit1800秒是新增复数预测算术在结果前预注册的本轮预算，不能称沿用1200秒。AMENDMENT已明确原DSP120秒、矩阵1800秒、资源/磁盘、数值容差及全准入保持；本轮审计若超时或失败必须保留，不能再加时取通过。两项修订均发生在实施/结果之前，不改变floor或裁判。

## 唯一映射、时序和单位

独立读取原D42更新：Cr=c*a+d*b，Ci=d*a-c*b，即residual×conj(echo)。由此H=(Cr+iCi)/E，预测pr=hr*er-hi*ei、pi=hr*ei+hi*er的虚部方向正确。旧E/R/Cr/Ci及N来自更新前统计，先计算当前预测及floor，再调用原更新，避免用当前样本拟合后评价自己。原输入FFT及历史窗口有重叠；这不是额外独立样本或物理路径真值。

当前P必须按double从保存的rr/ri计算rr²+ri²，不能直接复用旧binary32 power字段（该字段保留原运算和1e-12f）。旧noise N与旧/当前FFT功率处于同一频点能量域，没有新增幅度或时域能量估计器。当前J=|residual-H·echo|²来自同一输入，模型不读取near、路径、窗口或未来标签，也不改变AEC/selector或反馈改变拟合输入。

模型valid仍由旧count10及E/R门槛决定；P归一化门槛只关闭gain，不把模型改为invalid。有效模型P=0、J>0应保留raw J及overshoot，floor仍0；J>P可以真实发生，不强制压J<=P。只将归一化gain比例截至[0,1]，不得clamp原J、截H或制造ratio0掩盖失配。所有有序double中间运算finite，非法或溢出作为测量缺陷保存，不临时补epsilon、换精度或放宽容差。

该结构可执行也可证伪：稳定线性echo可能得到较小J；但预测路径变化、过往混合near以及模型失配也可能提高J或误抬gain，不能把创新天然称near。D46纯echoABA持续差异的证据仅排除“全部只是短尾”的解释，不证明此H模型能解决它。原全量no-near和pure-echo准入用于保留这种负结果。

## 诊断、投影及独立验证合同

原power18列的历史q、E/R汇总和innovation_sum=R*(1-q)保持，不能漂白成当前J。actual floor及其派生计数/旧floor²×过去R按明确含义报告；仅末尾追加current P/J汇总及J>P计数，按valid集升序double左折叠，empty严格0。旧innovation<=过去R约束只约束历史列，不套用于新的J。

原25列bin中的更新前E/R/Cr/Ci/N及当前er/ei/rr/ri足以独立重建H、prediction、J/P和newfloor。追加诊断不成为新裁判；固定快照算术覆盖不能冒称全bin全frame或完整FFT/EMA/noise历史重建。原NS/RES状态、更新前/后模型、speech/noise及原FFT操作数投影保持；与D45对照必须排实际floor及其派生字段，不能误要求新floor等旧floor。两模式observer之外无新跨帧算法状态，actual sizeof仍须测量。

原184次/505944帧、四组合960组新波形和原每臂24near/72no-near/4pure-echo whole全部独立复算。near中位<=-3 dB、至少18改善和两项+1 dB上限保持；future4不评分，repeat不增加独立样本。RMS1e-10 dB、float exact、double汇总max(1e-24,1e-12abs(expected))与expected0严格0保持。测量缺陷与DEVELOPMENT_REJECTED分开记录，任何候选仍无shipping批准。

## 身份、预算、执行与资格边界

主代理只读intake session95981已提供terminal0/46来源/9829锁/noDSP/noWrite，原五D45 pins保持；此处是主执行证据，我未重跑该preflight。新preflight先核固定五源再调用旧helper，避免旧动态selfhash冒充冻结基线。未来实际source/input/artifact和D18/D30/D39/D42裁判必须精确绑定；本计划通过不代表那些未来终态已验证。

算法scoped22000 B、measurement<=65536 B且加D30<=131072 B、4 MiB单工件/1536 MiB根/free3 GiB均保持。追加power字段如果超限应停并保存，不能删锁或缩覆盖；宿主预算不能替代目标板栈/RSS/CPU/热功耗。单因果映射、无参数搜索和完整失败保存边界合理。

正式root/own及parent symlink提前拒绝、完整existing-root manifest负例、排他intent先于操作、异常null/partial及未知同handle对账已冻结。实际实现、known-answer/定向测试、执行控制及独立auditor仍须另审，尚无新正式结果。最终README追加采用精确历史ac998973保存映射，保留D46旧247snapshot和更旧625af备份，不可演变为任意源漂移fallback。

field无独立near真值；数据为已查看development/synthetic及adaptive reuse，不是blind验证。D45拒绝、D46归因、旧0–46结果/失败/裁判保持。Provider unresolved/NEEDS_REVIEW，无耐久归档成功；真人/ASR/KWS、AISpeech产品链、目标板/HIL/E001/至少72小时Product Certification均未由本计划建立。总体native目标active，不因PLAN PASS完成；无commit/push/PR/merge/release/设备写。
