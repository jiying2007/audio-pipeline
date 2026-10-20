"""D49 private harness boundaries; acoustic admission is a separate experiment."""
import tempfile
import sys
from pathlib import Path
import unittest

from tools.codex_assets import device_magnitude_lower_bound as d49


class Boundaries(unittest.TestCase):
    def test_failed_start_preserves_attempted_command(self):
        command = ['/nonexistent-d49-private-child']
        outcome = d49.run_child(command)
        self.assertEqual(outcome['command'], command)
        self.assertFalse(outcome['child_started'])
        self.assertIsNone(outcome['exit_code'])
        self.assertIsNone(outcome['terminal'])
        self.assertIn('FileNotFoundError', outcome['error'])

    def test_timeout_preserves_reaped_child_outcome(self):
        command = ['rtk', sys.executable, '-c', 'import time; time.sleep(10)']
        outcome = d49.run_child(command, timeout_seconds=0.4)
        self.assertEqual(outcome['command'], command)
        self.assertTrue(outcome['child_started'])
        self.assertTrue(outcome['timed_out'])
        self.assertTrue(outcome['terminal'])
        self.assertIsInstance(outcome['exit_code'], int)
        self.assertLess(outcome['exit_code'], 0)

    def test_wrong_root_rejected_before_input_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'not-formal-or-private-root'
            with self.assertRaisesRegex(ValueError, 'fixed absent private root'):
                d49.qualify(path)
            self.assertFalse(path.exists())

    def test_receipt_exclusive_preserves_previous_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'receipt.json'
            path.write_bytes(b'PREVIOUS_RECEIPT')
            with self.assertRaises(FileExistsError):
                d49.write_exclusive(path, dict(status='replacement'))
            self.assertEqual(path.read_bytes(), b'PREVIOUS_RECEIPT')


if __name__ == '__main__':
    unittest.main()
