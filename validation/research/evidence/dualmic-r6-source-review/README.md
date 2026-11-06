# R6 source-only 准备：最终独立审查原件

本目录紧凑保留最终独立源码审查的原始 receipt、命令清单和全部 28 次 Python 调用的原始输出（共约 108 KiB），包括未通过的原 A3 环境用例。另有实际 workflow 版本分支检查的记录。原文件逐字节复制，不改写执行结果、失败文本或源码身份。

## 身份与审查范围

| 身份 | 值 |
|---|---|
| 本地实际审查提交 | `7998cc5870889e37191b1e91d77575309a4ba98d` |
| 远端实际准备提交 | `e12288f7c977ba9a40c71fd40f222ff0945c3b0c` |
| 两者相同的审查 tree | `bd026252b07d6213cf1add4660098d298c1404c3` |
| 已核对的未来实现候选提交 | `516ace7230f4846ab76941bcdeacc5465f79e2ce` |
| 未来候选 tree | `e5e23d76fa8bf54b40505fcd853c02ef57dfbe4e` |

本地与远端是两个不同的 commit 身份，不能互换审查日志中的 SHA；源字节审查结论绑定相同 tree。可以从公共仓库读取远端准备提交并核对 tree，恢复被审查源码，无需额外 bundle：

```sh
git fetch --no-tags https://github.com/jiying2007/audio-pipeline.git \
  e12288f7c977ba9a40c71fd40f222ff0945c3b0c
git rev-parse FETCH_HEAD^{tree}
# expected: bd026252b07d6213cf1add4660098d298c1404c3
```

[准备 PR #916](https://github.com/jiying2007/audio-pipeline/pull/916) 对应这一远端准备提交。本包**不声称准备 PR 已完成 CI**。原 receipt 的 `CI_PENDING` 是独立审查当时记录；后续实际 Verify 结果须按其真实远端提交、run/attempt 和结果另行记录。

## 已完成的独立源码核对

- 准备分支 `src`、`include` 和 `CMakeLists.txt` 与 `438fe09` 精确相同，当前版本仍为 2.3.61。
- 原 B3 77、共享 executable 66、F0 88 集合不变。候选 13 个例外均与真实候选文件身份一致；53 个共享未变成员和 22 个 F0 独有成员保持。
- 30 个历史 pins 与原基线字节一致；13 项 delta 独立正向应用后等于候选字节，反向应用后恢复历史字节。
- F1 原 96 成员为 83 个原字节与 13 个已注册例外；A3 原 88 成员全部保持原字节。
- 五个派生入口保留 102 个完整函数与 8 个完整类；F1/A3 各一个 `build_only` 仅更改唯一初始失败状态字符串。两个函数不在 metadata 白名单，其他 AST、控制流和源码字节受保护。
- runtime 新注册绑定 6 个源码文件，原 2.3.57–2.3.61 注册不变；新增 14 负例，原 16 + 12/12/12 负例保持。
- 原数值、资源、期限、过程管理与证据预算保持。22 个实际 shell 路由检查包含 14 个正确的已知版本路由与 8 个未知版本拒绝。

## 实际测试与未通过项

| 实际执行 | normal / `-O` / `-OO` |
|---|---|
| R6 source self-test | 每种模式均通过：31 新负例，保留 R5 27 |
| R6 derivation self-test | 每种模式均通过：24 新负例 |
| runtime self-test | 每种模式均通过：旧 16+12/12/12、新 14 |
| literal identity 方法 | 每种模式均通过：12 负例 |
| 原 F1 source | 每种模式 35 tests 通过 |
| 原 F1 build | 每种模式 48 tests 通过 |
| 原 A3 source audit | 每种模式 17 tests 通过 |
| 原 A3 static | 每种模式 18/19 通过，1 环境错误，未记作 PASS |

新增 B3 parser/schedule 与 F0 metadata self-test 均实际通过。当前准备分支 `--check-current` 返回原 R5 / 2.3.61 身份；直接 `--check` 申请 R6 身份按预期 exit 2、`R6_VERSION_NOT_REGISTERED`。

A3 三个模式的原始错误均保留：

```text
test_fake_full_pipeline_records_eight_not_executed_objects
A3_REQUIRED_PINNED_COMPILER_MISSING
Ran 19 tests
FAILED (errors=1)
```

该用例依赖既有固定路径的工具链，本地环境未满足。未替换工具、放宽路径或修改测试；完整构建和完整 Verify 仍需既有固定 CI 工具链的实际结果。本审查没有执行新的 B3/F0 DSP、F1/A3 研究可执行程序或物理设备测试。

## 文件索引与完整性

- `review-receipt.json`：原独立审查 receipt，SHA-256 `cec6ce32cb43e932a079485ac7eec7847043e90b68e699b08ec456458970b09e`。
- `key-gates.json`、`historical-tests.json`：原命令、实际返回码、耗时与日志哈希。
- `normal-*`、`O-*`、`OO-*`：相应原始测试输出，包含三个 A3 错误日志。
- `additional-tests.json`：B3/F0、当前身份、预期拒绝、literal 方法的命令，以及 22 个实际版本路由记录。
- `additional-00.log` / `01`：B3 / F0 self-test；`02`：当前 R5 身份；`03`：R6 当前版本预期拒绝；`04`–`06`：normal / `-O` / `-OO` literal 方法检查。
- `artifact-manifest.json`：本目录独立清单，校验所有保留原件与此 README；清单自身不递归收录。

可在本目录运行完整性回读：

```sh
python3 - <<'PYVERIFY'
import hashlib, json
from pathlib import Path
root = Path('.')
manifest = json.loads((root / 'artifact-manifest.json').read_text())
for name, expected in manifest['files'].items():
    raw = (root / name).read_bytes()
    if len(raw) != expected['bytes'] or hashlib.sha256(raw).hexdigest() != expected['sha256']:
        raise SystemExit('evidence mismatch: ' + name)
print('retained source-review evidence verified')
PYVERIFY
```

结论限定为精确源码树的 source-only 准备审查未发现阻塞代码问题，不继承历史声学结果，不授予候选音质、SAFE 修复效果、四麦 SDK 或 SSC305 资格。
