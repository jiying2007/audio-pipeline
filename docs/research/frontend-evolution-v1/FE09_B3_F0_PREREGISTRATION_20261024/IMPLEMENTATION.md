# B3-F0 私有组合与验真入口

本页描述 #837 冻结合同的实现，判定以精确执行源码所产生、通过回读的 `receipt.json` 为准。登记文件中的未执行状态保留冻结时的历史含义；本页不能替代实际 PR、main、目标和 run/attempt 的结果。

## 组合边界

私有 `fe09_b3_f0_bind`／`fe09_b3_f0_process_one` 将原 source owner、Capture-only SRC/FIR33、独立 Render SRC 与真实 mono CALL 串接。原生产源码、公开头文件、根 CMake、既有 SRC/BF/owner 组件保持冻结字节。原 B1B1 `.c` 在私有组合单元中仅编译一次，用于读取真实布局；没有复制或改写 DSP。

Bind 用原初始化器生成固定配置的 fresh 状态，核对实际 Capture header、SRC、BF 和 mono 状态，排除已经预推 Render 但尚未处理 Capture 的 mono。Capture 的比较只规范化两项分配地址，初始化器不写的对齐 padding 不作配置真值。逐帧准入检查固定身份、配置、长度、范围及别名；owner 是最后一个可能正常拒绝的状态提交阶段。提交后的异常归为 `COMPOSITION_INVARIANT_BREACH`，停止并保留失败帧真实进度。

PAP 的40个缺席事件没有 Render PCM；SDK 内部欠载产生的零参考不代表来源方投递。201／241帧的两次显式通知，与 SYNC 路径变化导致的自动 AEC reset 分开计数。外部 Capture 状态必须保留；mono 内部 reset 所涉及的9类状态在实际通知 wrapper 中核验。

## 独立控制与真实观察

Direct control 从固定帧范围直接调用原接口，不读取新 adapter 的分类或控制回执。ALL_P／PAP、两次重复、plain／observed 和 direct 的逐帧 PCM、公开 metrics、事件与 Capture 历史分别比较。未来控制只反转241帧起的输入，前240帧连同真实调用观测必须不变。

14个只读链接 wrapper 各调用原函数一次，保持参数和返回值，记录实际阶段顺序、Activity→AEC／NS 门控、AGC 参数、频域 RES 谓词、精确 SYNC samples、公共通知和 reset 分类。原库显式关闭 Unity／IPO，两个二进制使用同一原库与相同 PRIVATE 编译定义。完整600帧观测存储上限为256KiB；文件写入均在处理结束后。

## 冻结输入与源码

`INPUT_FIXTURE_FREEZE.json` 封存独立 Python 输入审计、两个600行输入／控制账本及源角色选择。C 的 `--fixture-only` 先生成输入但不初始化／执行 DSP，必须与该独立 SHA256 真值一致。归档回读重新进行纯整数构造和逐帧检查，不因为缺少成功 PCM 而降低输入验真级别。

`source-lock.json` 的整体 SHA256 固定了全部77项路径、角色和身份，其中66项编译依赖必须逐字节不变；其余11项是冻结时的依据快照。新增源码、工作流、登记文件、实际执行 Git commit/tree、库、ELF、生成头、编译／链接 recipe 和工具版本另行绑定。

冻结来源仍为 `81ee5598…`。`EXECUTION_BASELINE.json` 必须另行记录执行前已独立通过的受保护基线、66项源码等价和精确 Verify／Release／convergence；缺少该凭据即 BLOCKED。候选 PR 与随后 squash 的新 main 各执行自己的完整矩阵。新 main 不在自己的 Verify 内等待该 Verify 尚未结束的 Release。

## 执行与回读

在干净、已提交且满足基线前置的源码中执行：

```sh
python3 tests/validation/frontend_evolution/fe09_b3_f0_qualification.py --self-test
python3 tests/validation/frontend_evolution/fe09_b3_f0_qualification.py \
  --collect --output fe09-b3-f0 --execution-source "$(git rev-parse HEAD)"
```

默认必须存在 native GCC、ASan／UBSan、AArch32 compiler／QEMU，缺少任何目标先保存 BLOCKED；不静默省略目标。本地可以显式选择 `--targets native,sanitized`，这种结果始终是部分执行，不具有完整资格。

已保留的同一源码证据可独立回读，零新增 DSP 帧：

```sh
python3 tests/validation/frontend_evolution/fe09_b3_f0_qualification.py \
  --verify --output fe09-b3-f0 --execution-source "$(git rev-parse HEAD)"
```

回读重新检查完整成员清单、字节、实际源码、输入真值、构建 recipe、逐帧事件／门控、跨对照等价及同一组8个重封语义负控。构建机绝对路径先绑定其原 source root，再按冻结相对路径核验，允许在另一个精确源码 checkout 读回，不接受 basename 模糊匹配。

每目标固定11条600帧轨迹；仅 plain PAP 第一次执行16个 API 负控，额外5次 producer setup 单列。三目标总计19800个成功组合帧。失败时保留已完成前缀与失败帧的 owner／front／mono／bridge 真进度；硬超时无结果时明确实际数量未知，该预定尝试已经消耗，不自动重跑。

## 时间、资源与归档

既有 `frontend-reference` 的15分钟上限不变。第一执行步骤通过既有只读 Actions 权限读取该 job 的真实 `started_at`，保存原 deadline；B3 的单次300秒总预算同时受这个原 deadline 减60秒归档预留约束。该读取失败不能另起一个15分钟计时。每个构建、DSP 子进程、Git 身份检查和验真循环使用同一剩余预算；每目标执行总额另有120／180／300秒账本。

原始执行先核对输出和 BF PCM 的实际字节，再保留其 SHA256、逐帧哈希、压缩 JSONL、公开 metrics 和构建资料；成功 PCM 不默认上传。失败保留原件或明确记录超限原件的位置与不完整状态。完整元数据上限32MiB。最终读回、封存或时间检查失败必须撤销资格，不能留下成功回执。

资源账本分别列出 Capture arena/work、mono、owner、bridge、receipt、bind 参考 scratch、测试 fixture／快照、输入／输出、日志、observer、ELF section 和编译器单函数栈。Bind 完整 fresh-state 校验使用96,384字节参考 scratch；这项开销属于私有研究实现，不能隐去或作为192KiB产品通过结论。最大单函数栈报告也不等于累计栈或全进程 RSS。

182 samples／11.375ms只包含身份 SRC、22-sample FIR33 与 mono 10ms 公开算法延迟，排除队列、调度、设备和端到端时限。D0 工程通过不批准声学优越性、物理时钟、公开 C4 API、SSC305、HIL、E001 或 shipping。
