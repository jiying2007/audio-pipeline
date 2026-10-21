# D5验证环境与SYNC观测结果

日期：2026-10-10；状态：LOCAL_MECHANICAL_PASS / INDEPENDENT_REVIEW_PENDING。
依据：[D5冻结计划](DEVICE_CONTINUATION_D5_PLAN.zh-CN.md)；D4拒绝结果保持不变。
Provider route unresolved，本记录是reviewing候选，未声明正式归档。

## 验证阻塞闭环

原Git2.25.1失败保留。相同29项CI/Git测试在离线Docker Git2.47.3下全部通过；
容器镜像ID=sha256:1cf40b2fb45b01fd39960c34b7764a4d3dc360db6af0b4e379c70a871c1a07d0，
network=none，源码只读，uid/gid=1001，临时fixture进入tmpfs；未挂载HOME/凭据/设备。
曾使用镜像默认入口时要求/source而失败，随后显式python3入口和/source只读挂载复验；未借用失败结果。

临时Git2.43.0按冻结exact上游commit与archive hash构建，仅使用/tmp内git目标，没有make install。
NO_CURL/NO_OPENSSL/NO_GETTEXT/NO_TCLTK/NO_EXPAT/NO_PERL限制可选依赖；没有系统Git替换或产品引入。
Python3.10.20+此临时Git PATH下完整verify-docs-gate.sh退出0，**28个门禁命令全部执行通过**，
包括原29项Git fixture测试、新16项设备契约测试和主线A2入口。断言、阈值、超时及接受要求均未改。
gate日志=/tmp/audio-fe-device-sync-d5-20261010/docs-gate.json，
sha256=18f7555a13ddf5ad988f98ecea0762fda19eb3f0eccd660f7bd4160e83d27480。

可复跑环境（工具位置为本机临时工件，不是长期发布接口）：

```sh
rtk env PATH=/tmp/audio-fe-device-git-2430-20261010/git-564d0252ca632e0264ed670534a51d18a689ef5d:/home/leiwenjun/.local/share/uv/python/cpython-3.10.20-linux-x86_64-gnu/bin:/usr/bin:/bin bash .github/scripts/verify-docs-gate.sh
```

## main接入身份

按39a445d4c21d2f716e6602450a0bf944f248383b读取三份第一方A2文件，Git blob与API逐字节一致：
manifest=e2b041298a6bb492cbd42209eacd44459506878b；
parser=0e7baf21bc1ec370d9967e999c6b760e464bb0ce；
canonical doc=c3a2987d76992dce1171cfa86d47e3f8d58eca70。
共享gate保留设备契约测试并增加A2自测；本地HEAD与原dirty未重置、暂存或提交。
仅导入元数据代码/契约，没有RealMAN CSV/FLAC字节、DOA效果或shipping资格引入。

其后main前进至4ea71ff7bd2717c9d56cbfc06197f9958107d42e，compare核实仅新增D1 CSV研究文件/工作流
及共享docs gate；AP处理源码未改。最新Verify38027344338在该检查点queued，旧main成功不可代用。
不为追逐其它开放PR扩展本轮实验；未来整合需保留D1 gate入口并对精确head重新验证。

## D5测量等价与发现

临时原始AP源码仅增加SYNC候选观测stderr；不改变选择、三次确认、drift或AEC路径。
严格构建通过，14/14 CTest通过；原ap_drift_res_tests退出0。
实际rpm480/far-motion的default、tracked1、fixed1三臂PCM和metrics与D3 **逐字节相同**；
fixed1没有跟踪trace是预期空值，不能伪造观测。D3整批receipt复验仍通过（16例、70固定+2重复）。
观测result=/tmp/audio-fe-device-sync-d5-20261010/result.json，
sha256=78b1e39072559fb15a1e27c1ae250bf21be5c553366160b53dcf8d7dbad83d84。

| 观测 | 当前delay/候选delay，samples | best / runner-up | unique | 确认次数 |
| --- | --- | --- | ---: | ---: |
| 设备tracked1接受172ms前 | 47 / 2752 | 0.723276794 / 0.719648540 | 0 | 2 |
| 既有已知真实路径测试接受前 | 645 / 1284 | 1.000000600 / 0.999998093 | 0 | 2 |

设备事件render_total=306880，按本回放样本计约19.18秒，不能替代真实AO路径时间戳。
score略大于1是保留的浮点观测，未夹紧或修饰原结果。
这验证D4拒绝的原因：同一个短窗唯一性规则同时排除该误跳和既有真实路径切换。
不能凭unique=0判定物理路径真假，也不能把三次局部峰确认视作充分声学证据。
现阶段没有可晋升SYNC修复；下一候选必须另冻结多帧/更充分证据方案，同时验收真实恢复。

## 接续与审查边界

作者自审范围=working-tree本轮工具/manifest/中文说明/共享门禁，不审查其它开放PR；
review_mode=whole-diff，independence=author-self-review；机械检查通过不代替独立reviewer/owner签收。
源码/输入/配置/输出锁和失败保留已复查；无产品DSP/default/API/ABI更改，无SCM写或设备部署。
下一阶段须分别补独立审查、Provider项目路由、真实render时间轴、SSC305资源/生命周期，
以及未参与选型的近端/远端/双讲/运动录音与KWS/ASR；本批development不升级blind/validation。
