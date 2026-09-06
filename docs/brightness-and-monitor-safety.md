# Per-display brightness and configuration safety

## What changes

Select a connected monitor in Better Displays, then use its Brightness slider.
The number is read through `omarchy brightness display --monitor NAME`. The
slider applies on release through the same backend, with `--no-osd` and an
absolute percentage. It never changes scale, position, workspaces, or terminal
settings. Laptop backlights and external DDC support are owned by Omarchy;
unsupported displays show an unavailable message. The slider is disabled during
hardware operations; reads/writes have a 12-second timeout. Old reads from a
previous selection are ignored, and a drag cannot transfer to another monitor.
The panel polls only while open. It does not install shell hooks.

The original Display widget remains separate and can stay enabled. The plugin's
panel/IPC identity is now `better.displays`, matching its manifest. Relative
position buttons use scaled, rotated logical dimensions rather than raw pixels.

## Monitor changes

`bin/omarchy-display-monitor` delegates to `monitor-settings.py` (Python 3).
`monitors.lua` is the authoritative persistent source; the fork does not write
a second competing copy of monitor settings into `displays.json`. Existing
terminal preferences in that JSON remain the terminal helper's responsibility.

Only requested fields in exactly one literal, single-line `hl.monitor` declaration
are edited. Extra fields, other monitors, global settings and comments are
preserved. Dynamic, nested, duplicate or multiline declarations are refused;
edit those manually. Mode/scale combinations must produce whole logical pixels.
A new overlap with another connected screen is refused; specify a compatible
position in the same CLI command or move the monitor first. Existing coordinates
are preserved unless position is explicitly requested, so scaling may create a
gap; no automatic rearrangement or workspace ownership change is performed.

Use `--dry-run` to preview without applying:

```bash
omarchy display monitor set eDP-1 --scale 2 --dry-run
```

Before applying, the helper checks existing Hyprland configuration errors,
checks Lua syntax with `luac`, backs up `monitors.lua` beneath
`~/.local/state/better-displays/backups/<UTC timestamp>/`, and atomically writes
the candidate preserving permissions. It reloads Hyprland, checks configuration
errors and verifies the live requested properties. If these checks fail, it
restores and reloads the original when no intervening edit has occurred.
Concurrent edits are not overwritten during rollback; the backup path is reported.
This is error recovery, not a timed visual-confirmation/revert dialog. Unsupported
hardware modes can still briefly blank a display during a requested modeset.

Dependencies: the upstream Omarchy prerequisites plus Python 3, Lua's `luac`,
and GNU `timeout`. The plugin does not change packaged Omarchy files.

## Development and installation

Development checkout on Kirk's machine: `$HOME/devsecops/better_displays`.
Keep source separate from the installed clone at
`~/.config/omarchy/plugins/better.displays`; do not symlink the plugin directory.

Run checks from the development checkout:

```bash
python3 tests/test-monitor-settings.py -v
omarchy plugin validate "$PWD"
/usr/lib/qt6/bin/qmlformat Panel.qml >/dev/null
```

Install from the fork's feature branch after backing up the old installed plugin
outside the plugin search directory. Clone with:

```bash
git clone --branch feature/brightness-and-safe-monitor-settings \
  https://github.com/KirkAlton-Class7/better.displays.git \
  ~/.config/omarchy/plugins/better.displays
```

If it already exists, do not clone over it. Check for local modifications before
updating, then pull the same branch. The bar keeps the same plugin ID and layout.
The plugin's existing startup installer refreshes its backend symlinks. Rescan
with `omarchy-shell shell rescanPlugins`; restart the shell only if necessary.

## Rollback

Restore the backed-up installed plugin directory, run its `install --silent`, and
rescan plugins. Keep the same bar ID. For monitor settings, restore only the
intended backed-up declaration into `~/.config/hypr/monitors.lua`, preserving any
later edits, then run `hyprctl reload` and `hyprctl configerrors`.
Brightness changes are hardware settings: use the slider to restore the desired
percentage; restoring a plugin or layout file does not restore brightness.

## Upstream contribution

Keep brightness and safe monitor persistence independently reviewable. Include
regression tests and a description of the behavior above. Do not attach private
monitor/workspace configurations or workstation screenshots to upstream issues.
Kirk's machine-specific deployment evidence belongs in the workstation repo.
