# 设备采集研究入口与回放

本入口落地 [实施契约](DEVICE_CAPTURE_IMPLEMENTATION.zh-CN.md)，复用已查看的PCR02设备数据，
用途固定为 **development/regression**。不能用于blind、独立声学验证或Product Certification。
历史 [D0–D2分析](DEVICE_CAPTURE_D0.zh-CN.md) 保留；D3使用新源码/实验/输出身份，不覆盖旧结果。

## 输入和权限

- `tools/codex_assets/device_capture.py` 独立验证app_audio_test schema-v2，不导入AISpeech源码/运行库。
- `device_replay.py` 只构建本仓第一方AP公共API与research-local运行器，不下载外部源码/权重。
- 输入只读；输出必须是源码和采集目录之外的新目录。失败保留 `failure.json` 和命令回执，成功结果
  先写 `receipt.partial.json`，全量回读后才发布 `receipt.json`。不得把partial/failure当成功。
- 命令超时、输出超量或启动失败先保存有界命令失败回执再传播错误；未知退出码为null。
  stdout/stderr保存总量最多1Mi字符，并记录原字符数及截断标志；该限制不表示子进程采集内存有界。
  修复与独立复审记录见 [D6](DEVICE_REVIEW_D6.zh-CN.md)。
- raw WAV/PCM不进入Git/知识正文；Git仅保存代码、冻结研究计划和逐文件hash锁。
- 旧80/100 WAV已锁定但不参与AEC回放；它们缺少通道/时轴/制品映射，不能静默选择参考声道。
- 运行器为Host测试工具；执行它需要本机Python3、CMake和C11编译器。Python测量不依赖NumPy。
  终端命令按本项目规则经rtk；子进程直接调用固定argv，不调用shell，不拼接用户命令字符串。

## 结构预检与dry-run

从仓库根目录：

```sh
rtk python3 -m tools.codex_assets.device_capture --root tests/audio --dry-run
rtk python3 -m tools.codex_assets.device_replay run --root tests/audio --output /tmp/ap-device-d3-run01 --dry-run
```

两条命令都校验全量119文件哈希、16轮精确集合、WAV/seq/offset/PTS/epoch、正式窗口及参考关系；
第二条同时给出固定执行集与build命令，不创建目录或运行算法。输入/工具错误退出2，不输出成功receipt。

从其它cwd：使用这两个Python文件的绝对路径执行 `--help`、`--root <绝对采集路径> --dry-run`。
工具不以当前cwd推断源码根或数据身份；`--plan`只接收仍符合冻结D3权威的计划，不接受任意调参。

## 固定运行与复验

```sh
rtk python3 -m tools.codex_assets.device_replay run --root tests/audio --output /tmp/ap-device-d3-run01
rtk python3 -m tools.codex_assets.device_replay verify --root tests/audio --receipt /tmp/ap-device-d3-run01/receipt.json
rtk python3 tests/validation/frontend_evolution/test_device_capture.py
```

重新完整运行必须选一个不存在的新目录。每次先固定源码/measurement/输入角色，不能覆盖先前失败来洗绿。
源码变化会使旧receipt无法通过“与当前源码相同”的复验；保留其source lock并用相应源码快照恢复，
不能改旧receipt哈希让它看起来属于新版本。

`receipt.json`绑定：研究计划与输入锁；第一方源码逐文件hash；库、运行器、build-info、CMake cache；
每个实际生效配置；每例实际适配的mic/render、输出和metrics、样本数、0退出码、原始输入hash、显式尾部处理。
复验重新读取PCM/metrics和捕获PTS，重新计算诊断窗口，并检查重复/默认/零参考控制。
`RECEIPT_CONTRACT_PASS`表示这些证据一致，不表示音质提高或声学资格通过。

## 帧、参考与配置

stage0为128点双麦/双参考，stage1为256点实际参考/输出。先配对，再截取完整160点AP帧；
记录raw未配对尾部和AP重组尾部，不补静音、不重采样、不重排麦克风、不改原文件。
AP使用raw参考第0路；`ref_used`只作逐点校验，避免重复施加20点预处理延迟。
物理左右麦位置与render时间戳仍需现场记录，不能由两路PCM或input PTS推导。

D3总共70个固定执行，另2个首例重复控制：

| 对照 | 次数 | 作用 |
| --- | ---: | --- |
| 每轮default/BF-isolated | 32 | 不改算法基线与输入路径控制 |
| 四远端sync-default-control/tracked1/fixed1 | 12 | 复现D1及默认逐点控制 |
| 四双讲tracked1/fixed1 | 8 | 开发诊断，不能凭输出能量选候选 |
| 两quiet fixed1 | 2 | 零参考逐点控制 |
| 两quiet、两motion的AGC/NS隔离 | 8 | 复现D2，输出噪声诊断 |
| 八远端/双讲tracked1-no-drift | 8 | 保持延迟跟踪、单独关闭漂移补偿 |

1ms为D1观察本批数据后的开发诊断假设，不是预先独立确认的产品最优延迟。
default→tracked1只改变启动延迟；tracked1→tracked1-no-drift只改变漂移补偿；
tracked1-no-drift→fixed1只改变延迟跟踪，按这个顺序解释配置因果。
所有AEC/RES/NS/AGC系数、产品默认和公共ABI不改。

## 诊断与声学边界

报告输出总RMS、rail、实际配置、内部delay/reset/slip计数及VAD-active占比，
窗口为预声明的4–6、10–12、19–21秒，按scene_start/捕获PTS映射，并补偿AP报告算法延迟。
它们是计划窗口，不是假定的真人语音标签。输出较小可能来自回声/噪声衰减或近端语音损失。
内部erle_valid和erle_db保留在原始metrics，不升级为标定ERLE。正式音质评价仍使用
`validation/tools` 与 `validation/authority.json`，本入口没有另建SI-SDR/MOS/KWS裁判。

后续先复核SYNC路径、NS→AGC→VAD保护和实测RPM关联，再冻结候选并补独立近端/房间/说话人录音、
人工听评和KWS/ASR。四麦、shipping模型许可、SSC305资源、真实HIL/72h和E001身份单独验收。
Provider路由未解决时只保留REVIEWING候选；本地receipt不等于正式归档回执。

本批已执行结果、回执身份和未闭环事项见 [D3本地结果](DEVICE_CAPTURE_D3.zh-CN.md)。
