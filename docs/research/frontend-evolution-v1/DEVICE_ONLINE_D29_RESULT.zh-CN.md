# D29 实际AEC、选择与过渡集成结果

日期2026-10-11；experiment=FE_DEVICE_ONLINE_D29；本地研究里程碑，总体目标仍active。
冻结合同见[PLAN](DEVICE_ONLINE_D29_PLAN.zh-CN.md)及[执行前范围澄清](DEVICE_ONLINE_D29_AMENDMENT.zh-CN.md)。
主测量decision=ONLINE_INTEGRATION_ENGINEERING_PASS_NO_PROMOTION；research_algorithm_changed=false、integration_changed=true、shipping_algorithm_changed=false。
promotion_allowed=false、shipping_approved=false。逐帧实际集成复现既有分段实验，不新增声学收益或产品默认资格。

## 身份与真实执行

local HEAD572b0e34a8a8e5663397ce16e378209ba9058d4d及既有dirty保留；冻结时live main373008e89f2ebaabc298d2c9613420b1d4811c78。
只链接原D18实际MDF库，SHA256=eb5b0c784c316e71d6ed9f58db6cb66f190b631daa00c55a94032168d5a47aa4，没有重编DSP库。
工件根`/tmp/audio-fe-device-online-d29-20261011`。
result SHA256=9ed85b81ee3487919b00cf441e84757c1fc7c72deb611cfdedf8c1944e0fa4ab。
binding SHA256=2120e2e139584972311fa2ac9a47b5984acf1159fb21d8234438846e49078520。
主execution回执`/tmp/audio-device-d29-execution.json` SHA256=7a692eaa762a36855a51ed1fc376fe9f774d63b024083487b91693cc13fd5f62，真实terminal exit0。
绑定651项生成工件；冻结源码、输入及runner起止hash相同。

44个原主来源（32设备development、12合成/oracle工程）各一次，加case07-used0的新进程repeat/future，共46次真实C回放。
双AEC指同一单路AEC-input及reference上的primary/shadow两套滤波状态，不是双麦逐路AEC或C2/C4整链。
online指本机每160点执行AEC→D27选择→D28过渡；上游AEC-input/reference和far/dt为冻结输入。
本轮未新执行BF/SYNC/Activity检测，也未执行NS/RES/AGC/KWS或AISpeech产品调用链。

| 实际统计 | 数值 | 口径 |
|---|---:|---|
| 帧数 | 126,486 | 46次执行累计 |
| 样本时刻 | 20,237,760 | 每帧160点 |
| primary调用 | 126,486 | 每帧一次 |
| shadow调用 | 44,564 | 仅通知后激活 |
| shadow完整reset | 30 | 每个有通知执行一次 |
| selector / transition调用 | 各126,486 | 使用实际bank能量与选择 |
| sync调用 | 0 | 上游未新执行 |
| 过渡混合样本时刻 | 88,640 | echo/residual共用alpha |
| 总切换事件 | 277 | 主矩阵251，repeat/future各13 |

8条音频共161,902,080个Float32：实际mic/reference、selected echo/residual及四bank。
另有primary state诊断、selector和transition三CSV；state.csv不是完整MDF内部状态转储。

## 集成等价与继承代价

全部46次四bank和primary诊断CSV逐byte等于原D26/D25来源，future对照原D26实际future。
44个正常主来源及repeat的selector逐byte复现D27，selected两音频和transition逐byte复现D28 fade。
主来源的原whole/固定窗/null资格、分数及事件诊断与D28全部精确相同；不增加裁判窗口或选择阈值。
实际能量按原顺序求和，固定50帧保持和320点过渡；没有输入旧选择control或复制旧输出代替AEC。
selected不反馈两套AEC；通知时复制primary再完整reset shadow，两套滤波状态独立演进。
全部音频finite、实际mic代数最大绝对误差2.2351741790771484e-08；所有过渡端点/过渡外值精确核验。
所有终态remaining=0，主事件censored=0。
repeat全部8音频和3CSV全量相同；future从通知帧1247开始将实际mic/reference取负，通知前11输出前缀相同。
future真实重新执行AEC/选择/过渡，按新bank独立核递推及实际mic代数；不评分、不参加候选，不证明所有可能输入的因果性。

