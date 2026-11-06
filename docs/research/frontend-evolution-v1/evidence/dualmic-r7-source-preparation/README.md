# R7 2.3.63 源码准备：作者定向验证原件

本目录是 source-only 作者验证，不是独立审查结论或远端 CI/DSP 结果。
实现提交 `70c0f6491e9959bab614b2c4719150d8f98c4d3f`，tree
`7fdf6fb2a1cee0435f46443e47a6f8f386ae2472`；准备基线为 protected main
`a920beed8e2c66ea9d90442d31af9632f5c75a23`。生产 CMake/src/include/API
仍为该基线的 2.3.61 原字节。真正登记的 proposal 是远端
`79636e3c53050639cf16573aa5cd6db37b153c93`，tree
`9fdbeb2a6af6672dfae96f23a23ae7931f279b3e`，两者身份没有互换。

## 实际验证

- R7 source 自检 31 个新负例，并执行原 R6 31 个及其历史负例；原 77/66/88
  集合和 13 个 reviewed exceptions 保持。独立读取 proposal 的全部 88 个成员
  验证登记；41 个历史 pin 与 protected base 原字节一致。
- 派生自检 24 个负例、窄 literal 方法自检 12 个负例；五组共 102 个科学函数
  和 8 个过程类保持字节一致，F1/A3 各仅一个初始失败状态 literal 改名。
- Runtime 原 16、12/12/12/14 个负例保持，新增 2.3.63 的 14 个；原六个版本
  映射与 forward patch 原字节不变，新映射准确绑定六个 proposal 文件。
- B3/F0 元数据 self-test 成功，没有调用 collect 或运行 DSP。
- 实际 shell 选择器检查 27 个情景，保留所有旧 B3/F0 路由、未知版本退出 2，
  F1/A3 的 2.3.61/62/63 分别选择 R2/R3/R4。
- source/derivation/runtime/routes 在普通 Python、`-O`、`-OO` 下通过。
  准备提交的 `--check-current` 正确选择 2.3.61/R5；Runtime `--check` 通过。
  新 quality YAML 解析通过。完整 Verify、编译、F1/A3 构建、QEMU、DUT 均未运行。

## 原始失败与唯一诊断期望调整

首次作者生成的未提交工作树产生三类真实失败，原 stdout/stderr/命令都保留，
不把它们写成最终 `70c0f64` 的失败或删除：R7 delta 文件名仍含 `_2_3_62`；
Runtime 旧版本跳跃负例的拒绝原因标签错误；新 route 测试把原 B3 2.3.56
的 `deadline-r1` 误写成 F0 的 `original-v1`。修复仅发生在新身份接线和新增
测试期望；原 workflow 的历史路由没有改动。

Runtime 的 **2.3.62→2.3.63 version-only 负例输入完全不变**。独立实测确认，
protected a920 原 checker 对该相同输入实际返回
`UNREGISTERED_FORWARD_MAINTENANCE_VERSION`。新增准确 2.3.63 登记后，单独
改版本恰好符合新 CMake blob，但旧 API 文本仍与新登记不符，新 checker 的
实际拒绝原因为 `CURRENT_MAINTENANCE_SOURCE_DRIFT_docs/API_CONTRACT.md`。
本轮首次自检沿用的默认期望标签是 CMake mismatch，随后仅纠正为 API mismatch；
这次标签纠正不能描述成原 R6 的实际拒绝原因从 CMake 转为 API。负例仍强制
拒绝、仍计入原 14 个；源码 verifier、门槛、补丁及原版本映射未放宽。

## 恢复和校验

`raw-records.json` 无损保存 74 个逻辑成员：首轮、最终普通模式、优化模式的
命令/原 stdout/stderr、源码审计和实际 authoring 脚本。每项记录 base64、原大小
及 SHA-256；用编码容器保留原换行，不清理原日志。`manifest.json` 校验当前
物理文件，`receipt.json` 记录本次作者验证范围和预算时点。

```sh
python3 - <<'PY'
import base64, hashlib, json
from pathlib import Path
records = json.loads(Path('raw-records.json').read_text())['members']
for name, item in records.items():
    raw = base64.b64decode(item['base64'], validate=True)
    if len(raw) != item['bytes'] or hashlib.sha256(raw).hexdigest() != item['sha256']:
        raise SystemExit('identity mismatch: ' + name)
print('verified original logical members:', len(records))
PY
```

后续仍须对准确准备 head 独立审查并通过 protected main，再由候选自己的新
head 执行 R7；本目录不继承 R6 或 b1f40864 的科学/资源/CI 结论。
