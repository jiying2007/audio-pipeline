# 设备采集D3本地落地与验收记录

日期：2026-10-10；状态：**LOCAL_IMPLEMENTED / NEEDS_REVIEW**。
实施依据：[冻结契约](DEVICE_CAPTURE_IMPLEMENTATION.zh-CN.md)；操作：[回放入口](DEVICE_CAPTURE_REPLAY.zh-CN.md)。
本记录为本地可审查研究结果，不是Provider归档成功、独立owner签收或产品放行。

## 落地产出

独立schema-v2预检、固定输入hash锁、显式256→160点适配、8种配置的公共AP研究运行器、
70个固定执行和2个重复控制、有限metrics/PTS窗口回读、逐例实际适配输入和输出绑定已落地。
工具完全不依赖AISpeech工作树、NumPy或子进程中的rtk；终端仍按项目规则经rtk执行。
已有docs gate和Verify语法检查纳入新工具；ci_impact仅将三份明确登记的研究工具列为release-neutral，
未登记backend仍须原有release判断。未改产品DSP/default/API/ABI、版本、E001或历史FE计划结果。

本地源码基线为 `572b0e34a8a8e5663397ce16e378209ba9058d4d`。
Verify `37946999926`、Release `37950522652` 成功只证明该基线；不证明本地未提交改动的托管CI。
最终复读发现PR #692已合并，live main前进到 `4395782b9b7e7c352bff56e1c240e3751465d59e`。
GitHub compare核实只改 `.github/workflows/quality.yml` 和 `DOA_GCCPHAT_A1.md`，
与本轮范围及AP回放source lock不重叠；不自动更新检出分支或重写实验基线。
该新main Verify `38006524852` 仍in_progress；不得延用旧基线成功状态认定新main通过。

## 本地证据

最终输出目录：`.cache/audio-fe-device-formal-20261010-final`（仓库已忽略）。
原始执行路径为 `/tmp/audio-fe-device-formal-20261010-final`；系统盘满后原样移动到上述位置，
receipt和相对路径绑定保持原字节，重新回读验证；构建日志中的原始绝对路径保留为历史身份。
最终receipt SHA-256：`068786d028aac2565592ada0a5eabcaca8ba59db0bf33725a5b1e2a061b3ab32`。
计划SHA-256：`41169d94d256aa42a5992ea0758fad6c747fa52e4750a20a6f4fc0f64b4860d9`。
输入锁SHA-256：`c63b37feff15d7eac6932c92c1ddaa99a1a6efa5d338feb0c2ec2d28443fa285`。
这些本机工件位置不是耐久归档契约；恢复需原始数据、source lock和对应源码快照。

| 验证项 | 新鲜结果 | 边界 |
| --- | --- | --- |
| 119文件锁、16轮schema/frame/PTS/ref校验 | 通过 | 音量80，development数据 |
| 70固定执行+2重复、回执回读 | 通过 | 仅Host现有AP诊断 |
| 与历史62个PCM逐点对照 | 62/62相同 | 保留D0–D2，不重写历史结果 |
| 新采集/运行器契约测试 | 16/16通过 | 含真实Host C运行器的EOF负例 |
| 完整实际receipt的负例 | 6/6拒绝 | promotion、缺例、缺配置、bool退出码、输出/适配输入hash篡改 |
| Host严格CMake构建/CTest | 14/14通过 | GCC 9.4.0，无目标板证据 |
| Host ASAN+UBSAN CTest | 14/14通过 | 不替代板级稳定性 |
| ASAN+UBSAN研究运行器真实far-motion回放 | 退出0，无报告 | 单轮Host，未扩称完整72次sanitizer通过 |
| docs gate按命令独立取证 | 26/27命令通过 | 完整gate仍失败，详见下文 |
| 非仓库cwd绝对路径help/dry-run | 通过 | dry-run不创建目录或运行处理器 |
| git diff --check | 通过 | 未自动暂存、提交、推送 |

完整receipt负例先严格加载一次真实输入，再复用已验证的不可变capture对象，逐次实际回读工件；
未伪造runner/DUT/数据可用性。失败变体另存文件，未修改成功receipt和原始PCM。
本轮首个成功版本还保留在 `/tmp/audio-fe-device-formal-20261009`；后续增加适配输入绑定并消除
CI对子进程rtk的依赖后，重新完整执行最终版本，没有修改旧receipt来匹配新源码。

## 新增对照结论

新增8个tracked1-no-drift只关闭drift compensation，保留delay tracking，构成单因果对照。
在4–6秒窗口，其输出RMS比tracked1高约3.15–6.17 dB；这只说明该诊断窗口的输出能量变化。
rpm480/far-motion在tracked1与tracked1-no-drift两臂都出现172ms估计值，
因此关闭漂移补偿不能消除该大跳变，也不能把漂移补偿单独认定为根因。
其余关闭漂移补偿的场景估计集合还可扩展至约9–13ms，不能将该开关据此推广到shipping。

D0–D2已有四个远端场景在fixed1下的早期输出相对默认更低约9.25–10.46dB。
但本批无独立clean near target和真人活动标注，总能量下降同时可能包括近端损伤，
不能宣称ERLE提高、双讲通过、KWS误唤醒改善或固定1ms最优。

## 仍需闭环的具体事项

1. **本机全量门禁**：系统Python3.8在既有Path.is_relative_to测试失败；使用现有Python3.10重跑后，
   唯一剩余失败为 `test_fixture_commit_does_not_spawn_maintenance`。
   Git2.25.1在临时测试仓提交时启动 `git gc --auto` 子进程；fixture虽配置gc.auto=0，
   既有测试要求没有maintenance/gc子进程，因而拒绝。未跳过测试或调整断言。
   用符合项目托管环境的较新Git完整复跑，或独立提出兼容性修复并验收；目前不声称full gate PASS。
2. **独立审查**：作者已检查输入拒绝、配置单因果、数据角色、输出长度、source lock、CI依赖和失败保留；
   未取得独立reviewer/owner签收，状态保持NEEDS_REVIEW；不能把自审或receipt回读当独立review。
3. **Provider归档**：context adapter实际返回repo_route=null、route_selection.status=unresolved，
   不使用返回的其它项目fallback建立当前项目归属。仓内本记录为可审查候选，未宣称正式已归档。
   系统盘随后达到普通用户可用空间0；迁移本轮最终回放工件约172MB仍不足以恢复系统盘写入。
   文档一致性改用工作区TMPDIR重新通过；未清理其它会话或用户数据。Runtime final实际执行返回
   `[FATAL] unable to read active Codex thread`，不能声明本轮Runtime conformance通过。
4. **设备集成与资源**：将source/config/binary identity和真实render PTS/sequence/gap绑定，再验证SSC305
   AP适配、实时预算/内存、profile生命周期、参考路径重开及输入连续性；当前只完成Host研究入口。
5. **独立声学数据**：另采未参与选择的房间/说话人/音量80与100/静止及rpm240、480；保存mic物理位置、
   同时钟render timestamp、实际执行制品、人工近端/远端/双讲标注。先冻结候选再盲评，
   分开验收回声、近端保真、噪声与KWS/ASR，不用当前development集合自选自证。

下一步算法调查优先SYNC大延迟跳变的confidence/hysteresis和参考连续性，随后独立考察NS→AGC→VAD；
每次冻结一项因果变更、保留失败并复跑当前入口。四麦/训练、第三方权利、shipping及E001/HIL/72h资格
继续沿各自授权和验证线推进。本轮未生成或安装产品候选，也未对远端SCM作写操作。
