# Named setups and guarded restoration

Version 1.3 introduces named profiles so a working hardware setup is not confused
with Omarchy's generic defaults. Profiles contain data, not executable scripts.
They are independent of the installed plugin checkout and survive plugin updates.

## Everyday controls

The widget selects its hosting monitor each time it opens. **Edit Display Name**
reveals the name field and Save / Reset / Cancel controls. Save or Reset applies
only to the selected hardware identity and closes the editor. Cancel or Escape
discards the draft; switching monitor or closing the panel also closes the editor.
Naming is unavailable for displays without an unambiguous identity.

**Manage Profiles** contains **Make Preferred** and **Delete**, with **Save Current Setup** on its own row below.
Each section has an independent profile dropdown. The one in **Restore Profile** sits
above Restore Setup and Restore Omarchy Defaults;
Undo Last Restore remains underneath. The Manage Profiles dropdown determines the profile managed by Make Preferred
and Delete. Changing it does not change the Restore Profile selection, and vice versa. The preferred button retains its
label and highlights only for the one preferred selection; clicking again clears
it. Saving creates and selects a new profile in Manage Profiles only. Both selectors
keep their own valid selection during refreshes. If their selected profile is
deleted, each independently falls back to the preferred profile or first available
profile; with none available it becomes empty. Save feedback and errors appear
immediately below Manage Profiles, with automatic scrolling to the message.

Delete expands an inline confirmation naming the selected profile. Cancel makes
no changes. Confirm Delete deletes only that captured profile ID; changing the
selector or closing the widget cancels confirmation. The preferred flag is cleared
only when that profile was preferred. Existing display settings and independent
restore history are untouched. A private recovery copy is retained at
`~/.local/state/better-displays/profiles/deleted-profiles/ID.json`. Copy it back to
`~/.config/better_displays/profiles/ID.json` to recover it (then choose preference
again if desired). CLI deletion requires `delete --id ID --confirm`; missing
confirmation is refused before any write. The same lock serializes save, preference,
delete and restore; deletion during a pending restore is refused.

The controls offer:

| Control | Result |
| --- | --- |
| Profile selector | Choose a saved setup without changing hardware. |
| Restore Setup | Preview the selected setup, then choose Apply and Test. |
| Save Current Setup | Reveal the setup name, optional inclusions and Save New Profile. |
| Make Preferred | Toggle the selected profile as preferred. Setting another replaces the old choice; clicking the active button clears it. Does not apply a setup. |
| Undo Last Restore | Preview the exact backup of the last kept restore. |
| Restore Omarchy Defaults | Preview a reset that explicitly warns custom fixes and aliases will be replaced. |
| Keep Changes | Keep the applied setup within the 20-second confirmation window. |
| Revert Now | Immediately recover the previous configuration. |

Editors and previews expand only when requested. Keyboard navigation scrolls
expanded controls into view. Normal panel shortcuts are suspended while typing
or searching. A working profile is never overwritten automatically or by Save:
duplicate names (case insensitive) are rejected with “That profile name already exists. Save with a different name.” Save a new name for a revision.
The first profile becomes preferred. The toggle follows the selected dropdown
entry immediately: it is active only for the single saved preferred ID. Changes
made in another widget instance synchronize through the persisted preference.
Clicking the active Make Preferred button clears the preference; with none set the selector falls back
to an available profile without marking it preferred. Saving another profile
does not override an explicitly cleared preference.

## Captured settings and matching

A profile always captures the **live** resolution, refresh rate, scale,
orientation, absolute logical position and alias of every connected display.
It does not assume that a requested configuration mode actually applied.
Names allow up to 40 characters. Brightness and terminal font sizes are explicit
optional inclusions, off by default. If brightness is requested but cannot be
read on a connected monitor, saving fails instead of silently omitting it.
Existing terminal files need one explicit font-size setting to be included.

External monitors match by manufacturer/model/serial identity. Internal panels
without serials also use machine scope, just like display naming. No raw machine
ID is stored. Connector names are resolved at restore time. If a renamed connector
has no declaration, a new literal declaration is added only when the existing
monitor file can be safely understood. Old/unrelated declarations are preserved.
Duplicate identities are not guessed; saving requires unique identities for all
connected screens. A restore requires at least one unique connected match.

Disconnected/unmatched screens stay in the saved file and are skipped during
apply. Their aliases and configurations are not rewritten by that partial apply.
Connected displays outside the profile are unchanged. A layout that would overlap
any connected monitor is refused rather than rearranging unrelated screens.
Absolute positions can leave gaps when only part of a setup is connected; save
separate full-desk and laptop-only profiles if appropriate. No profile is applied
automatically on hotplug. Workspace ownership and keybinding files are not edited.

Live refresh rates can be more precise than advertised modes. Restore chooses a
matching advertised mode token and verifies its result with a small refresh-rate
tolerance. Equivalent existing spellings (e.g. `60` vs `60.00`) are preserved to
avoid unnecessary modesets. Unchanged files are not rewritten.

## Apply, confirmation and recovery

Preview validates the profile, target identities, supported modes, geometry,
editable declarations and Lua syntax. Apply rebuilds/validates the plan, acquires
the shared monitor and naming locks, and saves a private transaction backup.
A systemd user timer is armed **before the first write**. If the timer cannot be
created, no configuration change is allowed. The timer does not depend on QML or
the panel remaining open. No additional persistent daemon or login service is
installed; transient timers finish after handling their transaction.

The helper writes configuration atomically, reloads Hyprland and checks actual
mode, scale, position, orientation and identity. A persistent fallback causes
transaction recovery after a bounded settling period. Verification never disables
or reconnects an output: automatic resets can worsen a failed modeset on some
Intel setups. Rollback restores configuration, but cannot guarantee recovery of a
physical link the driver has lost. Incomplete recovery is reported with backups.

