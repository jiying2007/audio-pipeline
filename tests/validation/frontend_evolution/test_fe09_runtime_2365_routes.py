#!/usr/bin/env python3
"""Source-only selectors: preserve old R9 bodies, test full R10 dispatchers."""
import hashlib
import json
import os
import tempfile
from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[3]
REL = 'tests/validation/frontend_evolution/'
SNAPSHOT = 'docs/research/frontend-evolution-v1/RUNTIME_2365_SOURCE_R10_20261116/ROUTE_SNAPSHOT.json'
SNAPSHOT_SHA = 'c4f36a0790cc04eb4dab0c4315308c6a2b6f56a054847bdfeec0ad5c975c1dba'


def selected(body, variable, version, names):
    script = variable + '="$1"\n' + body + '\nprintf "%s\\n" ' + ' '.join('"$' + n + '"' for n in names)
    return subprocess.run(['bash', '-eu', '-c', script, 'route-only', version],
                          capture_output=True, text=True, timeout=5, check=False)


def region(text, name):
    start, end = '# R10_SELECTION_' + name + '_BEGIN', '# R10_SELECTION_' + name + '_END'
    if text.count(start) != 1 or text.count(end) != 1:
        raise AssertionError('dispatcher marker identity')
    return text.split(start, 1)[1].split(end, 1)[0]


