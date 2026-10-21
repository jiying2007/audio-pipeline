"""D47 preserves the old evaluator and state projections; current energy is separate."""
from pathlib import Path
import hashlib
import struct
import tempfile
import unittest
from unittest.mock import patch
from tools.codex_assets import device_current_innovation as gate


class CurrentInnovationTests(unittest.TestCase):
    def test_preflight_unique_reads_preserve_all_semantic_constraints(self):
        with tempfile.TemporaryDirectory(prefix='audio-d47-input-') as name:
            path=Path(name)/'pcm';raw=struct.pack('<ff',1,2);path.write_bytes(raw)
            digest=hashlib.sha256(raw).hexdigest();inputs=gate.PreflightInputs()
            inputs.add(path,digest);inputs.add(path,digest);seen=[]
            with patch.object(gate,'bounded',wraps=gate.bounded) as reader:
                inputs.verify_all({str(path):[lambda data:seen.append(data),lambda data:gate.pcm_bytes(data,2)]})
                self.assertEqual(reader.call_count,1)
            self.assertEqual(seen,[raw]);self.assertEqual(inputs.checked,inputs.expected)
            self.assertEqual(inputs.expected,{str(path):digest})
            with self.assertRaises(ValueError):inputs.add(path,'0'*64)
            with self.assertRaises(ValueError):inputs.consume(path)
            # A second reference with a conflicting shape must still reject.
            other=gate.PreflightInputs();other.add(path,digest)
            with self.assertRaises(ValueError):
                other.verify_all({str(path):[lambda data:gate.pcm_bytes(data,2),lambda data:gate.pcm_bytes(data,3)]})

    def test_preflight_identity_missing_drift_and_undeclared_inputs(self):
        with tempfile.TemporaryDirectory(prefix='audio-d47-input-') as name:
            path=Path(name)/'missing';inputs=gate.PreflightInputs()
            for bad_path,bad_hash in ((Path('relative'),'0'*64),(path,'A'*64),(path,'0'*63)):
                with self.assertRaises(ValueError):inputs.add(bad_path,bad_hash)
            inputs.add(path,'0'*64)
            with self.assertRaises(ValueError):inputs.verify_all({})
            path.write_bytes(b'drift')
            with self.assertRaises(ValueError):inputs.verify_all({})
            self.assertEqual(inputs.checked,{})
            with self.assertRaises(ValueError):inputs.verify_all({str(path.with_name('undeclared')):[lambda raw:None]})

    def test_preflight_document_cache_cannot_skip_semantic_validation(self):
        with tempfile.TemporaryDirectory(prefix='audio-d47-input-') as name:
            path=Path(name)/'document';raw=b'{"value":1}';path.write_bytes(raw)
            inputs=gate.PreflightInputs();inputs.add(path,hashlib.sha256(raw).hexdigest())
            with patch.object(gate,'bounded',wraps=gate.bounded) as reader:
                self.assertEqual(inputs.document(path),{'value':1})
                self.assertEqual(inputs.document(path),{'value':1})
                inputs.verify_all({});self.assertEqual(reader.call_count,1)
            with self.assertRaises(ValueError):inputs.verify_all({str(path):[lambda data:None]})

    def test_preflight_pcm_and_activity_reject_invalid_bytes(self):
        gate.pcm_bytes(struct.pack('<ff',1,2),2)
        for raw,samples in ((b'abc',1),(struct.pack('<f',float('nan')),1),(struct.pack('<f',float('inf')),1)):
            with self.assertRaises(ValueError):gate.pcm_bytes(raw,samples)
        gate.activity_bytes(b'frame,far,dt\n0,1,0\n1,0,1\n',2)
        for raw,frames in ((b'frame,far,dt\n1,1,0\n',1),(b'frame,far,dt\n0,2,0\n',1),(b'frame,far,dt\n0,1,0\n',2)):
            with self.assertRaises(ValueError):gate.activity_bytes(raw,frames)
        with self.assertRaises(UnicodeError):gate.activity_bytes(b'\xff',1)

    def test_preflight_start_cache_does_not_hide_later_input_drift(self):
        with tempfile.TemporaryDirectory(prefix='audio-d47-input-') as name:
            path=Path(name)/'input';path.write_bytes(b'start')
            inputs=gate.PreflightInputs();inputs.add(path,hashlib.sha256(b'start').hexdigest())
            with patch.object(gate,'bounded',wraps=gate.bounded) as reader:
                inputs.verify_all({});locks=dict(inputs.expected)
                path.write_bytes(b'end')
                self.assertFalse(all(gate.sha(gate.bounded(Path(p),4*1024*1024))==h for p,h in locks.items()))
                self.assertEqual(reader.call_count,2)

    def test_schema_keeps_old_meanings_in_prefix(self):
        self.assertEqual(gate.POWER_FIELDS[:-3],gate.d45.POWER_FIELDS)
        self.assertEqual(gate.CURRENT_FIELDS,['current_residual_sum','current_innovation_sum','prediction_overshoot_bins'])
        self.assertEqual(gate.BIN_FIELDS,gate.d45.BIN_FIELDS)
        self.assertEqual((len(gate.POWER_FIELDS),len(gate.BIN_FIELDS)),(21,25))

    def test_baseline_preserves_operands_and_allows_only_floor_derivatives(self):
        previous={'power':[{'innovation_sum':'1','residual_sum':'2','floor_mean':'.2','positive_floor_bins':'1','raised_bins':'0','post_would_raise_bins':'1','floor2_residual_sum':'.08'}],
                  'bins':[{'E':'1','R':'2','N':'.1','floor':'.2','combined_gain_before':'.12','combined_gain_after':'.12'}]}
        current={'power':[dict(previous['power'][0],floor_mean='.5',positive_floor_bins='2',raised_bins='1',post_would_raise_bins='2',floor2_residual_sum='.5',current_residual_sum='0',current_innovation_sum='1',prediction_overshoot_bins='1')],
                 'bins':[dict(previous['bins'][0],floor='.5',combined_gain_after='.5')]}
        gate.baseline_trace(current,previous)
        for section,key in (('power','innovation_sum'),('power','residual_sum'),('bins','E'),('bins','R'),('bins','N'),('bins','combined_gain_before')):
            with self.subTest(section=section,key=key):
                old=current[section][0][key];current[section][0][key]='9'
                with self.assertRaises(ValueError):gate.baseline_trace(current,previous)
                current[section][0][key]=old

    def test_current_diagnostics_are_identical_between_modes(self):
        monitor={'power':[{'raised_bins':'0','post_would_raise_bins':'2','current_residual_sum':'0','current_innovation_sum':'1','prediction_overshoot_bins':'1'}],
                 'bins':[{'floor':'.5','combined_gain_before':'.12','combined_gain_after':'.12'}]}
        candidate={'power':[dict(monitor['power'][0],raised_bins='2')],
                   'bins':[dict(monitor['bins'][0],combined_gain_after='.5')]}
        gate.paired_traces(monitor,candidate)
        for key in gate.CURRENT_FIELDS+['post_would_raise_bins']:
            value=candidate['power'][0][key];candidate['power'][0][key]='8'
            with self.assertRaises(ValueError):gate.paired_traces(monitor,candidate)
            candidate['power'][0][key]=value

    def test_existing_external_indirect_and_unapproved_root_rejected_first(self):
        with tempfile.TemporaryDirectory(prefix='audio-d47-root-') as name:
            root=Path(name);link=root/'alias';link.symlink_to(root)
            with patch.object(gate,'preflight',side_effect=AssertionError('must reject before input reads')):
                for target in (root,link,link/'new',Path('/var/audio-d47'),Path('/tmp/audio-d47-unapproved-new-root')):
                    with self.subTest(target=str(target)):
                        with self.assertRaises(ValueError):gate.run(target)

    def test_empty_current_aggregates_nonfinite_and_overshoot_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix='audio-d47-trace-') as name:
            root=Path(name)
            def write(fields,rows,filename):
                (root/filename).write_text(','.join(fields)+'\n'+''.join(','.join(row[k] for k in fields)+'\n' for row in rows))
            power={k:'0' for k in gate.POWER_FIELDS};protection={k:'0' for k in gate.PROTECTION_FIELDS};bins=[]
            for k in range(257):
                row={key:'0' for key in gate.BIN_FIELDS};row['bin']=str(k)
                row['combined_gain_before']='.12';row['combined_gain_after']='.12';bins.append(row)
            write(gate.PROTECTION_FIELDS,[protection],'protection.csv');write(gate.BIN_FIELDS,bins,'bins.csv')
            write(gate.POWER_FIELDS,[power],'power.csv')
            self.assertEqual(gate.trace(root,1,'monitor',bytes((0,0)))['bin_rows'],257)
            for key,value in (('current_residual_sum','1'),('current_innovation_sum','1'),('current_innovation_sum','nan'),('current_residual_sum','-1'),('prediction_overshoot_bins','1')):
                with self.subTest(key=key,value=value):
                    old=power[key];power[key]=value;write(gate.POWER_FIELDS,[power],'power.csv')
                    with self.assertRaises(ValueError):gate.trace(root,1,'monitor',bytes((0,0)))
                    power[key]=old

    def test_monitor_waveforms_and_control_cannot_be_excluded(self):
        with tempfile.TemporaryDirectory(prefix='audio-d47-waveform-') as name:
            root=Path(name);current=root/'current';previous=root/'previous';current.mkdir();previous.mkdir()
            for directory in (current,previous):
                for filename in gate.OUTPUTS[:4]:(directory/filename).write_bytes(b'exact')
                (directory/'protection.csv').write_text(','.join(gate.PROTECTION_FIELDS)+'\n'+','.join(['0']*8)+'\n')
            gate.baseline_outputs(current,previous,'monitor')
            for filename in gate.OUTPUTS[:4]:
                (current/filename).write_bytes(b'drift')
                with self.assertRaises(ValueError):gate.baseline_outputs(current,previous,'monitor')
                (current/filename).write_bytes(b'exact')
            (current/'ns.f32le').write_bytes(b'candidate-change');gate.baseline_outputs(current,previous,'candidate')

    def test_row_count_and_columns_cannot_be_dropped(self):
        with self.assertRaises(ValueError):gate.project_equal([{}],[],set(),'rows')
        with self.assertRaises(ValueError):gate.project_equal([{'old':'1'}],[{}],set(),'columns')

    def test_no_output_argument_can_implicitly_execute(self):
        with patch('sys.argv',['tool','--output-root','/tmp/audio-fe-device-current-innovation-d47-20261013']),patch.object(gate,'preflight',side_effect=AssertionError('must not read')):
            with self.assertRaises(ValueError):gate.main()


if __name__=='__main__':unittest.main()
