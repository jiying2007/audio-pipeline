#!/usr/bin/env python3
"""Exact-byte SpeexDSP source preflight. It never compiles or executes upstream code."""
from __future__ import annotations
import argparse, hashlib, json, os, stat, subprocess
from pathlib import Path
from contracts import ROOT, load_json, require, sha256

LOCK = ROOT / '.github/research/frontend-evolution-v1/speexdsp-source-lock.json'
GENERATED = """#ifndef __SPEEX_TYPES_H__
#define __SPEEX_TYPES_H__
#include <stdint.h>
typedef int16_t spx_int16_t;
typedef uint16_t spx_uint16_t;
typedef int32_t spx_int32_t;
typedef uint32_t spx_uint32_t;
#endif
"""

def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')

def git_blob(data: bytes) -> str:
    return hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()

def run_git(source: Path, *args: str) -> str:
    env={'PATH':os.environ.get('PATH','/usr/bin:/bin'),'LC_ALL':'C','HOME':str(source)}
    p=subprocess.run(['git','-C',str(source),*args],capture_output=True,text=True,env=env,timeout=20,check=False)
    require(p.returncode == 0, 'git identity read failed: ' + ' '.join(args))
    return p.stdout.strip()

def preflight(source: Path, output: Path) -> dict:
    lock=load_json(LOCK); expected=lock['git_blob_sha1']
    require(not output.exists(), 'fresh output required')
    require(source.is_dir() and not source.is_symlink(), 'invalid source directory')
    require(run_git(source,'rev-parse','HEAD') == lock['upstream_commit'], 'upstream commit mismatch')
    require(run_git(source,'rev-parse','HEAD^{tree}') == lock['upstream_tree'], 'upstream tree mismatch')
    output.mkdir(parents=True)
    hashes={}
    for name,wanted in sorted(expected.items()):
        path=source/name
        mode=path.lstat().st_mode
        require(stat.S_ISREG(mode) and not path.is_symlink(), 'non-regular source: '+name)
        data=path.read_bytes()
        require(git_blob(data)==wanted, 'upstream Git blob mismatch: '+name)
        dest=output/'upstream'/name; dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(data)
        hashes[name]=sha256(data)
    generated=output/'generated/include/speex/speexdsp_config_types.h'
    generated.parent.mkdir(parents=True); generated.write_text(GENERATED)
    identity=hashlib.sha256(json.dumps(hashes,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    receipt={
      'schema_version':1,'source_id':'speexdsp','source_commit':lock['upstream_commit'],
      'source_tree':lock['upstream_tree'],'scope':lock['scope'],'rights_review':lock['rights_review'],
      'files_sha256':hashes,'materialized_source_sha256':identity,
      'generated_config_sha256':sha256(generated.read_bytes()),'source_lock_sha256':sha256(LOCK.read_bytes()),
      'file_count':len(hashes),'status':'SOURCE_BYTES_VERIFIED_NOT_EXECUTED','shipping_authority':False
    }
    write_json(output/'source-receipt.json',receipt)
    verify(output)
    return receipt

def verify(output: Path) -> dict:
    lock=load_json(LOCK); receipt=load_json(output/'source-receipt.json')
    require(receipt['source_commit']==lock['upstream_commit'] and receipt['source_tree']==lock['upstream_tree'],'source identity drift')
    require(receipt['scope']==lock['scope'] and receipt['rights_review']==lock['rights_review'],'scope/rights drift')
    require(receipt['source_lock_sha256']==sha256(LOCK.read_bytes()),'lock drift')
    require(receipt['shipping_authority'] is False and receipt['status']=='SOURCE_BYTES_VERIFIED_NOT_EXECUTED','authority drift')
    hashes={}
    for name,wanted in sorted(lock['git_blob_sha1'].items()):
        data=(output/'upstream'/name).read_bytes()
        require(git_blob(data)==wanted,'materialized Git blob mismatch: '+name)
        hashes[name]=sha256(data)
    require(hashes==receipt['files_sha256'] and len(hashes)==receipt['file_count']==16,'materialized source set mismatch')
    identity=hashlib.sha256(json.dumps(hashes,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    require(identity==receipt['materialized_source_sha256'],'materialized source identity drift')
    generated=output/'generated/include/speex/speexdsp_config_types.h'
    require(generated.read_text()==GENERATED and sha256(generated.read_bytes())==receipt['generated_config_sha256'],'generated types drift')
    actual={p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file()}
    expected={'source-receipt.json','generated/include/speex/speexdsp_config_types.h'} | {'upstream/'+x for x in lock['git_blob_sha1']}
    require(actual==expected,'unexpected/missing preflight files')
    return {'status':'VERIFIED_SOURCE_BYTES_NOT_EXECUTED','files':len(hashes),
            'source_commit':receipt['source_commit'],'source_tree':receipt['source_tree'],
            'materialized_source_sha256':identity}

def negative(output: Path) -> dict:
    target=output/'upstream/libspeexdsp/mdf.c'; original=target.read_bytes()
    target.write_bytes(original+b'changed')
    try:
        verify(output)
    except (ValueError,KeyError,AssertionError,RuntimeError):
        rejected=True
    else:
        rejected=False
    target.write_bytes(original)
    require(rejected,'tampered source accepted')
    verify(output)
    return {'status':'PASS','rejected':['source-byte-tamper']}

def main() -> int:
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--verify',action='store_true');p.add_argument('--negative-evidence',action='store_true')
    a=p.parse_args()
    if a.negative_evidence:r=negative(a.output)
    elif a.verify:r=verify(a.output)
    else:
        require(a.source is not None,'source required for preflight')
        r=preflight(a.source,a.output)
    print(json.dumps(r,sort_keys=True,allow_nan=False));return 0
if __name__=='__main__': raise SystemExit(main())
