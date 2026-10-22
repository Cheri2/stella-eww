import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.local/bin'))
from telemetry.features import WIDGETS, selected_features
from telemetry.main import Collector
from telemetry.panels import render, validate_profile
from telemetry.routing import get_routing


class PanelTests(unittest.TestCase):
    def render(self, profile):
        return render(profile, ROOT / '.config/eww/widgets.yuck', ROOT / '.local/bin/eww.py')

    def test_selected_only_and_interval_cache(self):
        with patch('telemetry.main.get_zfs', return_value={'text': 'tank'}) as zfs, patch('telemetry.main.get_ceph') as ceph, patch('telemetry.main.get_routing') as routing, patch('telemetry.main.SystemMonitor') as system:
            collector = Collector({'zfs'})
            self.assertEqual(collector.update(0), {'network': {}, 'zfs': {'text': 'tank'}})
            collector.update(1)
            self.assertEqual(zfs.call_count, 1)
            collector.update(5)
            self.assertEqual(zfs.call_count, 2)
            ceph.assert_not_called()
            routing.assert_not_called()
            system.assert_not_called()

    def test_empty_features_do_not_query(self):
        with patch('subprocess.run') as run:
            self.assertEqual(Collector(set()).update(), {'network': {}})
            run.assert_not_called()

    def test_hugepages_can_run_without_system(self):
        with patch('telemetry.main.SystemMonitor') as monitor:
            monitor.return_value.read_hugepages.return_value = {'hp_2m': {}}
            result = Collector({'hugepages'}).update()
            self.assertEqual(result['system']['hugepages'], {'hp_2m': {}})
            monitor.return_value.update.assert_not_called()
        with patch('telemetry.main.SystemMonitor') as monitor:
            Collector({'system'}).update()
            monitor.return_value.update.assert_called_once_with(include_hugepages=False)

    def test_routing_does_not_query_disabled_daemons(self):
        with patch('telemetry.routing.get_bgp', return_value={'state': 'OK'}) as bgp, patch('telemetry.routing.get_routes') as routes, patch('telemetry.routing.get_ospf_neighbors') as neighbors, patch('telemetry.routing.get_ospf_routers') as database:
            self.assertEqual(get_routing({'bgp'})['bgp'], {'state': 'OK'})
            bgp.assert_called_once()
            routes.assert_not_called()
            neighbors.assert_not_called()
            database.assert_not_called()
        with patch('telemetry.routing.get_bgp') as bgp, patch('telemetry.routing.get_routes', return_value=[]):
            get_routing({'internet'})
            bgp.assert_not_called()

    def test_profile_validation_and_empty_column_removal(self):
        for profile in ({}, {'panels': []}, {'panels': ['bad']}, {'panels': ['system', 'system']}, {'panels': ['system'], 'columns': 0}, {'panels': ['system'], 'gap': True}, {'panels': ['system'], 'typo': 1}):
            with self.subTest(profile=profile), self.assertRaises(ValueError):
                validate_profile(profile)
        text = self.render({'panels': ['zfs'], 'columns': 4})
        self.assertEqual(text.count(':valign "start"'), 1)
        self.assertIn('(zfs-widget)', text)
        self.assertNotIn('(ceph-widget)', text)

    def test_order_and_columns(self):
        text = self.render({'panels': ['system', 'zfs', 'nvmeof'], 'columns': 2})
        self.assertEqual(text.count(':valign "start"'), 2)
        self.assertLess(text.index('(system-summary-widget)'), text.index('(zfs-widget)'))
        self.assertLess(text.index('(zfs-widget)'), text.index('(nvmeof-widget)'))

    def test_environment_selection(self):
        with patch.dict('os.environ', {'STELLA_PANELS': 'system,zfs'}):
            self.assertEqual(selected_features(), {'system', 'zfs'})
        with patch.dict('os.environ', {'STELLA_PANELS': 'typo'}), self.assertRaises(ValueError):
            selected_features()

    def test_generated_collector_command(self):
        text = self.render({'panels': ['system']})
        line = text.splitlines()[0]
        decoder = json.JSONDecoder()
        initial_text = line.split(':initial ', 1)[1]
        initial, end = decoder.raw_decode(initial_text)
        self.assertIn('cpu_model', json.loads(initial)['system'])
        command, _ = decoder.raw_decode(initial_text[end:].lstrip())
        process = subprocess.Popen(shlex.split(command), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            data = json.loads(process.stdout.readline())
            self.assertEqual(set(data), {'network', 'system'})
            self.assertIn('cpu_model', data['system'])
            self.assertEqual(data['system']['hugepages'], {})
        finally:
            process.terminate()
            process.communicate(timeout=5)

    def test_full_profile_includes_every_panel(self):
        profile = validate_profile(json.loads((ROOT / 'profiles/full.json').read_text()))
        self.assertEqual(set(profile['panels']), set(WIDGETS),
                         "Update profiles/full.json whenever panels are added or removed")

    def test_all_example_profiles_generate_repeatably(self):
        with tempfile.TemporaryDirectory() as directory:
            for profile in (ROOT / 'profiles').glob('*.json'):
                command = [sys.executable, '-B', str(ROOT / '.local/bin/stella-panels.py'), str(profile), '--output', directory]
                subprocess.run(command, check=True, capture_output=True)
                first = (Path(directory) / 'eww.yuck').read_text()
                subprocess.run(command, check=True, capture_output=True)
                self.assertEqual(first, (Path(directory) / 'eww.yuck').read_text())

    def test_generator_preserves_unrelated_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'eww.yuck'
            target.write_text('user config')
            result = subprocess.run([sys.executable, '-B', str(ROOT / '.local/bin/stella-panels.py'), str(ROOT / 'profiles/router.json'), '--output', directory], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(target.read_text(), 'user config')
