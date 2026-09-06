import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
spec = importlib.util.spec_from_file_location('names', Path(__file__).resolve().parents[1] / 'bin/display-names.py')
n = importlib.util.module_from_spec(spec)
spec.loader.exec_module(n)


def monitor(port='DP-1', serial='serial-one'):
    return dict(name=port, make='Dell', model='Same Model', serial=serial)


class NamesTests(unittest.TestCase):
    def test_identity_survives_connector_change_and_distinguishes_twins(self):
        self.assertEqual(n.identity(monitor('DP-1'), 'host'), n.identity(monitor('DP-4'), 'host'))
        self.assertNotEqual(n.identity(monitor(), 'host'), n.identity(monitor(serial='serial-two'), 'host'))

    def test_internal_is_machine_bound_without_serial(self):
        m = monitor('eDP-1', '')
        self.assertEqual(n.identity(m, 'host'), n.identity(dict(m, name='eDP-2'), 'host'))
        self.assertNotEqual(n.identity(m, 'host'), n.identity(m, 'other'))
        self.assertIsNone(n.identity(m, ''))

    def test_missing_and_duplicate_serials_do_not_guess(self):
        for serial in ['', '0', '000000', 'unknown']:
            self.assertIsNone(n.identity(monitor(serial=serial), 'host'))
        twin = [monitor(), monitor('DP-2')]
        data = n.decorate(twin, {n.identity(twin[0], 'host'): 'One'}, 'host')
        self.assertEqual([m['displayLabel'] for m in data], ['DP-1', 'DP-2'])
        self.assertTrue(all(not m['displayIdentity'] for m in data))

    def test_validation(self):
        self.assertEqual(n.normalize_label('  Café  '), 'Café')
        self.assertEqual(n.normalize_label('a'*20), 'a'*20)
        for label in ['', 'a'*21, 'A\nB', 'A\x00B', 'A\u202eB']:
            with self.assertRaises(ValueError): n.normalize_label(label)

    def test_save_reconnect_reset_and_stale_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'display-names.json'
            m = monitor()
            key = n.identity(m, 'host')
            n.save_name(path, [m], 'host', 'DP-1', key, 'Left Dell')
            self.assertEqual(n.decorate([dict(m, name='DP-4')], n.read_names(path)['names'], 'host')[0]['displayLabel'], 'Left Dell')
            before = path.read_bytes()
            with self.assertRaises(ValueError): n.save_name(path, [monitor(serial='different')], 'host', 'DP-1', key, 'Wrong')
            self.assertEqual(path.read_bytes(), before)
            n.save_name(path, [m], 'host', 'DP-1', key)
            self.assertEqual(n.read_names(path)['names'], {})

    def test_duplicate_alias_and_corrupt_file_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'display-names.json'
            a,b = monitor(),monitor('DP-2','two')
            n.save_name(path,[a,b],'host','DP-1',n.identity(a,'host'),'Desk')
            with self.assertRaises(ValueError): n.save_name(path,[a,b],'host','DP-2',n.identity(b,'host'),'desk')
            path.write_text('{corrupt')
            with self.assertRaises(ValueError): n.save_name(path,[a,b],'host','DP-1',n.identity(a,'host'),'New')
            self.assertEqual(path.read_text(), '{corrupt')


if __name__ == '__main__': unittest.main()
