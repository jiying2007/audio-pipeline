# 当前 AP 可搬移工程包：源码身份、双麦帧与宿主复验

## 目的与状态

`FE-AP-CURRENT-PORTABLE-V1` 为另立的 F05 新八说话人、32 句、
128 例双麦整链研究保全实际处理器。冻结合同是
[`ap-current-portable-v1.json`](../../../.github/research/frontend-evolution-v1/ap-current-portable-v1.json)。
本入口只构建当前公开科研源码的 `ap_process_pcm` 与 `ap_build_info_dump`，
执行有限合成工程检查；不消费新真实语音、不选择算法、参数或延迟，
不产生声学通过、模型晋级、设备测量或产品认证。

方法发布并通过工程 CI 前，实际构建状态为 **NOT_RUN**。随后以实际
`ci-receipt.json`、`bundle.json` 和工程报告为准，不把本文或离线 tiny
测试当作真实二进制执行证据。真实 F05 128 例必须另按其公开冻结合同执行。

## 源码身份与编译边界

构建入口要求显式 40 位 `--expected-head`，必须等于干净 checkout 的
实际公开科研 commit。两 ELF 内的 `source_revision` 必须等于它。
**不能将科研分支构建说成 main 构建**：另以 59 个精确文件的 SHA256
证明 DSP、头文件、CMake、构建模板及两个 CLI 源码仍与
`4eec2329be9f2138c7ac73e8dd59026f3dc0a3ba` 的原字节相同。
源码快照共 349,879 B；原 `LICENSE` 同包保存。

仅在 Actions Ubuntu 24.04 / x86_64 使用既有 GNU C、CMake、Make。
没有本地编译、依赖安装或网络取件。Release、严格警告、scalar、
MDF / EMA / bandlimited、完整模块、双麦及资源上限逐项写入合同。
保留实际工具路径、版本与字节 SHA、目标 triple、CMake cache、
编译命令、生成头、链接命令、静态库与两 ELF。禁用 fast-math；
不设置 `AP_BUILD_SOURCE_REVISION` 覆盖值。

两程序静态链接本项目库，系统 `libc/libm/loader` 不重分发。
使用现有、原字节不变的 `webrtc_aec3_ci.runtime_identity` 观察实际动态
依赖，记录 SONAME、解析路径、SHA 和 OS/kernel/machine；可获得的系统
包 copyright 文件单独保存。源码闭包包括实际加载的 AP helper、tiny
测试、合同、workflow、AEC3 observer/source helper 与 contracts。

拷贝两 ELF 后，先改名原 build 目录；拒绝绝对 RPATH/RUNPATH 和仍指向
原源码/build 的动态依赖，然后从 bundle 跑全部合成检查。后续搬移验证
使用原命令记录中的目录解释历史路径，不要求本机目录与 CI 一致。

## 预编译原 canonical 相关性数学库

F05 secondary 的原 `render_corr_exact._load_native` 在冷进程内会自动调用
C 编译器。这个既有行为与本次“仅 Actions 编译”的执行合同冲突，因此
本包另保全 **原样** `validation/tools/render_corr_exact.c` 生成的
`lib/librender_corr_exact.so`。原 C、原 Python loader 和原
`run_validation_engine.normalized_corr` 所在文件分别精确锁定；不改原
loader/engine，不将研究数学库计入 59 个 main DSP 文件，也不链接进产品运行时。

同一实际 GNU 编译器使用原 Linux loader 的完整 flags：
`-O3 -std=c11 -Wall -Wextra -Werror -fno-fast-math -ffp-contract=off -fPIC -shared`，
接原 C 路径、`-lm -o` 和输出路径。单独 helper 编译最多 30 s，和 AP
CMake 编译**共享原 240 s 阶段**，总 600 s 不扩。保全原源码、实际编译命令、
日志、库 SHA、ELF、实际依赖与 compiler 标识。库只在 Actions 构建。

工程在同一原 60 s 预算内增加 4 个有限数学检查：不等长输入的 `+17/-17`
样点延迟、零能量、有效重叠少于 64 样点；向量最多 320 样点、16 kHz。
每例调用原 `find_best_lag` 与原 `exact_score` 各一次，共 **8 次 native
数学函数调用**。原 exact-score 路径仍使用原 `normalized_corr(stride=4)`
重算最终值，保留原 `1e-10` 一致性拒绝。四例的 Python 全 lag oracle
各固定 3201 个 lag，仅用于这组短合成检查，不能用于真实语音、候选搜索或
改动原科学计分。数学检查与 **42 次 AP 音频调用、4 次 AP metadata 查询**
分别记录，不产生新声学通过。

