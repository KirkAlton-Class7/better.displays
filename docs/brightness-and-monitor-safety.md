> Current restoration flow (v1.3): see [Named setups and guarded restoration](display-profiles.md).
> All restores now use preview, Apply and Test, and independent 20-second Keep/Revert.
> Monitor naming is opened explicitly with Edit Display Name. Historical descriptions
> of an immediate defaults reset below are superseded by that flow.

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

## Stock panel interaction conventions

Better Displays uses the installed shell's `PanelKeyCatcher`, `Button`,
`TextField`, `SearchableDropdown`, and `CursorSurface`. It keeps a panel cursor
separate from the actual selected monitor, scale, and orientation. Hover updates
that cursor; it never writes settings. Buttons activate by clicking or with
Enter/Space. The selected setting retains the stock active appearance.

Up/Down (or j/k) moves between control groups; Left/Right (or h/l) moves between
buttons within a group, including wrapped monitor-position choices. The first
navigation key establishes a cursor if none is active. Disabled and hidden
controls are skipped. Navigation stops at the ends and scrolls the highlighted
control into view. On brightness, Left/Right explicitly requests a five-point
change, using the existing busy guard; wheel and touchpad scrolling never adjust
brightness. Enter on that row does nothing. Click/drag still writes on release.

Enter or a click starts editing a display name. Typing and arrow keys then belong
to the field. Enter saves, Escape returns to panel navigation, and Tab leaves the
field for Save. Unsaved text survives periodic refresh and losing input focus;
switching monitors replaces the draft with that monitor's saved name. Save/Reset
returns keyboard focus to the panel. The resolution popup owns its search and
selection keys until it closes. Outside editors, Tab/Shift+Tab follows the stock
panel-switching action and Escape closes the panel.

Hover during active panel scrolling does not move the panel cursor, and hovering
another control does not steal keys from an active editor or resolution search.
Connector tooltips use the shared button's `tooltipText` API.

Verification on Omarchy 4.0.2: QML parse, manifest validation, four automated
slider interaction cases (plus test setup/cleanup), and live keyboard navigation
through groups with automatic scrolling passed. Full physical input acceptance
and monitor hotplug remain review items. No monitor settings were intentionally
changed during the navigation check. For a manual check, hover scale/orientation
choices without clicking and confirm the active value remains unchanged; scroll
across brightness and confirm only panel content moves; enter a name, leave the
field, wait over four seconds, then save; open resolution search, type and cancel
without choosing a mode.


## Click-focused brightness and Restore Defaults (current behavior)

Clicking the brightness slider now takes keyboard focus and permits both dragging
and wheel adjustments (five percentage points per wheel event). Hover alone
continues to pass scrolling to the panel. Leaving the slider, choosing another
control/monitor, or closing the panel ends wheel adjustment. Pressed drags retain
the mouse grab, so the surrounding ScrollView cannot steal the gesture. The
slider remains responsive during hardware reads/writes; it coalesces pending
brightness values to the latest requested target and writes serially. This
supersedes the earlier unconditional wheel blocking described above. A parent /
child enabled-state dependency was removed to prevent disabling the slider.

The **Restore Defaults** section contains a **Restore Defaults** button. It now previews the stated scope before Apply and Test, with a recovery backup and
timed confirmation:

- All literal monitor declarations in `~/.config/hypr/monitors.lua`: preferred
  mode, automatic scale and position, normal orientation. Unrelated fields,
  globals, comments, workspace rules and bindings are preserved.
- Existing terminal configurations: font sizes from the installed Omarchy
  templates (currently 9pt). Other terminal settings are preserved. Reopen
  terminals to apply fonts; this action does not terminate terminal processes.
- Every saved display alias, including disconnected monitors: cleared.
- Existing plugin monitor cache: cleared; terminal-size cache updated.
- Hardware brightness: unchanged, because Omarchy defines no factory/default
  brightness percentage. This is stated beside the button.

The monitor policy is verified against `/usr/share/omarchy/config/hypr/monitors.lua`
before writing; unknown future syntax/policy is refused instead of guessed.
Terminal defaults are read from `/usr/share/omarchy/config` at invocation. This
restores installed defaults, not a snapshot of personal settings from first use.
Complex monitor declarations or ambiguous font-size settings require manual
restoration. Other Hyprland files can override these settings; they are not reset.

Preview without applying: `python3 bin/restore-defaults.py --dry-run`.
Apply using the button or `python3 bin/restore-defaults.py`. The helper uses the
monitor editor lock and display-name lock, validates Lua and existing Hyprland
errors, saves files, reloads, and checks configuration errors and active outputs.
Failures roll back files that still match its writes, preserving concurrent edits.
Backups are in `~/.local/state/better-displays/defaults-backups/<UTC timestamp>/`.
`manifest.json` maps each original path to its backup and permission mode; a null
backup means the original did not exist. To undo, close the panel, restore those
listed files (remove newly created files listed with null), then run `hyprctl
reload` and `hyprctl configerrors`. Resolve concurrent edits selectively. Automatic
rollback detects errors; it is not a timed visual keep/revert dialog.

Validation: five restore tests cover policy recognition/refusal, scoped file
changes, successful apply, failed-reload rollback and concurrent edit preservation.
Run `python3 tests/test-restore-defaults.py -v`. The existing thirteen Python
regressions pass. Qt slider tests now cover five input behaviors (seven passes
including setup/cleanup), including click-to-enable wheel and leave-to-scroll.
The real-machine restore preview passes; restoration itself is intentionally
not triggered as part of installing the button.
