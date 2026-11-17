# D7 双麦 HPF 与 BF 分离观测：执行前合同

状态：PREREGISTRATION / NOT_RUN。实验 FE-DUALMIC-UPSTREAM-D7，候选数为0。
基线 main e348843a570503728930f06451633262b2546fa5，tree b420d795337483612bc02924e60f693166a5727f，
生产版本2.3.64。研究追踪 #944；总研究 #657 继续开放；本合同只定义一次中性上游诊断。
2026-11-11 已读当前main、87个checks（required summary成功）、公开开放issue/PR；
未发现同题实施占用，既有 #925 与 #714 不属于本轮修改。
先单独冻结本合同与完整机器锁，再独立复审准确字节；未获该复审通过不得实施。
实现须另经独立审查，才打开触发研究的PR；本冻结不声称已经执行音频或取得质量结果。

## 1. 问题、可回答范围与停止边界

D1第一条实际上游音频是HPF/BF联合输出，不能分开两级。当前BF在Activity之前
用混合输入的相关性历史选择方向；这不等于已经证明它跟随远端回声。
原A构造近端TDOA为0、35mm/60度回声TDOA约1.413919样点，near source从frame150
开始放置，far source从frame0放置。必须直接观察当前运行的两路HPF前后信号、
BF输出及完整真实状态，才知道既有变化和状态是否在时间上关联。

本轮不改变DSP、参数、控制路径、公共ABI/API、默认配置或版本；不关闭模块、
扫描阈值、修改AGC/NS/RES，不回扫已关闭D3/D5/D6或其他AGC变体。
D7没有候选准入屏障，唯一成功终态为UPSTREAM_OBSERVATION_VALID_NO_PROMOTION；
任何身份、连续性、中性、闭包、数值或预算失败为MEASUREMENT_INVALID。
有效诊断也不自动授权后继变体、算法修改或新的实验。

S003的HPF-aware oracle已将该历史mic-mismatch候选线终结为
CLOSED_DIAGNOSTIC_METRIC_REFERENCE_ARTIFACT_REJECTED。原raw-clean SI-SDR严重下降
在HPF-aware reference下消失，HPF-only输出对右通道替换保持不变。
因此本轮raw→HPF的固定参考分数变化只能报告为频谱/相位/参考域敏感性，
不能称HPF损伤、缺陷或听感根因。保留S003原结论，不新跑该oracle，不换本轮参考，
不通过HPF-aware重评分制造候选资格。BF变化也不是来源因果归属；
“跟随回声”“near损伤原因”等结论均需后继独立结构假设与数据。

## 2. 唯一原件与完整准入

唯一下载为原D2 run42321833898 / attempt1，
source cc853616685b9faf7880e6d8f8f1a89d187d342a，
artifact13553232106，ZIP474165229 bytes，
SHA256 a3ab7823fdcd7586c3b72eb214b5536dcfb7531fdf0b1611d49e1575a29b2c3d。
3551成员、861385743解包字节，D2 report
f259693095d73e8cca74e15cc60f0c4e1e157cfecab32706bee35926f2fca9ea，
manifest e43fa150e38d65ecb43020f19a403547fce9634736735b0367512040b9c58a63。
API元数据当前expired=false、expires_at=2027-02-05T01:02:47Z；
该元数据不是本轮已完成下载准入的声明。

完整dualmic-upstream-d7-input-lock.json嵌入未经改动的D3原件准入身份与D2完整60例锁，
包括原顺序、argv、事件、近端参考身份和父tap绑定。另逐例列出全部原mic/render/clean/
auxiliary路径、旧端点和七lane目录。raw输入的完整hash权威是固定ZIP、
原D1 manifest和selected-members.json到内部A/C ZIP的逐字节绑定；
不伪造未下载raw的独立hash，也不把可重新封存的新manifest当原件权威。

