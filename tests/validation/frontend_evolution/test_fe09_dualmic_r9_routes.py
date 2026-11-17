#!/usr/bin/env python3
"""Execute only existing shell version selectors; never invoke collectors/builds."""
from pathlib import Path
import re
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[3]
REL = 'tests/validation/frontend_evolution/'


def run_selector(body, variable, version, suffix):
    return subprocess.run(['bash', '-eu', '-c', variable + '="$1"\n' + body + '\n' + suffix,
                           'source-selector', version], capture_output=True, text=True,
                          timeout=5, check=False)


class R9VersionRouting(unittest.TestCase):
    def test_b3_f0_exact_versions_and_unknown_rejection(self):
        text = (ROOT / '.github/workflows/quality.yml').read_text()
        bodies = re.findall(r'          case "\$version" in\n.*?\n          esac', text, re.S)
        self.assertEqual(len(bodies), 2)
        known = [('2.3.56', '', 'original-v1'),
                 ('2.3.57', '_r2', 'forward-r2'), ('2.3.58', '_r2', 'forward-r2'),
                 ('2.3.59', '_r3', 'forward-r3'), ('2.3.60', '_r4', 'forward-r4'),
                 ('2.3.61', '_r5_path_r1', 'forward-r5-path-r1'),
                 ('2.3.62', '_r6', 'forward-r6-dualmic-v1'),
                 ('2.3.63', '_r7', 'forward-r7-dualmic-v1'),
                 ('2.3.64', '_r9', 'forward-r9-dualmic-v1')]
        for body, prefix in zip(bodies, ('fe09_b3_f0_deadline', 'fe09_t3s3_f0_call_resource')):
            for version, infix, kind in known:
                with self.subTest(prefix=prefix, version=version):
                    if prefix == 'fe09_b3_f0_deadline' and version == '2.3.56':
                        infix, kind = '_r1', 'deadline-r1'
                    result = run_selector(body, 'version', version, 'printf "%s\\n%s\\n" "$script" "$source_kind"')
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.splitlines(), [REL + prefix + infix + '_qualification.py', kind])
            for version in ('2.3.65', '2.3.64-rc', '3.0.0', 'unknown'):
                with self.subTest(prefix=prefix, unknown=version):
                    result = run_selector(body, 'version', version, 'printf "UNREACHABLE\\n"')
                    self.assertEqual(result.returncode, 2)
                    self.assertNotIn('UNREACHABLE', result.stdout)

    def test_f1_a3_keep_r6_and_select_distinct_successors(self):
        text = (ROOT / '.github/scripts/verify-docs-gate.sh').read_text()
        match = re.search(r'case "\$source_version" in\n.*?\nesac', text, re.S)
        self.assertIsNotNone(match)
        for version, revision in (('2.3.61', 'r2'), ('2.3.62', 'r3'), ('2.3.63', 'r4'), ('2.3.64', 'r6')):
            with self.subTest(version=version):
                result = run_selector(match.group(), 'source_version', version,
                                      'printf "%s\\n%s\\n%s\\n" "$f1_source" "$f1_build" "$a3_static"')
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.splitlines(), [REL + 'fe09_f1_' + revision + '_source_bridge.py',
                    REL + 'fe09_f1_' + revision + '_build.py', REL + 'fe09_a3_' + ('r5' if version == '2.3.64' else revision) + '_static_build.py'])


if __name__ == '__main__':
    unittest.main()
