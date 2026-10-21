"""D49 formal control negative cases; fixtures carry no acoustic claims."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from tools.codex_assets import device_magnitude_lower_bound_matrix as matrix


class Identities(unittest.TestCase):
    def baseline(self):
        cases = [dict(name='synthetic-contract-'+str(i)) for i in range(46)]
        names = [mode+'-'+arm+'-'+c['name'] for c in cases
                 for arm in ('primary', 'selected') for mode in ('monitor', 'candidate')]
        result = dict(experiment='FE_DEVICE_CURRENT_MEASUREMENT_D48',
                      decision='MEASUREMENT_CONTRACT_VERIFIED_NO_PROMOTION',
                      measurement_only=True, executions=184, frames=505944,
                      data_role='development-and-synthetic-engineering',
                      promotion_allowed=False, shipping_approved=False,
                      development_admission=dict(accepted=False,
                          arms={a: dict(accepted=False) for a in ('primary', 'selected')}),
                      cases=[dict(name=n) for n in names])
        binding = dict(source_input_start_end_equal=True,
                       locked_files={str(i): '0'*64 for i in range(11744)},
                       artifacts={str(i): '0'*64 for i in range(1884)})
        return result, binding, cases

    def test_correct_measurement_baseline_contract(self):
        matrix.baseline_contract(*self.baseline())

    def test_wrong_decision_or_data_role_rejected(self):
        for key, value in [('decision', 'DEVELOPMENT_REJECTED'),
                           ('measurement_only', False), ('data_role', 'blind'),
                           ('promotion_allowed', True), ('shipping_approved', True),
                           ('frames', 505943)]:
            with self.subTest(key=key):
                result, binding, cases = self.baseline()
                result[key] = value
                with self.assertRaises(ValueError):
                    matrix.baseline_contract(result, binding, cases)

    def test_acceptance_or_missing_cases_rejected(self):
        for change in ('accepted', 'arm', 'case', 'artifact', 'input', 'end'):
            with self.subTest(change=change):
                result, binding, cases = self.baseline()
                if change == 'accepted': result['development_admission']['accepted'] = True
                elif change == 'arm': result['development_admission']['arms']['selected']['accepted'] = True
                elif change == 'case': result['cases'].pop()
                elif change == 'artifact': binding['artifacts'].pop('0')
                elif change == 'input': binding['locked_files'].pop('0')
                else: binding['source_input_start_end_equal'] = False
                with self.assertRaises(ValueError):
                    matrix.baseline_contract(result, binding, cases)

    def test_hash_conflict_never_overwrites_old_identity(self):
        locks = {}
        matrix.add_identity(locks, Path('/tmp/d49-contract-file'), 'a'*64)
        matrix.add_identity(locks, Path('/tmp/d49-contract-file'), 'a'*64)
        with self.assertRaisesRegex(ValueError, 'conflicting input SHA'):
            matrix.add_identity(locks, Path('/tmp/d49-contract-file'), 'b'*64)
        self.assertEqual(locks, {'/tmp/d49-contract-file': 'a'*64})

    def test_relative_and_invalid_hash_rejected(self):
        for path, digest in [(Path('relative'), 'a'*64), (Path('/tmp/a'), 'z'*64),
                             (Path('/tmp/a'), '0'*63)]:
            with self.assertRaises(ValueError):
                matrix.add_identity({}, path, digest)


class RootAndDiagnostics(unittest.TestCase):
    def test_existing_and_symlink_roots_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            existing = parent/'existing';existing.mkdir()
            link = parent/'link';link.symlink_to(parent/'missing', target_is_directory=True)
            parent_link = parent/'parent-link';parent_link.symlink_to(parent, target_is_directory=True)
            for root in (existing, link, parent_link/'new'):
                with self.subTest(root=str(root)), mock.patch.object(matrix, 'FORMAL_ROOT', root):
                    with self.assertRaisesRegex(ValueError, 'fixed new direct /tmp root'):
                        matrix.root_guard(root)

    def test_noncanonical_root_rejected_without_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'other'
            with self.assertRaises(ValueError): matrix.root_guard(path)
            self.assertFalse(path.exists())

    def test_floor_changes_allowed_but_raw_current_drift_rejected(self):
        previous = dict(power=[dict(frame='0', current_residual_sum='1',
            current_innovation_sum='4', prediction_overshoot_bins='1',
            floor_mean='1', raised_bins='0')],
            bins=[dict(frame='0', floor='1', combined_gain_after='1', noise='0')])
        current = copy.deepcopy(previous)
        current['power'][0].update(floor_mean='0', raised_bins='1')
        current['bins'][0].update(floor='0', combined_gain_after='.2')
        matrix.baseline_trace(current, previous)
        for key in matrix.d47.CURRENT_FIELDS:
            mutated = copy.deepcopy(current);mutated['power'][0][key] = '999'
            with self.subTest(key=key), self.assertRaises(ValueError):
                matrix.baseline_trace(mutated, previous)
        mutated = copy.deepcopy(current);mutated['bins'][0]['noise'] = '1'
        with self.assertRaises(ValueError): matrix.baseline_trace(mutated, previous)


if __name__ == '__main__':
    unittest.main()
