#!/usr/bin/env python3
"""Conservative edits to literal, single-line Hyprland monitor declarations."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time


def run(*args):
    return subprocess.check_output(args, text=True, stderr=subprocess.STDOUT, timeout=20).strip()


def edit_config(text, output, changes):
    # Deliberately refuse dynamic/multiline configurations, rather than attempting
    # to parse arbitrary Lua or append a competing declaration.
    pattern = re.compile(r'^([ \t]*hl\.monitor\(\{[^{}\n]*?\}\)[ \t]*(?:--[^\n]*)?)$', re.M)
    matches = [m for m in pattern.finditer(text)
               if re.search(r'\boutput\s*=\s*"' + re.escape(output) + r'"', m[0])]
    declarations = re.findall(r'\boutput\s*=\s*"' + re.escape(output) + r'"', text)
    if len(matches) != 1 or len(declarations) != 1:
        raise ValueError('Need exactly one literal single-line hl.monitor declaration for ' + output + '. Edit complex configurations manually.')
    match = matches[0]
    line = match[0]
    for key, value in changes.items():
        # Field boundaries prevent matching text within another field name.
        field = re.compile(r'([,{]\s*' + key + r'\s*=\s*)("[^"\n]*"|[0-9]+(?:\.[0-9]+)?)(?=\s*[,}])')
        found = list(field.finditer(line))
        encoded = json.dumps(value)
        if len(found) == 1:
            line = field.sub(lambda m: m[1] + encoded, line)
        elif re.search(r'\b' + key + r'\s*=', line):
            raise ValueError('Cannot safely replace nonliteral or duplicate ' + key)
        else:
            line = re.sub(r',?\s*\}\)', ', ' + key + ' = ' + encoded + ' })', line, count=1)
    return text[:match.start()] + line + text[match.end():]


def geometry(m):
    w, h = m['width'], m['height']
    if m.get('transform', 0) % 2: w, h = h, w
    return (m['x'], m['y'], w / m['scale'], h / m['scale'])


def overlaps(a, b):
    ax, ay, aw, ah = geometry(a)
    bx, by, bw, bh = geometry(b)
    return min(ax + aw, bx + bw) > max(ax, bx) + .01 and min(ay + ah, by + bh) > max(ay, by) + .01


def proposal(current, args, monitors, reflow=False):
    proposed = dict(current)
    changes = {}
    if args.mode:
        mode = re.fullmatch(r'(\d+)x(\d+)@(\d+(?:\.\d+)?)(?:Hz)?', args.mode)
        if not mode: raise ValueError('Mode must be WxH@Hz')
        w, h, hz = int(mode[1]), int(mode[2]), float(mode[3])
        if w <= 0 or h <= 0 or hz <= 0: raise ValueError('Mode values must be positive')
        available = current.get('availableModes', [])
        if available and not any(re.fullmatch(rf'{w}x{h}@{re.escape(mode[3])}(?:Hz)?', m) for m in available):
            raise ValueError('Choose a mode reported by the monitor')
        proposed.update(width=w, height=h, refreshRate=hz)
        changes['mode'] = f'{w}x{h}@{mode[3]}'
    if args.scale is not None:
        if not math.isfinite(args.scale) or not .25 <= args.scale <= 8:
            raise ValueError('Scale must be between 0.25 and 8')
        proposed['scale'] = args.scale
        changes['scale'] = args.scale
    if args.mode or args.scale is not None:
        for size in (proposed['width'], proposed['height']):
            logical = size / proposed['scale']
            if abs(logical - round(logical)) > .01:
                raise ValueError('Scale must produce whole logical pixels for the selected resolution; choose another scale')
    if args.pos:
        if args.pos != 'auto' and not re.fullmatch(r'-?\d+x-?\d+', args.pos):
            raise ValueError('Position must be XxY or auto')
        if args.pos != 'auto': proposed['x'], proposed['y'] = map(int, args.pos.split('x'))
        changes['position'] = args.pos
    if args.transform is not None:
        proposed['transform'] = args.transform
        changes['transform'] = args.transform
    if not changes: raise ValueError('Specify at least one setting')
    if args.pos != 'auto' and not reflow:
        for other in monitors:
            if other['name'] != current['name'] and overlaps(proposed, other) and not overlaps(current, other):
                raise ValueError('This would overlap ' + other['name'] + '. Move the display first, or pass --pos with the scale/mode change.')
    return proposed, changes


def arrange(monitors, proposed, args):
    """Preserve order, gaps and perpendicular offsets in rows/columns.

    Anchor the first screen. A larger logical desktop pushes later screens;
    shrinking pulls them back. Complex layouts retain explicit positions and
    refuse new overlaps instead of guessing which branch should move.
    """
    result = [dict(proposed if m['name'] == proposed['name'] else m) for m in monitors]
    if not args.pos:
        for axis, dimension in ((0, 2), (1, 3)):
            ordered = sorted(monitors, key=lambda m: geometry(m)[axis])
            if all(geometry(a)[axis] + geometry(a)[dimension] <= geometry(b)[axis] + .01
                   for a, b in zip(ordered, ordered[1:])):
                by_name = {m['name']: m for m in result}
                coordinate = ('x', 'y')[axis]
                for a, b in zip(ordered, ordered[1:]):
                    gap = geometry(b)[axis] - geometry(a)[axis] - geometry(a)[dimension]
                    new_a = by_name[a['name']]
                    by_name[b['name']][coordinate] = round(geometry(new_a)[axis] + geometry(new_a)[dimension] + gap)
                break
    if args.pos != 'auto':
        before = {m['name']: m for m in monitors}
        for i, a in enumerate(result):
            for b in result[i + 1:]:
                if overlaps(a, b) and not overlaps(before[a['name']], before[b['name']]):
                    raise ValueError('This would overlap ' + a['name'] + ' and ' + b['name'] + '. Adjust Position first for this layout.')
    return result


def verify_layout(expected, auto_output=None):
    """Check preserved modes as well as edited fields, with one fallback retry."""
    def inspect():
        actual = {m['name']: m for m in json.loads(run('hyprctl', 'monitors', '-j'))}
        errors, fallback = [], []
        if set(actual) != {m['name'] for m in expected}:
            errors.append('Monitor connections changed during apply')
        for wanted in expected:
            m = actual.get(wanted['name'])
            if not m: continue
            if any(m.get(k) != wanted.get(k) for k in ('make', 'model', 'serial')):
                errors.append('Monitor identity changed: ' + wanted['name'])
                continue
            for key in ('width', 'height', 'refreshRate', 'scale', 'x', 'y', 'transform'):
                if wanted['name'] == auto_output and key in ('x', 'y'): continue
                if abs(m.get(key, 0) - wanted.get(key, 0)) > (.2 if key == 'refreshRate' else .01):
                    errors.append('Hyprland did not apply requested ' + key + ': ' + wanted['name'])
                    if key in ('width', 'height', 'refreshRate'): fallback.append(wanted['name'])
        return errors, set(fallback)
    for attempt in range(2):
        for poll in range(10):
            errors, fallback = inspect()
            if not errors: return
            time.sleep(.2)
        if attempt or not fallback: break
        # Some docks accept the scale but fall back to another resolution. Only
        # reinitialize the same physical output once; never cycle other screens.
        for output in sorted(fallback):
            run('hyprctl', 'dispatch', 'function() hl.monitor({ output = ' + json.dumps(output) + ', disabled = true }) end')
        time.sleep(.25)
        run('hyprctl', 'reload')
        errors = run('hyprctl', 'configerrors')
        if errors and errors != 'ok': raise ValueError(errors)
    raise ValueError('; '.join(errors))


def atomic_write(path, content, mode):
    fd, temp = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp, mode)
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['list', 'set'])
    parser.add_argument('output', nargs='?')
    parser.add_argument('--mode')
    parser.add_argument('--scale', type=float)
    parser.add_argument('--pos', '--position')
    parser.add_argument('--transform', type=int, choices=range(4))
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    monitors = json.loads(run('hyprctl', 'monitors', '-j'))
    if args.command == 'list':
        for m in monitors:
            print(f'{m["name"]}\tmode={m["width"]}x{m["height"]}@{m["refreshRate"]}\tscale={m["scale"]}\tpos={m["x"]},{m["y"]}\ttransform={m["transform"]}')
        return
    config = Path.home() / '.config/hypr/monitors.lua'
    lock = Path(os.environ.get('XDG_RUNTIME_DIR', tempfile.gettempdir())) / f'better-displays-{os.getuid()}.lock'
    with lock.open('w') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        pending_path = Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state'))) / 'better-displays/profiles/pending.json'
        if pending_path.exists() and json.loads(pending_path.read_text()).get('status') in ('applying', 'waiting'):
            raise ValueError('Keep or revert the pending restore first')
        monitors = json.loads(run('hyprctl', 'monitors', '-j'))
        current = next((m for m in monitors if m['name'] == args.output), None)
        if current is None: raise ValueError('Selected monitor is not connected')
        original = config.read_text()
        # Honor explicitly configured modes even if the driver is currently in
        # fallback. Runtime geometry remains the reference for arranging screens.
        intended = [dict(m) for m in monitors]
        for m in intended:
            for line in original.splitlines():
                if not re.match(r'\s*hl\.monitor\(', line): continue
                if not re.search(r'\boutput\s*=\s*"' + re.escape(m['name']) + r'"', line): continue
                mode_match = re.search(r'\bmode\s*=\s*"(\d+)x(\d+)@(\d+(?:\.\d+)?)"', line)
                if mode_match:
                    m.update(width=int(mode_match[1]), height=int(mode_match[2]), refreshRate=float(mode_match[3]))
        wanted = next(m for m in intended if m['name'] == args.output)
        proposed, changes = proposal(wanted, args, intended, reflow=True)
        expected = arrange(intended, proposed, args)
        candidate = edit_config(original, args.output, changes)
        for before, after in zip(monitors, expected):
            if (before['x'], before['y']) != (after['x'], after['y']):
                candidate = edit_config(candidate, after['name'], {'position': f'{after["x"]}x{after["y"]}'})
        if args.dry_run:
            print(candidate, end='')
            return
        if candidate == original:
            verify_layout(expected, args.output if args.pos == 'auto' else None)
            print('Already configured and verified; no change')
            return
        subprocess.run(['luac', '-p', '-'], input=candidate, text=True, check=True, capture_output=True, timeout=10)
        errors = run('hyprctl', 'configerrors')
        if errors and errors != 'ok': raise ValueError('Resolve existing Hyprland config errors first: ' + errors)
        backup = Path.home() / '.local/state/better-displays/backups' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        backup.mkdir(parents=True)
        shutil.copy2(config, backup / 'monitors.lua')
        mode = config.stat().st_mode & 0o777
        if config.read_text() != original: raise ValueError('Configuration changed during preflight; retry')
        atomic_write(config, candidate, mode)
        try:
            run('hyprctl', 'reload')
            errors = run('hyprctl', 'configerrors')
            if errors and errors != 'ok': raise ValueError(errors)
            verify_layout(expected, args.output if args.pos == 'auto' else None)
        except Exception:
            if config.read_text() == candidate:
                atomic_write(config, original, mode)
                run('hyprctl', 'reload')
                rollback_errors = run('hyprctl', 'configerrors')
                if rollback_errors and rollback_errors != 'ok':
                    print('Rollback config errors: ' + rollback_errors, file=sys.stderr)
                try: verify_layout(monitors)
                except Exception as error: print('Recovery needs attention: ' + str(error) + '; backup: ' + str(backup), file=sys.stderr)
            else:
                print('Concurrent edit detected; restore selectively from ' + str(backup), file=sys.stderr)
            raise
        print('Applied ' + args.output + '; backup: ' + str(backup / 'monitors.lua'))


if __name__ == '__main__':
    try: main()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