原D28工程条件重新判断全部为true，主设备243事件、合成8事件；此轮没有新的声学改善。
设备事件residual差分平方和仍为hard15.245871150636518、fade12.983306823542838，合计下降约14.84%。
原55个事件增加仍保留，最大+0.07081278739013859（case08-used0、frame1979）；不能称全部事件改善或无点击。
原128个设备窗能量delta仍为-0.03529466576168261..+0.07466469566093892dB。
原108个合成known-near误差delta仍为0..+0.12601249578147744dB；不升级为真人保护或实际双讲检测通过。

## 资源与失败保留

真实sizeof：单AEC33,020B，两套66,040B，selector20B，transition16B，8个160点Float32帧缓冲5,120B。
合计71,196B，满足本轮局部128KiB预算；不含其它局部变量、stdio、库、总线程栈或进程开销。
两套AEC状态自身超过B0 50,000B arena；B0预算不改，本轮不能批准SSC305部署候选。
没有DUT CPU/RSS/完整栈/功耗/热或物理听感证据。

预编译第0次真实exit1：旧D26全局primary/shadow先可见，导致D27头同名参数触发-Wshadow。
仅调整新D29 C头包含顺序；不改原依赖、不削弱严格警告。第1次编译及集成自测真实exit0。
失败回执`/tmp/audio-device-d29-precheck-0.json` SHA256=d43355a892f20aa6af943dce10dc8315168960f1b3c759b8a73ce779e508fbbf，原writer/失败保留。
预编译retry1，主46次DSP重跑0，不能称整轮零失败。
主严格C11编译、自测及5个C参数拒绝符合合同；4个完整非法参数所有输出sentinel保持且primary/shadow调用0。
非仓cwd help/dry-run/4项输入契约测试均terminal exit0；dry-run未创建输出根。

## 独立实际审计

独立audit/六负例均首次执行真实terminal exit0、retry0；不导入新测量器，不执行C/AEC/selector。
独立核46case、368trace、161,902,080个Float32；三类CSV各126,486行、252,972个gate byte。
184个bank文件及46个primary诊断文件全量等价；正常44来源及repeat的四项离线等价共180文件全部相同。
独立复算476个窗口（本轮正常及repeat240、旧hard对照236）、1,133个有效channel及295个null。
236个delta及108个near delta、RMS/peak/delta误差均0；实际mic代数最大误差与主报告一致。
实际calls、277个事件及71,196B局部口径独立重算一致；repeat/future各13事件，原候选条件保持。
另从原D19 control.csv逐帧重建32个field gate，96,438帧与本轮gate文件精确一致，保留可复跑脚本和回执。
audit脚本/回执SHA256=5ec3ba746a76fe4edc7967cc09964b13e049556b106f7b2dee4ef0da94f1a6ce / 0770a9e594fdc1b3269d2cd5212a845d5b15765356c11ae5c44702cf53ff421f。
gates脚本/回执SHA256=a74c882ca1b02037dc147e0587cceff51b05d5aa0110df581ce7f3513abe470c / 87d4d18ae1bb562174c069ffad0a9f9f33c165f0e7fe3fa09ba0b8c1d2047599。
六次工具拒绝均exit2：missing/真实input分别指向旧D28、新D29及仓根。
旧D28的499文件与新D29的655文件完整manifest起止同；仓根只核工具可能写的measurement-invalid路径，0文件，不扩张为全dirty锁。
negative脚本/回执SHA256=a150c7d9c83a870f249575a4f84d6224e19713f3d668aa18d6c3c7248ea0d83d / be1ea089bd9ac8343c2d19f524a3cbf95e61f4894ca6dc842781eed8c11442b8。
源码、结果、失败记录及检查由review-snapshot-v1.json绑定；整轮独立fresh review及REVIEW后的复验另见[REVIEW](DEVICE_ONLINE_D29_REVIEW.zh-CN.md)。

## 资格与后续

Provider context仍route unresolved、current为空，知识线NEEDS_REVIEW；仓内仅reviewing candidate，没有正式归档成功声明。
无commit/push/PR/merge、发布或设备写；原D0-D28算法、库、工件及用户dirty保留。
接续真实近端/双讲检测闭环、完整前后处理链及资源整改；这些须另冻结合同，不能由此次等价集成批准。
独立声学数据角色、真人保护、AISpeech产品链、API/default、owner/E001/Product Qualification各自未闭合。
Runtime final仅闭合本地研究里程碑，总体native goal保持active。
