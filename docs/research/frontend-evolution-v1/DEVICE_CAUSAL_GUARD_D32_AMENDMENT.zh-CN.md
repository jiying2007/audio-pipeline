# D32 严格预编译格式修复

日期2026-10-11；原PLAN字节不改。
第0次严格预编译真实exit1：新增guard自测if后同一行接声明，触发-Werror=misleading-indentation。
失败回执=/tmp/audio-device-d32-precheck-0.json；原C可还原base64/hash快照=/tmp/audio-device-d32-precheck-attempt0-source.json；preserve writer和原precheck writer保留。
修复仅将声明与if分行；不改main处理、guard结构/公式/阈值/验收、原DSP库或严格警告。
新precheck-attempt1回执与runner独立，不覆盖第0次；预编译retry1/2，主92回放尚未执行。
工具起止身份增加锁本AMEND；仍须实施fresh审查通过后才开始主回放。
不称整轮零失败；原D31的独立生命周期/顺序问题仍保留，不把不同轮次失败混为同一根因。

实施fresh审查另发现MAJOR-1：Activity CSV校验引用f32但未导入，独立只读复现NameError；主矩阵尚未启动。
原工具ccf33b4f99f1ec8f3fba170e0a9d78b9c317f32d6e959bc5e4575bb9a21ea200的base64快照保留于/tmp/audio-device-d32-implementation-attempt0-source.json。
最小修复显式导入已冻结的Float32转换，并新增完整observe单帧CSV/轨迹解析路径测试；不修改C/header、候选参数或验收。
新增测试使用合成解析fixture和冻结score占位，不作为实际DSP或声学评分证据；主92回放仍须修复后实施复审PASS才执行。

首次执行wrapper的help exit0、dry-run exit2（/tmp/audio-device-d32-execution-0.json、-1.json）保留，主矩阵未启动。
根因是wrapper将仓库根目录传给--root；该参数沿用历史intake契约，要求tests/audio采集根目录。只读集合及哈希核验确认119个封存输入无新增、无缺失、无内容变化。
后续attempt1 wrapper仅修正--root为仓库/tests/audio，使用独立回执，不修改输入集合门禁、算法、评分或验收条件；实际DSP重跑仍为0。
