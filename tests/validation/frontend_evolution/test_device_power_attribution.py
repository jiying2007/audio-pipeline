"""D43 malformed trace rejection and fixed sparse coverage contracts."""
import csv
from pathlib import Path
import tempfile
import unittest
from tools.codex_assets import device_power_attribution as power

class PowerAttributionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='audio-d43-unit-')
        self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.p={k:'0' for k in power.POWER_FIELDS}
        self.b=[{k:'0' for k in power.BIN_FIELDS} for _ in range(257)]
        for k,row in enumerate(self.b):row['bin']=str(k)

    def save(self):
        for name,fields,rows in (('power.csv',power.POWER_FIELDS,[self.p]),('bins.csv',power.BIN_FIELDS,self.b)):
            with (self.root/name).open('w',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=fields)
                writer.writeheader();writer.writerows(rows)

    def check(self):
        self.save();return power.trace(self.root,1,'monitor',b'\0\0')

    def test_full_inactive_snapshot(self):
        result=self.check();self.assertEqual(result['bin_rows'],257)
        self.assertEqual(result['snapshot_frames'],[0])

    def test_boundary_schedule_and_actual_last_frame(self):
        frames=power.snapshot_frames(2000)
        self.assertEqual(len(frames),33);self.assertEqual(frames[-1],1999)
        self.assertTrue({9,10,11,999,1000,1001,1199,1200,1201,1599,1600,1601,1799,1800,1801}<=set(frames))
        self.assertEqual(len(power.snapshot_frames(3024)),44)
        self.assertEqual(power.snapshot_frames(10),[0,1,9])
        for bad in (0,-1,True,1.5,10001):
            with self.assertRaises(ValueError):power.snapshot_frames(bad)

    def test_nonfinite_and_negative_noise(self):
        for value in ('nan','inf','-inf','-0.01'):
            self.b[31]['N']=value
            with self.assertRaises(ValueError):self.check()

    def test_duplicate_missing_extra_bin(self):
        original=[dict(row) for row in self.b]
        self.b[15]['bin']='14'
        with self.assertRaises(ValueError):self.check()
        self.b=original[:-1]
        with self.assertRaises(ValueError):self.check()
        self.b=original+[dict(original[-1])]
        with self.assertRaises(ValueError):self.check()

    def test_gate_and_warmup_identity(self):
        self.p['far']='1'
        with self.assertRaises(ValueError):self.check()
        self.p['far']='0';self.p['count_before']='1'
        with self.assertRaises(ValueError):self.check()

    def test_monitor_cannot_claim_raise(self):
        self.p['raised_bins']='1'
        with self.assertRaises(ValueError):self.check()

    def test_inactive_gain_and_nonzero_empty_aggregate(self):
        self.b[20]['res_gain']='0.5'
        with self.assertRaises(ValueError):self.check()
        self.b[20]['res_gain']='0';self.p['noise_sum']='0.1'
        with self.assertRaises(ValueError):self.check()

    def test_schema_and_row_width(self):
        self.save()
        text=(self.root/'power.csv').read_text()
        (self.root/'power.csv').write_text(text.replace('floor2_residual_sum','wrong'))
        with self.assertRaises(ValueError):power.trace(self.root,1,'monitor',b'\0\0')
        self.save()
        with (self.root/'bins.csv').open('a') as stream:stream.write('0,0\n')
        with self.assertRaises(ValueError):power.trace(self.root,1,'monitor',b'\0\0')

    def test_mode_exclusions_preserve_past_state(self):
        a={'power':[{'raised_bins':'0','noise_sum':'1'}],
            'bins':[{'old_gain':'1','applied_target':'0.1','res_gain':'0.5','N':'1','floor':'0.4'}]}
        b={'power':[{'raised_bins':'1','noise_sum':'1'}],
            'bins':[{'old_gain':'0.9','applied_target':'0.4','res_gain':'0.6','N':'1','floor':'0.4'}]}
        power.paired_traces(a,b)
        b['bins'][0]['N']='2'
        with self.assertRaises(ValueError):power.paired_traces(a,b)
        b['bins'][0]['N']='1';b['power'][0]['noise_sum']='2'
        with self.assertRaises(ValueError):power.paired_traces(a,b)

    def test_existing_root_rejected_before_preflight(self):
        with self.assertRaises(ValueError):power.run(self.root)
        self.assertEqual(list(self.root.iterdir()),[])

    def test_artifact_size_budget(self):
        path=self.root/'too-large'
        with path.open('wb') as stream:stream.truncate(4*1024*1024+1)
        with self.assertRaises(ValueError):power.size_budget(self.root)

    def test_active_to_inactive_retains_old_count_before_reset(self):
        frames=12;gates=b'\1\0'*11+b'\0\0';rows=[];bins=[]
        for f in range(frames):
            row={k:'0' for k in power.POWER_FIELDS}
            row.update(frame=str(f),far='1' if f<11 else '0',count_before=str(min(f,10)))
            rows.append(row)
        for f in power.snapshot_frames(frames):
            for k in range(257):
                row={key:'0' for key in power.BIN_FIELDS}
                row.update(frame=str(f),bin=str(k),far=rows[f]['far'],count_before=rows[f]['count_before'])
                bins.append(row)
        for name,fields,data in (('power.csv',power.POWER_FIELDS,rows),('bins.csv',power.BIN_FIELDS,bins)):
            with (self.root/name).open('w',newline='') as stream:
                writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(data)
        result=power.trace(self.root,frames,'monitor',gates)
        self.assertEqual(result['power'][11]['count_before'],'10')
        rows[11]['count_before']='0'
        with (self.root/'power.csv').open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=power.POWER_FIELDS);writer.writeheader();writer.writerows(rows)
        with self.assertRaises(ValueError):power.trace(self.root,frames,'monitor',gates)

if __name__=='__main__':unittest.main()