显式 `bind_render_corr_native` 在原 `_NATIVE_LOCK` 中只接收初始
`_NATIVE_STATE=None`、`_NATIVE_TEMP=None`，或本 binder 已拥有的同一
state/CDLL/function/路径/字节身份。任何自动编译缓存、被清除/替换的状态
都会拒绝；不能仅凭状态字典自报 SHA 接收另一个函数。
`build_bound_max_abs_corr` 返回 guarded callable：每次原 `exact_score`
前后核对状态、源码、库和真实加载依赖，不能落回冷 loader 编译。
原锁是非重入锁，guard 内不再调用公开 bind。

CDLL 在 Python 父进程加载，清理子进程环境不够。装载前同时检查当前环境
和 `/proc/self/environ` 保存的启动环境，拒绝 `LD_PRELOAD/LD_AUDIT/LD_LIBRARY_PATH`
污染；不能运行中删除变量后宣称已清除预载库。要求 fresh clean Linux Python。
实际加载后对照 `/proc/self/maps` 与 ldd 的路径、设备、inode、SHA，完整保全
helper 与依赖。三项 ELF 的依赖均纳入工程 `runtime_identity` 首尾检查。

纯 `verify_bundle/verify_engineering` 不装载库；它们用原 Python normalized-corr
复核四个短 oracle 和已封存的数学记录。F05 独立读回可**显式**加载已封存
数学库重算原 canonical secondary，仍为 0 编译、0 SDK 处理器、0 decoder。
`render_corr_runtime_identity` 只做本次宿主/加载库观察，不隐式重做 42 次
AP 工程；读者宿主与原测量宿主分别记录。`verify_render_corr_runtime` 是共享
纯 metadata 校验，要求已保存 mappings 恰好覆盖全部 ldd 依赖及一个 helper，
逐项核 SHA/设备/inode，不要求旧绝对路径在读者机器上存在。

## 固定工程检查及延迟含义

固定 `call/assistant` × `capture-only/full-zero-render` 四组，16 kHz、
S16LE、双麦交错输入、160 样点/10 ms 帧、单声道输出。
42 次实际音频调用共请求 **3.7404375 s** 名义双麦 capture 输入；上限
48 次、5 s。每组保全零信号、固定冲激、固定双通道序列、重复序列、
8 帧前缀、前缀相同而未来不同的 20 帧序列、空输入，以及截断帧、奇数字节、
不完整双麦组负例。另有非法 profile/通道数负例。

检查实际退出码、有效负例前缀、严格尾帧拒绝、输出确切字节数、完整连续
frame trace、finite 字段、重复字节一致、前缀连续性与未来输入不影响
已完成前缀。保留所有命令、起算时长、stdout/stderr、输入、输出和 trace。
空输入成功只代表零帧传输；失败原样留存，不重试。

CALL 与 ASSISTANT 的预声明值均为 **10 ms / 160 样点**，来自原
`ap_pipeline_algorithmic_latency_ms`：16→16 kHz 边界重采样贡献零，
NS 贡献 `AP_FRAME_MS=10`。原 CLI 在读输入前保存该值，工程检查要求
从首帧到末帧全部 trace 都等于 10 ms。
这是源码声明的缓存 metadata，**不是实际物理相位/传声延迟校准**，
不能消除 HPF/BF 相位，也不从冲激峰或真实 target 搜索 lag。

原 CLI 会为短 render 补零，此行为没有改变。新工程/科研 wrapper 必须
在执行前拒绝 render 长度与 capture 每通道长度不等，拒绝输出复用和
输入/输出路径别名。负例单独标注，不能宣称原 CLI 已新增该约束。

另做四次非音频 metadata 查询：build-info、显式 CALL、显式 ASSISTANT、
隐式默认 tuning。保留三个默认参数原 stdout 和 parsed dict，要求
`implicit_default_equals_call=true`。科研矩阵读取这些绑定回执，
不另调用 metadata，也不添加调参 flags。

## 预算、失败与包结构

CI 内部总墙钟 600 s；configure 90 s、compile 240 s、engineering
60 s、工程单次进程 10 s；零自动重试。工作流外部 kill 为 630 s，job
12 分钟留出 checkout 和上传失败前缀。包最多 64 MiB、512 个文件。
晚发生的源身份、预算、归档或读回失败会撤销 PASS bundle；已经产生的
原归档、manifest 和回执改名保全为失败前原件，明确 FAIL，不丢弃字节。
600 s 与 60 s 进程内时钟包括准入和读回；630 s 只为失败回收留出宽限。

`bundle.json` 的 `files` 是全部普通文件的 SHA256 映射，仅排除它自身；
拒绝链接、特殊文件、路径穿越、重复 key、缺失和额外文件。
主要路径为：

