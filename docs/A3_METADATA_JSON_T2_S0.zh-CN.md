# FE09 A3-R2-T2-S0：有限 JSON 元数据数值拒绝（Syntax-only）

**本阶段只是修复可证明的语法校验缺口，既不运行原始 A3，也不授予来源、实验或产品资格。**

- 固定基线：受保护 main `48ed19a5a6607d6373cfe1196fc7f747b8c7958f`；来源预登记 [Issue #847](https://github.com/jiying2007/audio-pipeline/issues/847#issuecomment-6570755544)。
- 历史原件：归档 `c4e9cb92af2fe42f09f09bcac0d0a814a511aab8` 内的 `fe09_a3_f0_source_admission.py`，Git blob `02566cc2904921fc6ea5a23129cae0a5e5ae4ce1`，保持不可修改。
- 确认的问题：历史 `json.loads(parse_constant=...)` 可拒绝字面 `NaN`，但 Python 默认浮点转换仍可把 `1e999` 转为无穷大。该历史缺口不证明任何真实 provider 响应成功利用。
- 修复仅为新派生文件 `fe09_a3_r2_metadata_json.py`：固定 UTF-8 字节上限、重复键、非法语法、浮点溢出和非零下溢、超长数字词元、孤立 Unicode surrogate 均拒绝，且只返回稳定错误码，不回显原始元数据。正常 JSON 对象、数组与有限数字允许解析。
- 与原始归档隔离：不导入或执行历史 source guard，不访问 GitHub、网络、文件、真实音频、C target 或保密凭据。不安装到公共 SDK；不改变原 C/h、88 个历史来源、FPR1 冻结、I025–I040 或任何原科学阈值。

## 离线验证

```sh
python3 tests/validation/frontend_evolution/test_fe09_a3_r2_metadata_json.py
python3 -O tests/validation/frontend_evolution/test_fe09_a3_r2_metadata_json.py
python3 -OO tests/validation/frontend_evolution/test_fe09_a3_r2_metadata_json.py
```

由现有 `.github/scripts/verify-docs-gate.sh` 接入，**没有新增 workflow、provider 调用、研究执行入口或 CI 调度**。拒绝型测试使用人工构造的元数据字节，不读取原 A3 科学输入。成功的 `authority_boundary()` 只显示 `syntax_only=true`，其余 source admission、freeze、formal controls、rolling33–49、RSS、public SDK、SSC305 HIL、shipping 全部为 `false`。

**验收**：PR exact-head Verify / App15368 summary / 受保护 squash / 新 main Verify；同源 Release 仍独立受 #511 治理凭据 401 阻塞。T2 后续真实 driver、collector、外部 PRE/POST freeze 和 117 项原注册控制，必须分别审查和提供原始证据，不能使用本语法测试替代。

## English contract

T2-S0 is a bounded UTF-8 JSON **syntax-only** correction. It rejects duplicate keys, literal and exponent-overflow nonfinite floats (e.g. `1e999`), silent nonzero underflow, token/byte overruns, malformed JSON and lone Unicode surrogate escapes. It is not a source provider or admission consumer, does not execute/import archived A3, does not change frozen scientific sources, and must never be counted as real A3 rolling, DUT/HIL or product certification.
