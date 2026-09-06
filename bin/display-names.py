#!/usr/bin/env python3
"""Persist display labels by unambiguous hardware identity, never by port."""
import argparse
from collections import Counter
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unicodedata


def normalize_label(value):
    value = unicodedata.normalize('NFC', value.strip())
    if not 1 <= len(value) <= 20:
        raise ValueError('Use a name between 1 and 20 characters.')
    if any(unicodedata.category(c).startswith('C') for c in value):
        raise ValueError('Names cannot contain control or invisible formatting characters.')
    return value


def identity(monitor, machine):
    make = str(monitor.get('make') or '').strip()
    model = str(monitor.get('model') or '').strip()
    serial = str(monitor.get('serial') or '').strip()
    if serial.lower() in ('', '0', 'unknown', 'none', 'n/a') or not serial.strip('0'):
        serial = ''
    if serial and make and model:
        parts = ['serial', make, model, serial]
    elif re.match(r'^(eDP|LVDS|DSI)-', monitor['name']) and machine and make and model:
        parts = ['internal', machine, make, model]
    else:
        return None
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()


def read_names(path):
    if not path.exists(): return {'version': 1, 'names': {}}
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or data.get('version') != 1 or not isinstance(data.get('names'), dict):
        raise ValueError('Unsupported display-name file. Restore or repair it before saving.')
    labels = set()
    for key, label in data['names'].items():
        if not re.fullmatch(r'[a-f0-9]{64}', key) or not isinstance(label, str) or normalize_label(label) != label:
            raise ValueError('Invalid saved display name.')
        if label.casefold() in labels: raise ValueError('Duplicate saved display names.')
        labels.add(label.casefold())
    return data


def decorate(monitors, names, machine):
    keys = [identity(m, machine) for m in monitors]
    counts = Counter(keys)
    result = []
    for m, key in zip(monitors, keys):
        unique = key is not None and counts[key] == 1
        alias = names.get(key, '') if unique else ''
        result.append(dict(m, displayIdentity=key if unique else '', displayAlias=alias,
                           displayLabel=alias or m['name'],
                           namingReason='' if unique else 'No unique hardware identity; using the connector name.'))
    return result


def save_name(path, monitors, machine, output, expected, label=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = read_names(path)
        m = next((m for m in decorate(monitors, data['names'], machine) if m['name'] == output), None)
        if not m or not m['displayIdentity'] or m['displayIdentity'] != expected:
            raise ValueError('Display identity changed or is ambiguous. Select the display again.')
        if label is None:
            data['names'].pop(expected, None)
        else:
            label = normalize_label(label)
            if any(key != expected and value.casefold() == label.casefold() for key, value in data['names'].items()):
                raise ValueError('That name is already assigned to another saved display.')
            data['names'][expected] = label
        fd, tmp = tempfile.mkstemp(prefix='.display-names-', dir=path.parent)
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.write('\n')
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp, path)
        finally:
            Path(tmp).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['list', 'save', 'reset'])
    parser.add_argument('--output')
    parser.add_argument('--identity')
    parser.add_argument('--label')
    args = parser.parse_args()
    path = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'better_displays/display-names.json'
    machine_path = Path('/etc/machine-id')
    machine = machine_path.read_text().strip() if machine_path.exists() else ''
    monitors = json.loads(subprocess.check_output(['hyprctl', 'monitors', '-j'], text=True, timeout=10))
    if args.action == 'list':
        error = ''
        try: names = read_names(path)['names']
        except (ValueError, OSError) as exc:
            names = {}
            error = 'Display names unavailable: ' + str(exc)
        print(json.dumps({'monitors': decorate(monitors, names, machine), 'error': error}))
    else:
        if not args.output or not args.identity or (args.action == 'save' and args.label is None):
            parser.error('Supply --output, --identity, and --label for save.')
        save_name(path, monitors, machine, args.output, args.identity, args.label if args.action == 'save' else None)


if __name__ == '__main__':
    try: main()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
