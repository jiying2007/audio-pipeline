"""Composition boundary tests; real MDF trajectories are verified in the matrix."""
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from tools.codex_assets.device_online import input_info
class OnlineContract(unittest.TestCase):
    def field(self,root,data):
        directory=root/'fixture';directory.mkdir();(directory/'gates.bin').write_bytes(data)
        return dict(kind='field',base=root,case=dict(name='fixture',execution_summary=dict(frames=2),notify_frame=1,
            source_hashes={str(root/'aec_input.f32le'):'fixture',str(root/'used0.reference.f32le'):'fixture'}))
    def test_field_preserves_exact_mic_reference_and_gate_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);s=self.field(root,bytes([1,0,0,1]));directory,mic,ref,gates,n,notify=input_info(s)
            self.assertEqual((directory,mic,ref,gates,n,notify),(root/'fixture',root/'aec_input.f32le',root/'used0.reference.f32le',bytes([1,0,0,1]),320,1))
    def test_truncated_gates_rejected_before_runner(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=self.field(Path(tmp),bytes([1,0,1]))
            with self.assertRaises(ValueError):input_info(s)
    def test_nonboolean_gates_rejected_before_runner(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=self.field(Path(tmp),bytes([1,0,1,2]))
            with self.assertRaises(ValueError):input_info(s)
    def test_return_maps_far_one_without_using_bank_decisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);directory=root/'fixture';directory.mkdir()
            rows=['frame,dt,bank']+[str(f)+','+str(int(1000<=f<1200))+','+str(f%2) for f in range(2000)]
            (directory/'selector.csv').write_text('\n'.join(rows)+'\n')
            s=dict(kind='return',base=root,case=dict(name='fixture',execution_summary=dict(frames=2000)))
            _,mic,ref,gates,n,notify=input_info(s)
            self.assertEqual((mic,ref,n,notify),(directory/'mic.f32le',directory/'reference.f32le',320000,1000))
            self.assertEqual(gates,bytes(v for f in range(2000) for v in (1,int(1000<=f<1200))))
if __name__=='__main__':unittest.main()