After successful apply, the user gets a full 20 seconds to Keep Changes. Without
confirmation the independent timer restores the prior files; Revert Now does the
same immediately. A crashed caller is covered by the timer armed before writes.
An apply that takes more than the initial 20-second guard interval is rejected and
recovered. DDC brightness operations are bounded but may delay recovery while an
in-flight operation completes. Keep rechecks topology, actual values, config
errors and file contents. A late confirmation cannot keep an expired transaction.

Undo Last Restore is available after Keep. It requires the same connected
hardware/connector mapping and unchanged affected files; otherwise use a named
profile or selective backup recovery. Undo itself has the same preview and timed
confirmation. It does not blindly overwrite newer edits.

Rollback restores a file only if it still matches the transaction's write. If
another editor changed it, that edit is preserved and the UI reports that recovery
needs attention. Runtime failures during rollback are also reported. Hardware
recovery cannot guarantee a physical image after a cable/driver failure; inspect
the reported mode and the screen. Profiles/backups are retained for manual repair.

## Omarchy defaults remain a separate choice

Defaults mean the currently installed Omarchy policy, not a saved personal setup:
preferred resolution, automatic scale and position, normal orientation, existing
terminal font sizes from installed templates, and all saved aliases cleared.
Hardware brightness is unchanged because Omarchy provides no default percentage.
Unrelated config, workspace bindings and extra monitor fields are preserved.
Generic preferred modes can be unsuitable for a dock/monitor combination. Use a
verified named setup as the ordinary restore choice; the defaults action requires
explicit preview/apply and has the same Keep/Revert protection.

## Storage, portability and CLI

- `${XDG_CONFIG_HOME:-~/.config}/better_displays/profiles/<id>.json`: versioned
  semantic profile. IDs are stable 32-character lowercase hexadecimal filenames;
  user-facing names are stored inside, so renaming labels does not create paths.
- `better_displays/preferred-profile.json` beside that directory: preferred ID.
- `${XDG_STATE_HOME:-~/.local/state}/better-displays/profiles/backups/<token>/transaction.json`:
  private before/after contents, permissions, expected modes and optional brightness.
- `pending.json` and `last-restore.json` in that state directory: current recovery
  state and most recent kept restore. These are machine/session recovery records,
  not portable profiles. Do not copy them to another workstation.

Copy profile JSON files and the preferred-ID file to back up/transfer setups.
Internal-screen identities need recreation after a machine-ID change. Profiles
for absent external hardware remain available. To retire a profile, close the
widget and move its JSON file into a separate archive directory outside `profiles`;
if it was preferred, choose another in the widget. Malformed profile files are
reported and skipped while valid profiles remain available.

From the plugin directory:

```bash
python3 bin/display-profiles.py list
python3 bin/display-profiles.py save --name 'Desk Working'
python3 bin/display-profiles.py save --name 'Desk with Fonts' --terminals
python3 bin/display-profiles.py preview --id PROFILE_ID
python3 bin/display-profiles.py start --id PROFILE_ID
python3 bin/display-profiles.py status
python3 bin/display-profiles.py keep --token RESTORE_TOKEN
python3 bin/display-profiles.py revert --token RESTORE_TOKEN
python3 bin/display-profiles.py preview --kind defaults
python3 bin/display-profiles.py preview --kind undo
python3 bin/display-profiles.py prefer --id PROFILE_ID
```

Use the IDs/tokens printed by prior commands. `start --kind defaults` and
`start --kind undo` apply those plans with the same timed guard.
`restore-defaults.py --dry-run` remains a read-only legacy preview;
`restore-defaults.py` delegates to the guarded defaults start, never an immediate
unguarded reset. CLI commands must run as the desktop user inside the active
Hyprland session, with access to its systemd user manager and IPC environment.

For manual recovery, close the panel, inspect a transaction's `files` records,
and selectively restore `before` text and `mode` to each `path`. A null `before`
means the file did not exist; remove it only if it still matches `after`. Back up
newer edits first. Run `hyprctl reload`, `hyprctl configerrors`, and compare
`hyprctl monitors -j` with `before_expected`. Names are not a substitute for matching
hardware identity. Do not invoke privileged commands for these user-owned files.

## Validation

Run the Python test files directly (hyphenated filenames are not discovered by
unittest's default pattern), then the Qt input tests:

```bash
python3 tests/test-display-profiles.py -v
python3 tests/test-restore-defaults.py -v
python3 tests/test-monitor-settings.py -v
python3 tests/test-display-names.py -v
QT_QPA_PLATFORM=offscreen /usr/lib/qt6/bin/qmltestrunner -input tests/qml -o -,txt
```

The profile suite covers immutable saves, renamed/missing/ambiguous identities,
new connector declarations, malformed input, overlap refusal, optional scope,
canonical modes, fallback detection without output resets, timer failure before write,
rollback, concurrent edits, Keep, Undo and expired confirmation. On the development
machine the real systemd timeout restored the previous setup; live apply/Keep,
Undo preview/apply and explicit Revert passed. Broad dock/hotplug and optional DDC
profile restoration still need hardware acceptance before the PR leaves draft.


The Profiles and Restore action buttons use shared bordered controls and spacing.
The preferred toggle has a stable width so its shorter active label does not move
Save Current Setup. The restore actions can wrap on narrow panels; Undo stays
underneath. Button labels have no trailing ellipses. CLI `prefer --id ID` remains
idempotent; `toggle-preferred --id ID` performs the widget's atomic toggle under
the shared lock.