| 包内路径 | 含义 |
|---|---|
| `bin/ap_process_pcm` | 实际两 profile 双麦处理器 |
| `bin/ap_build_info_dump` | 同 source/build 的身份查询程序 |
| `lib/librender_corr_exact.so` | 原 canonical 相关性数学 helper；不链接产品 DSP |
| `source/` | 59 个 main 相同原件及方法控制闭包 |
| `build/build-receipt.json` | 实际工具、源码、配置、命令、ELF 与依赖身份 |
| `engineering/engineering.json` | CI 宿主的完整实际合成工程报告 |
| `engineering/render-corr-checks.json` | 四个短数学检查、源码/库绑定及真实父进程映射 |
| `licenses/` | 本项目许可及可获得的已安装系统包版权说明 |

成功报告只能写 `PASS_ENGINEERING_ONLY`。归档生成后重新逐成员读取并
比较原文件 SHA，保留 tar SHA、大小和 manifest SHA。Actions artifact
保留 90 天仅作运输；长期原包应与科研结果一起持久保存。

## 入口与独立读回

以下路径相对于冻结公开源码 checkout。第一条只能在对应 CI job 执行：

```sh
python3 -B tests/validation/frontend_evolution/ap_current_ci.py run \
  --expected-head PUBLIC_RESEARCH_COMMIT --output /tmp/ap-current-portable
python3 -B tests/validation/frontend_evolution/ap_current_ci.py verify \
  --bundle /path/to/bundle
python3 -B tests/validation/frontend_evolution/ap_current_ci.py engineering \
  --bundle /path/to/bundle --output /path/to/new-host-engineering
```

`verify_bundle` 与 `verify_engineering` 只检查已保存字节、源码/二进制
身份、固定输入、trace、默认参数、预算和结论结构，不执行 DSP，也不要求
当前宿主与原执行宿主相同。完整 Git 公共源码对象须可读取，当前加载的
方法必须与 build 的 `source_revision` 同字节；原构建目录不必存在。

真正开始科研调用时，`require_host_engineering` 会重新观察当前宿主依赖。
与选中工程报告不一致则拒绝，必须显式先跑上面 60 s/5 s 内的合成
`engineering`，保留新旧两份实际回执。Debian 13 可以建立自己的报告，
不能复制 Ubuntu 的 ldd 字段伪称本机观测。两个入口均复用
`execution_environment()`，去掉动态库预载/搜索路径和编译器注入变量；
科研 subprocess 也使用它。新宿主检查不运行新真实语音、不测 target lag。

## 混合科研集成的明确选择

新增外层 scope 首先验证完整当前 workflow；去掉唯一声明的 AP wiring 后，
必须逐字恢复公开 `819849ee` workflow。D1–D8 与 AEC3 job 整段不改，
AEC3 模块不改。原 AEC3 tiny 只获得这一可证明的 predecessor view，
新 tiny 另外检查完整实际 workflow、真实 c7 64 路径和真实 38e1a85d
transport 变更、两个 job 必选及隐藏改动负例。

实际比较基线始终是 Actions 的 `BASE_SHA`，不拿历史 c7 替代当前 base。
合同逐文件登记 `4eec→c7`、`4eec→38e1a85d`、`38e1a85d→c3894ed2`
及后两者可审的精确合成旧/新 SHA；纯结果、F08
和已审运输改动不触发工程。另精确登记公开 `23d3a51` 的两项 source
custody 与说明文档；原 84 对象不改，两个新增对象继续保留，均禁止 GC。
初次混合引入 AEC3 方法与 AP/F05 方法时，
**AEC3 与 AP 两个工程 job 都执行，D1–D8 全 false**。若运输已在 base
中，未变化文件不参与选择；把较新 quality.yml 回退成已登记的旧 c7
字节仍拒绝。只有精确声明的 tiny/nav 增量可合成，不泛放行 quality、
其它 workflow、旧科学文件或 DSP 改动，也不以回落历史 job 处理拒绝。

为使测量完成后只提交结果、不再改变执行方法，执行前另外保留五个精确结果
路径：`F05_DUALMIC_VALIDATION_20261128/` 中的 `README.zh-CN.md`、
`measurement-summary.json`、`independent-readback.json`、`primary-by-speaker.svg`，
以及 `PLATFORM_IMPLEMENTATION_CLOSURE_20261128.zh-CN.md`。这些都是上述本目录
下的路径，仅允许原 base 不存在时新增，不能删除或重写旧科学文件。
结果路径及唯一固定结果导航片段只算 support；结果单独变更选择两个工程
job 均为 false，初次完整方法集成仍必须二者都执行。未知结果路径直接拒绝。
路径准入不预先批准结果数值、独立性或任何科学结论。
