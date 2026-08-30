#!/usr/bin/env python3
from pathlib import Path

path = Path('tools/runner_preflight.py')
text = path.read_text(encoding='utf-8')
text = text.replace(
'''    if args.role == "audio-validation":
        checks.append(_path_check("validation:data-root", args.data_root, "dir", required=True))
        checks.append(_path_check("validation:seal", args.seal, "file", required=True))
        checks.append(_path_check("validation:dns-data-root", args.dns_data_root, "dir", required=False))
''',
'''    if args.role == "audio-validation":
        checks.append(_path_check("validation:data-root", args.data_root, "dir", required=True))
        has_public_seal = bool(args.seal)
        has_extended_catalog = bool(args.extended_catalog)
        checks.append(_check(
            "validation:dataset-contract",
            has_public_seal ^ has_extended_catalog,
            "exactly one of --seal or --extended-catalog must be supplied",
        ))
        checks.append(_path_check("validation:seal", args.seal, "file", required=False))
        checks.append(_path_check("validation:extended-catalog", args.extended_catalog, "file", required=False))
        checks.append(_path_check("validation:dns-data-root", args.dns_data_root, "dir", required=False))
''', 1)
text = text.replace('        "seal": None,\n        "dns_data_root": None,\n', '        "seal": None,\n        "extended_catalog": None,\n        "dns_data_root": None,\n', 1)
text = text.replace(
'''        assert validation["classification"] == "READY", validation

        builder = evaluate(
''',
'''        assert validation["classification"] == "READY", validation
        extended_catalog = data / "extended.datasets.lock.json"
        extended_catalog.write_text("{}\\n", encoding="utf-8")
        extended_validation = evaluate(
            _namespace(
                "audio-validation", data_root=str(data), extended_catalog=str(extended_catalog),
                writable_path=[str(data)],
            ),
            which=fake_which,
            system_name="Linux",
        )
        assert extended_validation["classification"] == "READY", extended_validation
        ambiguous_validation = evaluate(
            _namespace(
                "audio-validation", data_root=str(data), seal=str(seal),
                extended_catalog=str(extended_catalog),
            ),
            which=fake_which,
            system_name="Linux",
        )
        assert ambiguous_validation["classification"] == "NOT_READY", ambiguous_validation

        builder = evaluate(
''', 1)
text = text.replace('    result.add_argument("--seal")\n    result.add_argument("--dns-data-root")\n', '    result.add_argument("--seal")\n    result.add_argument("--extended-catalog")\n    result.add_argument("--dns-data-root")\n', 1)
if '--extended-catalog' not in text:
    raise SystemExit('runner preflight patch did not apply')
path.write_text(text, encoding='utf-8')
print('extended audio-validation preflight mode applied')