复用未改动的D3严格获取/路径/成员/hash准入器和完整D2读回。随后复核原D1
report/manifest/source/build/readback/phase及所有成员闭包，并调用原verify_origins，
把所有保留raw逐字节核回内部原A/C ZIP。
原D1在original/result，report hash
472e050dd155973c0a49fca1fb17c8204e240411ca37d99e3a81c1b777d8e958，
manifest hash 84c6884037fc61aeee222033cf0b5a6f06c644114ffdeee1349ed61e6c2e86cf。
原代码及成功结果证明该包保留A双路mic/render/clean-near/auxiliary、
C双路capture/render、原端点、D1全部taps和exact source。
实际完整性仍须本轮准入确认，缺失立即失败，不重新生成或换包；
不额外下载原A/C，不运行语音模型。

全部60视图（A56+C4）、35916帧、5746560样点、原362固定窗口保持。
32例具有原clean-near参考，28例原null；C mixed duplex_mono绝不当clean truth。
角色始终为disclosed-regression：英语真实语音加合成传播、中文同一句的相关视图，
不是60名说话者、新holdout、真人阵列实录或真机声学证据。

## 3. 当前源码与旧原件的独立身份

机器锁完整列出当前65个生产/构建notice文件的Git mode、blob、长度、SHA256，
以及26个旧测量/准入/评分/原场景/S003解释依赖的同样身份。
新builder从实际精确HEAD制作有界的selected-source Git archive：
包含完整src/include/cmake/examples、CMakeLists/CMakePresets/CHANGELOG和必要notice，
全部冻结传递依赖，以及当次D7代码、合同、锁、实现说明和工作流。
它是完整编译/测量闭包的选定源码archive，不冒称整个仓库archive。
Git tree、根对象、所有成员和运行时仓库导入都核到该HEAD；不消费未留存模块。

旧tools/codex_assets/dualmic_stages_build.py继续只接受旧4daa7e2生产字节及2.3.63，
不得调用其build或修改其约束。本轮使用新的
tests/validation/frontend_evolution/dualmic_upstream_d7_build.py，
分别从准确当前archive构建plain与observer；原历史库/原端点保留旧身份。

普通构建保留原Release / -O3 -DNDEBUG、C_FLAGS空、SCALAR、MDF、EMA、
BANDLIMITED、完整模块mask1023、direction tracking enabled、fast_math=0配方。
plain source_revision为本次HEAD；observer为本次HEAD-D7-observer，版本均诚实为2.3.64。
保存真实compiler lookup、直接symlink目标、解析后的普通文件realpath/hash/version，
实际编译与链接argv、compile_commands、flags、generated headers、静态库、程序和日志。
实际compiler argv使用解析后的普通文件。此解析例外不允许证据路径symlink。
不声称当前compiler/libc/libm等于历史环境；若旧端点不能复现，按失败停止，不调flags/容差。

## 4. 仅测量副本中的可逆封装

原D1的五处生产定义rename保持，并增加且仅增加两处：
ap_hpf_process→ap_hpf_process_d7_real，
ap_beamformer_process→ap_beamformer_process_d7_real。
七处生产函数体和调用点均逐byte保持；每处只命中一次，逆变换后等于原blob。
旧D1 C在仓库不改动。为准确组合main，仅在测量副本把其最终
int main(int argc, char **argv) 定义可逆改名为ap_d7_d1_main。
D7 C包含此派生副本，自己main在该入口前后打开/关闭D7证据；
D1原有生产CLI include、原7lane观察、事件、PCM/JSONL输出均保持。
这是一处额外helper入口定义rename，不是第八个生产DSP变换。
不得依赖外围#define main：D1内部会自行define/undef，必须核查实际预处理组合。
原版/派生版及全部before/after/inverse hashes、准确changed-file集合都保留。

五条新增原始Float32LE信号：
- hpf_input_l、hpf_input_r：实际HPF输入，与原16k双路S16除32768逐样点相等。
- hpf_output_l、hpf_output_r：实际HPF输出，必须逐byte等于BF的两路输入。
- bf_output：实际BF输出，必须等于AEC input；capture-only则等于NS input。

