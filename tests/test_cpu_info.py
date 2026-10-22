import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / '.local/bin'))
from telemetry.cpu_info import get_cpu_info
from telemetry.system import SystemMonitor


class CpuInfoTests(unittest.TestCase):
    def read(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / 'cpuinfo'
            path.write_text(text)
            return get_cpu_info(path)

    def test_smt_and_multiple_sockets(self):
        text = '\n\n'.join(
            f'processor : {i}\nmodel name : Test CPU\nphysical id : {i // 4}\ncore id : {(i % 4) // 2}'
            for i in range(8)
        )
        self.assertEqual(self.read(text), {'cpu_model': 'Test CPU', 'cpu_cores': 4, 'cpu_threads': 8})

    def test_missing_topology(self):
        data = self.read('processor : 0\nmodel name : Virtual CPU\n\nprocessor : 1\nmodel name : Virtual CPU\n')
        self.assertEqual(data, {'cpu_model': 'Virtual CPU', 'cpu_cores': 'N/A', 'cpu_threads': 2})

    def test_empty_missing_and_invalid(self):
        self.assertEqual(self.read('')['cpu_threads'], 'N/A')
        self.assertEqual(get_cpu_info(pathlib.Path('/nonexistent/cpuinfo'))['cpu_model'], 'N/A')
        self.assertEqual(self.read('processor : 0\nphysical id : invalid\ncore id : 0')['cpu_cores'], 'N/A')

    def test_arm_model(self):
        self.assertEqual(self.read('processor : 0\n\nHardware : Test Board')['cpu_model'], 'Test Board')

    def test_system_payload(self):
        data = SystemMonitor().update()
        self.assertIn('cpu_model', data)
        self.assertIn('cpu_cores', data)
        self.assertIn('cpu_threads', data)
