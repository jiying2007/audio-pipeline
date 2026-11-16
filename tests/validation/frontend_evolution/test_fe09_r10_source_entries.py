#!/usr/bin/env python3
"""Source metadata only. Integration mode requires real clean committed2.3.65.
No source_check mocks, build_only, compiler, collector execution or DSP calls.
"""
import argparse
import ast
import hashlib
import inspect
import json
import re
from pathlib import Path
import sys
import fe09_b3_f0_r10_source_admission as source
import fe09_b3_f0_deadline_r10_qualification as b3
import fe09_t3s3_f0_call_resource_r10_qualification as f0
import fe09_f1_r7_source_bridge as f1
import fe09_f1_r7_build as f1_build
import fe09_a3_r6_static_build as a3
ROOT = Path(__file__).resolve().parents[3]
DOCS = ROOT / 'docs/research/frontend-evolution-v1/RUNTIME_2365_SOURCE_R10_20261116'

def need(ok, why):
    if not ok:
        raise ValueError(why)

def metadata_tests():
    checked = []
    for path in [*b3.OWN_FILES, *f0.OWN, *(DOCS / n for n in ('PREREGISTRATION.json','DERIVATION.json','README.md'))]:
        need(path.is_file() and not path.is_symlink(), 'ENTRY_DEPENDENCY_MISSING:' + str(path))
        checked.append(str(path.relative_to(ROOT)))
    # Explicitly check the live function gates and every embedded R10 doc path;
    # this does not substitute for the real integration calls below.
    for function in (b3.source_preflight, f0.source_record):
        constants = [n.value for n in ast.walk(ast.parse(inspect.getsource(function)))
                     if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        need('2.3.65' in constants and '2.3.64' not in constants,
             'ENTRY_VERSION_LITERAL_STALE')
        for text in constants:
            if text.startswith('docs/research/'):
                need((ROOT/text).is_file(), 'ENTRY_DOCUMENT_MISSING:' + text)
    # Constructed A3 header-parser controls, not a generated CMake build receipt.
    header = (b'#define AP_VERSION_STRING "2.3.65"\n'
              b'#define AP_BUILD_MAX_MIC_CHANNELS 2\n#define AP_HAVE_PIPELINE 1\n'
              b'#define AP_BUILD_FAST_MATH 0\n')
    a3.generated_config(header)
    for version in (b'2.3.64', b'2.3.66'):
        try:
            a3.generated_config(header.replace(b'2.3.65', version))
        except a3.Rejected:
            pass
        else:
            raise ValueError('A3_VERSION_NEGATIVE_ACCEPTED')
    return {'status':'R10_ENTRY_METADATA_SELF_TEST_PASS_NO_DSP',
            'dependency_paths':sorted(set(checked)), 'a3_constructed_header_negatives':2,
            'real_current_source_entry_executed':False, 'science_executed':False}

def integration(execution_source):
    metadata_tests()
    # Every call below uses its default real committed/current-source semantics.
    admitted = source.source_check(execution_source)
    need(admitted['candidate_version']=='2.3.65', 'INTEGRATION_VERSION')
    b3_result = b3.source_preflight(execution_source, require_committed=True)
    f0_result = f0.source_record(execution_source, require_committed=True)
    f1_result = f1.check(ROOT)
    f1_build_result = f1_build.source_check(ROOT)
    for receipt in (b3_result['forward_source_admission'], f0_result['forward_source_admission']):
        need(receipt == admitted, 'ENTRY_SOURCE_RECEIPT_DIVERGENCE')
    # Preserve old source rejection of this real new committed candidate.
    try:
        source.previous.source_check(execution_source)
    except source.previous.Reject:
        pass
    else:
        raise ValueError('R9_ACCEPTED_NEW_RUNTIME_SOURCE')
    return {'status':'R10_REAL_COMMITTED_SOURCE_ENTRIES_PASS_NO_DSP',
            'execution_source':execution_source, 'source':admitted,
            'b3':b3_result, 'f0':f0_result, 'f1':f1_result,
            'f1_build_source_only':f1_build_result,
            'old_r9_rejected':True, 'science_executed':False,
            'a3_build_executed':False, 'compiler_invocations':0}

def check_current(execution_source=None):
    current = source.legacy.git("rev-parse", "HEAD").decode().strip()
    need(execution_source is None or execution_source == current, 'CURRENT_HEAD_MISMATCH')
    raw = source.legacy.committed_bytes('CMakeLists.txt')
    match = re.search(rb'(?m)^project\(audio_pipeline VERSION ([0-9]+\.[0-9]+\.[0-9]+) LANGUAGES C\)$', raw)
    need(match is not None, 'CURRENT_VERSION_UNPARSED')
    version = match.group(1).decode()
    if version == '2.3.65':
        return integration(current)
    need(version == '2.3.64', 'UNREGISTERED_ENTRY_VERSION')
    metadata = metadata_tests()
    previous = source.previous.source_check(current)
    return {'status':'R10_265_REAL_ENTRIES_NOT_RUN_CURRENT_PREP_264',
            'execution_source':current, 'current_version':version,
            'current_r9_source_status':previous['status'],
            'entry_metadata_status':metadata['status'],
            'real_265_source_entries_executed':False, 'science_executed':False}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--self-test',action='store_true')
    group.add_argument('--check-integration',action='store_true')
    group.add_argument('--check-current',action='store_true')
    parser.add_argument('--execution-source')
    args=parser.parse_args()
    if args.check_integration and not args.execution_source:
        parser.error('--execution-source required for real integration')
    try:
        value=(metadata_tests() if args.self_test else
               check_current(args.execution_source) if args.check_current else
               integration(args.execution_source))
        print(json.dumps(value,sort_keys=True));return 0
    except Exception as error:
        print('R10_SOURCE_ENTRIES_REJECTED:'+type(error).__name__+':'+str(error),file=sys.stderr)
        return 2
if __name__=='__main__':
    raise SystemExit(main())