不选择更好通道，不以平均信号代替L/R，不归一化，不S16往返量化。
每条完整5746560值/22986240 bytes。调用总数HPF71832、BF35916；
每帧严格HPF0→HPF1→BF→原Activity→可选AEC→原NS→原AGC。

HPF在两个调用前后各保存完整state；冻结布局24 bytes：r、x[2]、y[2]、channels。
BF前后完整state为180 bytes：history[2][8]、lag_score[17]、fallback_gain、
lag/max_lag/fallback_lag、counter/score_updates及全部fallback和fixed_health字段。
实际sizeof、每个offsetof、整数/IEEE Float32宽度及little-endian均须编译和运行核验。
每帧binary trace为16-byte frame/track_direction/output_alias/n，
加四份24-byte HPF状态、两份180-byte BF状态，共472 bytes；
35916条共16952352 bytes。字段来自真实调用前后，不是公式伪造的内部观测。
记录真实track_direction及输出别名分类；本完整pipeline应为独立输出buffer。

lag_score是实际EMA状态，不是内部瞬时相关系数。两wrapper不能直接观察局部
aa/bb/xy/coherence，报告不得如此命名。有效输出lag必须使用after.fallback_active ?
after.fallback_lag : after.lag，不能拿tracked lag替代fallback输出lag。
35mm/16k的max_lag为3，搜索范围±3；每次tracking更新最多移动±1是slew，
不是搜索范围，也不等于声学DOA。

## 5. 必须通过的旧原件中性桥

对每个完整视图同时要求：
1. 当前plain、当前observer、原A/C的out.pcm三者逐byte相同。
2. 当前plain、当前observer、原A/C的metrics.jsonl三者逐byte相同，不重格式化。
3. 当前observer的原D1七条lane和control.csv逐byte复现原D2内的父D1。
4. AEC缺席保持真实absent：capture-only5858帧，AEC30058次；
   Activity/NS/AGC各35916次，独立时域RES仍0次。

只比较两份fresh输出不够。旧原件、当前plain、派生observer各自身份完整保留。
任何不等都不能增加epsilon、改变原输出格式、替换baseline或仅用分数相近放行。
通过全部中性、源和时序检查前不解释新stage值。

事件仍是原CLI输入。只在原8个render-gap的frame300处理前，
原notify_stream_discontinuity重置HPF/BF；flags=2、lost_frames=4不额外插入零帧。
echo-path-change通知不重置HPF/BF，不裁窗初始化或创造reset。
每个流首帧/reset前state要匹配初始化；其他before必须等于前次after。
HPF未处理通道、r/channels不变，保存x/y分别匹配实际末端input/output；
BF after.history必须等于当前HPF输出的原始尾部，不能是BF输出尾部。
保留实际score更新计数、cadence、非更新帧不变的score和半径外不变项；
按实际after输出route及before.history独立Float32重建BF输出并全样点byte比较。
重建量明确标记为重建，不称额外C内部观测。

## 6. 唯一固定评分和完整状态关联

只调用冻结D1 measure_lane/stage_delta、canonical si_sdr_span及D19 energy，
不增设另一评分器或声学通过门槛。五条新lane offset均0；
旧NS/AGC输出offset160。所有stage使用物理共同跨度[0,N-160)，
完整原1秒及短尾窗共362个，不搜lag、不挑窗、不挑pair、不换参考。
native whole-buffer能量另外保存，不能与共同跨度混用。

分别报告rawL→HPFL、rawR→HPFR、HPFL→BF、HPFR→BF的固定增量，
并保留每条lane全部原canonical SI-SDR、rms_dbfs、linear peak和null原因。
原D1下游数据/分数必须原样复现。HPF两路分数差不是损伤判据，
两路BF比较也不是独立因果干预或可相加的贡献分解。

完整全帧记录须关联旧far/DT及原事件；全部固定窗口、每例whole另报告：
真实tracking模式计数、score更新/cadence、tracked/effective输出lag直方图与所有变化、
fallback/hard/strong-channel/恢复/arm/fixed-health状态，完整score/history可追溯。
每个变化保留原frame和来源放置状态，不只输出少数极端帧。

