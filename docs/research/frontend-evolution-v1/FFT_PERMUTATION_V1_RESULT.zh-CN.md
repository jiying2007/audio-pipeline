# FFT 位反转表有界实验：NO_ADVANCE

基线 `8f282f0b8b55cf71285bf77b76598e101f9ba3c0`。单一研究候选将≤512点的位反转循环替换为固定uint16索引表，不改变浮点蝶形算术、公开接口、生产源码或默认配置。已有FFT优化#3为twiddle表、#8为NS输入打包，本次不是重复它们。

严格GCC编译通过；22,000组正逆变换（1–1024点，含特殊浮点工程输入）与基线逐字节一致。原仓FFT测试在两臂均通过；故意损坏索引表的负对照被拒绝。56次交替host CPU计时的8组中位比几何均值为**0.9503498490056138**，未满足执行前冻结的≤0.95门槛，故**NO_ADVANCE，候选关闭**，不四舍五入放宽门槛，不重跑挑选有利结果。只读表增加1024B，代码段增加101B，无调用者状态增长。

首次ASan/UBSan执行因ptrace环境下LeakSanitizer fatal退出1，原错误保留。独立标记、仅关闭LSan的补充ASan/UBSan执行退出0，22,000组比较通过、stderr为空；不宣称LSan通过。其附带计时不参与性能结论。CMake未安装，完整pipeline配置未执行。未验证完整PCM链、ARM或SSC305，不把FFT等价夸大为完整端到端验证。基准未绑核、无置信区间，短host微基准仅作有限预算筛选。

[完整原始证据](fft-permutation-v1/RESULT.md)、[预先冻结合同](fft-permutation-v1/PLAN.json)、[编译和执行命令](fft-permutation-v1/COMMANDS.txt)、[逐文件哈希](fft-permutation-v1/manifest.json)包含原始输出、源副本、编译身份与二进制哈希。无工作流、生产代码、阈值或既有实验更改；归档不是科学重跑。PR保护资格与fresh-main复验另行核对。
