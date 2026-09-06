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

## Persistent display names

Select a monitor, enter a name (up to 20 characters), and choose Save or press
Enter. Reset removes its alias. Names appear in the selector, brightness heading,
and relative-position buttons; hover over a selector for its current connector.
Labels never become command arguments in place of actual output names.

Names are saved with atomic writes and a writer lock to
`${XDG_CONFIG_HOME:-~/.config}/better_displays/display-names.json`, outside the
installed plugin and Git checkout. Back up this file with your user configuration.
Disconnected displays retain their entries. The file schema is versioned, and a
malformed file is not overwritten: the panel falls back to connector labels and
shows an error until the file is repaired or restored. Duplicate names are refused,
including names belonging to currently disconnected saved devices. To retire such
an alias, back up the file and remove only that saved entry, or reconnect and Reset.

External identity is a hash of manufacturer, model and non-placeholder serial.
For a built-in panel without a serial, identity combines the machine ID with
manufacturer and model; the raw machine ID is not stored. Renaming ports does not
change either identity. A missing identity or duplicate identity among connected
screens disables naming rather than guessing. Devices that lie about or reuse
serials cannot be reliably distinguished; no connector fallback is persisted.
After an OS reinstall changes machine ID, reassign the laptop alias. A dock or
adapter that reports different identity data likewise requires reassignment.

User labels do not change monitor rules, A/B/C groups, brightness, terminal
settings or firmware. A name follows physical hardware, not its left/right
position. New devices show connector names until named; no machine-specific
aliases are shipped in this repository.

Additional tests: `python3 tests/test-display-names.py -v`. These cover connector
renumbering, same-model displays, internal machine scoping, ambiguous/missing
serials, name validation, reconnect/reset, stale save rejection and corrupted
file preservation. Physical cable hotplug remains a separate acceptance check.

## Brightness input and panel scrolling

Brightness changes require a left click or drag on the slider. Mouse-wheel and
touchpad scroll gestures over it pass through to the containing scroll view;
hovering or prior interaction does not enable wheel adjustment. Canceled drags
reset their preview without committing brightness. This prevents vertical panel
navigation from unexpectedly changing the display.

`ClickSlider.qml` retains the Omarchy slider appearance with plugin-local input
in `ClickSliderInput.qml`. The original packaged slider is untouched. These files
are adapted from Omarchy's MIT-licensed PanelSlider; attribution/license is in
`licenses/omarchy-license.txt`. The Qt event tests run without the Quickshell
runtime by exercising that same input component inside a real ScrollView:

```bash
QT_QPA_PLATFORM=offscreen /usr/lib/qt6/bin/qmltestrunner -input tests/qml -o -,txt
```

The `tst_*.qml` filename is required for Qt test discovery. Tests cover hover,
wheel propagation and intentional click/drag commits.
