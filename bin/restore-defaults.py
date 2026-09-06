#!/usr/bin/env python3
"""Restore panel-managed values from installed Omarchy defaults, with rollback."""
import argparse
from contextlib import ExitStack
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

spec = importlib.util.spec_from_file_location('monitor_settings', Path(__file__).with_name('monitor-settings.py'))
settings = importlib.util.module_from_spec(spec)
spec.loader.exec_module(settings)

TERMINALS = {
    'alacritty': ('alacritty/alacritty.toml', r'(?m)^(size\s*=\s*)([0-9.]+)(\s*(?:#.*)?)$'),
    'kitty': ('kitty/kitty.conf', r'(?m)^(font_size\s+)([0-9.]+)(\s*(?:#.*)?)$'),
    'ghostty': ('ghostty/config', r'(?m)^(font-size\s*=\s*)([0-9.]+)(\s*(?:#.*)?)$'),
    'foot': ('foot/foot.ini', r'(?m)^(font\s*=.*:size=)([0-9.]+)([^\n]*)$'),
}


def monitor_defaults(template):
    # Fail closed if the installed default changes to another policy or syntax.
    active = '\n'.join(line for line in template.splitlines() if not line.lstrip().startswith('--'))
    if not (re.search(r'local\s+omarchy_monitor_scale\s*=\s*"auto"', active)
            and re.search(r'hl\.monitor\(\{\s*output\s*=\s*"",\s*mode\s*=\s*"preferred",\s*position\s*=\s*"auto",\s*scale\s*=\s*omarchy_monitor_scale\s*\}\)', active)):
        raise ValueError('Installed Omarchy monitor defaults are not recognized; no files changed.')
    return dict(mode='preferred', position='auto', scale='auto', transform=0)


def reset_monitors(original, defaults):
    active = '\n'.join(line for line in original.splitlines() if not line.lstrip().startswith('--'))
    outputs = re.findall(r'\boutput\s*=\s*"([^"\n]*)"', active)
    if not outputs or len(outputs) != active.count('hl.monitor(') or len(set(outputs)) != len(outputs):
        raise ValueError('Monitor declarations are dynamic, missing, or duplicated; restore manually.')
    # Existing conservative editor matches declarations only, but its occurrence
    # check includes comments: reject ambiguous files rather than rewrite comments.
    candidate = original
    for output in outputs:
        candidate = settings.edit_config(candidate, output, defaults)
    return candidate


def build_plan(config, stock):
    monitor = config / 'hypr/monitors.lua'
    plan = {monitor: reset_monitors(monitor.read_text(), monitor_defaults((stock / 'hypr/monitors.lua').read_text()))}
    sizes = {}
    for term, (relative, pattern) in TERMINALS.items():
        target = config / relative
        if not target.exists(): continue
        defaults = re.findall(pattern, (stock / relative).read_text())
        if len(defaults) != 1: raise ValueError('Cannot determine default font size for ' + term)
        size = defaults[0][1]
        original = target.read_text()
        if len(re.findall(pattern, original)) != 1:
            raise ValueError('Need one explicit font-size setting for ' + term + '; no files changed.')
        plan[target] = re.sub(pattern, lambda m: m[1] + size + m[3], original)
        sizes[term] = float(size)
    names = config / 'better_displays/display-names.json'
    plan[names] = json.dumps({'version': 1, 'names': {}}, indent=2) + '\n'
    cache = config / 'omarchy/displays.json'
    if cache.exists():
        data = json.loads(cache.read_text())
        if not isinstance(data, dict): raise ValueError('Invalid display preference cache')
        data['monitors'] = {}
        data['terminals'] = sizes
        plan[cache] = json.dumps(data, indent=2) + '\n'
    return plan


def apply_plan(plan, backup):
    originals = {p: p.read_bytes() if p.exists() else None for p in plan}
    modes = {p: p.stat().st_mode & 0o777 if p.exists() else 0o600 for p in plan}
    backup.mkdir(parents=True, mode=0o700)
    manifest = []
    for i, (path, content) in enumerate(originals.items()):
        saved = str(i) + '-' + path.name
        if content is not None: (backup / saved).write_bytes(content)
        manifest.append(dict(path=str(path), backup=saved if content is not None else None, mode=modes[path]))
    (backup / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    written = []
    try:
        for path, candidate in plan.items():
            now = path.read_bytes() if path.exists() else None
            if now != originals[path]: raise ValueError('Concurrent edit: ' + str(path))
            path.parent.mkdir(parents=True, exist_ok=True)
            settings.atomic_write(path, candidate, modes[path])
            written.append(path)
        settings.run('hyprctl', 'reload')
        errors = settings.run('hyprctl', 'configerrors')
        if errors and errors != 'ok': raise ValueError(errors)
        if not json.loads(settings.run('hyprctl', 'monitors', '-j')):
            raise ValueError('No active monitors after restore')
    except Exception:
        for path in reversed(written):
            if path.read_text() != plan[path]:
                print('Concurrent edit preserved: ' + str(path), file=sys.stderr)
                continue
            if originals[path] is None: path.unlink()
            else: settings.atomic_write(path, originals[path].decode(), modes[path])
        print('Recovery backup: ' + str(backup), file=sys.stderr)
        try:
            settings.run('hyprctl', 'reload')
            errors = settings.run('hyprctl', 'configerrors')
            if errors and errors != 'ok': print('Rollback config errors: ' + errors, file=sys.stderr)
        except subprocess.SubprocessError as error:
            print('Rollback reload failed: ' + str(error), file=sys.stderr)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    if not args.dry_run:
        # All user-facing defaults restores use the independent timed guard.
        os.execv(sys.executable, [sys.executable, str(Path(__file__).with_name('display-profiles.py')), 'start', '--kind', 'defaults'])
    config = Path.home() / '.config'
    names_config = Path(os.environ.get('XDG_CONFIG_HOME', str(config)))
    stock = Path('/usr/share/omarchy/config')
    lock = Path(os.environ.get('XDG_RUNTIME_DIR', tempfile.gettempdir())) / f'better-displays-{os.getuid()}.lock'
    names_lock = names_config / 'better_displays/display-names.lock'
    names_lock.parent.mkdir(parents=True, exist_ok=True)
    with ExitStack() as stack:
        for path in (lock, names_lock):
            handle = stack.enter_context(path.open('a'))
            fcntl.flock(handle, fcntl.LOCK_EX)
        plan = build_plan(config, stock)
        if names_config != config:
            content = plan.pop(config / 'better_displays/display-names.json')
            plan[names_config / 'better_displays/display-names.json'] = content
        subprocess.run(['luac', '-p', '-'], input=plan[config / 'hypr/monitors.lua'], text=True, check=True, capture_output=True, timeout=10)
        print(json.dumps({str(p): text for p, text in plan.items()}, indent=2))



if __name__ == '__main__':
    try: main()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