class Runtime2365Routes(unittest.TestCase):
    def test_checkout_ownership_sha_resolution(self):
        # Git's real ownership gate, not a mocked rev-parse result. Only the
        # current checkout may be trusted, with no persistent/global setting.
        docs = (ROOT / '.github/scripts/verify-docs-gate.sh').read_text()
        line = '  execution_source=$(git -c "safe.directory=$PWD" rev-parse HEAD)'
        self.assertEqual(docs.count(line), 1)
        self.assertIn('--check-integration --execution-source "$execution_source"', docs)
        with tempfile.TemporaryDirectory(prefix='r10-owner-') as tmp:
            root = Path(tmp)
            env = dict(os.environ)
            for name in tuple(env):
                if name.startswith('GIT_'):
                    del env[name]
            env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
            def git(*args, check=True):
                return subprocess.run(['git', *args], cwd=root, env=env,
                    capture_output=True, text=True, timeout=10, check=check)
            git('init', '-q')
            git('-c', 'user.name=R10 test', '-c', 'user.email=r10@example.invalid',
                'commit', '--allow-empty', '-qm', 'ownership fixture')
            expected = git('rev-parse', 'HEAD').stdout.strip()
            env['GIT_TEST_ASSUME_DIFFERENT_OWNER'] = '1'
            denied = git('rev-parse', 'HEAD', check=False)
            self.assertNotEqual(denied.returncode, 0)
            self.assertIn('dubious ownership', denied.stderr)
            wrong = git('-c', 'safe.directory=' + str(root / 'other'),
                        'rev-parse', 'HEAD', check=False)
            self.assertNotEqual(wrong.returncode, 0)
            actual = subprocess.run(['sh', '-eu', '-c', line +
                '\nprintf "%s\\n" "$execution_source"'], cwd=root, env=env,
                capture_output=True, text=True, timeout=10, check=False)
            self.assertEqual(actual.returncode, 0, actual.stderr)
            self.assertEqual(actual.stdout.strip(), expected)
            self.assertNotEqual(git('rev-parse', 'HEAD', check=False).returncode, 0)

    def test_preserved_r9_selectors(self):
        raw = (ROOT / SNAPSHOT).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), SNAPSHOT_SHA)
        old = json.loads(raw)
        quality = (ROOT / '.github/workflows/quality.yml').read_text()
        bodies = re.findall(r'          case "\$version" in\n.*?\n          esac', quality, re.S)
        self.assertEqual(len(bodies), 2)
        docs = (ROOT / '.github/scripts/verify-docs-gate.sh').read_text()
        bodies.append(re.search(r'case "\$source_version" in\n.*?\nesac', docs, re.S).group())
        for name, body in zip(('b3', 'f0', 'f1_a3'), bodies):
            self.assertEqual(body, old[name]['body'])
            self.assertEqual(hashlib.sha256(body.encode()).hexdigest(), old[name]['sha256'])
        # These are explicitly the historical selector bodies, not the complete
        # new dispatcher tested below. Old B3/F0 still reject future 2.3.65.
        for body in bodies[:2]:
            self.assertEqual(selected(body, 'version', '2.3.65', ('script',)).returncode, 2)

    def test_full_b3_f0_dispatchers(self):
        text = (ROOT / '.github/workflows/quality.yml').read_text()
        old = [('2.3.56', '', 'original-v1'), ('2.3.57', '_r2', 'forward-r2'),
               ('2.3.58', '_r2', 'forward-r2'), ('2.3.59', '_r3', 'forward-r3'),
               ('2.3.60', '_r4', 'forward-r4'), ('2.3.61', '_r5_path_r1', 'forward-r5-path-r1'),
               ('2.3.62', '_r6', 'forward-r6-dualmic-v1'), ('2.3.63', '_r7', 'forward-r7-dualmic-v1'),
               ('2.3.64', '_r9', 'forward-r9-dualmic-v1'), ('2.3.65', '_r10', 'forward-r10-runtime-v1')]
        for tag, prefix in [('B3', 'fe09_b3_f0_deadline'), ('F0', 'fe09_t3s3_f0_call_resource')]:
            body = region(text, tag)
            for version, infix, kind in old:
                if tag == 'B3' and version == '2.3.56':
                    infix, kind = '_r1', 'deadline-r1'
                with self.subTest(tag=tag, version=version):
                    r = selected(body, 'version', version, ('script', 'source_kind'))
                    self.assertEqual(r.returncode, 0, r.stderr)
                    self.assertEqual(r.stdout.splitlines(), [REL + prefix + infix + '_qualification.py', kind])
            for version in ('2.3.66', '2.3.65-rc', '3.0.0', 'unknown', ''):
                self.assertEqual(selected(body, 'version', version, ('script',)).returncode, 2)
        for step in ('fe09_b3_f0', 'fe09_t3s3_f0'):
            self.assertIn("steps." + step + ".outputs.source_kind == 'forward-r10-runtime-v1'", text)
        self.assertEqual(text.count('forward-r10-runtime-v1-${{ github.run_id }}-attempt-${{ github.run_attempt }}'), 2)

    def test_full_f1_a3_dispatcher(self):
        text = (ROOT / '.github/scripts/verify-docs-gate.sh').read_text()
        body = region(text, 'F1_A3')
        for version, f1, a3 in [('2.3.56', 'r2', 'r2'), ('2.3.57', 'r2', 'r2'),
                ('2.3.58', 'r2', 'r2'), ('2.3.59', 'r2', 'r2'), ('2.3.60', 'r2', 'r2'),
                ('2.3.61', 'r2', 'r2'), ('2.3.62', 'r3', 'r3'), ('2.3.63', 'r4', 'r4'),
                ('2.3.64', 'r6', 'r5'), ('2.3.65', 'r7', 'r6')]:
            r = selected(body, 'source_version', version, ('f1_source', 'f1_build', 'a3_static', 'f1_output', 'a3_output'))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(r.stdout.splitlines(), [REL + 'fe09_f1_' + f1 + '_source_bridge.py',
                REL + 'fe09_f1_' + f1 + '_build.py', REL + 'fe09_a3_' + a3 + '_static_build.py',
                'f1-' + f1 + '-t1', 'a3-' + a3 + '-t1'])
        for version in ('2.3.66', '2.3.65-rc', '3.0.0', 'unknown', ''):
            self.assertEqual(selected(body, 'source_version', version, ('f1_source',)).returncode, 2)


if __name__ == '__main__':
    unittest.main()
