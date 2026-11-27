"""Copy only admitted spatial source files out of one pinned CAS artifact.

Metadata parsing reuses the unchanged original CAS implementation. This module
never unpacks the scientific result tree and never admits source bytes itself;
speech_pinned_snapshot subsequently calls speech_spatial_weights.source_check.
"""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import stat
import tempfile
import zipfile

from contracts import ROOT
from speech_source_cache_profiles import SPATIAL, require_profile

PREFIX = 'effects/data/'
MAX_SOURCE_FILES = 128
MAX_SOURCE_BYTES = 80000000


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def transport_reader():
    path = ROOT / '.github/scripts/ci_evidence_transport.py'
    need(hashlib.sha256(path.read_bytes()).hexdigest() == SPATIAL.transport_tool_sha256,
         'PINNED_CAS_READER_SOURCE_CHANGED')
    spec = importlib.util.spec_from_file_location('_spatial_source_cas_reader', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def outer_members(z, profile=SPATIAL):
    """Format/identity check; no copying or source admission."""
    p = require_profile(profile)
    entries = z.infolist()
    need(len(entries) == 2 and {i.filename for i in entries} == {'evidence.zip', 'transport.json'}
         and not z.comment, 'CAS_OUTER_EXACT_MEMBER_SET')
    for item in entries:
        need(not item.is_dir() and stat.S_IFMT(item.external_attr >> 16) == stat.S_IFREG
             and not item.flag_bits & 1 and item.compress_type == zipfile.ZIP_STORED,
             'CAS_OUTER_TYPE_OR_ENCODING')
    need(z.getinfo('evidence.zip').file_size == p.inner_bytes
         and 0 < z.getinfo('transport.json').file_size <= 32768,
         'CAS_OUTER_SIZE_LIMIT')


def source_rows(z, record, reader, profile=SPATIAL):
    """Strict CAS manifest/object metadata, returning only source rows.

This pure parser can test tiny formats; it neither establishes the pinned
outer/inner byte identity nor authorizes arbitrary manifest source contents.
"""
    p = require_profile(profile)
    entries = z.infolist()
    need(0 < len(entries) <= reader.MAX_FILES + 1 and not z.comment,
         'CAS_INNER_COUNT_OR_COMMENT')
    seen = set()
    for item in entries:
        need(item.filename not in seen and not item.is_dir()
             and stat.S_IFMT(item.external_attr >> 16) == stat.S_IFREG
             and not item.flag_bits & 1 and item.compress_type == zipfile.ZIP_DEFLATED
             and 0 <= item.file_size <= reader.MAX_FILE_BYTES,
             'CAS_INNER_MEMBER_TYPE_OR_SIZE')
        need(item.filename == 'manifest.json' or
             (item.filename.startswith('objects/') and reader.SHA.fullmatch(item.filename[8:])),
             'CAS_INNER_OBJECT_PATH')
        seen.add(item.filename)
    need('manifest.json' in seen and 0 < z.getinfo('manifest.json').file_size <= reader.MAX_MANIFEST_BYTES,
         'CAS_MANIFEST_MISSING_OR_UNBOUNDED')
    raw = z.read('manifest.json')
    need(hashlib.sha256(raw).hexdigest() == record.get('manifest_sha256'), 'CAS_MANIFEST_DIGEST')
    manifest = reader.parse_json(raw, reader.MAX_MANIFEST_BYTES)
    groups = reader.validate_manifest(manifest, p.origin_main, str(p.verify_run))
    need(manifest['tool_sha256'] == p.transport_tool_sha256, 'CAS_TOOL_IDENTITY')
    need(seen == {'manifest.json'} | {'objects/' + sha for sha in groups},
         'CAS_OBJECT_MEMBERSHIP')
    for sha, rows in groups.items():
        need(z.getinfo('objects/' + sha).file_size == rows[0]['bytes'], 'CAS_OBJECT_DECLARED_SIZE')
    for key, value in {'files':len(manifest['files']), 'unique_blobs':len(groups),
                       'logical_bytes':manifest['logical_bytes'], 'unique_bytes':manifest['unique_bytes']}.items():
        need(type(record.get(key)) is int and record[key] == value, 'CAS_SIDECAR_TOTALS')
    ordinary = 22 + sum(z.getinfo('objects/' + row['sha256']).compress_size +
                       76 + 2 * len(row['path'].encode('utf-8')) for row in manifest['files'])
    need(type(record.get('equivalent_regular_zip_bytes')) is int and
         record['equivalent_regular_zip_bytes'] == ordinary, 'CAS_SIZE_ACCOUNTING')
    selected = [row for row in manifest['files'] if row['path'].startswith(PREFIX)]
    need(12 <= len(selected) <= MAX_SOURCE_FILES and
         sum(row['bytes'] for row in selected) <= MAX_SOURCE_BYTES, 'CAS_SOURCE_SUBSET_BOUND')
    names = set()
    for row in selected:
        relative = row['path'][len(PREFIX):]
        need(relative and not relative.startswith('.') and len(relative.split('/')) <= 2
             and ('/' not in relative or relative.startswith('flac/')), 'CAS_SOURCE_TREE_DEPTH')
        names.add(relative)
    need({'source-receipt.json','ATTRIBUTION.txt','LICENSE.TXT','README.TXT','SPEAKERS.TXT'} <= names,
         'CAS_SOURCE_NOTICES_MISSING')
    return selected


def validate_sidecar(record, reader, profile=SPATIAL):
    p = require_profile(profile)
    need(set(record) == {'schema','authority','execution_source','run_id','manifest_sha256',
         'archive_sha256','archive_bytes','files','unique_blobs','logical_bytes','unique_bytes',
         'equivalent_regular_zip_bytes','wire_or_billing_measurement'}, 'CAS_SIDECAR_FIELDS')
    need(record['schema'] == reader.SCHEMA and record['authority'] == 'BYTE_TRANSPORT_ONLY'
         and record['execution_source'] == p.origin_main and record['run_id'] == str(p.verify_run)
         and record['wire_or_billing_measurement'] is False
         and type(record['archive_bytes']) is int and record['archive_bytes'] == p.inner_bytes
         and record['archive_sha256'] == p.inner_sha256
         and record['manifest_sha256'] == p.manifest_sha256, 'CAS_SIDECAR_PINNED_IDENTITY')


def copy_source(archive: Path, scratch: Path, profile=SPATIAL):
    """Called only after the outer ZIP exact byte identity has been checked."""
    p = require_profile(profile)
    need(scratch.is_dir() and not scratch.is_symlink() and not any(scratch.iterdir()),
         'CAS_SOURCE_SCRATCH_NOT_FRESH')
    reader = transport_reader()
    with zipfile.ZipFile(archive) as outer, tempfile.TemporaryDirectory(
            prefix='.spatial-cas-', dir=scratch.parent) as temp:
        outer_members(outer, p)
        raw = outer.read('transport.json')
        record = reader.parse_json(raw, reader.MAX_RECEIPT_BYTES)
        validate_sidecar(record, reader, p)
        inner = Path(temp) / 'evidence.zip'
        count, digest = 0, hashlib.sha256()
        with outer.open('evidence.zip') as source, inner.open('xb') as target:
            for block in iter(lambda: source.read(1024 * 1024), b''):
                count += len(block); need(count <= p.inner_bytes, 'CAS_INNER_OVERFLOW')
                digest.update(block); target.write(block)
        need(count == p.inner_bytes and digest.hexdigest() == p.inner_sha256, 'CAS_INNER_DIGEST')
        with zipfile.ZipFile(inner) as z:
            selected = source_rows(z, record, reader, p)
            need(p.inner_bytes + len(raw) <= record['equivalent_regular_zip_bytes'], 'CAS_COMPRESSED_SIZE_REGRESSION')
            for row in selected:
                relative = row['path'][len(PREFIX):]
                target = scratch / relative
                need(target.resolve().is_relative_to(scratch.resolve()), 'CAS_SOURCE_PATH_ESCAPE')
                target.parent.mkdir(exist_ok=True)
                count, digest = 0, hashlib.sha256()
                with z.open('objects/' + row['sha256']) as source, target.open('xb') as destination:
                    for block in iter(lambda: source.read(1024 * 1024), b''):
                        count += len(block); need(count <= row['bytes'], 'CAS_SOURCE_OBJECT_OVERFLOW')
                        digest.update(block); destination.write(block)
                need(count == row['bytes'] and digest.hexdigest() == row['sha256'], 'CAS_SOURCE_OBJECT_DIGEST')
                target.chmod(row['mode'])
        need(hashlib.sha256((scratch/'source-receipt.json').read_bytes()).hexdigest() == p.source_receipt_sha256,
             'CAS_ORIGINAL_SOURCE_RECEIPT_CHANGED')
