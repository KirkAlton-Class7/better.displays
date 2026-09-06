import argparse
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('settings', Path(__file__).resolve().parents[1] / 'bin/monitor-settings.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class MonitorTests(unittest.TestCase):
    def test_preserve_extra_fields_comments_and_other_outputs(self):
        original = '-- custom\nhl.env("GDK_SCALE", "2")\nhl.monitor({ output = "DP-1", mode = "1920x1080@60", scale = 2, bitdepth = 10 }) -- keep\nhl.monitor({ output = "DP-2", scale = 1 })\n'
        result = m.edit_config(original, 'DP-1', {'scale': 1.5})
        self.assertEqual(result, original.replace('scale = 2,', 'scale = 1.5,'))

    def test_reject_ambiguous_dynamic_multiline_and_missing(self):
        line = 'hl.monitor({ output = "DP-1", scale = 2 })\n'
        for original in [line + line, 'hl.monitor({\n output = "DP-1", scale = 2\n})',
                         line.replace('scale = 2', 'scale = custom_scale'), '',
                         line.replace('scale = 2', 'nested = { scale = 2 }')]:
            with self.assertRaises(ValueError): m.edit_config(original, 'DP-1', {'scale': 1.5})

    def test_add_field_with_trailing_comma(self):
        actual = m.edit_config('hl.monitor({ output = "DP-1", scale = 2, })', 'DP-1', {'transform': 1})
        self.assertEqual(actual, 'hl.monitor({ output = "DP-1", scale = 2, transform = 1 })')

    def test_mode_scale_uses_new_resolution(self):
        current = dict(name='DP-1', width=1920, height=1080, scale=2, x=0, y=0, transform=0)
        args = argparse.Namespace(mode='2560x1440@60', scale=1.6, pos=None, transform=None)
        actual, _ = m.proposal(current, args, [current])
        self.assertEqual(actual['width'] / actual['scale'], 1600)
        args.scale = 0
        with self.assertRaises(ValueError): m.proposal(current, args, [current])

    def test_new_overlap_rejected_existing_geometry_preserved(self):
        a = dict(name='A', width=1920, height=1080, scale=2, x=0, y=0, transform=0)
        b = dict(a, name='B', x=960)
        args = argparse.Namespace(mode=None, scale=1, pos=None, transform=None)
        with self.assertRaises(ValueError): m.proposal(a, args, [a, b])
        args.pos = '-960x0'
        proposal, _ = m.proposal(a, args, [a, b])
        self.assertFalse(m.overlaps(proposal, b))

    def test_atomic_write_retains_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'monitors.lua'
            target.write_text('old')
            m.atomic_write(target, 'new', 0o640)
            self.assertEqual(target.read_text(), 'new')
            self.assertEqual(target.stat().st_mode & 0o777, 0o640)
            self.assertEqual(len(list(Path(directory).iterdir())), 1)

    def test_failed_apply_restores_config(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            target = home / '.config/hypr/monitors.lua'
            target.parent.mkdir(parents=True)
            original = 'hl.monitor({ output = "DP-1", scale = 2 })\n'
            target.write_text(original)
            current = dict(name='DP-1', width=1920, height=1080, scale=2, x=0, y=0, transform=0)
            import json
            calls = []
            def run(*args):
                calls.append(args)
                if 'monitors' in args: return json.dumps([current])
                return ''
            with patch.object(m.Path, 'home', return_value=home), patch.object(m, 'run', side_effect=run), patch('sys.argv', ['monitor-settings.py', 'set', 'DP-1', '--scale', '1.5']):
                with self.assertRaisesRegex(ValueError, 'did not apply'): m.main()
            self.assertEqual(target.read_text(), original)
            self.assertEqual(calls.count(('hyprctl', 'reload')), 2)
            self.assertEqual(len(list((home / '.local/state/better-displays/backups').glob('*/monitors.lua'))), 1)


if __name__ == '__main__': unittest.main()
