# ARM static precheck：原结果与源码身份封存

本目录保存原有静态预检结果，不重新下载、编译、运行 ARM 程序或重跑测量。实际源码为 base `438fe09d79ff768306c00573849517bcd91cbc6e` 与 candidate `9a9202eca32cfa03d92644f5735bfc2c2429efbc`。原日志、工具包 URL/SHA、配置和 report 均按原字节保留在 `original/`。

## 结果与预算事实

| 项目 | Base | Candidate | 原有上限 |
|---|---:|---:|---:|
| `.text + .rodata` | 30,852 B | 36,156 B | 40,960 B |
| Pipeline arena | 38,832 B | 38,864 B | — |
| Runtime arena | 6,424 B | 6,424 B | — |
| 两个 caller-owned arenas 合计 | 45,256 B | 45,288 B | 50,000 B |

候选 ROM 余量 4,804 B，arena 余量 4,712 B。使用实际 Debian ARM GNU GCC 14.2.0-19 与 binutils 2.44、原 `ssc305-cortex-a32-low` preset、原 `rom_probe.c` 和 `.text + .rodata` 口径。Arena 从原交叉编译 getter 的常量返回反汇编读出，没有运行 ARM 程序。

**原任务总预算没有通过。** 原编译与静态测量约 233 秒完成，但连同证据整理总计约 326 秒，超出 300 秒预算约 26 秒。233 秒不能替代总耗时，也不能据资源数值在限额内宣称任务整体通过。`resource-receipt.json` 将 `total_budget_passed` 记为 false，并保留两个时间。

这些数值仅为有限的本地 AArch32 静态预检，不是完整 CI、QEMU、DUT、音质、帧时限、RSS/栈、热或功耗资格。原工具链 bootstrap 失败说明仍在原 report；没有全局安装、伪造 `/usr/bin` 工具或放宽 A3 要求。

## 固定源码续包

`source-continuation.bundle.b64` 的固定 head 为 `9a9202eca32cfa03d92644f5735bfc2c2429efbc`，prerequisite 为 `be45d8127b3f9b986fc7280a8208b09c560eece2`，后者已在 V1 源码包。包不包含当前 ARM 报告封存或包自身的后续保存。原始本地测量提交身份单独保留，不用远端另建提交的 SHA 替换。

已在新的隔离仓库实际依次恢复：仅 depth=1 的共同 605 基线 → V1 → 本续包。导入前候选 head 不存在，导入后 commit/tree、完整 CMake/src/include tar 和测量导出源码文件哈希一致，`git bundle verify` 与 `git fsck` 均成功。基线 438 的测量源码也与原导出一致，并确认这些源码字节存在于共同 605 snapshot；没有将 605 重新命名为原 438 commit。

恢复时先按 `../dualmic-local-source-v1/README.md` 建立恢复仓库并导入 V1，然后在本目录解码与校验：

```sh
python3 - <<'PYVERIFY'
import base64, hashlib, json
from pathlib import Path
m = json.loads(Path('source-continuation-manifest.json').read_text())['bundle']
e = Path('source-continuation.bundle.b64').read_bytes()
if len(e) != m['encoded_bytes'] or hashlib.sha256(e).hexdigest() != m['encoded_sha256']:
    raise SystemExit('encoded identity mismatch')
if not e.endswith(b'\n') or e.count(b'\n') != 1:
    raise SystemExit('encoded format mismatch')
b = base64.b64decode(e[:-1], validate=True)
if len(b) != m['bytes'] or hashlib.sha256(b).hexdigest() != m['sha256']:
    raise SystemExit('bundle identity mismatch')
with Path('source-continuation.bundle').open('xb') as f:
    f.write(b)
PYVERIFY
git -C /absolute/path/to/recovery bundle verify /absolute/path/to/source-continuation.bundle
git -C /absolute/path/to/recovery fetch --no-tags /absolute/path/to/source-continuation.bundle \
  'refs/dualmic-local/arm-static-9a9202e:refs/dualmic-local/arm-static-9a9202e'
git -C /absolute/path/to/recovery show 9a9202eca32cfa03d92644f5735bfc2c2429efbc:CMakeLists.txt
```

`source-continuation-manifest.json` 记录包的原始/encoded SHA-256、大小、完整提交集合及隔离恢复结果；`measured-source-manifest.json` 记录实际测量源码的哈希；`artifact-manifest.json` 独立校验本目录保留文件。原 `.deb`、编译器与完整 ELF 不写入 Git，仅保留实际哈希，原 scratch 工件已再次回读验证。
