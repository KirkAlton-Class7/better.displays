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

    def test_scale_presets_reflow_row_and_preserve_gap(self):
        a = dict(name='A', width=1920, height=1080, refreshRate=60, scale=2, x=0, y=0, transform=0)
        b = dict(a, name='B', x=960, y=100)
        c = dict(a, name='C', x=2000)
        for scale in (1, 1.25, 1.5, 1.6, 2, 3, 4):
            args = argparse.Namespace(mode=None, scale=scale, pos=None, transform=None)
            proposed, _ = m.proposal(b, args, [a, b, c], reflow=True)
            actual = m.arrange([a, b, c], proposed, args)
            self.assertEqual(actual[0], a)
            self.assertEqual(actual[1]['x'], 960)
            self.assertEqual(actual[2]['x'], 960 + 1920 / scale + 80)
            self.assertEqual(actual[1]['y'], 100)
            self.assertFalse(m.overlaps(actual[1], actual[2]))

    def test_column_orientation_reflows_and_manual_overlap_still_refused(self):
        a = dict(name='A', width=1920, height=1080, scale=2, x=0, y=0, transform=0)
        b = dict(a, name='B', y=540)
        args = argparse.Namespace(mode=None, scale=None, pos=None, transform=1)
        proposed, _ = m.proposal(a, args, [a, b], reflow=True)
        actual = m.arrange([a, b], proposed, args)
        self.assertEqual(actual[1]['y'], 960)
        args.pos = '0x300'
        with self.assertRaisesRegex(ValueError, 'overlap'): m.arrange([a, b], dict(b, y=300), args)

    def test_1440p_invalid_exact_scales_are_rejected(self):
        a = dict(name='A', width=2560, height=1440, scale=2, x=0, y=0, transform=0)
        for scale in (1.5, 3):
            with self.assertRaisesRegex(ValueError, 'whole logical pixels'):
                m.proposal(a, argparse.Namespace(mode=None, scale=scale, pos=None, transform=None), [a], reflow=True)

    def test_preserved_mode_fallback_never_resets_outputs(self):
        import json
        a = dict(name='A', width=1920, height=1080, refreshRate=60, scale=1.5, x=0, y=0, transform=0, serial='a')
        b = dict(a, name='B', width=2560, height=1440, serial='b', x=1280, scale=2)
        actual = [a, dict(b, width=2048, height=1280)]
        calls = []
        def run(*args):
            calls.append(args)
            if 'monitors' in args: return json.dumps(actual)
            if args == ('hyprctl', 'reload'): actual[1] = b
            return ''
        with patch.object(m, 'run', side_effect=run), patch.object(m.time, 'sleep'):
            with self.assertRaisesRegex(ValueError, 'did not apply'): m.verify_layout([a, b])
        self.assertTrue(all(args == ('hyprctl', 'monitors', '-j') for args in calls))

    def test_existing_fallback_blocks_scale_before_writes_or_reload(self):
        import json
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            target = home / '.config/hypr/monitors.lua'
            target.parent.mkdir(parents=True)
            original = 'hl.monitor({ output = "DP-1", mode = "2560x1440@59.95", scale = 1.6 })\n'
            target.write_text(original)
            current = dict(name='DP-1', width=2048, height=1280, refreshRate=59.99, scale=1.6, x=0, y=0, transform=0)
            with patch.object(m.Path, 'home', return_value=home), patch.object(m, 'run', return_value=json.dumps([current])) as run, patch('sys.argv', ['monitor-settings.py', 'set', 'DP-1', '--scale', '2']):
                with self.assertRaisesRegex(ValueError, 'already running a fallback'): m.main()
                self.assertTrue(all(call.args == ('hyprctl', 'monitors', '-j') for call in run.call_args_list))
            self.assertEqual(target.read_text(), original)
            self.assertFalse((home / '.local/state/better-displays/backups').exists())

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
