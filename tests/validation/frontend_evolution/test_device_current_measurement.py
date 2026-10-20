"""D48 measurement contract: old scoring statements and common fields stay exact."""
import ast
import builtins
import inspect
import symtable
import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch
from tools.codex_assets import device_current_measurement as gate
from tools.codex_assets import device_noise_conditioned_protection as previous


class CurrentMeasurementTests(unittest.TestCase):
    def test_formal_output_requires_explicit_run_and_fixed_new_root(self):
        with patch('sys.argv',['tool','--output-root','/tmp/audio-fe-device-current-measurement-d48-20261013']),patch.object(gate,'preflight',side_effect=AssertionError('must reject before input reads')):
            with self.assertRaises(ValueError):gate.main()
        with tempfile.TemporaryDirectory(prefix='audio-d48-root-') as name:
            root=Path(name);alias=root/'alias';alias.symlink_to(root)
            with patch.object(gate,'preflight',side_effect=AssertionError('must reject before input reads')):
                for target in (root,alias,alias/'new',Path('/var/audio-d48'),Path('/tmp/audio-d48-unapproved-new-root')):
                    with self.subTest(target=str(target)):
                        with self.assertRaises(ValueError):gate.run(target)

    def test_dry_run_and_default_cannot_call_formal_run(self):
        for argv in (['tool'],['tool','--dry-run']):
            with patch('sys.argv',argv),patch.object(gate,'preflight',return_value=([],{})),patch.object(gate,'run',side_effect=AssertionError('readonly path must not execute')),patch('builtins.print') as output:
                self.assertEqual(gate.main(),0)
                self.assertEqual(output.call_count,1)

    def test_observer_dependencies_resolve_in_all_branches(self):
        table=symtable.symtable(inspect.getsource(gate.observe),'observe','exec')
        available=set(vars(gate))|set(vars(builtins))
        def verify(scope):
            for symbol in scope.get_symbols():
                if symbol.is_global() and symbol.is_referenced():
                    self.assertIn(symbol.get_name(),available)
            for child in scope.get_children():verify(child)
        verify(table)

    def test_common_projection_keeps_every_scoring_and_control_field(self):
        common={key:object() for key in gate.COMMON_OBSERVATION_FIELDS}
        old=dict(common,noise_conditioned_floor_monotone=True)
        new=dict(common,historical_floor_diagnostic={'monotone':False})
        self.assertEqual(gate.common_observation(old),gate.common_observation(new))
        for key in common:
            invalid=dict(new);del invalid[key]
            with self.assertRaises(ValueError):gate.common_observation(invalid)
        with self.assertRaises(ValueError):gate.common_observation(dict(new,unexpected=1))
        with self.assertRaises(ValueError):gate.common_observation(common)

    def test_statistical_and_control_statements_are_the_frozen_old_contract(self):
        old=ast.parse(inspect.getsource(previous.observe)).body[0]
        new=ast.parse(inspect.getsource(gate.observe)).body[0]
        dump=lambda value:ast.dump(value,include_attributes=False)
        # The entire waveform/statistics/control prefix is copied exactly.
        self.assertEqual([dump(x) for x in old.body[:-3]],
                         [dump(x) for x in new.body[:-6]])
        old_loop=old.body[-2];new_loop=new.body[-2]
        self.assertIsInstance(old_loop,ast.For);self.assertIsInstance(new_loop,ast.For)
        self.assertEqual(dump(old_loop.target),dump(new_loop.target))
        self.assertEqual(dump(old_loop.iter),dump(new_loop.iter))
        self.assertEqual([dump(x) for x in old_loop.body[:-2]],
                         [dump(x) for x in new_loop.body[:-6]])
        self.assertEqual(dump(old_loop.body[-1]),dump(new_loop.body[-1]))
        old_require=old_loop.body[-2].value;new_require=new_loop.body[-6].value
        self.assertIsInstance(old_require.args[0],ast.BoolOp)
        self.assertEqual(dump(old_require.args[0].values[0]),dump(new_require.args[0]))
        old_return=old.body[-1].value;new_return=new.body[-1].value
        old_fields={k.arg:dump(k.value) for k in old_return.keywords}
        new_fields={k.arg:dump(k.value) for k in new_return.keywords}
        self.assertEqual({k:old_fields[k] for k in gate.COMMON_OBSERVATION_FIELDS},
                         {k:new_fields[k] for k in gate.COMMON_OBSERVATION_FIELDS})
        self.assertEqual(set(old_fields)-gate.COMMON_OBSERVATION_FIELDS,{'noise_conditioned_floor_monotone'})
        self.assertEqual(set(new_fields)-gate.COMMON_OBSERVATION_FIELDS,{'historical_floor_diagnostic'})


if __name__=='__main__':unittest.main()
