#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('restore', Path(__file__).parents[1] / 'bin/restore-defaults.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)
_stock_temp = tempfile.TemporaryDirectory()
STOCK = Path(_stock_temp.name)
(STOCK / 'hypr').mkdir()
(STOCK / 'hypr/monitors.lua').write_text('local omarchy_monitor_scale = "auto"\nhl.monitor({ output = "", mode = "preferred", position = "auto", scale = omarchy_monitor_scale })\n')
(STOCK / 'kitty').mkdir()
(STOCK / 'kitty/kitty.conf').write_text('font_size 9.0\n')


class RestoreTests(unittest.TestCase):
    def test_monitor_fields_preserve_other_configuration(self):
        original = '-- custom\nhl.env("GDK_SCALE", "2")\nhl.monitor({ output = "DP-1", mode = "1920x1080@60", scale = 2, position = "0x0", transform = 1, vrr = 1 })\n'
        result = r.reset_monitors(original, r.monitor_defaults((STOCK / 'hypr/monitors.lua').read_text()))
        self.assertIn('mode = "preferred"', result)
        self.assertIn('scale = "auto"', result)
        self.assertIn('transform = 0', result)
        self.assertIn('vrr = 1', result)
        self.assertIn('hl.env("GDK_SCALE", "2")', result)

    def test_unrecognized_and_dynamic_defaults_refused(self):
        with self.assertRaises(ValueError): r.monitor_defaults('hl.monitor(dynamic)')
        with self.assertRaises(ValueError): r.reset_monitors('hl.monitor(dynamic)', {})

    def test_plan_resets_names_and_terminal_size_only(self):
        with tempfile.TemporaryDirectory() as td:
            config = Path(td)
            (config / 'hypr').mkdir()
            (config / 'hypr/monitors.lua').write_text('hl.monitor({ output = "DP-1", scale = 2 })\n')
            (config / 'kitty').mkdir()
            terminal = config / 'kitty/kitty.conf'
            terminal.write_text('font_size 14\nbackground #123456\n')
            plan = r.build_plan(config, STOCK)
            self.assertEqual(plan[terminal], 'font_size 9.0\nbackground #123456\n')
            self.assertEqual(json.loads(plan[config / 'better_displays/display-names.json'])['names'], {})
            self.assertEqual(terminal.read_text(), 'font_size 14\nbackground #123456\n')

    def test_reload_failure_rolls_back_files_and_new_names(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / 'monitors.lua'
            target.write_text('original')
            names = root / 'names.json'
            def run(*args):
                if args == ('hyprctl', 'configerrors'): return 'bad config'
                return ''
            with patch.object(r.settings, 'run', side_effect=run):
                with self.assertRaises(ValueError): r.apply_plan({target: 'candidate', names: '{}'}, root / 'backup')
            self.assertEqual(target.read_text(), 'original')
            self.assertFalse(names.exists())
            self.assertTrue((root / 'backup/manifest.json').exists())

    def test_success_and_concurrent_edit_preservation(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / 'monitors.lua'
            target.write_text('original')
            def run(*args):
                if args == ('hyprctl', 'monitors', '-j'): return '[{"name":"DP-1"}]'
                return 'ok'
            with patch.object(r.settings, 'run', side_effect=run):
                r.apply_plan({target: 'candidate'}, root / 'backup')
            self.assertEqual(target.read_text(), 'candidate')
            def fail(*args):
                target.write_text('concurrent user edit')
                raise ValueError('reload failed')
            with patch.object(r.settings, 'run', side_effect=fail):
                with self.assertRaises(ValueError): r.apply_plan({target: 'next'}, root / 'backup2')
            self.assertEqual(target.read_text(), 'concurrent user edit')


if __name__ == '__main__': unittest.main()
