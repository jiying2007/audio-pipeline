# 本地实际测量源码恢复包 V1

本包保存原始本地运行和独立审查使用的 Git 提交。GitHub 连接器重新创建提交时 SHA 会改变；这里的 SHA **不是远程 Verify SHA**，也不将本地结果视为远程 CI、真实设备或声学验收结果。

## 固定范围

共同 prerequisite 为 `6056682486c1a2a2c84d77135de8118e07fc8cf3`。该提交及其祖先不装入 bundle；恢复前须从公共仓库取得它。本次先固定四个 head，再生成包，随后根工作树的新提交不会混入这个版本。后续 SAFE 修正须另行封存，不能重写这里的原始测量身份。

| 捕获来源 | 固定提交 | Bundle 内非分支引用 |
|---|---|---|
| sync | `fdcea684300f4f6846fbe130cd567ab7f412158b` | `refs/dualmic-local/sync` |
| health | `a38662fd6df11a1a8a99202220a5556fe4e05b1c` | `refs/dualmic-local/health` |
| profiles | `d55edf6e34e717b2dfc2e257d898a0854d504923` | `refs/dualmic-local/profiles` |
| integration | `be45d8127b3f9b986fc7280a8208b09c560eece2` | `refs/dualmic-local/integration` |

共 22 个共同基线之后的提交。bundle 使用临时 producer 仓库中的 `refs/dualmic-local/*`，没有创建或修改项目分支、root index 或提交。

## 校验值

| 工件 | 字节数 | SHA-256 |
|---|---:|---|
| 解码后的 `source.bundle` | 115740 | `3ce088c0b631083c585f5b5f1b5a87bebf6800f1de4ef8d3288adca70ca7093b` |
| `source.bundle.b64`，含末尾 LF | 154321 | `17c5c9a3c169e14fee324c930489820da29f59cc439da0435a89deff2820872f` |

`manifest.json` 记录所有捕获 head/tree、完整提交集合、四个关键提交的 src/include 树与完整源码 tar 哈希，以及保留日志/报告的源身份绑定。

## 恢复步骤

把 `EVIDENCE_DIR` 指向这三个工件所在目录，把 `RECOVERY_DIR` 设为一个新的空目录。以下操作只建立恢复仓库与非分支档案引用，不改变当前工程分支。

```sh
EVIDENCE_DIR=/absolute/path/to/dualmic-local-source-v1
RECOVERY_DIR=/absolute/path/to/audio-dualmic-recovery
mkdir -p "$RECOVERY_DIR"
python3 - "$EVIDENCE_DIR" "$RECOVERY_DIR/source.bundle" <<'PYVERIFY'
import base64, hashlib, json, sys
from pathlib import Path
source, destination = Path(sys.argv[1]), Path(sys.argv[2])
manifest = json.loads((source / 'manifest.json').read_text())['bundle']
encoded = (source / manifest['encoded_path']).read_bytes()
assert len(encoded) == manifest['encoded_bytes']
assert hashlib.sha256(encoded).hexdigest() == manifest['encoded_sha256']
assert encoded.endswith(b'\n') and encoded.count(b'\n') == 1
raw = base64.b64decode(encoded[:-1], validate=True)
assert len(raw) == manifest['bytes']
assert hashlib.sha256(raw).hexdigest() == manifest['sha256']
with destination.open('xb') as stream:
    stream.write(raw)
print('bundle bytes and hashes verified')
PYVERIFY
git -C "$RECOVERY_DIR" init
git -C "$RECOVERY_DIR" fetch --no-tags --depth=1 \
  https://github.com/jiying2007/audio-pipeline.git \
  6056682486c1a2a2c84d77135de8118e07fc8cf3
git -C "$RECOVERY_DIR" bundle verify "$RECOVERY_DIR/source.bundle"
git -C "$RECOVERY_DIR" fetch --no-tags "$RECOVERY_DIR/source.bundle" \
  'refs/dualmic-local/*:refs/dualmic-local/*'
git -C "$RECOVERY_DIR" log --all --oneline
```

恢复后可以直接以完整 SHA 读取源码，或在另一目录以 detached worktree 重建某个提交。例如：

```sh
git -C "$RECOVERY_DIR" show edff155ce9541dc42feb1660e6b7a30d8e9fa63a:examples/process_pcm.c
git -C "$RECOVERY_DIR" cat-file -t fdcea684300f4f6846fbe130cd567ab7f412158b
git -C "$RECOVERY_DIR" cat-file -t 4f2a1c63455736c42ce72f8c7103b35b3b0f9893
git -C "$RECOVERY_DIR" cat-file -t 50068fa285bfa7d209e635c63e86e36bec1bd3e1
```

## 已实际执行的隔离验证

在新的 bare 仓库中先仅 fetch prerequisite，`--depth=1` 后确认恰好 **1 个 commit object**，四个关键提交均不存在。随后真实执行 `git bundle verify` 与 `git fetch bundle`。导入后恰好 **23 个 commit object**，新增提交集合与原仓库精确相同，`git fsck --full --no-reflogs` 返回 0。

逐项检查四个关键 commit/tree，重新读取其整个 `src` 和 `include` 并导出 tar，与原仓库逐字节相等；提交日志也逐字节相等。

| 关键本地提交 | Tree | src/include 文件数 |
|---|---|---:|
| `edff155ce9541dc42feb1660e6b7a30d8e9fa63a` | `e0b0edcf78d7abc732ddf8f127549ef15cd9d8cd` | 49 |
| `fdcea684300f4f6846fbe130cd567ab7f412158b` | `993fde2190a4e887b1f2fcf63668baad69e190a3` | 49 |
| `4f2a1c63455736c42ce72f8c7103b35b3b0f9893` | `b1d449ec06f19458245129e5b2708799f1e92f7f` | 49 |
| `50068fa285bfa7d209e635c63e86e36bec1bd3e1` | `adfa31b50ae6d7977829a65b039eddb529068985` | 49 |

还实际恢复并核验了 profile 的 receipt、report、artifact manifest 和四份日志，以及 BF 的 summary 和十五份日志/JSON。报告中的 `edff155…`、`4f2a1c6…` 源提交都能在恢复仓库中解析；BF summary 的四个源文件 SHA-256 与该实际测量提交一致。SYNC 结果文档及其列明的三个源码 SHA-256 也与恢复的 `fdcea684…` 一致。整合提交 `50068fa…` 中的 BF 实现、内部头文件、健康测试与已测量 BF 提交相同；这不宣称两个提交的整个构建环境或所有模块相同。

## 保留边界

这是源码恢复包。完整 42-case PCM、本地二进制以及尚未纳入 Git 的 SYNC 原始日志没有装入本包；已提交的报告和紧凑日志按原字节保留。本次恢复验证不重跑声学指标、DSP、板端测试或远程 CI，也不生成新的胜出或质量结论。
