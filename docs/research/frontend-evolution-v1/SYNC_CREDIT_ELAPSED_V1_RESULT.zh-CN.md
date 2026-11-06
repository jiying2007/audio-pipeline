# SYNC credit 有效观测时基修复：结果 V1

**唯一候选通过默认63/63与真实composition-tiny 33/33原CTest；原漂移断言未改。**
生产修改仅让有效相邻观测的credit使用与ppm相同的capture elapsed。正常100ms
保留原乘除顺序；无有效basis保留旧nominal100ms，未回填失效/未知区间。
EMA/clamp、误差反馈、四次slip限额、插值、route和生命周期失效点均未改。
没有新增驻留状态或逐帧演化，未修改CMake、版本或公共API；后继版本/源准入另行整合。

## 精确身份

- 被修复实际merge：`5728a4f1b43d9d66f6cea8467ac3443efe14297e`。
- 先冻结合同：`86c96af3fb8754eb7451f8bca2f83c3d003493f9`。
- 唯一源码/测试提交：`a64090d73dd4206fffc9f1f69d7f139e9c158996`。
- 原 `tests/test_drift_res.c` 在前后SHA-256均为
  `b2018a9dee2843347f45986f90db9d1043a648ab49601011d34b7040feb44b58`。

## 真实执行结果

| 检查 | Before | After |
| --- | --- | --- |
| 原tiny漂移fixture | merge5728原测试SIGABRT，line66 | 原测试通过，包含后续route/negative-drift阶段 |
| 新credit直接回归默认16k | exit1，0.4s负向slips0、credit -0.992500007 | PASS |
| 同一新回归旧tiny8k库 | exit1，同样未跨过slip | PASS |
| 默认完整CTest | 本轮不重跑旧完整集 | 63/63，exit0 |
| 实际composition-tiny完整CTest | 原失败另存 | 33/33，exit0 |
| 8/16k observation及内部边界 | 原有测试保留 | 默认8/16k、tiny8k均通过 |
| opaque SYNC模块尺寸 | 默认32840B、tiny8264B | 相同，新增0B |

24个正负/拒绝类型/时间间隔直接案例使用真实相关搜索。它们从credit ±0.98
出发，单样点innovation经0.05 EMA在0.4/1.0/1.3s都贡献0.05样点积分，跨过
一个slip并保留约±0.03。另检查大credit的四次slip上限、tracking/drift-disabled
首basis的nominal100ms，以及非递增counter重建；原reset/timestamp/rate/route测试未删。

## 正常100ms兼容性

对相同扩展测试，在旧/新源码执行时逐帧记录完整opaque SYNC模块和reference字节：

| 构建 | 实际比较字节数 | 旧/新共同SHA-256 |
| --- | ---: | --- |
| 默认，含16k及8k | 7,330,400 | `3d9f23b2648a39f59095f3331b86807641cf5293d305867bde94601d882406de` |
| 真实tiny，仅8k | 944,240 | `e72904442075bb964a5371ca86f8fee83ad30ed46be7477286de950e1e548099` |

两项均逐字节相同，可读ppm/delay/slip轨迹也逐字节相同。这是冻结正常节拍
轨迹的状态/reference兼容性，不是全语料声学等价声明。共同二进制原字节保留在
证据压缩容器，未仅留下哈希。

## 失败保留、命令与预算

[证据入口](evidence/sync-credit-elapsed-v1/README.md) 保存70个原始成员及逐成员
哈希，包括前置诊断、before失败、after日志、完整原始命令数组与正常节拍字节。
另外保留原Verify 42186062706、job127787874362完整日志文本及source/run身份。
旧诊断中1.412581488608的elapsed积分只是当时的算术推断；本轮以上after结果
来自真正执行的唯一候选，二者没有混写。

默认使用Release、bench OFF、strict warnings ON；tiny使用原composition-tiny
preset。每次build/test设300秒上限，并受剩余600秒总预算约束。配置、完整构建、
CTest、定向观察和正常轨迹的每条真实命令/退出码/耗时在execution JSON中。
Before默认使用扩展测试加旧credit源码（测试改动导致自动build标记dirty）；
其生产SYNC字节与merge5728相同。Before tiny将同一扩展测试链接精确merge5728
原tiny库。After构建均来自干净a64090d源码提交。

执行起点为2026-11-06 08:26:58 UTC。证据准备完成时间为 2026-11-06T08:37:02.192941+00:00，累计 604.192941 秒；
**整体600秒预算失败：证据准备累计604.192941秒，超过4.192941秒。**
证据提交 `85f998b984fa4147c24f7122be750318da432fd4` 的Git时间为
2026-11-06 08:37:02 UTC，同样晚于08:36:58截止；配置、构建和测试各命令均在
各自300秒限额内。此次完成回执仅更正旧版结果正文误写的“总预算通过”；
summary.json原有false判定、604.192941秒原始计时和全部原日志均保留不变。
回执核对时整体预算仍失败，不将后续封存时间排除或重定义起点。
本地软件回归不替代后继版本的精确CI、真实播放设备、KWS FAR/FRR或真人对讲评价。