只有A且clean_near非null时，scheduled-near source placement为[24000,88000)
即frame[150,550)；原参考内部停顿仍是实际语音内容，不能改成人工VAD标签。
far-only/path-change/render-gap虽复制near_start dimensions，却没有near source，
不得误标为frame150有near。C的近端真值/来源放置身份保持unknown/null。
评分窗口按physical range对应原帧；全流state另包含共同跨度排除的最后一帧。
全矩阵、正负增量、null、whole与每窗都保留，不把关联称为因果、漏检率或听感改善。

## 7. 自检、实际负例与独立验收

工程控制覆盖实际sizeof/offset/Float32、两通道顺序和before/after、
fixed/tracking、lag正/负/0、normal/soft/hard路由及独立/精确别名buffer，
初始化/连续历史/真reset/path-change区别、非有限/长度/次序/写盘/关闭失败，
全部逆变换、旧新身份区分、compiler selector与证据symlink区分和硬timeout。

机器锁预先列出51类实际证据篡改，覆盖五信号、全部状态类别、控制/事件、
旧PCM/JSONL/七lane/control中性锚、window/null/near schedule/关联计数、
来源/函数体/入口/header/compiler/argv、闭包额外文件/空目录/symlink，
失败phase/command、原准入/输入绑定和readback回执。
先完整验证未经修改的合格证据，再在隔离副本逐项篡改；每项预期的专属拒绝理由
须在实现独立审查中确定、在执行前冻结。I/O、timeout、无关异常或未拒绝都不能算通过。
只读自己的回读和独立作者的原件审计分别记录；独立审计不重跑DSP/模型，
覆盖源/原件/中性/全帧状态/固定窗，缺项或未执行必须如实说明。

完整源码、原始输入、实际程序/命令、全部输出及回执具有严格文件和目录闭包。
不允许通过更换manifest自证被改来源。成功与失败阶段均用新路径，
首失败类型、目标、reason、退出码、耗时和已完成文件保留；
不得覆盖旧失败或把未执行阶段重标为成功。

## 8. 资源、CI与逐步落地

每阶段300秒：获取准入、plain configure/build、observer configure/build与工程控制、
全60例plain+observer run、analysis、readback、negative。
所有新子进程在启动时硬timeout=min(30秒,该阶段剩余秒)，包括compiler、git及构建命令；
不是事后计算超时。旧D3读取器不改写，其准入为同进程调用；
父阶段300秒hard deadline包含I/O、hash、最终回执写盘。总Actions job20分钟。
不得因失败延长预算、换输入、flags、算术或测量定义。

源码闭包上限16MiB；本轮新结果闭包上限512MiB，明确与固定原ZIP474165229 bytes、
解包861385743 bytes分开，不套用D6的256MiB限制或隐藏旧包体积。
五条新增lane约115MB、原七lane约146MB、状态约17MB，加端点、metrics及构建证明；
512MiB是执行前上限，不是实测或后验放宽。
保留完整原ZIP独立上传，不重复上传其整个解包树；原输入准入/hash和成员闭包同留存。

只在现有.github/workflows/frontend-research.yml添加scoped dualmic-upstream-d7 job，
D7-only变更保持所有旧job区域byteexact且不选择它们，不新增workflow。
checkout/upload action SHA保持既有pin。精确PR head/current main分别执行自己的全部适用
Verify/required summary；打开PR前完成实现审查。不得借旧head CI。
原件、首次失败、成功产物始终上传，include-hidden-files=true，retention90天。
受保护squash合并前再次核head/base与审查，合并后独立核fresh-main门禁。

全部实际DSP只在已授权公开仓库GitHub Actions；本轮不使用Codex Cloud/CLI/local、
ChatGPT Work、付费/私有数据、模型或真机任务。无tag、商业发布、
真实WAN/MOS、KWS/ASR泛化或物理SSC305资源结论。
