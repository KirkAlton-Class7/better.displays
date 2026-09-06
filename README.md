# Better Displays

A [Omarchy](https://omarchy.org/) shell plugin that puts **granular display and
terminal control** in a bar widget you open directly from the status bar.

![preview](preview.png)

## Features

- **Per-monitor** resolution (real modes reported by the monitor), scale,
  position (left/right/above/below another display), and orientation
  (0°/90°/180°/270°).
- **Per-terminal font size** for alacritty, kitty, ghostty, and foot, with
  live − / + steppers.
- All changes apply **live** via Hyprland and **persist** to
  `~/.config/omarchy/displays.json` and `~/.config/hypr/monitors.lua` (so they
  survive a reboot).
- A matching `omarchy display ...` CLI group and an interactive Display menu
  submenu (the scripts are installed onto `PATH` automatically).

## Requirements

- Omarchy (Hyprland-based) with the Quickshell shell.
- `bash` and `jq` (both standard on Omarchy).
- `hyprctl` (provided by Hyprland).

## Install

### Via `omarchy plugin add` (recommended)

```bash
omarchy plugin add https://github.com/nightdevil00/better.displays.git --enable
```

This clones the plugin, validates it, and enables the bar widget. When the
shell loads the plugin it **auto-installs the backend scripts** onto `PATH`
(`~/.local/bin`, falling back to `/usr/local/bin`), so the `omarchy display`
CLI group and the Display menu submenu work immediately. No manual step needed.

### Manual

```bash
git clone https://github.com/nightdevil00/better.displays.git \
  ~/.config/omarchy/plugins/better.displays
cd ~/.config/omarchy/plugins/better.displays
./install                 # symlink the backend scripts into ~/.local/bin
omarchy plugin enable better.displays
omarchy restart shell
```

## Use it

- Click the **Better Displays** icon in the bar (next to the monitor icon), or
  summon it: `omarchy-shell shell summon better.displays`.
- Pick a monitor, then adjust Resolution / Scale / Position / Orientation, and
  tune each terminal's font size.

CLI equivalents (interactive shell):

```bash
omarchy display monitor list
omarchy display monitor set DP-1 --mode 2560x1440@144 --scale 1.6 --pos 0x0 --transform 0
omarchy display terminal list
omarchy display terminal set ghostty 14
omarchy display terminal set-all 13
```

## Uninstall

```bash
~/.config/omarchy/plugins/better.displays/uninstall   # drop the PATH symlinks
omarchy plugin remove better.displays
```

(`uninstall` removes the `omarchy-display-*` symlinks; `omarchy plugin remove`
deletes the plugin folder. Order does not matter, but run both for a clean
removal.)

## How it works

The plugin folder bundles everything it needs:

```
better.displays/
├── manifest.json        # plugin metadata (bar-widget)
├── Panel.qml            # the bar widget + popup (reuses Omarchy's qs.Ui kit)
├── bin/                 # backend scripts (self-contained, travel with the plugin)
│   ├── omarchy-display-monitor
│   ├── omarchy-display-terminal
│   └── omarchy-display-pick
├── install              # symlink bin/* into ~/.local/bin (idempotent)
├── uninstall            # remove those symlinks
├── preview.png
└── README.md
```

`Panel.qml` invokes the scripts by their absolute path inside `bin/`, so the
widget works the moment the folder is present — the `install` step only exists
to expose the `omarchy display` CLI / menu.

## Security

The plugin receives monitor names, mode strings, positions, and scale values
from Hyprland (`hyprctl monitors -j`) and passes them through several layers:

**Panel.qml** — constructs `bash -c` commands to call the backend scripts. All
interpolated values (monitor name, flags, terminal names, sizes) are wrapped
with `shellEscape()` which quotes each argument with single quotes and escapes
any embedded single quotes, preventing shell metacharacter injection.

**omarchy-display-monitor** —

| Concern | Mitigation |
| --- | --- |
| Monitor name in jq filter | `jq --arg` used instead of string interpolation, so names cannot break out of the filter expression |
| Values embedded in Lua expressions (`hyprctl eval`, `monitors.lua`) | All inputs validated against strict regex patterns **before** use: output names match `[a-zA-Z0-9_-]+(:[a-zA-Z0-9_-]+)?`, modes match `WxH@R[Hz]`, positions match `XxY` or `auto`, scales are numeric, transforms are `0`–`3`. String values are also run through `lua_escape()` which escapes `\` and `"` for safe Lua double-quote embedding |
| Values used in grep/awk patterns | `persist_to_lua` uses the same `lua_escape()` output in its grep regex and awk `-v` assignments |

**omarchy-display-terminal** — validates that the terminal name is one of the
known set (`alacritty`, `kitty`, `ghostty`, `foot`) via a whitelist check and
that the font size is numeric (`^[0-9]+(\.[0-9]+)?$`).

## License

MIT — do what you like, attribute if you're feeling generous.

## Fork enhancements

This fork adds brightness for the selected display using Omarchy's existing
hardware backend, fixes logical display positioning, and adds conservative
monitor-file updates with backups, validation and error rollback. It supersedes
the original persistence behavior described above: monitor edits are now stored
only in `monitors.lua`, preserving unrelated fields instead of replacing the
whole declaration. See [behavior, tests, installation and rollback](docs/brightness-and-monitor-safety.md).


### Monitor selection and Restore Defaults

Each time Better Displays opens, it selects the monitor hosting that widget's bar.
The matching monitor button uses the existing active styling and its saved name,
if assigned. Keyboard focus on another screen does not affect this selection.
You can select another monitor while the panel is open; periodic refresh keeps
that choice. Reopening returns to the widget's own monitor. If that screen is
unavailable, the monitor refresh falls back to the focused connected monitor,
then the first available monitor.

**Restore Omarchy Defaults**, under **Restore**, previews a reset of all configured monitor declarations to Omarchy's
installed policy: preferred resolution, automatic scale and position, and normal
orientation. Existing terminal font sizes reset from installed Omarchy templates
(currently 9pt); reopen terminals afterward. All saved display names are cleared,
including disconnected monitors. Hardware brightness stays unchanged because
Omarchy defines no default brightness percentage. Workspace bindings and unrelated
configuration are preserved. These are installed defaults, not a snapshot of
personal settings from first use.

Apply and Test creates a recovery backup before writing. Keep Changes confirms the
result; otherwise an independent timer reverts it after 20 seconds. Full scope, preview commands, limitations and recovery steps
are in [the configuration runbook](docs/brightness-and-monitor-safety.md#click-focused-brightness-and-restore-defaults-current-behavior).


### Named setups (version 1.3)

Use **Save Current Setup** in **Manage Profiles** to reveal profile naming and optional brightness/font
inclusions. **Restore Setup** previews a saved configuration, then **Apply and
Test** offers **Keep Changes / Revert Now**. **Make Preferred** chooses your preferred
profile. **Undo Last Restore** recovers the last kept restore when its
files and connected hardware have not changed. Profiles match hardware identities,
survive plugin updates and never overwrite another saved setup.

**Edit Display Name** now reveals Save / Reset / Cancel only while editing.
Editors and restore previews stay collapsed otherwise. Omarchy defaults remain an
explicit secondary choice because generic preferred modes can replace custom
hardware fixes. They never overwrite your saved profiles.

See [named setup controls, storage, recovery, CLI and tests](docs/display-profiles.md)
for the current restore behavior, including disconnected monitors, optional scope,
timed rollback and driver fallback handling. This supersedes the older direct
reset flow described in historical enhancement notes.


Manage Profiles contains **Make Preferred** and **Delete**, with **Save Current Setup** on its own row below. Manage Profiles has its own profile selector for preference and deletion. The
separate Restore Profile selector chooses only the setup to restore. Make Preferred remains a clearable, exclusive toggle. Delete asks for
confirmation naming the selected profile and retains a private recovery copy.
Save feedback and errors appear below Manage Profiles. Existing profile names
report: “That profile name already exists. Save with a different name.”

Scale buttons now disable exact scales incompatible with the current resolution.
Rows and columns reflow when changing scale, resolution or orientation, preserving
screen order, gaps and perpendicular offsets. Complex layouts refuse new overlap.
Every edit checks all connected displays, including preserved resolutions, and
reports driver fallback without disabling/reconnecting outputs. An existing
fallback blocks scale/layout edits until a working resolution is selected.

Verification: 47 Python tests and five Qt input behavior cases (seven Qt passes
including setup/cleanup). See the runbooks for coverage and hardware limitations.
