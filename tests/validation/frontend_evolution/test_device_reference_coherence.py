import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock

PATH=Path(__file__).resolve().parents[3]/'tools/codex_assets/device_reference_coherence.py'
spec=importlib.util.spec_from_file_location('d35',PATH);d35=importlib.util.module_from_spec(spec);spec.loader.exec_module(d35)


class ReferenceCoherenceTests(unittest.TestCase):
    def test_timeout_preserves_partial_receipt(self):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp);error=d35.subprocess.TimeoutExpired(['observer'],120,output=b'partial\xff',stderr=b'failed')
            with mock.patch.object(d35.subprocess,'run',side_effect=error):
                with self.assertRaises(d35.subprocess.TimeoutExpired):d35.logged(output,'timeout',['observer'])
            r=d35.read_json(output/'timeout.json')
            self.assertIsNone(r['exit_code']);self.assertEqual(r['error_type'],'TimeoutExpired')
            self.assertEqual(r['stdout'],'partial\ufffd');self.assertEqual(r['stderr'],'failed')
            self.assertGreaterEqual(r['elapsed_seconds'],0)

    def test_start_error_receipt_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)
            with mock.patch.object(d35.subprocess,'run',side_effect=OSError('start denied')):
                with self.assertRaises(OSError):d35.logged(output,'start',['observer'])
            p=output/'start.json';before=p.read_bytes();r=d35.read_json(p)
            self.assertIsNone(r['exit_code']);self.assertEqual(r['error_type'],'OSError')
            with self.assertRaises(ValueError):d35.logged(output,'start',['observer'])
            self.assertEqual(before,p.read_bytes())

    def test_nearest_rank_and_null(self):
        result=d35.stats([None,9.,1.,5.,3.,7.])
        self.assertEqual((result['valid'],result['null'],result['p10'],result['p50'],result['p90']),(5,1,1.,5.,9.))
        self.assertIsNone(d35.stats([None])['p50'])
        with self.assertRaises(ValueError):d35.stats([float('nan')])

    def test_previous_guard_only(self):
        self.assertEqual(d35.guard_predecessors([0,1,0,1]),[0,2])
        with self.assertRaises(ValueError):d35.guard_predecessors([1,0])

    def test_null_is_not_zero(self):
        row=dict(valid_lags=0,max_cos2=-1,chosen_lag=-1,zero_lag_cos2=-1)
        result=d35.selected_stats([row],[0])
        self.assertEqual(result['max_cos2']['null'],1)
        self.assertIsNone(result['max_cos2']['min'])

    def test_startup_and_invalid_rows(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'data.csv'
            header=','.join(d35.FIELDS)+'\n'
            p.write_text(header+'0,1,0,1,-1,-1,-1,-1\n')
            self.assertEqual(d35.rows_from(p,1)[0]['tested_lags'],1)
            for row in ('0,1536,0,1,-1,-1,-1,-1\n','0,1,0,NaN,-1,-1,-1,-1\n','0,1,0,1,0,-1,-1,-1\n'):
                p.write_text(header+row)
                with self.assertRaises(ValueError):d35.rows_from(p,1)

    def test_json_and_output_reject(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'input.json'
            for text in ('{"x":1,"x":2}','{"x":Infinity}'):
                p.write_text(text)
                with self.assertRaises(ValueError):d35.read_json(p)
            with self.assertRaises(ValueError):d35.preflight(Path(temp))


if __name__=='__main__':unittest.main()
