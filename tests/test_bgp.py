import json
import pathlib
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / '.local/bin'))
from telemetry.bgp import get_bgp
from telemetry.routing import get_routing, initial_routing


class BgpTests(unittest.TestCase):
    def summary(self, data):
        with patch('telemetry.bgp.subprocess.run', return_value=subprocess.CompletedProcess([], 0, json.dumps(data))):
            return get_bgp()

    def test_dual_stack_mixed_sessions(self):
        data = self.summary({
            'ipv4Unicast': {'peers': {
                '192.0.2.1': {'state': 'Established', 'remoteAs': 65001, 'pfxRcd': 0},
                '192.0.2.2': {'state': 'Active', 'remoteAs': 65002, 'pfxRcd': 12},
            }},
            'ipv6Unicast': {'peers': {
                '2001:db8::1': {'state': 'Established', 'remoteAs': 65001, 'pfxRcd': 42},
            }},
        })
        self.assertTrue(data['available'])
        self.assertEqual(data['state'], '2/3 ESTABLISHED')
        self.assertEqual(data['peers'][0]['received'], 0)
        self.assertIsNone(data['peers'][1]['received'])
        self.assertIn('RX 42', data['text'])

    def test_empty_and_invalid(self):
        self.assertEqual(self.summary({'ipv4Unicast': {'peers': {}}})['state'], 'NO PEERS')
        for data in ({}, [], {'error': 'bgpd is not running'}, {'ipv4Unicast': {}},
                     {'ipv4Unicast': {'peers': {'192.0.2.1': {}}}}):
            with self.subTest(data=data):
                result = self.summary(data)
                self.assertEqual(result['state'], 'UNAVAILABLE')
                self.assertIsNone(result['total'])

    def test_command_failures(self):
        for error in (FileNotFoundError(), PermissionError(), subprocess.TimeoutExpired('vtysh', 3), subprocess.CalledProcessError(1, 'vtysh')):
            with self.subTest(error=error), patch('telemetry.bgp.subprocess.run', side_effect=error):
                self.assertEqual(get_bgp()['state'], 'UNAVAILABLE')
        with patch('telemetry.bgp.subprocess.run', return_value=subprocess.CompletedProcess([], 0, 'bad json')):
            self.assertEqual(get_bgp()['state'], 'UNAVAILABLE')

    def test_routing_integration(self):
        self.assertEqual(initial_routing()['bgp']['state'], 'LOADING')
        bgp = self.summary({'ipv4Unicast': {'peers': {}}})
        with patch('telemetry.routing.get_routes', return_value=[]), patch('telemetry.routing.get_ospf_neighbors', return_value=None), patch('telemetry.routing.get_ospf_routers', return_value={'self': 'N/A', 'routers': []}), patch('telemetry.routing.get_bgp', return_value=bgp):
            data = get_routing()
        self.assertEqual(data['bgp'], bgp)
        self.assertEqual(data['ospf']['state'], 'UNAVAILABLE')
