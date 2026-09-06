#!/usr/bin/env python3
"""Named display profiles and shell-independent, timed restore transactions."""
import argparse
from contextlib import contextmanager, ExitStack
from collections import Counter
from datetime import datetime, timezone
import fcntl
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


reset = module('profile_defaults', 'restore-defaults.py')
names = module('profile_names', 'display-names.py')
s = reset.settings
CONFIG = Path.home() / '.config'
NAMES = Path(os.environ.get('XDG_CONFIG_HOME', str(CONFIG))) / 'better_displays/display-names.json'
PROFILES = NAMES.parent / 'profiles'
STATE = Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state'))) / 'better-displays/profiles'
PENDING = STATE / 'pending.json'
LAST = STATE / 'last-restore.json'
SECONDS = 20


def encoded(data): return json.dumps(data, ensure_ascii=False, indent=2) + '\n'


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    s.atomic_write(path, encoded(data), 0o600)


def read_json(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{32}', value): raise ValueError('Invalid profile/restore ID')
    return value


def label(value):
    if not isinstance(value, str): raise ValueError('Profile name must be text')
    value = value.strip()
    if not 1 <= len(value) <= 40 or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError('Use a profile name of 1–40 characters without control characters')
    return value


def monitors(): return json.loads(s.run('hyprctl', 'monitors', '-j'))


def machine(): return Path('/etc/machine-id').read_text().strip()


def identity_map(items):
    keys = [names.identity(m, machine()) for m in items]
    counts = Counter(keys)
    return {key: m for key, m in zip(keys, items) if key and counts[key] == 1}


@contextmanager
def locked():
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    NAMES.parent.mkdir(parents=True, exist_ok=True)
    paths = [STATE / 'transaction.lock', Path(os.environ.get('XDG_RUNTIME_DIR', '/tmp')) / f'better-displays-{os.getuid()}.lock', NAMES.with_suffix('.lock')]
    with ExitStack() as stack:
        for path in paths:
            handle = stack.enter_context(path.open('a'))
            fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def validate(profile):
    if not isinstance(profile, dict) or profile.get('version') != 1: raise ValueError('Unsupported profile format')
    label(profile.get('name'))
    displays = profile.get('displays')
    if not isinstance(displays, dict) or not displays: raise ValueError('Profile has no displays')
    for key, d in displays.items():
        if not re.fullmatch(r'[a-f0-9]{64}', key) or not isinstance(d, dict): raise ValueError('Invalid display identity')
        for field in ('width', 'height', 'x', 'y', 'transform'):
            if type(d.get(field)) is not int: raise ValueError('Invalid ' + field)
        if not (0 < d['width'] <= 32768 and 0 < d['height'] <= 32768 and d['transform'] in range(4)
                and abs(d['x']) <= 100000 and abs(d['y']) <= 100000): raise ValueError('Invalid display geometry')
        for field, low, high in [('scale', .25, 8), ('refreshRate', 1, 1000)]:
            value = d.get(field)
            if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high: raise ValueError('Invalid ' + field)
        if not isinstance(d.get('alias', ''), str): raise ValueError('Invalid display alias')
        if d.get('alias') and names.normalize_label(d['alias']) != d['alias']: raise ValueError('Invalid display alias')
        if 'brightness' in d and (type(d['brightness']) is not int or not 1 <= d['brightness'] <= 100): raise ValueError('Invalid brightness')
    fonts = profile.get('terminals', {})
    if not isinstance(fonts, dict): raise ValueError('Invalid terminal settings')
    for term, size in fonts.items():
        if term not in reset.TERMINALS or type(size) not in (int, float) or not math.isfinite(size) or not 6 <= size <= 40:
            raise ValueError('Invalid terminal font size')
    return profile


def capture(name, include_brightness=False, include_terminals=False):
    connected = monitors()
    mapped = identity_map(connected)
    if len(mapped) != len(connected): raise ValueError('Every connected display needs a unique hardware identity before saving a setup')
    aliases = names.read_names(NAMES)['names']
    displays = {}
    for key, monitor in mapped.items():
        display = {k: monitor[k] for k in ('width', 'height', 'refreshRate', 'scale', 'x', 'y', 'transform')}
        display['alias'] = aliases.get(key, '')
        display['description'] = monitor.get('description', monitor['name'])
        if include_brightness:
            value = s.run('timeout', '12', 'omarchy', 'brightness', 'display', '--monitor', monitor['name'])
            display['brightness'] = int(value)
        displays[key] = display
    result = dict(version=1, name=label(name), created=datetime.now(timezone.utc).isoformat(), displays=displays, terminals={})
    if include_terminals:
        for term, (relative, pattern) in reset.TERMINALS.items():
            path = CONFIG / relative
            if not path.exists(): continue
            matches = re.findall(pattern, path.read_text())
            if len(matches) != 1: raise ValueError('Cannot read explicit font size for ' + term)
            result['terminals'][term] = float(matches[0][1])
    return validate(result)


def save_profile(name, brightness=False, terminals=False):
    PROFILES.mkdir(parents=True, exist_ok=True)
    name = label(name)
    for path in PROFILES.glob('*.json'):
        existing = validate(read_json(path))
        if existing['name'].casefold() == name.casefold(): raise ValueError('That profile name already exists. Save with a different name.')
    profile = capture(name, brightness, terminals)
    key = uuid.uuid4().hex
    write_json(PROFILES / (key + '.json'), profile)
    preferred = PROFILES.parent / 'preferred-profile.json'
    if not preferred.exists(): write_json(preferred, {'id': key})
    return key


def set_preferred(key, toggle=False):
    validate(read_json(PROFILES / (identifier(key) + '.json')))
    path = PROFILES.parent / 'preferred-profile.json'
    current = read_json(path, {}).get('id', '')
    selected = '' if toggle and current == key else key
    write_json(path, {'id': selected})
    return dict(preferred=selected, message='Preferred restore profile updated.' if selected else 'No preferred restore profile selected.')


def delete_profile(key, confirmed=False):
    if not confirmed: raise ValueError('Deleting a profile requires --confirm')
    path = PROFILES / (identifier(key) + '.json')
    profile = validate(read_json(path))
    # Keep a recoverable private copy; deleting a profile never applies it or
    # changes monitor settings, aliases, or the independent restore history.
    backup = STATE / 'deleted-profiles' / (key + '.json')
    write_json(backup, profile)
    preferred_path = PROFILES.parent / 'preferred-profile.json'
    preferred = read_json(preferred_path, {}).get('id', '')
    if preferred == key:
        preferred = ''
        write_json(preferred_path, {'id': ''})
    path.unlink()
    return dict(preferred=preferred, message='Profile deleted. A recovery copy was saved to ' + str(backup))


def edit_profile_monitor(text, connector, fields):
    if not re.fullmatch(r'[A-Za-z0-9_-]+', connector): raise ValueError('Unsupported connector name')
    if not re.search(r'\boutput\s*=\s*"' + re.escape(connector) + r'"', text):
        # A renamed port may have no explicit declaration. Only extend a file
        # whose existing declarations the conservative editor understands.
        reset.reset_monitors(text, {})
        text = text.rstrip() + '\n' + 'hl.monitor({ output = ' + json.dumps(connector) + ' })\n'
    return s.edit_config(text, connector, fields)


def profile_plan(profile, current):
    validate(profile)
    mapped = identity_map(current)
    matched = set(mapped) & set(profile['displays'])
    if not matched: raise ValueError('No uniquely identified connected display matches this profile')
    proposed = {m['name']: dict(m) for m in current}
    original = (CONFIG / 'hypr/monitors.lua').read_text()
    candidate = original
    aliases = names.read_names(NAMES)
    brightness = {}
    expected = {}
    for key in sorted(matched):
        m, saved = mapped[key], profile['displays'][key]
        hz = saved['refreshRate']
        mode = f'{saved["width"]}x{saved["height"]}@{hz}'
        available = m.get('availableModes', [])
        def supported(value):
            match = re.fullmatch(r'(\d+)x(\d+)@([0-9.]+)(?:Hz)?', value)
            return match and int(match[1]) == saved['width'] and int(match[2]) == saved['height'] and abs(float(match[3]) - hz) < .2
        matches = [value for value in available if supported(value)]
        if available and not matches: raise ValueError('Saved mode is unavailable on ' + m['name'])
        if matches:
            # Runtime Hz may have more precision than the advertised mode token.
            # Submit the advertised token, while verifying against saved live Hz.
            mode = min(matches, key=lambda v: abs(float(v.split('@')[1].removesuffix('Hz')) - hz)).removesuffix('Hz')
        for size in (saved['width'], saved['height']):
            if abs(size / saved['scale'] - round(size / saved['scale'])) > .01: raise ValueError('Saved scale does not produce whole logical pixels')
        # Avoid re-modesetting a working output solely for decimal formatting.
        line = next((line for line in original.splitlines() if re.match(r'\s*hl\.monitor', line) and re.search(r'output\s*=\s*"' + re.escape(m['name']) + r'"', line)), '')
        configured = re.search(r'\bmode\s*=\s*"([^"]+)"', line)
        if configured and supported(configured[1]): mode = configured[1]
        fields = dict(mode=mode, scale=saved['scale'], position=f'{saved["x"]}x{saved["y"]}', transform=saved['transform'])
        candidate = edit_profile_monitor(candidate, m['name'], fields)
        expected[m['name']] = {k: saved[k] for k in ('width', 'height', 'refreshRate', 'scale', 'x', 'y', 'transform')}
        expected[m['name']]['identity'] = key
        proposed[m['name']].update(expected[m['name']])
        if saved.get('alias'): aliases['names'][key] = saved['alias']
        else: aliases['names'].pop(key, None)
        if 'brightness' in saved: brightness[key] = saved['brightness']
    # Leave unplugged identities saved in the profile; apply only connected matches.
    # Do not overlap unrelated monitors when restoring a partial setup.
    values = list(proposed.values())
    for i, a in enumerate(values):
        for b in values[i + 1:]:
            if s.overlaps(a, b): raise ValueError('Saved arrangement would overlap ' + a['name'] + ' and ' + b['name'] + '; connect the full setup or save a compatible arrangement')
    labels = list(aliases['names'].values())
    if len({v.casefold() for v in labels}) != len(labels): raise ValueError('Restored names would duplicate an existing display name')
    plan = {CONFIG / 'hypr/monitors.lua': candidate, NAMES: encoded(aliases)}
    for term, size in profile.get('terminals', {}).items():
        relative, pattern = reset.TERMINALS[term]
        path = CONFIG / relative
        if not path.exists(): raise ValueError('Saved terminal configuration is missing: ' + term)
        text = path.read_text()
        if len(re.findall(pattern, text)) != 1: raise ValueError('Ambiguous terminal font size: ' + term)
        plan[path] = re.sub(pattern, lambda m: m[1] + str(size) + m[3], text)
    cache = CONFIG / 'omarchy/displays.json'
    if cache.exists():
        data = read_json(cache)
        if not isinstance(data, dict): raise ValueError('Invalid display cache')
        data['monitors'] = {}
        data.setdefault('terminals', {}).update(profile.get('terminals', {}))
        plan[cache] = encoded(data)
    summary = [f'{mapped[key]["name"]}: {profile["displays"][key]["width"]}×{profile["displays"][key]["height"]}, scale {profile["displays"][key]["scale"]}' for key in sorted(matched)]
    skipped = len(profile['displays']) - len(matched)
    if skipped: summary.append(f'{skipped} disconnected/unmatched display(s) retained in the profile and skipped')
    summary.append('Names and arrangement included. Brightness ' + ('included.' if brightness else 'unchanged.'))
    if profile.get('terminals'): summary.append('Terminal font sizes included; reopen terminals afterward.')
    return plan, brightness, expected, '\n'.join(summary)


def build(kind, key=''):
    current = monitors()
    if kind == 'profile':
        profile = validate(read_json(PROFILES / (identifier(key) + '.json')))
        plan, brightness, expected, summary = profile_plan(profile, current)
        return plan, brightness, expected, profile['name'] + '\n' + summary
    if kind == 'defaults':
        plan = reset.build_plan(CONFIG, Path('/usr/share/omarchy/config'))
        if NAMES != CONFIG / 'better_displays/display-names.json': plan[NAMES] = plan.pop(CONFIG / 'better_displays/display-names.json')
        return plan, {}, {}, 'Omarchy defaults replace custom display fixes and clear all saved names. Brightness stays unchanged. You must Keep Changes within 20 seconds or the setup reverts.'
    if kind == 'undo':
        transaction = read_json(LAST)
        if not transaction: raise ValueError('No kept restore to undo')
        if transaction['topology'] != topology(current): raise ValueError('Connected displays changed. Restore a named profile instead of undoing raw configuration.')
        for f in transaction['files']:
            path = Path(f['path'])
            if (path.read_text() if path.exists() else None) != f['after']: raise ValueError('Configuration changed since the last restore; use a named profile or recover selectively from backup')
        return {Path(f['path']): f['before'] for f in transaction['files']}, transaction['brightness_before'], transaction.get('before_expected', {}), 'Undo the last kept restore. Restore its backed-up settings; Keep Changes within 20 seconds.'
    raise ValueError('Unknown restore type')


def topology(items):
    return {m['name']: names.identity(m, machine()) for m in items}


def config_errors():
    errors = s.run('hyprctl', 'configerrors')
    if errors and errors != 'ok': raise ValueError('Hyprland config errors: ' + errors)


def check_expected(expected, actual):
    mapped = identity_map(actual)
    for connector, fields in expected.items():
        m = mapped.get(fields['identity'])
        if not m or m['name'] != connector: raise ValueError('Display topology changed during restore')
        for field, wanted in fields.items():
            if field == 'identity': continue
            if abs(m[field] - wanted) > (.2 if field == 'refreshRate' else .01): raise ValueError('Display did not apply saved ' + field + ': ' + connector)
    if not actual: raise ValueError('No active displays')


def verify_applied(expected):
    for attempt in range(10):
        try:
            check_expected(expected, monitors())
            return
        except ValueError:
            if attempt < 9: time.sleep(.2)
    mapped = identity_map(monitors())
    # A modeset can leave a connected output stuck on a fallback. Retry that
    # output once. This uses normal compositor hotplug handling, no window or
    # workspace dispatches. Never disable an unrelated or replaced device.
    for connector, fields in expected.items():
        actual = mapped.get(fields['identity'])
        if not actual or actual['name'] != connector: continue
        if any(abs(actual[k] - fields[k]) > (.2 if k == 'refreshRate' else .01) for k in ('width', 'height', 'refreshRate')):
            if not re.fullmatch(r'[A-Za-z0-9_-]+', connector): raise ValueError('Cannot safely reinitialize output name')
            s.run('hyprctl', 'dispatch', 'function() hl.monitor({ output = ' + json.dumps(connector) + ', disabled = true }) end')
            time.sleep(.25)
            s.run('hyprctl', 'reload')
            config_errors()
    for attempt in range(10):
        try:
            check_expected(expected, monitors())
            return
        except ValueError:
            if attempt == 9: raise
            time.sleep(.2)


def get_brightness(targets):
    result = {}
    mapped = identity_map(monitors())
    for key in targets:
        if key not in mapped: raise ValueError('Brightness target disconnected')
        result[key] = int(s.run('timeout', '12', 'omarchy', 'brightness', 'display', '--monitor', mapped[key]['name']))
    return result


def put_brightness(targets, skip_missing=False):
    mapped = identity_map(monitors())
    for key, value in targets.items():
        if key not in mapped:
            if skip_missing: continue
            raise ValueError('Brightness target disconnected')
        s.run('timeout', '12', 'omarchy', 'brightness', 'display', '--no-osd', '--monitor', mapped[key]['name'], str(value) + '%')


def pending(): return read_json(PENDING)


def active(transaction): return transaction and transaction['status'] in ('applying', 'waiting')


def preflight(plan):
    cfg = CONFIG / 'hypr/monitors.lua'
    if cfg in plan:
        if plan[cfg] is None: raise ValueError('Cannot remove monitor configuration')
        subprocess.run(['luac', '-p', '-'], input=plan[cfg], text=True, capture_output=True, check=True, timeout=10)
    config_errors()


def revert(transaction):
    if not active(transaction): return transaction
    conflicts = []
    for item in reversed(transaction['files']):
        path = Path(item['path'])
        now = path.read_text() if path.exists() else None
        if now == item['before']: continue
        if now != item['after']:
            conflicts.append(str(path))
            continue
        if item['before'] is None: path.unlink(missing_ok=True)
        else: s.atomic_write(path, item['before'], item['mode'])
    try:
        s.run('hyprctl', 'reload')
        config_errors()
        # If a driver keeps a fallback mode after reload, report the mismatch;
        # do not silently claim that file restoration proves physical recovery.
        connected = topology(monitors())
        expected = {k: v for k, v in transaction.get('before_expected', {}).items() if connected.get(k) == v['identity']}
        if not conflicts: verify_applied(expected)
        put_brightness(transaction['brightness_before'], skip_missing=True)
    except (ValueError, OSError, subprocess.SubprocessError) as exc: conflicts.append(str(exc))
    transaction['status'] = 'reverted' if not conflicts else 'recovery_needed'
    transaction['message'] = 'Previous setup restored.' if not conflicts else 'Automatic recovery needs attention: ' + '; '.join(conflicts)
    write_json(PENDING, transaction)
    write_json(STATE / 'backups' / transaction['token'] / 'transaction.json', transaction)
    return transaction


def start(kind, key=''):
    if active(pending()): raise ValueError('Keep or revert the pending restore first')
    plan, brightness, expected, summary = build(kind, key)
    preflight(plan)
    current = monitors()
    mapped = identity_map(current)
    before_expected = {m['name']: dict({k: m[k] for k in ('width', 'height', 'refreshRate', 'scale', 'x', 'y', 'transform')}, identity=identity) for identity, m in mapped.items()}
    token = uuid.uuid4().hex
    transaction = dict(token=token, status='applying', deadline=time.time() + SECONDS, summary=summary, topology=topology(current), files=[], brightness_before=get_brightness(brightness), before_expected=before_expected, expected=expected)
    for path, text in plan.items():
        transaction['files'].append(dict(path=str(path), before=path.read_text() if path.exists() else None, after=text, mode=path.stat().st_mode & 0o777 if path.exists() else 0o600))
    transaction["deadline"] = time.time() + SECONDS
    write_json(STATE / 'backups' / token / 'transaction.json', transaction)
    write_json(PENDING, transaction)
    try:
        # Arm BEFORE the first file write. The timer belongs to systemd, not QML,
        # so panel close, shell restart or a dead caller cannot cancel recovery.
        s.run('systemd-run', '--user', '--collect', '--quiet', '--unit=better-displays-revert-' + token,
              '--on-active=' + str(SECONDS) + 's', '--timer-property=AccuracySec=1s',
              sys.executable, str(Path(__file__).resolve()), 'revert', '--token', token, '--expired')
        for item in transaction['files']:
            path = Path(item['path'])
            if (path.read_text() if path.exists() else None) != item['before']: raise ValueError('Concurrent edit: ' + str(path))
            if item['after'] == item['before']: continue
            path.parent.mkdir(parents=True, exist_ok=True)
            if item['after'] is None: path.unlink(missing_ok=True)
            else: s.atomic_write(path, item['after'], item['mode'])
        if any(item['path'] == str(CONFIG / 'hypr/monitors.lua') and item['after'] != item['before'] for item in transaction['files']):
            s.run('hyprctl', 'reload')
        config_errors()
        verify_applied(expected)
        put_brightness(brightness)
        if time.time() >= transaction['deadline']: raise ValueError('Apply took too long; reverted instead of offering an expired confirmation')
        transaction['status'] = 'waiting'
        transaction['deadline'] = time.time() + SECONDS
        transaction['message'] = 'Keep this setup? It reverts automatically unless confirmed.'
        write_json(PENDING, transaction)
        return transaction
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        revert(transaction)
        raise ValueError(str(exc) + '; recovery backup: ' + str(STATE / 'backups' / token)) from exc


def public_status():
    transaction = pending()
    if not transaction: return dict(status='idle', token='', remaining=0, message='')
    return {k: transaction.get(k, '') for k in ('status', 'token', 'message')} | {'remaining': max(0, math.ceil(transaction['deadline'] - time.time()))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['list', 'save', 'prefer', 'toggle-preferred', 'delete', 'preview', 'start', 'keep', 'revert', 'status'])
    parser.add_argument('--confirm', action='store_true')
    parser.add_argument('--name')
    parser.add_argument('--id', default='')
    parser.add_argument('--kind', choices=['profile', 'defaults', 'undo'], default='profile')
    parser.add_argument('--token', default='')
    parser.add_argument('--expired', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--brightness', action='store_true')
    parser.add_argument('--terminals', action='store_true')
    args = parser.parse_args()
    if args.action == 'revert' and args.expired:
        # The guard is armed before apply; after successful verification the user
        # receives a fresh full confirmation interval. Never hold a lock asleep.
        while True:
            with locked():
                transaction = pending()
                if not active(transaction) or transaction['token'] != identifier(args.token):
                    return
                remaining = transaction['deadline'] - time.time()
                if remaining <= 0:
                    revert(transaction)
                    return
            time.sleep(min(remaining, 1))
    with locked():
        if args.action == 'list':
            options, errors = [], []
            for path in sorted(PROFILES.glob('*.json')):
                try:
                    identifier(path.stem)
                    profile = validate(read_json(path))
                    options.append(dict(value=path.stem, label=profile['name']))
                except (ValueError, OSError) as exc: errors.append(path.name + ': ' + str(exc))
            try:
                preferred = read_json(PROFILES.parent / 'preferred-profile.json', {}).get('id', '')
            except (ValueError, OSError, AttributeError):
                preferred = ''
                errors.append('Preferred profile record is unreadable; select a profile manually.')
            print(encoded(dict(profiles=options, preferred=preferred, errors=errors, undo=LAST.exists(), pending=public_status())))
        elif args.action == 'status': print(encoded(public_status()))
        elif args.action == 'revert':
            transaction = pending()
            if transaction and transaction['token'] == identifier(args.token): revert(transaction)
            print(encoded(public_status()))
        elif args.action == 'keep':
            transaction = pending()
            if not active(transaction) or transaction['status'] != 'waiting' or transaction['token'] != identifier(args.token): raise ValueError('No matching restore awaiting confirmation')
            if time.time() >= transaction['deadline']:
                revert(transaction)
                raise ValueError('Confirmation expired; previous setup restored')
            if topology(monitors()) != transaction['topology']:
                revert(transaction)
                raise ValueError('Connected displays changed; restore reverted')
            config_errors()
            check_expected(transaction.get('expected', {}), monitors())
            for item in transaction['files']:
                path = Path(item['path'])
                if (path.read_text() if path.exists() else None) != item['after']:
                    raise ValueError('Configuration changed during confirmation; revert or recover selectively')
            transaction['status'] = 'kept'
            transaction['message'] = 'Setup kept. Undo Last Restore is available.'
            write_json(LAST, transaction)
            write_json(PENDING, transaction)
            write_json(STATE / 'backups' / transaction['token'] / 'transaction.json', transaction)
            print(encoded(public_status()))
        else:
            if active(pending()): raise ValueError('Keep or revert the pending restore first')
            if args.action == 'save': print(encoded(dict(id=save_profile(args.name, args.brightness, args.terminals), message='Setup saved as a new profile.')))
            elif args.action in ('prefer', 'toggle-preferred'):
                print(encoded(set_preferred(args.id, toggle=args.action == 'toggle-preferred')))
            elif args.action == 'delete': print(encoded(delete_profile(args.id, args.confirm)))
            elif args.action == 'preview':
                plan, _, _, summary = build(args.kind, args.id)
                preflight(plan)
                print(encoded(dict(summary=summary, files=[str(p) for p in plan])))
            elif args.action == 'start':
                start(args.kind, args.id)
                print(encoded(public_status()))


if __name__ == '__main__':
    try: main()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
