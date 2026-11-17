# D6 帧内增益过渡：实施说明

状态：IMPLEMENTATION / NOT_RUN。冻结合同
[DUALMIC_GAIN_RAMP_D6_PLAN.zh-CN.md](DUALMIC_GAIN_RAMP_D6_PLAN.zh-CN.md)
与[完整输入锁](dualmic-gain-ramp-d6-input-lock.json)保持原字节；
冻结提交 caaed2efa09243b99064c8ee793d3c27591ab6df。
实时追踪 [#942](https://github.com/jiying2007/audio-pipeline/issues/942)。

## 实现和算术

研究构建从已准入原D2 source archive取C/header，baseline链接封存原库；
五个精确源码替换点只增加隔离接口/extra观测并替换最终输出循环，
原target gate、alpha、state update均未修改。候选导出使用d6前缀，
extra state独立为8字节，原AGC state仍12字节，生产src/API/default/版本不变。

当前G是原更新后的state gain经过原unity/peak条件后的系数。
首次/原reset使extra P=+0、initialized=0，本帧S=G；其他帧S=当前cap(P)。
Float32次序为delta=G-S、weight=(i+1)/160、product=delta*weight、
interpolated=S+product；i159明确用G。每个系数重复原cap后记录，
再执行原Float32乘法与sample clamp，最后保存实际coefficient159。
不使用累加斜坡、不改变target、不合并D3/D5、不添加下一帧依赖。

C硬查IEEE binary32、FLT_EVAL_METHOD=0、FE_TONEAREST和结构大小。
编译固定C11/O2/ffp-contract=off/Wall/Wextra/Werror、AGC定义、
原头及库、libm，记录cc selector/解析目标/hash/version/完整argv。
证据文件仍拒绝symlink，不将compiler selector例外扩展为证据例外。
当前compiler不是旧compiler的承诺；baseline不复现则测量失败。

## 实际字节和独立读回

每帧84字节trace包含四份完整state共48字节、
extra before/after共16、实际S/G共8、allow/reset/zero共12。
candidate-gain.f32le保存全部5746560个实际乘法系数，非仅公式重建。
baseline state/PCM必须逐字节等于原D2；
candidate原12-byte state每帧也必须等于baseline。

Python只读逐操作Float32重建全部系数/输出及cap/clamp，
核验S、G、P连续性、端点G、首帧/reset/常数G中性。
target/alpha等重建值明确标注，不冒称直接内部观察。
near-only/silent-render现在也可能改变PCM，不能沿用D5的allow=true中性要求。

原60视图/362窗由未改canonical scorer完整评分，
baseline端点/分数与原D2核对，保留所有level/peak/null和中文风险。
measurement_valid和development_screen分离：
有效负结果为NO_ADVANCE；满足全部冻结屏障为
DEVELOPMENT_SCREEN_PASS_NO_PROMOTION，仍不是实质质量/听感/ASR证明。
原rms_dbfs的1e-12 floor保持，不把其无上升当作floor以下raw energy证据。

## 绑定、自测和负例

完整锁内60例原输入对象、23个依赖的blob/bytes/SHA256、
原准入、C/header/library、生产树对象均核验。
原admission回执逐项检查experiment、3551成员、861385743解包字节、
promotion_allowed=false及原elapsed_scope完整口径；工程负例分别拒绝篡改和缺失字段。
运行时仓库内导入模块必须包含在封存闭包；
源及输出文件/目录集合、HEAD/tree、真实compiler和命令都读回核对。
源上限16MiB，result上限256MiB；重封存不能绕过源码或候选派生一致性。

Python控制包含确定性派生、原state/中性/动态算术、peak guard、
NaN/Inf/extra初始化位、硬timeout、五项最保守屏障、原输出不可覆盖、
source/空目录/symlink和compiler selector身份。
C控制覆盖两profile、五个state初值、十个输入level、五个前系数、
初始/连续/常数G、rising/falling与reset/gate变换。
这些都是工程测试，不是新增声学候选或质量样本。

40类实际负例先完整读回未改合格原件，再逐项复制并篡改。
每项冻结专属reason，I/O、timeout、任意其它异常不能冒充预期拒绝。
包含实际系数及端点、P/initialized/S/G、state/PCM、controls、
target/alpha、错窗/漏case/null、screen决策/谓词、source/tree/argv、
重封存源/header、额外文件/目录/symlink、失败回执和原输入绑定。

## CI与预算

只在现有Frontend Research加scoped D6 job，D6-only时历史D1/D3/D4/D5
job区域逐字节保持且不选择它们；旧研究源码与合同不改。
每阶段300秒，包含最终写盘；子进程参数明确min(30,剩余阶段时间)，job20分钟。
原冻结dualmic_stages_source.remaining本身已经把返回值限制到30秒，
所以D5旧实现也已有硬上限；D6显式min是可见的同一约束，不是修复历史缺陷。

实际调用顺序：原工程控制、原D2准入、build、run、analysis、verify、40项negative。
所有产物在/tmp/ap-dualmic-d6，首次成功/失败及完整结果始终上传，
原artifact来源独立保留。不得覆盖旧回执、失败后调预算或静默改门槛。
本提交仅是未执行实现，待独立精确head审查后才打开PR触发CI。
没有新模型、私有数据、付费/Codex/ChatGPT Work资源或真机执行。
