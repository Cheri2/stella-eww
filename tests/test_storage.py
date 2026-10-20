import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / '.local/bin'))
from telemetry.zfs import get_zfs
from telemetry.nvmeof import get_nvmeof


class StorageTests(unittest.TestCase):
    def test_pool_capacity(self):
        with patch('telemetry.zfs.subprocess.run', return_value=subprocess.CompletedProcess([], 0, 'tank\t4096\t1024\t3072\tONLINE\nbackup\t8192\t0\t8192\tDEGRADED\n')):
            data = get_zfs()
        self.assertTrue(data['available'])
        self.assertEqual(data['pools'][0]['free_bytes'], 3072)
        self.assertIn('backup  DEGRADED', data['text'])

    def test_pool_failures(self):
        for error in (FileNotFoundError(), PermissionError(), subprocess.TimeoutExpired('zpool', 3), subprocess.CalledProcessError(1, 'zpool')):
            with self.subTest(error=error), patch('telemetry.zfs.subprocess.run', side_effect=error):
                self.assertEqual(get_zfs()['status'], 'UNAVAILABLE')
        with patch('telemetry.zfs.subprocess.run', return_value=subprocess.CompletedProcess([], 0, 'tank 4096 - - FAULTED')):
            self.assertEqual(get_zfs()['status'], 'UNAVAILABLE')

    def test_empty_pools(self):
        with patch('telemetry.zfs.subprocess.run', return_value=subprocess.CompletedProcess([], 0, '')):
            self.assertEqual(get_zfs()['status'], 'NONE')

    def test_fabrics_and_multipath(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            blocks = root / 'block'
            blocks.mkdir()
            subsystem = root / 'nvme-subsys0'
            subsystem.mkdir()
            for index, transport in enumerate(('tcp', 'rdma', 'pcie')):
                controller = subsystem / f'nvme{index}'
                controller.mkdir()
                for name, value in {'transport': transport, 'address': 'traddr=192.0.2.1,trsvcid=4420', 'state': 'live'}.items():
                    (controller / name).write_text(value)
                namespace = controller / f'nvme{index}n1'
                namespace.mkdir()
                (namespace / 'nsid').write_text('1')
                (blocks / namespace.name).symlink_to(namespace)
            head = subsystem / 'nvme3n1'
            head.mkdir()
            (head / 'nsid').write_text('1')
            (blocks / head.name).symlink_to(head)
            (blocks / 'nvme0c0n1').symlink_to(subsystem / 'nvme0' / 'nvme0n1')
            (blocks / 'nvme0n1p1').mkdir()  # Partitions must not be listed.
            data = get_nvmeof(blocks)
            self.assertEqual(data['status'], 'OK')
            self.assertEqual([d['device'] for d in data['devices']], ['/dev/nvme0n1', '/dev/nvme1n1', '/dev/nvme3n1'])
            self.assertEqual([p['transport'] for p in data['devices'][-1]['paths']], ['tcp', 'rdma'])
            self.assertEqual(data['text'], '/dev/nvme0n1\n/dev/nvme1n1\n/dev/nvme3n1')
            (subsystem / 'nvme0' / 'transport').unlink()
            self.assertEqual(get_nvmeof(blocks)['status'], 'UNAVAILABLE')

    def test_empty_and_unreadable_sysfs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            self.assertEqual(get_nvmeof(root)['status'], 'NONE')
            self.assertEqual(get_nvmeof(root / 'missing')['status'], 'UNAVAILABLE')


if __name__ == '__main__':
    unittest.main()
