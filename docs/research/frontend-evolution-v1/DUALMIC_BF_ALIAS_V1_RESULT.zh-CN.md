# 双麦 BF 原位处理修复 2.3.64 候选

基线：7c82ecf101ad9660398c387caebae7932998c1ab。状态：IMPLEMENTED_HOST_TESTED_SOURCE_ADMISSION_PENDING。

公共 standalone 接口只禁止部分重叠，但精确 output==mic0/mic1 会覆盖延迟读取和原始历史。先保存两路各8点尾部，再仅在被覆盖通道需要延迟时反向写输出；上一帧历史保持到整帧读取完成。没有调整 BF 权重、健康阈值、方向估计、公共结构或状态尺寸。

实际 GCC14.2 主机测试共12240帧：8/16k、17个lag、三种别名、固定/跟踪、五种内部路由状态。原基线10368项不等；候选 O2、fast-math、ASan/UBSan 均0项不等。两版非别名输出与完整状态逐字节相同。状态180B；新增局部尾部数组64B，不是目标板栈测量。首次 LeakSanitizer 因 ptrace 环境失败；后续仅关闭 leak detection，ASan/UBSan 保持启用，代码无堆分配。旧失败不改写。

复跑：cc -std=c11 -Wall -Wextra -Werror -O2 -I src tests/test_beamformer_alias.c src/frontend/ap_beamformer.c -lm -o /tmp/bf-alias && /tmp/bf-alias

这只是直接C工程测试，不是CMake整库、ARM、音质、真人或主线资格。当前候选不得直接合并：必须先为2.3.64建立精确R8源码登记和原B3/F0/F1/A3科学执行器的受保护派生，保留所有R1–R7原件；随后取得候选自己的全部适用门禁、独立审核和受保护合并后的fresh-main验证。不得用本报告或旧CI替代这些步骤。#925保持独立未修改。
