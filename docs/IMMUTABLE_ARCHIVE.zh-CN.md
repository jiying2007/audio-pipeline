# 不可变历史归档的空白格式门禁

2026-10-21：用户明确批准固定SHA方案，用于保全设备采集与已绑定哈希的研究原字节。
PR #821 首次 Verify 39454312314 的 `git diff --check` 仍为失败：16个原文件、44项空白格式告警。
该失败不改写为严格检查通过，也不代表研究效果或产品资格失败。

## 分离注册与导入

本政策PR仅引入检查器、注册清单和测试，没有导入原始数据。首次政策提交的base没有检查器，
Verify继续直接执行原来的 `git diff --check`。政策先经受保护PR合入main，数据PR才能消费该base。

Verify从base提取并执行 `tools/codex_assets/immutable_whitespace.py`。
完整差异严格检查通过时不需要例外；只有严格检查确实exit2时，才核对base上的
`.github/research/frontend-evolution-v1/immutable-whitespace-v1.json`。
数据PR的head必须保留政策和检查器的相同字节，不能自授权。

清单固定16个路径、原Git普通文件模式（14项100644、2项100755）、完整blob SHA256、逐文件诊断输出SHA256和44项告警计数。
仅允许原路径首次新增；修改、移动、不同模式、额外告警或未知错误都失败。
其余所有变更路径继续严格检查。没有通配白名单、Git全局豁免或属性关闭。
检查在临时bare Git对象视图中执行，不加载工作树、index或info/global attributes，候选属性不能隐藏告警。
政策可单独维护，但包含需例外导入的PR不得同时改变政策/检查器。

## 复跑

```sh
python3 tests/validation/test_immutable_whitespace.py
python3 tools/codex_assets/immutable_whitespace.py --base BASE_SHA --head HEAD_SHA
```

第一条用临时Git仓库验证真实blob、错误路径、模式、重复键、SHA、诊断、政策/检查器自修改与Git异常。
第二条只读Git对象；`--root`可显式指定仓库，`--help`可以从任意cwd调用。
`STRICT_PASS`与`IMMUTABLE_IMPORT_VERIFIED`分别保留严格通过和经批准导入的真实区别。

本合同只改变限定的历史导入格式接纳，不改变科学阈值、原音频、训练/晋级角色、隐私/素材权利、
产品默认/API、E001/HIL或产品认证要求。新原始字节需要独立注册评审，不能临时扩大清单以获得绿色CI。
