import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'bin/omarchy-display-terminal'


class TerminalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        bindir = self.home / 'bin'
        bindir.mkdir()
        for name in ('omarchy', 'pkill'):
            path = bindir / name
            path.write_text('#!/bin/sh\nexit 0\n')
            path.chmod(0o755)
        self.env = dict(os.environ, HOME=str(self.home), PATH=str(bindir) + ':' + os.environ['PATH'])
        self.files = {}
        for term, relative, content in [('alacritty', 'alacritty/alacritty.toml', '[font]\nsize = 9\n'), ('kitty', 'kitty/kitty.conf', 'font_size 9.0\n'), ('ghostty', 'ghostty/config', 'font-size = 9\n'), ('foot', 'foot/foot.ini', '[main]\nfont=monospace:size=9\n')]:
            path = self.home / '.config' / relative
            path.parent.mkdir(parents=True)
            path.write_text(content)
            self.files[term] = path

    def command(self, *args):
        return subprocess.run([str(SCRIPT), *args], env=self.env, text=True, capture_output=True)

    def test_decimal_sizes_all_terminals_and_cache(self):
        result = self.command('set-all', '10.5')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.files['kitty'].read_text(), 'font_size 10.5\n')
        sizes = json.loads(self.command('list', '--json').stdout)
        self.assertEqual({float(v) for v in sizes.values()}, {10.5})
        cache = json.loads((self.home / '.config/omarchy/displays.json').read_text())
        self.assertEqual(set(cache['terminals'].values()), {10.5})

    def test_missing_explicit_size_and_invalid_size_do_not_write(self):
        for size in ('0', '41', 'nan'):
            self.assertNotEqual(self.command('set', 'kitty', size).returncode, 0)
        self.files['kitty'].write_text('# default font\n')
        self.assertEqual(json.loads(self.command('list', '--json').stdout)['kitty'], 'n/a')
        self.assertNotEqual(self.command('set', 'kitty', '12').returncode, 0)
        self.assertEqual(self.files['kitty'].read_text(), '# default font\n')
        self.assertFalse((self.home / '.config/omarchy/displays.json').exists())

    def test_corrupt_cache_refuses_before_config_mutation(self):
        cache = self.home / '.config/omarchy/displays.json'
        cache.parent.mkdir(parents=True)
        cache.write_text('{broken')
        before = self.files['kitty'].read_bytes()
        self.assertNotEqual(self.command('set', 'kitty', '12').returncode, 0)
        self.assertEqual(self.files['kitty'].read_bytes(), before)
        self.assertEqual(cache.read_text(), '{broken')


if __name__ == '__main__': unittest.main()
