#!/usr/bin/env python3
from pathlib import Path

path = Path('.github/research/continuous-optimization/hosted-validation/prepare_full_validation.py')
text = path.read_text(encoding='utf-8')


def replace_once(old: str, new: str, label: str) -> None:
    global text
    if old not in text:
        raise SystemExit(f'progress patch anchor missing: {label}')
    text = text.replace(old, new, 1)


replace_once(
    '''def load_json(path: Path) -> dict:\n    return json.loads(path.read_text(encoding="utf-8"))\n\n\n''',
    '''def load_json(path: Path) -> dict:\n    return json.loads(path.read_text(encoding="utf-8"))\n\n\ndef write_progress(path: Path | None, stage: str, status: str = "in_progress", **details: object) -> None:\n    if path is None:\n        return\n    payload = {"schema_version": 1, "stage": stage, "status": status, **details}\n    path.parent.mkdir(parents=True, exist_ok=True)\n    temporary = path.with_name(path.name + ".tmp")\n    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\\n", encoding="utf-8")\n    temporary.replace(path)\n\n\n''',
    'write_progress helper',
)

replace_once(
    '''def bootstrap(source_root: Path, data_root: Path, seal: Path,\n              archive_lock_path: Path, output: Path, aec_limit: int) -> dict:\n    if aec_limit <= 0:\n''',
    '''def bootstrap(source_root: Path, data_root: Path, seal: Path,\n              archive_lock_path: Path, output: Path, aec_limit: int,\n              progress_output: Path | None = None) -> dict:\n    write_progress(progress_output, "bootstrap-init")\n    if aec_limit <= 0:\n''',
    'bootstrap signature',
)

replace_once(
    '''    data_root.mkdir(parents=True, exist_ok=True)\n    aec_evidence = materialize_aec(source_root, source_lock_path, data_root, aec, aec_limit)\n\n    slr_item = archive_by_role(hosted_lock, "slr28")\n''',
    '''    data_root.mkdir(parents=True, exist_ok=True)\n    write_progress(progress_output, "aec-materialization")\n    aec_evidence = materialize_aec(source_root, source_lock_path, data_root, aec, aec_limit)\n    write_progress(progress_output, "aec-materialization", "success",\n                   materialized_files=aec_evidence["materialized_files"])\n\n    write_progress(progress_output, "slr28-materialization")\n    slr_item = archive_by_role(hosted_lock, "slr28")\n''',
    'AEC/SLR stage',
)

replace_once(
    '''    run([\n        sys.executable, str(source_root / "validation/tools/dataset_lock.py"), "seal",\n        "--lock", str(source_lock_path), "--seal", str(seal),\n        "--dataset-id", "openslr-slr28", "--asset", str(slr_path),\n    ], cwd=source_root)\n\n    fetch = source_root / "validation/tools/fetch_public_data.py"\n''',
    '''    run([\n        sys.executable, str(source_root / "validation/tools/dataset_lock.py"), "seal",\n        "--lock", str(source_lock_path), "--seal", str(seal),\n        "--dataset-id", "openslr-slr28", "--asset", str(slr_path),\n    ], cwd=source_root)\n    write_progress(progress_output, "slr28-materialization", "success",\n                   bytes=slr_path.stat().st_size, sha256=digest_file(slr_path))\n\n    write_progress(progress_output, "dns-checkout")\n    fetch = source_root / "validation/tools/fetch_public_data.py"\n''',
    'SLR/DNS checkout stage',
)

replace_once(
    '''    dns_head = run(["git", "-C", str(dns_repo), "rev-parse", "HEAD"], capture=True).strip()\n    if dns_head != hosted_lock["dns_revision"]:\n        raise ValueError("materialized DNS repository revision mismatch")\n\n    archive_dir = data_root / "github-hosted-dns-archives"\n''',
    '''    dns_head = run(["git", "-C", str(dns_repo), "rev-parse", "HEAD"], capture=True).strip()\n    if dns_head != hosted_lock["dns_revision"]:\n        raise ValueError("materialized DNS repository revision mismatch")\n    write_progress(progress_output, "dns-checkout", "success", revision=dns_head)\n\n    archive_dir = data_root / "github-hosted-dns-archives"\n''',
    'DNS checkout completion',
)

