# SAFE 修复实际源码：本地恢复续包

本目录的日志与 `summary.json` 保留公开SAFE反例及实际before/after结果。
`source.bundle.b64`、`source-manifest.json`构成独立源码续包，使本地执行SHA在
远程提交通过API重新构图后仍可恢复。它不把本地CTest称为远程CI或目标板测量。

## 固定捕获范围与依赖

本包只捕获结果提交 `8633f9ff8cef169c23ad79046c91b2badb217640`，对应bundle的
`HEAD`引用。其prerequisite为
`be45d8127b3f9b986fc7280a8208b09c560eece2`，该提交及祖先不重复装入本包。
prerequisite已在根工作包的
`validation/research/evidence/dualmic-local-source-v1`中；先按V1的README恢复它。

| 本包新增提交 | 含义 |
|---|---|
| `9ec381e4f4fa6e6ecd1c9016d3b0711c79343a75` | SAFE修复前的根整合基线及已有行为说明 |
| `a72e056420f4254f72a4b4ebae87d118d65aec2f` | 独立SAFE补充冻结与原始public反例 |
| `88003920f952af69dd7f88fea969122ba726e706` | 本次实际测试的生产代码和扩展测试 |
| `8633f9ff8cef169c23ad79046c91b2badb217640` | 实际结果、原字节日志与源码/二进制绑定 |

**本包不包含保存bundle、manifest及本README的后续提交。** 生成时先固定上表结果
提交，再从其HEAD排除be45及祖先创建bundle；没有自包含循环，也未修改V1。
Git提交原始身份和先前失败不会因根工作包重新提交或cherry-pick而被改写。

## 完整性

| 工件 | 字节数 | SHA-256 |
|---|---:|---|
| 解码后的source.bundle | 21,956 | `15f2d2530287cf885c784056deeeb0342a975ed51569a2b1035da5e0eeb053bc` |
| source.bundle.b64，单行含一个末尾LF | 29,277 | `269284c505ca247f4816ba3e3e0be1aa730fd73bed30733775705060b7304a0b` |

manifest另记录V1包与manifest哈希、唯一prerequisite、四个新增commit、恢复后的
完整tree、src/include tar哈希、实际执行源码绑定和隔离恢复命令。

## 恢复步骤

先按V1说明恢复6056682 prerequisite及V1，使新恢复仓库中已有be45d812。
然后令以下两个变量分别指向本目录和该恢复仓库；命令只创建非分支档案引用。

```sh
SAFE_EVIDENCE_DIR=/absolute/path/to/dualmic-fixed-health-safe-v1
RESTORE_DIR=/absolute/path/to/dualmic-recovery

git -C "$RESTORE_DIR" cat-file -e be45d8127b3f9b986fc7280a8208b09c560eece2^{commit}
python3 - "$SAFE_EVIDENCE_DIR" "$RESTORE_DIR/safe-source.bundle" <<'PYVERIFY'
import base64, hashlib, json, sys
from pathlib import Path
source, destination = Path(sys.argv[1]), Path(sys.argv[2])
metadata = json.loads((source / 'source-manifest.json').read_text())['bundle']
encoded = (source / metadata['encoded_path']).read_bytes()
assert len(encoded) == metadata['encoded_bytes']
assert hashlib.sha256(encoded).hexdigest() == metadata['encoded_sha256']
assert encoded.endswith(b'\n') and encoded.count(b'\n') == 1
raw = base64.b64decode(encoded[:-1], validate=True)
assert len(raw) == metadata['bytes']
assert hashlib.sha256(raw).hexdigest() == metadata['sha256']
with destination.open('xb') as stream:
    stream.write(raw)
PYVERIFY
git -C "$RESTORE_DIR" bundle verify "$RESTORE_DIR/safe-source.bundle"
git -C "$RESTORE_DIR" fetch --no-tags "$RESTORE_DIR/safe-source.bundle" \
  HEAD:refs/dualmic-local/safe
git -C "$RESTORE_DIR" cat-file -t 88003920f952af69dd7f88fea969122ba726e706
git -C "$RESTORE_DIR" show 88003920f952af69dd7f88fea969122ba726e706:src/core/ap_pipeline.c
git -C "$RESTORE_DIR" fsck --full --no-reflogs
```

可以再以8800392建立独立detached worktree，按SAFE结果文档的命令重建。
本包不包含本地可执行文件、完整PCM轨迹或其自身的打包提交。

## 已实际执行的隔离验证

使用一个新的bare仓库，清除外部Git对象/alternate相关环境，未使用共享对象目录：

1. 从现有本地仓库只浅取精确6056682，实际仅有1个commit object；不是联网取得。
2. 校验V1原base64、解码哈希，执行真实bundle verify/fetch；此时23个commit object，
   be45d812存在，8800392和8633f9f均不存在。
3. 校验并导入本续包后，实际27个commit object；新增集合精确等于上表四个提交。
4. 8800392恢复的完整tree为`9d76fb1a1148fb5d143d1fe874ef8a8f3444ff27`；
   结果提交8633f9f的完整tree为`dec7b67af5570657a7028379782c550c5ae70b5c`。
   两个commit原文、各自49个src/include文件导出的337,920 B tar，分别与原库
   对应提交逐字节相等。tar包含提交归档元数据，不能用两提交的tar哈希差异推断源码变化。
5. 恢复结果summary，验证其中实际执行SHA为8800392；四个源文件哈希及20份
   紧凑证据的SHA-256/字节数全部匹配。`git fsck --full --no-reflogs`返回0。

这次恢复只验证对象和原字节工件，没有重新运行DSP、声学、远程CI或物理设备实验。
