#!/usr/bin/env python3
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('profiles', Path(__file__).parents[1] / 'bin/display-profiles.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        config, state = root / 'config', root / 'state'
        for name, value in dict(CONFIG=config, NAMES=config / 'better_displays/display-names.json', PROFILES=config / 'better_displays/profiles', STATE=state, PENDING=state / 'pending.json', LAST=state / 'last-restore.json').items():
            patcher = patch.object(p, name, value)
            patcher.start(); self.addCleanup(patcher.stop)
        self.monitor = dict(name='DP-1', make='Dell', model='Panel', serial='1234', width=1920, height=1080, refreshRate=60., scale=1., x=0, y=0, transform=0, availableModes=['1920x1080@60.00Hz'])
        self.items = [self.monitor]
        patcher = patch.object(p, 'machine', return_value='test-machine')
        patcher.start(); self.addCleanup(patcher.stop)
        patcher = patch.object(p, 'monitors', side_effect=lambda: copy.deepcopy(self.items))
        patcher.start(); self.addCleanup(patcher.stop)
        self.config = config / 'hypr/monitors.lua'
        self.config.parent.mkdir(parents=True)
        self.config.write_text('-- custom\nhl.monitor({ output = "DP-1", mode = "1920x1080@60", scale = 1, position = "0x0", vrr = 1 })\n')
        p.write_json(p.NAMES, {'version': 1, 'names': {}})
        self.calls = []
        def run(*args):
            self.calls.append(args)
            if args[:2] == ('hyprctl', 'configerrors'): return ''
            return 'ok'
        patcher = patch.object(p.s, 'run', side_effect=run)
        patcher.start(); self.addCleanup(patcher.stop)

    def profile(self): return p.capture('Working')

    def test_save_never_overwrites_and_rejects_duplicate_name(self):
        key = p.save_profile('Working')
        original = (p.PROFILES / (key + '.json')).read_bytes()
        with self.assertRaisesRegex(ValueError, 'already exists'): p.save_profile('working')
        self.assertEqual((p.PROFILES / (key + '.json')).read_bytes(), original)
        self.assertEqual(len(list(p.PROFILES.glob('*.json'))), 1)

    def test_preferred_toggle_switches_exclusively_and_clears(self):
        first = p.save_profile('First')
        second = p.save_profile('Second')
        self.assertEqual(p.set_preferred(first)['preferred'], first)
        self.assertEqual(p.set_preferred(second, toggle=True)['preferred'], second)
        self.assertEqual(p.read_json(p.PROFILES.parent / 'preferred-profile.json')['id'], second)
        self.assertEqual(p.set_preferred(second, toggle=True)['preferred'], '')
        self.assertEqual(p.set_preferred(first, toggle=True)['preferred'], first)
        self.assertEqual(len(list(p.PROFILES.glob('*.json'))), 2)

    def test_explicit_prefer_is_idempotent_and_invalid_profile_preserves_choice(self):
        first = p.save_profile('First')
        p.set_preferred(first)
        self.assertEqual(p.set_preferred(first)['preferred'], first)
        with self.assertRaises(ValueError): p.set_preferred('0' * 32, toggle=True)
        self.assertEqual(p.read_json(p.PROFILES.parent / 'preferred-profile.json')['id'], first)

    def test_connector_renumbering_matches_identity(self):
        profile = self.profile()
        self.items[0]['name'] = 'DP-9'
        self.config.write_text(self.config.read_text().replace('DP-1', 'DP-9'))
        plan, _, expected, _ = p.profile_plan(profile, self.items)
        self.assertIn('DP-9', expected)
        self.assertIn('vrr = 1', plan[self.config])
        self.assertNotIn('DP-1', plan[self.config])

    def test_new_connector_gets_a_literal_declaration(self):
        profile = self.profile()
        self.items[0]['name'] = 'DP-9'
        plan, _, expected, _ = p.profile_plan(profile, self.items)
        self.assertIn('DP-9', expected)
        self.assertIn('output = "DP-9"', plan[self.config])
        self.assertIn('output = "DP-1"', plan[self.config])

    def test_disconnected_display_is_skipped_and_profile_retained(self):
        other = dict(self.monitor, name='DP-2', serial='5678', x=1920)
        self.items.append(other)
        profile = self.profile()
        self.items.pop()
        original = copy.deepcopy(profile)
        _, _, expected, summary = p.profile_plan(profile, self.items)
        self.assertEqual(len(expected), 1)
        self.assertIn('skipped', summary)
        self.assertEqual(profile, original)

    def test_ambiguous_identity_refused(self):
        self.items.append(dict(self.monitor, name='DP-2'))
        with self.assertRaisesRegex(ValueError, 'unique hardware'): self.profile()

    def test_missing_and_unsupported_mode_refused(self):
        profile = self.profile()
        with self.assertRaisesRegex(ValueError, 'No uniquely'): p.profile_plan(profile, [])
        self.items[0]['availableModes'] = ['640x480@60Hz']
        with self.assertRaisesRegex(ValueError, 'unavailable'): p.profile_plan(profile, self.items)

    def test_unrelated_monitor_overlap_refused(self):
        profile = self.profile()
        self.items.append(dict(self.monitor, name='DP-2', serial='5678', x=1000))
        with self.assertRaisesRegex(ValueError, 'overlap'): p.profile_plan(profile, self.items)

    def test_malformed_profile_refused(self):
        for field, value in [('scale', float('nan')), ('x', 'shell text'), ('transform', 9)]:
            profile = self.profile()
            next(iter(profile['displays'].values()))[field] = value
            with self.assertRaises(ValueError): p.validate(profile)
        with self.assertRaises(ValueError): p.identifier('../elsewhere')

    def test_optional_fonts_and_brightness_not_captured_by_default(self):
        profile = self.profile()
        self.assertEqual(profile['terminals'], {})
        self.assertNotIn('brightness', next(iter(profile['displays'].values())))
        self.assertFalse(self.calls)

    def test_timer_armed_before_write_and_revert_restores_exact_content(self):
        key = p.save_profile('Working')
        before = self.config.read_text()
        orig_run = p.s.run.side_effect
        def run(*args):
            if args[0] == 'systemd-run': self.assertEqual(self.config.read_text(), before)
            return orig_run(*args)
        p.s.run.side_effect = run
        transaction = p.start('profile', key)
        self.assertEqual(transaction['status'], 'waiting')
        self.assertTrue(any(c[0] == 'systemd-run' and '--on-active=20s' in c for c in self.calls))
        p.revert(transaction)
        self.assertEqual(self.config.read_text(), before)
        self.assertEqual(p.pending()['status'], 'reverted')

    def test_failed_timer_leaves_configuration_untouched(self):
        key = p.save_profile('Working')
        before = self.config.read_text()
        orig_run = p.s.run.side_effect
        def run(*args):
            if args[0] == 'systemd-run': raise OSError('no user manager')
            return orig_run(*args)
        p.s.run.side_effect = run
        with self.assertRaisesRegex(ValueError, 'no user manager'): p.start('profile', key)
        self.assertEqual(self.config.read_text(), before)

    def test_revert_preserves_concurrent_edits(self):
        key = p.save_profile('Working')
        transaction = p.start('profile', key)
        self.config.write_text('-- concurrent change\n' + self.config.read_text())
        p.revert(transaction)
        self.assertTrue(self.config.read_text().startswith('-- concurrent'))
        self.assertEqual(p.pending()['status'], 'recovery_needed')

    def test_keep_and_undo_and_expired_keep(self):
        key = p.save_profile('Working')
        original = self.config.read_text()
        transaction = p.start('profile', key)
        with patch('sys.argv', ['profiles', 'keep', '--token', transaction['token']]): p.main()
        self.assertEqual(p.pending()['status'], 'kept')
        plan, _, _, _ = p.build('undo')
        self.assertEqual(plan[self.config], original)
        transaction = p.start('undo')
        transaction['deadline'] = time.time() - 1
        p.write_json(p.PENDING, transaction)
        with patch('sys.argv', ['profiles', 'keep', '--token', transaction['token']]):
            with self.assertRaisesRegex(ValueError, 'expired'): p.main()
        self.assertEqual(p.pending()['status'], 'reverted')

    def test_runtime_refresh_uses_advertised_mode_token(self):
        self.items[0]['refreshRate'] = 60.001
        self.config.write_text(self.config.read_text().replace('1920x1080@60', 'preferred'))
        profile = self.profile()
        plan, _, expected, _ = p.profile_plan(profile, self.items)
        self.assertIn('1920x1080@60.00', plan[self.config])
        self.assertNotIn('@60.001', plan[self.config])
        self.assertEqual(expected['DP-1']['refreshRate'], 60.001)

    def test_equivalent_configured_mode_spelling_is_preserved(self):
        profile = self.profile()
        plan, _, _, _ = p.profile_plan(profile, self.items)
        self.assertIn('mode = "1920x1080@60"', plan[self.config])

    def test_fallback_reinitializes_only_affected_output_once(self):
        profile = self.profile()
        _, _, expected, _ = p.profile_plan(profile, self.items)
        self.items[0]['width'] = 640
        original_run = p.s.run.side_effect
        def run(*args):
            if args[:2] == ('hyprctl', 'dispatch'): self.items[0]['width'] = 1920
            return original_run(*args)
        p.s.run.side_effect = run
        with patch.object(p.time, 'sleep'): p.verify_applied(expected)
        calls = [c for c in self.calls if c[:2] == ('hyprctl', 'dispatch')]
        self.assertEqual(len(calls), 1)
        self.assertIn('output = "DP-1"', calls[0][2])

    def test_runtime_mode_fallback_fails_verification(self):
        profile = self.profile()
        _, _, expected, _ = p.profile_plan(profile, self.items)
        actual = [dict(self.monitor, width=640, height=480)]
        with self.assertRaisesRegex(ValueError, 'did not apply'): p.check_expected(expected, actual)


if __name__ == '__main__': unittest.main()