replace_once(
    '''    archive_evidence = []\n    for role in ("dns-clean", "dns-noise"):\n        item = archive_by_role(hosted_lock, role)\n''',
    '''    archive_evidence = []\n    for role in ("dns-clean", "dns-noise"):\n        write_progress(progress_output, f"{role}-archive")\n        item = archive_by_role(hosted_lock, role)\n''',
    'DNS archive stage start',
)

replace_once(
    '''        archive_evidence.append({\n            "id": item["id"], "role": role, "bytes": actual_size,\n            "sha256": actual_sha, "url": item["url"], "wav_count": moved,\n        })\n\n    clean, noise, total = dns_counts(dns_root)\n''',
    '''        archive_evidence.append({\n            "id": item["id"], "role": role, "bytes": actual_size,\n            "sha256": actual_sha, "url": item["url"], "wav_count": moved,\n        })\n        write_progress(progress_output, f"{role}-archive", "success",\n                       bytes=actual_size, sha256=actual_sha, wav_count=moved)\n\n    clean, noise, total = dns_counts(dns_root)\n''',
    'DNS archive completion',
)

replace_once(
    '''    derived_index = data_root / "dns5-hosted-minimal-sha1.csv.bz2"\n    index_rows = write_derived_dns_index(dns_root, derived_index)\n''',
    '''    write_progress(progress_output, "dns-index")\n    derived_index = data_root / "dns5-hosted-minimal-sha1.csv.bz2"\n    index_rows = write_derived_dns_index(dns_root, derived_index)\n    write_progress(progress_output, "dns-index", "success", rows=index_rows)\n''',
    'DNS index stage',
)

replace_once(
    '''    prepare = source_root / "validation/tools/prepare_public_validation.py"\n    verify_text = run([\n''',
    '''    write_progress(progress_output, "full-cache-verification")\n    prepare = source_root / "validation/tools/prepare_public_validation.py"\n    verify_text = run([\n''',
    'verification stage start',
)

replace_once(
    '''    verification = json.loads(verify_text)\n    report = {\n''',
    '''    verification = json.loads(verify_text)\n    write_progress(progress_output, "full-cache-verification", "success")\n    report = {\n''',
    'verification stage completion',
)

replace_once(
    '''    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\\n", encoding="utf-8")\n    return report\n''',
    '''    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\\n", encoding="utf-8")\n    write_progress(progress_output, "ready", "success",\n                   dns_clean_wavs=clean, dns_noise_wavs=noise, dns_total_wavs=total)\n    return report\n''',
    'ready stage',
)

replace_once(
    '''    parser.add_argument("--output", type=Path)\n    parser.add_argument("--aec-limit", type=int, default=60)\n''',
    '''    parser.add_argument("--output", type=Path)\n    parser.add_argument("--progress-output", type=Path)\n    parser.add_argument("--aec-limit", type=int, default=60)\n''',
    'progress CLI argument',
)

replace_once(
    '''    report = bootstrap(\n        args.source_root, args.data_root, args.seal, args.archive_lock, args.output, args.aec_limit)\n''',
    '''    try:\n        report = bootstrap(\n            args.source_root, args.data_root, args.seal, args.archive_lock, args.output,\n            args.aec_limit, args.progress_output)\n    except Exception as exc:\n        stage = "bootstrap"\n        if args.progress_output is not None and args.progress_output.exists():\n            try:\n                stage = str(load_json(args.progress_output).get("stage", stage))\n            except Exception:\n                pass\n        write_progress(args.progress_output, stage, "failure",\n                       error_type=type(exc).__name__, error=str(exc))\n        raise\n''',
    'main failure capture',
)

path.write_text(text, encoding='utf-8')
