# 双麦 BF 原位处理修复 2.3.64 候选

基线：7c82ecf101ad9660398c387caebae7932998c1ab。状态：SOURCE_ADMITTED_CANDIDATE_CI_PENDING。

公共 standalone 接口只禁止部分重叠，但精确 output==mic0/mic1 会覆盖延迟读取和原始历史。先保存两路各8点尾部，再仅在被覆盖通道需要延迟时反向写输出；上一帧历史保持到整帧读取完成。没有调整 BF 权重、健康阈值、方向估计、公共结构或状态尺寸。

实际 GCC14.2 主机测试共12240帧：8/16k、17个初始lag、三种别名、固定/跟踪、五种初始内部路由状态；每种组合连续12帧。跟踪模式会改变lag/路由，固定方向会清除软fallback，因此不是17个固定lag或五条持续不变路由的穷尽覆盖。原基线10368项不等；候选 O2、fast-math、ASan/UBSan 均0项不等。两版非别名输出与完整状态逐字节相同。状态180B；新增局部尾部数组64B，不是目标板栈测量。首次 LeakSanitizer 因 ptrace 环境失败；后续仅关闭 leak detection，ASan/UBSan 保持启用，代码无堆分配。旧失败不改写。

复跑：cc -std=c11 -Wall -Wextra -Werror -O2 -I src tests/test_beamformer_alias.c src/frontend/ap_beamformer.c -lm -o /tmp/bf-alias && /tmp/bf-alias

这只是直接C工程测试，不是CMake整库、ARM、音质、真人或主线资格。R8源码登记及原B3/F0/F1/A3执行器的精确派生已由PR #926受保护合并为5a683e001157fd9ee2f0578ecaa4d032997a6260，所有R1–R7原件保留。实现候选仍需自己的全部适用门禁、独立审核和受保护合并后的fresh-main验证。不得用本报告或旧CI替代这些步骤。#925保持独立未修改。


## 独立补充检查

public-wrapper目录保存单独的公开模块接口回归：8/16k、mic0/mic1/同时别名、固定/跟踪，每条轨迹120帧，在零基帧索引61前reset。tracking-enabled基线1440次调用中960不等，候选0不等；tracking-disabled候选包含720成功处理和720 AP_ESTATE拒绝且不修改输入/输出/状态的检查，均通过。ASan/UBSan的tracking-enabled候选1440次也通过。此处采用明确手写的最小BF配置header，不是生成SDK或CMake整库资格；公开wrapper状态为188B。原冻结proposal及旧日志不改写。

同目录host-resource.log为实际GCC14.2/x86_64/O2结果：process编译器静态栈估计384→384B，独立object text5391→5551B。不是目标板栈、最终ROM或性能实测。独立只读审核检查了补充测试与证据校验值，没有发现阻塞性逻辑问题。

源码准备的独立fresh-main push Verify42827397960在精确提交5a683e001157fd9ee2f0578ecaa4d032997a6260上完成：80成功、1预期跳过、summary成功。这仅验证2.3.63源码准备主线，不替代本2.3.64候选的检查。
