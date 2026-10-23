import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.local/bin'))
from telemetry.corosync import get_corosync, parse_status, write_snapshot
from telemetry.main import Collector

STATUS = '''Quorum information
------------------
Quorum provider: corosync_votequorum
Nodes: 2
Node ID: 1
Ring ID: 1.20
Quorate: Yes

Votequorum information
----------------------
Expected votes: 3
Total votes: 3
Quorum: 2
Flags: Quorate Qdevice

Membership information
----------------------
Nodeid Votes Qdevice Name
1 1 A,V,NMW 192.0.2.1 (local)
2 1 A,V,NMW 192.0.2.2
0 1 Qdevice
'''


class CorosyncTests(unittest.TestCase):
    def test_membership_quorum_and_qdevice(self):
        data = parse_status(STATUS, 0)
        self.assertEqual(data['state'], 'QUORATE')
        self.assertEqual(data['node_count'], 2)
        self.assertEqual(data['expected_votes'], 3)
        self.assertEqual(len(data['members']), 2)
        self.assertTrue(data['members'][0]['local'])

    def test_not_quorate_is_a_valid_observation(self):
        data = parse_status(STATUS.replace('Quorate: Yes', 'Quorate: No'), 2)
        self.assertTrue(data['available'])
        self.assertFalse(data['quorate'])
        self.assertEqual(data['state'], 'NOT QUORATE')

    def test_no_votequorum_provider(self):
        text = 'Nodes: 1\nNode ID: 0x00000001\nQuorate: Yes\nNodeid Name\n0x00000001 192.0.2.1 (local)\n'
        data = parse_status(text, 0)
        self.assertEqual(data['node_count'], 1)
        self.assertIsNone(data['total_votes'])

    def test_invalid_and_partial_results(self):
        for text, code in ((STATUS, 1), (STATUS, 2), ('', 0),
                           (STATUS.replace('Nodes: 2', 'Nodes: 3'), 0),
                           (STATUS.replace(' (local)', ''), 0)):
            with self.subTest(code=code), self.assertRaises((ValueError, KeyError)):
                parse_status(text, code)

    def test_direct_command_is_read_only(self):
        with patch('telemetry.corosync.subprocess.run', return_value=subprocess.CompletedProcess([], 0, STATUS)) as run:
            self.assertTrue(get_corosync()['available'])
            self.assertEqual(run.call_args.args[0], ['corosync-quorumtool', '-s', '-p', '-i'])
            self.assertEqual(run.call_args.kwargs['env']['LC_ALL'], 'C')
        for error in (PermissionError(), FileNotFoundError(), subprocess.TimeoutExpired('query', 3)):
            with patch('telemetry.corosync.subprocess.run', side_effect=error):
                data = get_corosync()
                self.assertEqual(data['state'], 'UNAVAILABLE')
                self.assertIsNone(data['node_count'])

    def test_snapshot_publish_read_stale_and_failed_refresh(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'status.json'
            with patch('telemetry.corosync.subprocess.run', return_value=subprocess.CompletedProcess([], 0, STATUS)):
                write_snapshot(path)
            with patch('telemetry.corosync.subprocess.run') as run:
                self.assertTrue(get_corosync(path)['available'])
                run.assert_not_called()
            self.assertEqual(path.stat().st_mode & 0o777, 0o644)
            data = json.loads(path.read_text())
            data['collected_at'] = time.time() - 60
            path.write_text(json.dumps(data))
            self.assertEqual(get_corosync(path)['state'], 'STALE')
            with patch('telemetry.corosync.subprocess.run', side_effect=PermissionError()):
                write_snapshot(path)
            self.assertEqual(get_corosync(path)['state'], 'UNAVAILABLE')
            path.write_text('invalid json')
            self.assertEqual(get_corosync(path)['state'], 'UNAVAILABLE')
            path.unlink()
            self.assertEqual(get_corosync(path)['state'], 'UNAVAILABLE')

    def test_feature_gating_and_cache(self):
        with patch('telemetry.main.get_corosync', return_value={'state': 'QUORATE'}) as read:
            Collector({'zfs'}).update()
            read.assert_not_called()
            collector = Collector({'corosync'})
            self.assertEqual(collector.update(0)['corosync']['state'], 'QUORATE')
            collector.update(1)
            read.assert_called_once()
            collector.update(5)
            self.assertEqual(read.call_count, 2)
