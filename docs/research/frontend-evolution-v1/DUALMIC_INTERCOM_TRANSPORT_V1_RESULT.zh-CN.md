# 双麦对讲传输 V1：本地软件集成结果

日期：2026-11-06（Asia/Shanghai）。结论：`HOST_INTEGRATION_COMPLETE`，仅对实际
执行提交 `dbbbe7ecff03f0a98920cf8317f979470bcd86b4` 成立；受保护 PR/main
须取得自己的源码/门禁与产物。算法版本仍是2.3.63，无 DSP、公共 API、Runtime
行为、默认 tuning、资源上限或版本修改。

依据[冻结合同](DUALMIC_INTERCOM_TRANSPORT_V1_PLAN.zh-CN.md)，已实际执行 libopus
及原 Linux worker：远端编码 → 固定到达日程 → 有界抖动队列 → 解码/PLC →
播放音量 → 同字节 Render → 合成双麦捕获 → CALL worker → 上行编码/解码。
这是实际软件组件与显式模拟网络的有限集成；没有真实设备、UDP/WAN或真人听评。
机器摘要见 [receipt.json](evidence/dualmic-intercom-v1/receipt.json)。

## 实际覆盖

八场景各608个10ms Runtime帧，逐一与同源码、同输入、同通知的同步 public API
执行比较，输出 PCM、逐帧 trace 与 consumed-render 均逐字节相同。另有normal
完整重复及固定不同未来后缀控制。因此正式矩阵共处理6080个Runtime帧、4864个
同步对照帧；不是6080个独立声学样本。

| 场景 | 每方向 PLC 包 | 每方向重复包 | 每方向迟到包 | Runtime discontinuity / render gap |
|---|---:|---:|---:|---|
| normal | 0 | 0 | 0 | 0 / 0 |
| reorder | 0 | 0 | 0 | 0 / 0 |
| duplicate | 0 | 1 | 0 | 0 / 0 |
| single-loss | 1 | 0 | 0 | 0 / 0 |
| burst-loss | 2 | 0 | 0 | 0 / 0 |
| late | 1 | 0 | 1 | 0 / 0 |
| gain-mute | 0 | 0 | 0 | 0 / 0 |
| reopen | 0 | 0 | 0 | 1 / 2 |

每场景下行300包、上行304包；每包实测60字节（20ms/24kbit/s/CBR）。播放队列
高水位均为3、固定容量6。每条下行播放97280样点/608帧，上行远端播放98560
样点/616帧。启动缓冲保留在产物中，没有靠裁掉静音缩短报告时延。

全部实际Runtime执行的input-full、failed-frame、output-drop、render-push和
capture-process失败均为0；所有帧FULL。网络PLC仍是PRESENT Render，没有把
包损失伪造为硬件XRUN。音量/mute后的播放轨与实际提交render实参回写文件完整
相同，两个实际错误参考（音量前、PLC前）均被独立字节绑定检查拒绝。不同未来
后缀的冻结前缀、重复执行的PCM/payload/非时间trace也全部相同。

**诊断队列并非零丢失。** 原Runtime的event queue深度为2，实际
`event_drop_events`在其余场景/两个控制中为1，reopen为3；`output_drop_events`
仍为0。当前源码仅在事件队列满时递增该计数，但本记录没有保留逐个丢失事件的
身份，不能推断它是哪一事件。保留这项限制，不修改生产队列/阈值消除计数，也
不声称完整事件日志无损。

## 实际配置、时间与来源

首次审查指出请求配置曾被误称有效配置，已按
[执行前修正记录](DUALMIC_INTERCOM_TRANSPORT_V1_IDENTITY_CORRECTION.zh-CN.md)
改为真实初始化后调用`ap_pipeline_get_config()`和`ap_pipeline_get_tuning()`。
修正执行实际回读CALL：tail96ms、mu0.219999999、NS floor0.119999997、AGC -20dBFS、
limiter -2dBFS；两份回读一致，tuning mask15。原e7f执行全部原件保留；与新执行的
输入、输出、压缩payload及trace逐字节相同，身份字段修正没有变更DSP结果。

实际host构建为GNU14.2.0/x86_64-linux-gnu/Release/SCALAR/MDF/EMA/BANDLIMITED，
fast-math=0。实际libopus1.5.2，加载实体SHA256
`621e97f23655dbf2727873b7717e3b65ae8c734f84a0848f88c21edb95202357`；查询到
lookahead104样点/6.5ms。采样和队列参数来自原合同，不是搜索所得最优组合。

| 阶段 | 实际耗时 | 原预算 |
|---|---:|---:|
| 新源码独立构建与C适配链接 | 2.726928s | 300s |
| 12项测试，normal及Python -O各一次 | 合计0.559961s | 300s |
| 正式矩阵及两控制，含进程结束与日志封存 | 9.804972s | 300s |
| 作者原件回读（296文件/6040包等6448检查） | 0.117161s | 300s |

报告内部记录9.684650506s，截止报告生成前；外层9.804972196s包含产物生成、
子进程结束及日志写入，二者不混用。这里的host执行耗时不是实时吞吐/真机性能。

时延只列组件：包收集最长20ms，准备后模拟缓冲60ms，首包模拟播放起点80ms，
实测Opus附加延迟6.5ms，原前端报告算法延迟10ms。没有把这些相加包装成实测
口到耳时延。有限fixture在输入结束后不追加codec flush；末尾lookahead对应的
内容没有继续输出，这与“每次调用/播放slot样本完整”分开披露，不能称为任意
通话结束的无损尾音交付。

主报告SHA256为
`5715a8930e047b4c4ff0666acda36b0fbb0fdc40edac5bc378358b645fc11192`，
296文件manifest SHA256为
`ec7599525faec15e227bb44a17ae1a9b631f17561acea52c43311b3283609c6c`。
小摘要记录源/库/bridge身份、各计数、阶段原件hash和原错误身份结果。大PCM与
payload保留在执行产物，不进入Git；后续CI需重新产生自己的完整产物。

## 可复现入口

用当前checkout的CMake构建原库和`ap_process_pcm`，再链接薄适配器；`BUILD`指
同一次配置生成的实际目录，不混用其他源码的库。无需把Opus链接进生产SDK。

```sh
cc -std=c11 -O2 -Wall -Wextra -Werror -I BUILD/generated -I include \
  tests/validation/frontend_evolution/dualmic_intercom_runtime.c \
  BUILD/libaudio_pipeline_runtime.a BUILD/libaudio_pipeline.a \
  -pthread -lm -o BUILD/dualmic_intercom_runtime
python3 tests/validation/frontend_evolution/test_dualmic_intercom_transport.py \
  --bridge BUILD/dualmic_intercom_runtime -v
python3 tests/validation/frontend_evolution/dualmic_intercom_transport.py \
  --bridge BUILD/dualmic_intercom_runtime --source-revision EXACT_COMMIT \
  --output NEW_EMPTY_RESULT_PATH
```

缺实际libopus、配置回读/源码身份不符、codec错误、截断PCM、错误Render、
不完整frame/packet/trace或超出预算均非成功。`--output`必须是新路径，失败
不得覆盖。实验不生成声学优胜、MOS、KWS/ASR或设备CPU结论；
quality_decision保持`NOT_EVALUATED`，promotion_allowed=false。
