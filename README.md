# Better Displays

An Omarchy bar widget for per-display brightness, naming, resolution, scale,
position and orientation, plus terminal font sizes and recoverable setup profiles.
Current version: **1.3.4**. The enhancements are under review in
[draft PR #5](https://github.com/nightdevil00/better.displays/pull/5).

## Everyday use

Open Better Displays from its bar icon. It initially selects the screen hosting
that widget; selecting another screen stays in effect until the panel closes.

- **Brightness:** click the slider to drag or adjust with the wheel. Moving the
  pointer away returns wheel input to panel scrolling. Uses Omarchy's hardware
  brightness backend for the selected monitor.
- **Display name:** Edit Display Name reveals Save / Reset / Cancel. Names follow
  unique hardware identities across connector changes; ambiguous devices retain
  connector labels. Names support up to 20 characters.
- **Resolution, scale, position, orientation:** select advertised modes and exact
  compatible scales. Rows/columns preserve order and gaps while neighboring
  positions adjust to the new logical size. Complex layouts refuse new overlaps.
- **Terminal fonts:** independent 6–40 point sizes, including decimals, for
  Alacritty, Kitty, Ghostty and Foot. Existing explicit font settings are required;
  Foot uses the new size in new windows.

### Manage Profiles

Its dropdown selects the profile managed by **Make Preferred** and **Delete**.
These buttons share a row; **Save Current Setup** sits underneath.

Make Preferred is an exclusive, clearable toggle. Saving creates a new named
profile and selects it only in this section. Existing names are refused with
“That profile name already exists. Save with a different name.” Profiles capture
connected displays' live modes, layout and names, with optional brightness/fonts.
Delete requires a confirmation naming the selected profile and retains a recovery
copy. Deleting the preferred profile clears that preference.

### Restore Profile

This section has its own independent dropdown, **Restore Setup** and **Restore
Omarchy Defaults**, with **Undo Last Restore** underneath. Selection alone changes
no display settings. Each restore previews its scope before **Apply and Test**.
An independent systemd timer provides 20 seconds to **Keep Changes** or **Revert
Now**; an unconfirmed restore automatically rolls back even if the widget closes.

Omarchy Defaults uses the installed templates, not a personal first-use snapshot.
It resets managed monitor settings, terminal font sizes and display names.
Brightness has no hardware default and stays unchanged; saved profiles are kept.
Generic preferred modes can replace hardware-specific fixes, so save a working
profile first. Undo requires unchanged affected files and matching hardware.

### Feedback and scrolling

Action notifications expire after six seconds and clear when the panel opens or
closes. Old restore history is never displayed as a new notification. Polling does
not revive expired messages. Live Keep/Revert countdowns and unapplied previews
remain visible while a decision is needed. Save results appear beneath Manage
Profiles. First opening Save or Delete completes layout before scrolling, so the
panel does not jump upward; already-visible controls preserve the scroll offset.

## Install the draft branch

Requires Omarchy with Lua-based Hyprland, Quickshell, `hyprctl`, Python 3, Bash,
`jq`, `luac`, `timeout`, and the desktop user's systemd manager. Brightness support
comes from Omarchy's existing backend. Run as the desktop user.

The draft changes are on the fork branch, not yet on upstream's default branch.
For a new installation with no existing plugin directory:

```bash
git clone --branch feature/brightness-and-safe-monitor-settings \
  https://github.com/KirkAlton-Class7/better.displays.git \
  ~/.config/omarchy/plugins/better.displays
cd ~/.config/omarchy/plugins/better.displays
./install
omarchy plugin validate .
omarchy plugin enable better.displays
omarchy restart shell
```

Keep the plugin as a real directory/independent clone, not a directory symlink.
For an existing installation from this branch, review local changes, then use
`git pull --ff-only origin feature/brightness-and-safe-monitor-settings` in the
installed clone. Validate and restart the shell if it retains cached QML. This
restarts the bar/widget, not the Hyprland session. The first-party Display widget
can remain installed alongside Better Displays.

## Persistence, verification and recovery

The panel passes argument arrays directly to its backend helpers. It does not
interpolate monitor names or user labels into shell command strings. Monitor
edits support literal, single-line `hl.monitor` declarations, preserve unrelated
fields/comments, validate Lua, and use locks, atomic writes and recovery backups.
Dynamic/ambiguous declarations are refused. Monitor settings persist in
`~/.config/hypr/monitors.lua`; terminal-size persistence also uses
`~/.config/omarchy/displays.json`. Names and profiles live separately under
`~/.config/better_displays/` and survive plugin updates.

Every display apply checks actual results. An existing configured/runtime mode
mismatch blocks ordinary scale/layout edits before writes; explicitly selecting a
working resolution on the affected monitor is still allowed. Neither direct nor
profile verification forcibly disables/reconnects an output. Failed changes use
configuration rollback and report incomplete recovery. A driver-level link loss
cannot be repaired or ruled out by configuration checks alone.

A recurring Intel legacy DRM modeset failure remains unresolved on the development
machine. The plugin mitigation avoids forced resets and repeated attempts at an
already-failing mode; it is not a hardware/driver fix. Physical dock/reconnect
coverage and optional brightness/font profile acceptance remain incomplete.

See the detailed runbooks for storage, matching, commands, rollback and limitations:

- [Profiles and guarded restoration](docs/display-profiles.md)
- [Brightness and monitor configuration safety](docs/brightness-and-monitor-safety.md)

## CLI examples

Choose modes reported by `hyprctl monitors -j` for your hardware. Preview edits
with `--dry-run` before applying them.

```bash
omarchy display monitor list
omarchy display monitor set DP-1 --scale 2 --dry-run
omarchy display terminal list
omarchy display terminal set ghostty 14
python3 ~/.config/omarchy/plugins/better.displays/bin/display-profiles.py list
```

The panel invokes scripts by absolute path; `install` exposes the matching
`omarchy display` CLI through symlinks in `~/.local/bin`.

## Validation

```bash
for test_file in tests/test-*.py; do python3 "$test_file" || exit; done
QT_QPA_PLATFORM=offscreen /usr/lib/qt6/bin/qmltestrunner -input tests/qml -o -,txt
/usr/lib/qt6/bin/qmlformat -n Panel.qml >/dev/null
omarchy plugin validate .
```

Latest regression results: **47 Python tests** (21 profiles, 12 monitor, 6 naming,
5 defaults and 3 terminal) and **21 Qt checks** (15 behavior cases plus lifecycle
checks). Qt behavior covers brightness interaction, notification lifetime/history,
and first-expansion scroll positioning. Historical live checks and outstanding
hardware acceptance are distinguished in the detailed runbooks and draft PR.

## Uninstall

```bash
~/.config/omarchy/plugins/better.displays/uninstall
omarchy plugin remove better.displays
```

Uninstall removes the installed command symlinks and plugin. User configuration,
profiles and recovery backups remain available for selective recovery.

## License

MIT. Omarchy-derived slider attribution is included in
[licenses/omarchy-license.txt](licenses/omarchy-license.txt).
