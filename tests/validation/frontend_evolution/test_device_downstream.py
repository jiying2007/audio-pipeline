import unittest
import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch
from tools.codex_assets.device_downstream import aligned_range,f32,encode,logged

class DownstreamContract(unittest.TestCase):
    def test_ola_whole_tail_is_explicit(self):
        self.assertEqual(aligned_range(0,3200,3200),dict(input_range=[0,3040],output_range=[160,3200],tail_truncated_samples=160))
    def test_fixed_window_shift(self):
        self.assertEqual(aligned_range(1600,1920,3200),dict(input_range=[1600,1920],output_range=[1760,2080],tail_truncated_samples=0))
    def test_tail_only_is_null(self):
        self.assertIsNone(aligned_range(3040,3200,3200))
    def test_invalid_range_rejected(self):
        for args in ((-1,10,320),(10,10,320),(0,400,320)):
            with self.assertRaises(ValueError):aligned_range(*args)
    def test_binary32_output_clamp_coordinate(self):
        limit=f32(10**(-2/20));gain=f32(.5)
        self.assertEqual(encode([max(-limit,min(limit,f32(v*gain))) for v in [-2,0,2]]),encode([-limit,0,limit]))
    def test_timeout_preserves_command_and_partial_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);error=subprocess.TimeoutExpired(['fixture'],120,output=b'partial',stderr=b'err')
            with patch('tools.codex_assets.device_downstream.subprocess.run',side_effect=error):
                with self.assertRaises(subprocess.TimeoutExpired):logged(root,'timeout',['fixture'],root)
            value=json.loads((root/'command-timeout.json').read_text())
            self.assertIsNone(value['exit_code']);self.assertEqual(value['stdout'],'partial');self.assertEqual(value['stderr'],'err')
            self.assertEqual(value['command'],['fixture']);self.assertEqual(value['error_type'],'TimeoutExpired')
            with patch('tools.codex_assets.device_downstream.subprocess.run') as run:
                with self.assertRaises(ValueError):logged(root,'timeout',['fixture'],root)
                run.assert_not_called()
    def test_start_failure_preserves_null_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with patch('tools.codex_assets.device_downstream.subprocess.run',side_effect=FileNotFoundError('fixture')):
                with self.assertRaises(FileNotFoundError):logged(root,'missing',['fixture'],root)
            value=json.loads((root/'command-missing.json').read_text())
            self.assertIsNone(value['exit_code']);self.assertEqual(value['error_type'],'FileNotFoundError')
            self.assertEqual(value['cwd'],str(root));self.assertGreaterEqual(value['elapsed_seconds'],0)

if __name__=='__main__':unittest.main()
