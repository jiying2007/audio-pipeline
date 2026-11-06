# SSC305 保守档交付与证据

> **当前研究范围**：本页仅定义技术研究与实测方法。当前准入以 [RESEARCH_ONLY_EXECUTION.md](RESEARCH_ONLY_EXECUTION.md) 为准，不依赖 GitHub Release、SKU 商用批准或产品认证；缺失真机证据只限制相应结论，不阻断独立软件/声学实验。原始许可、测量和盲测隔离要求保持不变。

[English / canonical contract](SSC305_DELIVERY.md)

研究构建必须区分不同身份：普通 SDK 是 hosted 原生构建；`reference-armhf-sdk`
是固定 CI 工具链编译的 `ssc305-cortex-a32-low`；实际 BSP 实验必须固定真实使用的
编译器、sysroot 和 ABI，并独立验证链接、加载和运行。参考包不能证明其 libc/loader 与产品固件一致，不能直接
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

## 如何使用研究构建产物

从明确选择且成功的 Verify 运行取回研究资源/工程产物，固定 source SHA、完整文件清单、
哈希与构建身份。Actions artifact 只是传输，不是独立声学结论或永久归档；需在失效前
保留实验原始证据。旧 v2.3.55 Release 打包协议仅是历史记录，不再是活动发布路径。
完整目录校验方法见英文契约；参考包不能替代真实 BSP 链接、加载和运行验证。

仍需产品侧确认 PCM 几何、真正播放后的 render reference、统一时间域、路由变化、
背压/丢帧处理、线程调度和完整资源预算。实际板端性能保持独立待测，
不因软件 CI 全绿而关闭。
