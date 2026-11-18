#!/usr/bin/env python3
"""Metadata-only known-source development quarantine; no audio evaluation."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'validation/tools'))
import authority
import tuning_iteration as tuning
import tuning_iteration_engine as engine
import tuning_replay as replay


sys.path.insert(0, str(ROOT / "scripts"))
import docs_consistency


class EngineAuthorityBoundary(unittest.TestCase):
    def test_shared_admission_only(self):
        good = ('from authority import enforce_corpus_source_role\n'
                'def enforce_partition_independence(dev, validation, shadow):\n'
                '    enforce_corpus_source_role(dev, "development")\n')
        check = docs_consistency.private_engine_authority_ok
        self.assertTrue(check(good, True))
        self.assertFalse(check(good, False))
        self.assertTrue(check('value = 1', False))
        for bad in (
                good.replace('enforce_corpus_source_role\n', 'tier_spec\n'),
                good.replace('enforce_corpus_source_role\n', 'enforce_corpus_source_role, tier_spec\n'),
                good.replace('from authority import enforce_corpus_source_role', 'import authority'),
                good.replace('from authority import enforce_corpus_source_role', 'from authority import enforce_corpus_source_role as guard'),
                good.replace('from authority import', 'from .authority import'),
                good.replace('"development"', '"validation"'),
                good.replace('    enforce_corpus_source_role(dev, "development")', '    pass'),
                good + 'enforce_corpus_source_role = lambda *a: None\n',
                good + 'def enforce_corpus_source_role(*args): pass\n',
                good + 'from authority import *\n',
                good + 'from authority.policy import tier_spec\n',
                good.replace('from authority import', 'from authority.policy import'),
                good.replace('(dev, validation, shadow)', '(dev, validation, enforce_corpus_source_role)'),
                good + 'import other as enforce_corpus_source_role\n',
                good + 'from other import thing as enforce_corpus_source_role\n'):
            with self.subTest(source=bad):
                self.assertFalse(check(bad, True))
        self.assertTrue(check((ROOT / 'validation/tools/tuning_iteration_engine.py').read_text(), True))


class SourceRoles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.paths = [self.root / (role + '.json') for role in ('development', 'validation', 'shadow')]
        self.data = []
        for i, role in enumerate(('development', 'validation', 'shadow')):
            self.data.append({'schema_version': 1, 'corpus_id': 'independent-' + role,
                'tier': 'research-validation', 'generator': {'seed': i},
                'sources': ['synthetic'], 'cases': [{'case_id': role, 'split': role, 'source': {'dataset_id': 'synthetic'}}]})
        self.save()
        self.checks = {
            'authority': lambda: authority.validate_optimizer_partitions(authority.load_authority(), *self.paths),
            'frontdoor': lambda: tuning.enforce_optimizer_authority(*self.paths),
            'strict': lambda: tuning.strict_partition_independence(*self.paths),
            'engine': lambda: engine.enforce_partition_independence(*self.paths),
            'replay': lambda: replay.enforce_role(self.paths[0], 'development'),
        }

    def save(self):
        for path, data in zip(self.paths, self.data):
            path.write_text(json.dumps(data))

    def reject_all(self):
        self.save()
        for name, check in self.checks.items():
            with self.subTest(entry=name):
                with self.assertRaisesRegex(ValueError, 'known AEC source'):
                    check()

    def test_top_level_and_case_sources_all_entries(self):
        for identity in ('microsoft-aec-challenge', 'microsoft-aec-challenge-hosted-real'):
            for composition in (identity, identity + '+other', 'other+' + identity,
                                'other+' + identity + '+third'):
                for location in ('top', 'case'):
                    with self.subTest(identity=composition, location=location):
                        self.data[0]['sources'] = [composition] if location == 'top' else ['synthetic']
                        self.data[0]['cases'][0]['source'] = {'dataset_id': composition} if location == 'case' else {'dataset_id': 'synthetic'}
                        self.reject_all()

    def test_erased_or_empty_source_identity_is_not_development(self):
        original = copy.deepcopy(self.data[0])
        mutations = [
            lambda c: c.pop('sources'), lambda c: c.update(sources=[]),
            lambda c: c.update(sources=['']), lambda c: c.update(sources=['  ']),
            lambda c: c.update(sources=['synthetic+']),
            lambda c: c.update(sources=[' microsoft-aec-challenge']),
            lambda c: c['cases'][0]['source'].update(dataset_id='synthetic+ microsoft-aec-challenge'),
            lambda c: c.update(sources=None), lambda c: c.update(sources='synthetic'),
            lambda c: c['cases'].append({'case_id': 'late-missing-source'}),
            lambda c: c['cases'][0].pop('source'),
            lambda c: c['cases'][0].update(source=None),
            lambda c: c['cases'][0]['source'].pop('dataset_id'),
            lambda c: c['cases'][0]['source'].update(dataset_id=''),
            lambda c: c['cases'][0]['source'].update(dataset_id='synthetic++other'),
        ]
        for mutate in mutations:
            self.data[0] = copy.deepcopy(original)
            mutate(self.data[0]); self.save()
            for name, check in self.checks.items():
                with self.subTest(entry=name, corpus=self.data[0]), self.assertRaises(ValueError):
                    check()
            # This is optimizer admission, not a new validation/shadow requirement.
            replay.enforce_role(self.paths[0], 'validation')
            replay.enforce_role(self.paths[0], 'shadow')

    def test_legacy_builder_identity_all_entries(self):
        for name in ('build_aec_research_corpus.py', 'build_hosted_aec_corpus.py'):
            with self.subTest(generator=name):
                self.data[0]['generator']['name'] = name
                self.reject_all()

    def test_rename_seed_hash_and_claimed_train_do_not_admit(self):
        self.data[0]['corpus_id'] = 'renamed-free-development'
        self.data[0]['generator']['seed'] = 987654
        self.data[0]['sources'] = ['microsoft-aec-challenge']
        self.data[0]['test_recording_ids_excluded'] = True
        self.data[0]['source_manifest_sha256'] = 'a' * 64
        self.data[0]['cases'][0]['source'] = {'dataset_id': 'microsoft-aec-challenge',
            'source_partition': 'datasets/real', 'training_verified': True}
        self.reject_all()

    def test_non_aec_and_nearby_names_remain_admissible(self):
        for name in ('synthetic', 'openslr-slr31+but-reverbdb+musan',
                     'not-microsoft-aec-challenge', 'microsoft-aec-challenge-unrelated'):
            with self.subTest(source=name):
                self.data[0]['sources'] = [name]
                self.data[0]['cases'][0]['source'] = {'dataset_id': name}
                self.save()
                for check in self.checks.values(): check()

    def test_validation_and_shadow_role_behavior_unchanged(self):
        for index in (1, 2):
            self.data[index]['sources'] = ['microsoft-aec-challenge']
            self.data[index]['cases'][0]['source'] = {'dataset_id': 'microsoft-aec-challenge-hosted-real'}
        self.save()
        for check in self.checks.values(): check()
        for index, role in ((1, 'validation'), (2, 'shadow')):
            self.assertEqual(replay.enforce_role(self.paths[index], role), 'research-validation')

    def test_original_tier_restrictions_remain(self):
        self.data[0]['tier'] = 'validation-grade-blind'; self.save()
        for check in self.checks.values():
            with self.assertRaises(ValueError): check()

    def test_malformed_source_declarations_fail(self):
        initial = copy.deepcopy(self.data[0])
        for change in ({'sources': 'microsoft-aec-challenge'}, {'sources': [42]},
                       {'cases': [{} , 42]}, {'cases': [{'source': []}]},
                       {'cases': [{'source': {'dataset_id': 42}}]}, {'generator': []}):
            with self.subTest(change=change):
                self.data[0] = dict(initial, **change); self.save()
                with self.assertRaises(ValueError):
                    authority.enforce_corpus_source_role(self.paths[0], 'development')


if __name__ == '__main__':
    unittest.main(verbosity=2)
