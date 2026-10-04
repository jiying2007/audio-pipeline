# SSC305 保守档交付与证据

[English / canonical contract](SSC305_DELIVERY.md)

发布包必须区分三个身份：普通 SDK 是 hosted 原生构建；`reference-armhf-sdk`
是固定 CI 工具链编译的 `ssc305-cortex-a32-low`；正式 BSP 包必须使用产品批准的
编译器、sysroot 和 ABI。参考包不能证明其 libc/loader 与产品固件一致，不能直接
把参考包或主机 SDK 当成板端量产包。

## 已接入的自动验证

现有 required Resource Gates 复用同一个保守档构建，验证干净安装后的 CMake、
pkg-config、runtime 和 build-info 消费。离线音频处理器链接这些相同的已安装库。
资源探针与安装探针的 source SHA、config digest 和所有字段必须一致。

声学部分复用 canonical generator v3、1307/2307/3307 三个固定 seed、每组 27 个
原始用例，以及未放宽的 `validation-smoke.json` 和用例断言。81 个用例分别重复
处理两次，比较真实输出 PCM SHA-256；同时保存原始逐条指标。报告绑定 QEMU
启动脚本哈希和真正执行的 AArch32 ELF 哈希，不用启动脚本代替二进制身份。
这证明选定配置的合成回归与重复性，不证明真实电机噪声、外壳远场或产品声学效果。

## 内存与实时性能边界

`ci/ssc305-resource-profiles.json` 是预算权威。保守档 pipeline + runtime 调用者
持有的状态合计不得超过 **50,000 字节**；线程栈、应用/libc RSS、外部 PCM 队列、
ALSA/kernel 缓冲和 Flight Recorder 仍需另计。效果优先档继续仅限研究用途。

`qemu_probe_repeat_identical` 仅表示资源探针原始 stdout 重复一致；PCM 重复性由
独立声学快照证明。算法延迟不是处理耗时或收敛时间。CPU/p95/p99/RSS/温升/功耗
保持待校准，不从 hosted 或 QEMU 时间推算 SSC305 数值。

## 非真机工程长稳

现有 runtime extended 测试增加可选长稳模式，required 门禁运行 200 万帧、64 次
生命周期，复用队列饱和、输出背压和控制命令测试，并插入丢帧、时间戳跳变、
缺失 render、XRUN/codec reopen 和路径变化。采用保守档的 native SCALAR 配置投影，
启用 ASan/UBSan/泄漏检测；运行时相关测试单独列出，原有 full CI 的全矩阵不减少。
默认包含 100 ms 延迟假设的通用测试不被伪装成 60 ms SKU 测试。

FNV-1a 指纹只用于长流循环诊断比较；真正的声学 PCM 证据使用 SHA-256。
处理了多少秒音频与主机实际运行时间分开记录，均不是真机 72 小时 route soak。
失败保留，未通过不能写成合格证据。

## 如何使用发布物

从 v2.3.55 开始，Release 只消费触发它的 exact-main Verify 产物；参考 SDK、SPDX、
配置/编译器/库哈希、声学回归和工程长稳证据进入相同的 manifest、SHA256SUMS 与
attestation，再由 immutable Release 保留。历史发布不重写，新发布不得降回旧的
八资产集合。完整目录校验方法见英文契约；参考包不是正式 BSP 包，也不产生
Product Certification 权威。

仍需产品侧确认 PCM 几何、真正播放后的 render reference、统一时间域、路由变化、
背压/丢帧处理、线程调度和完整资源预算。正式板端性能与量产认证保持独立待办，
不因软件 CI 全绿而关闭。
