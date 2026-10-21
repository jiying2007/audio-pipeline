"""D45 baseline exclusions must preserve waveform and past-state contracts."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools.codex_assets import device_post_ns_protection as gate

class PostNsProtectionTests(unittest.TestCase):
    def test_baseline_projection_preserves_original_res_and_floor(self):
        a={'power':[{'noise_sum':'1','floor_mean':'.2','raised_bins':'1','post_would_raise_bins':'1'}],
           'bins':[{'N':'1','valid':'1','floor':'.2','old_gain':'.5',
                    'updated_noise':'1','combined_gain_before':'.1','combined_gain_after':'.2'}]}
        b={'power':[{'noise_sum':'1','floor_mean':'.2','raised_bins':'0'}],
           'bins':[{'N':'1','valid':'1','floor':'.2','old_gain':'.5'}]}
        gate.baseline_trace(a,b)
        for section,key in (('power','noise_sum'),('power','floor_mean'),
                            ('bins','N'),('bins','valid'),('bins','floor'),('bins','old_gain')):
            with self.subTest(section=section,key=key):
                original=b[section][0][key];b[section][0][key]='2'
                with self.assertRaises(ValueError):gate.baseline_trace(a,b)
                b[section][0][key]=original

    def test_mode_projection_only_allows_actual_raise_and_final_gain(self):
        a={'power':[{'raised_bins':'0','post_would_raise_bins':'1'}],
           'bins':[{'combined_gain_before':'.1','combined_gain_after':'.1','res_gain':'.5'}]}
        b={'power':[{'raised_bins':'1','post_would_raise_bins':'1'}],
           'bins':[{'combined_gain_before':'.1','combined_gain_after':'.2','res_gain':'.5'}]}
        gate.paired_traces(a,b)
        for section,key in (('power','post_would_raise_bins'),('bins','combined_gain_before'),('bins','res_gain')):
            original=b[section][0][key];b[section][0][key]='9'
            with self.assertRaises(ValueError):gate.paired_traces(a,b)
            b[section][0][key]=original

    def test_new_schema_keeps_legacy_prefix(self):
        self.assertEqual(gate.POWER_FIELDS[:-1],gate.d43.POWER_FIELDS)
        self.assertEqual(gate.BIN_FIELDS[:-3],gate.d43.BIN_FIELDS)
        self.assertEqual(len(gate.POWER_FIELDS),18)
        self.assertEqual(len(gate.BIN_FIELDS),25)

    def test_projection_rejects_missing_and_extra_rows(self):
        for a,b in (([],[{}]),([{}],[]),([{},{}],[{}])):
            with self.assertRaises(ValueError):gate.project_equal(a,b,set(),'test')

    def test_monitor_protection_preserves_floor(self):
        a=[{key:'0' for key in gate.PROTECTION_FIELDS}]
        b=[dict(a[0],raised_bins='1')]
        gate.project_equal(a,b,{'raised_bins'},'monitor')
        for key in (k for k in gate.PROTECTION_FIELDS if k!='raised_bins'):
            with self.subTest(key=key):
                b[0][key]='1'
                with self.assertRaises(ValueError):gate.project_equal(a,b,{'raised_bins'},'monitor')
                b[0][key]='0'

    def test_existing_root_and_symlink_rejected_without_preflight(self):
        with tempfile.TemporaryDirectory(prefix='audio-d45-unit-') as name:
            root=Path(name)
            with patch.object(gate,'preflight',side_effect=AssertionError('must not read')):
                with self.assertRaises(ValueError):gate.run(root)
                link=root/'alias';link.symlink_to(root)
                with self.assertRaises(ValueError):gate.run(link)
                with self.assertRaises(ValueError):gate.run(Path('/var/audio-d45-new-root'))
                with self.assertRaises(ValueError):gate.run(link/'new-root')

    def test_trace_rejects_new_schema_nonfinite_and_wrong_post_count(self):
        with tempfile.TemporaryDirectory(prefix='audio-d45-trace-') as name:
            root=Path(name)
            def write(fields,rows,filename):
                (root/filename).write_text(','.join(fields)+'\n'+''.join(
                    ','.join(row[k] for k in fields)+'\n' for row in rows))
            power={k:'0' for k in gate.POWER_FIELDS}
            protection={k:'0' for k in gate.PROTECTION_FIELDS}
            bins=[]
            for k in range(257):
                row={key:'0' for key in gate.BIN_FIELDS};row['bin']=str(k)
                row['combined_gain_before']='0.12';row['combined_gain_after']='0.12'
                bins.append(row)
            write(gate.POWER_FIELDS,[power],'power.csv')
            write(gate.PROTECTION_FIELDS,[protection],'protection.csv')
            write(gate.BIN_FIELDS,bins,'bins.csv')
            self.assertEqual(gate.trace(root,1,'monitor',bytes((0,0)))['bin_rows'],257)
            for key,value in (('updated_noise','nan'),('combined_gain_before','1.1'),
                              ('combined_gain_after','0.5'),('applied_target','0.1')):
                original=bins[0][key];bins[0][key]=value
                write(gate.BIN_FIELDS,bins,'bins.csv')
                with self.assertRaises(ValueError):gate.trace(root,1,'monitor',bytes((0,0)))
                bins[0][key]=original
            write(gate.BIN_FIELDS,bins,'bins.csv')
            power['post_would_raise_bins']='1';write(gate.POWER_FIELDS,[power],'power.csv')
            with self.assertRaises(ValueError):gate.trace(root,1,'monitor',bytes((0,0)))
            write(gate.BIN_FIELDS[:-1],bins,'bins.csv')
            with self.assertRaises(ValueError):list(gate.records(root/'bins.csv',gate.BIN_FIELDS))

    def test_original_ns_res_controls_are_required_exact(self):
        with tempfile.TemporaryDirectory(prefix='audio-d45-control-') as name:
            root=Path(name);a=root/'a';b=root/'b';a.mkdir();b.mkdir()
            def write(directory,row):
                (directory/'control.csv').write_text(','.join(gate.CONTROL_FIELDS)+'\n'+
                    ','.join(row[k] for k in gate.CONTROL_FIELDS)+'\n')
            original={k:'0' for k in gate.CONTROL_FIELDS};changed=dict(original,gain_after='1')
            write(a,original);write(b,changed);gate.paired_controls(a,b)
            for key in ('frequency_active','speech_probability','noise_rms_dbfs','residual_gain'):
                changed[key]='1';write(b,changed)
                with self.assertRaises(ValueError):gate.paired_controls(a,b)
                changed[key]='0'

    def test_monitor_audio_and_control_never_excluded(self):
        with tempfile.TemporaryDirectory(prefix='audio-d45-unit-') as name:
            root=Path(name);a=root/'a';b=root/'b';a.mkdir();b.mkdir()
            for directory in (a,b):
                for filename in gate.OUTPUTS[:4]:(directory/filename).write_bytes(b'original')
                (directory/'protection.csv').write_text(','.join(gate.PROTECTION_FIELDS)+'\n'+','.join(['0']*8)+'\n')
            gate.baseline_outputs(a,b,'monitor')
            for filename in gate.OUTPUTS[:4]:
                with self.subTest(filename=filename):
                    (a/filename).write_bytes(b'changed')
                    with self.assertRaises(ValueError):gate.baseline_outputs(a,b,'monitor')
                    (a/filename).write_bytes(b'original')
            (a/'ns.f32le').write_bytes(b'candidate-change')
            gate.baseline_outputs(a,b,'candidate')
            (a/'bypass.f32le').write_bytes(b'changed')
            with self.assertRaises(ValueError):gate.baseline_outputs(a,b,'candidate')

if __name__=='__main__':unittest.main()
