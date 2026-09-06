import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Io
import qs.Ui
import qs.Commons

Panel {
  id: root
  moduleName: "better.displays"
  ipcTarget: "better.displays"
  manageIpc: true

  property var monitors: []
  property string selected: ""
  property var terminalSizes: ({})
  property int brightnessPercent: 0
  property int pendingBrightness: -1
  property bool brightnessAvailable: false
  property string brightnessMessage: "Select a monitor"
  property string actionError: ""
  property string namesError: ""
  property string namesReadError: ""
  property bool nameEditing: false
  property bool profileEditing: false
  property bool saveBrightness: false
  property bool saveTerminals: false
  property var profiles: []
  property string selectedProfile: ""
  property string preferredProfile: ""
  property var restoreState: ({status: "idle", token: "", remaining: 0})
  property bool canUndo: false
  property string previewKind: ""
  property string previewId: ""
  property string previewText: ""
  readonly property bool restoreBusy: defaultsProc.running || restoreState.status === "applying" || restoreState.status === "waiting"

  function profileAction(action, kind, id) {
    if (defaultsProc.running) return
    defaultsProc.action = action
    var command = ["python3", root.scriptDir + "/display-profiles.py", action]
    if (kind) command = command.concat(["--kind", kind])
    if (id) command = command.concat(["--id", id])
    if (action === "keep" || action === "revert") command = command.concat(["--token", root.restoreState.token])
    if (action === "delete") command.push("--confirm")
    if (action === "save") {
      command = command.concat(["--name", profileNameField.text])
      if (root.saveBrightness) command.push("--brightness")
      if (root.saveTerminals) command.push("--terminals")
    }
    if (action === "preview") { root.previewKind = kind; root.previewId = id; root.previewText = "" }
    root.defaultsMessage = ""
    defaultsProc.command = command
    defaultsProc.running = true
  }

  // Match the stock Display panel: one panel cursor, explicit activation,
  // native editor/dropdown key ownership, and shared theme control surfaces.
  property int cursorRow: 0
  property int cursorColumn: 0
  property bool cursorActive: false

  function controls() {
    var result = []
    function visit(item) {
      if (item.navRow !== undefined && item.visible && item.enabled) result.push(item)
      for (var i = 0; i < item.children.length; i++) visit(item.children[i])
    }
    visit(panelColumn)
    return result.sort(function(a, b) { return a.navRow - b.navRow || a.navColumn - b.navColumn })
  }

  function cursorOn(item) {
    return cursorActive && cursorRow === item.navRow && cursorColumn === item.navColumn
  }

  function pointCursor(item) {
    if (nameField.activeFocus || profileNameField.activeFocus || profileDropdown.popupOpen || resolutionDropdown.popupOpen || scrollArea.contentItem.moving) return
    cursorRow = item.navRow
    cursorColumn = item.navColumn
    cursorActive = true
  }

  function reveal(item) {
    var flick = scrollArea.contentItem
    var y = item.mapToItem(flick.contentItem, 0, 0).y
    if (y < flick.contentY) flick.contentY = Math.max(0, y - 6)
    else if (y + item.height > flick.contentY + flick.height)
      flick.contentY = Math.max(0, Math.min(flick.contentHeight - flick.height, y + item.height - flick.height + 6))
  }

  function moveCursor(dx, dy) {
    var items = controls()
    if (!items.length) return
    var current = items.find(function(item) { return root.cursorOn(item) })
    if (!current) current = items[0]
    else if (dy) {
      var rows = items.filter(function(item) { return dy > 0 ? item.navRow > current.navRow : item.navRow < current.navRow })
      if (rows.length) {
        var row = dy > 0 ? rows[0].navRow : rows[rows.length - 1].navRow
        current = rows.find(function(item) { return item.navRow === row })
      }
    } else if (dx && current === brightnessRow) {
      root.setBrightness(root.brightnessPercent + dx * 5)
    } else if (dx) {
      var siblings = items.filter(function(item) { return item.navRow === current.navRow })
      current = siblings[Math.max(0, Math.min(siblings.length - 1, siblings.indexOf(current) + dx))]
    }
    cursorRow = current.navRow
    cursorColumn = current.navColumn
    cursorActive = true
    reveal(current)
  }

  function activateCursor() {
    var item = controls().find(function(item) { return root.cursorOn(item) })
    if (item) item.activate()
  }

  component NavigationButton: Button {
    id: control
    required property int navRow
    property int navColumn: 0
    enabled: !root.restoreBusy
    hasCursor: root.cursorOn(control)
    onHovered: function(inside) { if (inside) root.pointCursor(control) }
    onClicked: {
      root.cursorRow = navRow
      root.cursorColumn = navColumn
      root.cursorActive = true
      keyCatcher.forceActiveFocus()
    }
    function activate() { clicked() }
  }

  function displayName(connector) {
    var m = root.monitorByName(connector)
    return m ? m.displayLabel : connector
  }

  function editName(reset) {
    var m = root.selectedMonitor()
    if (!m || !m.displayIdentity || nameAction.running || root.restoreBusy) return
    nameAction.command = ["python3", root.scriptDir + "/display-names.py", reset ? "reset" : "save",
                          "--output", m.name, "--identity", m.displayIdentity]
    if (!reset) nameAction.command = nameAction.command.concat(["--label", nameField.text])
    root.namesError = ""
    nameAction.running = true
  }

  function loadNameField() {
    var m = root.selectedMonitor()
    nameField.text = m ? m.displayAlias : ""
    nameField.identity = m ? m.displayIdentity : ""
    nameField.dirty = false
  }


  function refreshBrightness() {
    if (!root.opened || !root.selected || brightnessRead.running || brightnessWrite.running || brightnessSlider.dragging) return
    brightnessRead.monitor = root.selected
    brightnessRead.command = ["timeout", "12", "omarchy", "brightness", "display", "--monitor", brightnessRead.monitor]
    brightnessRead.running = true
  }

  onSelectedChanged: {
    root.pendingBrightness = -1
    root.nameEditing = false
    if (brightnessSlider.activeFocus) keyCatcher.forceActiveFocus()
    root.loadNameField()
    root.brightnessAvailable = false
    root.brightnessMessage = "Reading brightness…"
    root.refreshBrightness()
  }

  function setBrightness(value) {
    if (!root.brightnessAvailable || root.restoreBusy) return
    root.pendingBrightness = Math.max(1, Math.min(100, Math.round(value)))
    root.brightnessPercent = root.pendingBrightness
    flushBrightness()
  }

  function flushBrightness() {
    if (brightnessWrite.running || brightnessRead.running || pendingBrightness < 0) return
    brightnessWrite.monitor = root.selected
    brightnessWrite.command = ["timeout", "12", "omarchy", "brightness", "display", "--no-osd", "--monitor", root.selected, pendingBrightness + "%"]
    pendingBrightness = -1
    brightnessWrite.running = true
  }


  // Absolute path to this plugin's bundled scripts, so the panel works on
  // install without relying on the shell's PATH. (Qt.resolvedUrl(".") is the
  // directory of this Panel.qml.)
  readonly property string scriptDir: Qt.resolvedUrl(".").toString().replace("file://", "") + "/bin"

  readonly property var scalePresets: ["1", "1.25", "1.5", "1.6", "2", "3", "4"]
  readonly property var transformPresets: ["0", "1", "2", "3"]
  readonly property var terminals: ["alacritty", "kitty", "ghostty", "foot"]

  function shellEscape(s) {
    if (s === undefined || s === null) return "''"
    var str = String(s)
    return "'" + str.replace(/'/g, "'\\''") + "'"
  }

  function selectedMonitor() {
    if (!root.monitors || root.monitors.length === 0) return null
    for (var i = 0; i < root.monitors.length; i++)
      if (root.monitors[i].name === root.selected) return root.monitors[i]
    for (var j = 0; j < root.monitors.length; j++)
      if (root.monitors[j].focused) return root.monitors[j]
    return root.monitors[0]
  }

  function currentModeString(m) {
    if (!m || !m.modes || m.modes.length === 0) return ""
    var best = ""
    var bestDiff = 1e9
    var cur = Number(m.refreshRate)
    for (var i = 0; i < m.modes.length; i++) {
      var s = m.modes[i]
      var at = s.indexOf("@")
      if (at < 0) continue
      var dims = s.slice(0, at)
      var rate = parseFloat(s.slice(at + 1).replace("Hz", ""))
      if (!isNaN(rate) && dims === (m.width + "x" + m.height)) {
        var diff = Math.abs(rate - cur)
        if (diff < bestDiff) { bestDiff = diff; best = s }
      }
    }
    return best
  }

  function modeOptions(m) {
    if (!m || !m.modes) return []
    var seen = {}
    var out = []
    for (var i = 0; i < m.modes.length; i++) {
      var s = m.modes[i]
      if (!s || seen[s]) continue
      seen[s] = true
      out.push({ value: s, label: s })
    }
    return out
  }

  function refresh() {
    if (!monitorProc.running) monitorProc.running = true
    if (!termProc.running) termProc.running = true
    if (!profileList.running) profileList.running = true
    root.refreshBrightness()
  }

  function validScale(value) {
    var m = selectedMonitor()
    if (!m) return false
    return [m.width, m.height].every(function(size) { return Math.abs(size / Number(value) - Math.round(size / Number(value))) <= 0.01 })
  }

  function setMonitor(flag, val) {
    var m = root.selectedMonitor()
    if (!m || actionProc.running || root.restoreBusy) return
    root.actionError = ""
    actionProc.command = [root.scriptDir + "/omarchy-display-monitor", "set", m.name, flag, String(val)]
    if (!actionProc.running) actionProc.running = true
  }

  function setTerminal(term, size) {
    if (actionProc.running || root.restoreBusy) return
    root.actionError = ""
    actionProc.command = [root.scriptDir + "/omarchy-display-terminal", "set", term, String(size)]
    if (!actionProc.running) actionProc.running = true
  }

  function stepTerminal(term, delta) {
    var cur = Number(root.terminalSizes[term] || 0)
    if (!(cur > 0)) return
    var next = cur + delta
    if (next < 6) next = 6
    if (next > 40) next = 40
    root.setTerminal(term, next)
  }

  function posFor(selected, other, dir) {
    var sr = Number(selected.transform) % 2 !== 0
    var orot = Number(other.transform) % 2 !== 0
    var sw = Math.round((sr ? selected.height : selected.width) / selected.scale)
    var sh = Math.round((sr ? selected.width : selected.height) / selected.scale)
    var ox = other.x, oy = other.y
    var ow = Math.round((orot ? other.height : other.width) / other.scale)
    var oh = Math.round((orot ? other.width : other.height) / other.scale)
    if (dir === "left") return (ox - sw) + "x" + oy
    if (dir === "right") return (ox + ow) + "x" + oy
    if (dir === "above") return ox + "x" + (oy - sh)
    if (dir === "below") return ox + "x" + (oy + oh)
    return "auto"
  }

  function monitorByName(name) {
    for (var i = 0; i < root.monitors.length; i++)
      if (root.monitors[i].name === name) return root.monitors[i]
    return null
  }

  function positionButtons() {
    var sel = root.selectedMonitor()
    if (!sel) return []
    var out = []
    var dirs = [
      { dir: "left", glyph: "◀" },
      { dir: "right", glyph: "▶" },
      { dir: "above", glyph: "▲" },
      { dir: "below", glyph: "▼" }
    ]
    for (var i = 0; i < root.monitors.length; i++) {
      var o = root.monitors[i]
      if (o.name === root.selected) continue
      for (var d = 0; d < dirs.length; d++)
        out.push({ label: dirs[d].glyph + " " + o.displayLabel, other: o.name, dir: dirs[d].dir })
    }
    return out
  }

  Component.onCompleted: {
    root.refresh()
    // Install the backend scripts onto PATH on first load so the `omarchy
    // display` CLI group and the Display menu submenu work after the plugin
    // is added/enabled. Idempotent — safe to run every load.
    if (!installProc.running) installProc.running = true
  }

  onOpenedChanged: {
    if (opened) {
      cursorActive = false
      // Use the panel's bar screen, not keyboard focus on another monitor.
      // Do this only on opening so polling preserves manual selections.
      root.selected = panel.screen ? panel.screen.name : ""
      refresh()
    }
    else {
      if (brightnessSlider.activeFocus) keyCatcher.forceActiveFocus()
      root.nameEditing = false
      root.profileEditing = false
      root.deleteProfileId = ""
      root.previewText = ""
    }
  }

  Timer {
    interval: 4000
    running: root.opened
    repeat: true
    onTriggered: root.refresh()
  }

  property string defaultsMessage: ""
  property string manageMessage: ""
  property string deleteProfileId: ""
  property string deleteProfileLabel: ""
  Timer {
    interval: 1000
    running: root.opened
    repeat: true
    onTriggered: if (!profileList.running) profileList.running = true
  }
  Process {
    id: profileList
    command: ["python3", root.scriptDir + "/display-profiles.py", "list"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        try {
          var result = JSON.parse(text)
          // Avoid rebuilding dropdown delegates while the user types in it.
          if (JSON.stringify(root.profiles) !== JSON.stringify(result.profiles)) root.profiles = result.profiles
          root.preferredProfile = result.preferred || ""
          if (!root.profiles.some(function(p) { return p.value === root.selectedProfile }))
            root.selectedProfile = root.profiles.some(function(p) { return p.value === root.preferredProfile }) ? root.preferredProfile : (root.profiles.length ? root.profiles[0].value : "")
          root.restoreState = result.pending
          root.canUndo = result.undo
          if (result.errors.length) root.defaultsMessage = result.errors.join("\n")
        } catch (e) { /* Keep last known state during a partial/failed read. */ }
      }
    }
  }
  Process {
    id: defaultsProc
    property string action: ""
    stdout: StdioCollector { id: defaultsOutput; waitForEnd: true }
    stderr: StdioCollector { id: defaultsError; waitForEnd: true }
    onExited: function(code, status) {
      if (code !== 0 || status !== 0) {
        if (["save", "delete", "prefer", "toggle-preferred"].indexOf(action) >= 0) {
          root.manageMessage = String(defaultsError.text).trim()
          Qt.callLater(function() { root.reveal(manageFeedback) })
        } else root.defaultsMessage = String(defaultsError.text).trim()
      }
      else {
        try {
          var result = JSON.parse(defaultsOutput.text)
          if (action === "preview") { root.previewText = result.summary; Qt.callLater(function() { root.reveal(previewActions) }) }
          else if (action === "save") {
            root.selectedProfile = result.id
            root.profileEditing = false
            keyCatcher.forceActiveFocus()
            root.manageMessage = result.message
            Qt.callLater(function() { root.reveal(manageFeedback) })
          } else if (action === "prefer" || action === "toggle-preferred" || action === "delete") {
            root.preferredProfile = result.preferred
            root.manageMessage = result.message
            if (action === "delete") { root.deleteProfileId = ""; root.previewText = "" }
            Qt.callLater(function() { root.reveal(manageFeedback) })
          }
          else {
            root.restoreState = result
            root.previewText = ""
            root.nameEditing = false
            nameField.dirty = false
          }
        } catch (e) { root.defaultsMessage = "Could not read restore result. Automatic recovery remains active." }
      }
      root.refresh()
    }
  }

  Process {
    id: monitorProc
    command: ["python3", root.scriptDir + "/display-names.py", "list"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        try {
          var result = JSON.parse(String(text || "{}"))
          var arr = result.monitors || []
          root.namesReadError = result.error || ""
          var out = []
          for (var i = 0; i < arr.length; i++) {
            var d = arr[i]
            var modeStrings = []
            if (Array.isArray(d.modes)) {
              for (var mi = 0; mi < d.modes.length; mi++) {
                var rm = d.modes[mi]
                if (rm && rm.width) modeStrings.push(rm.width + "x" + rm.height + "@" + rm.refreshRate)
              }
            }
            if (modeStrings.length === 0 && Array.isArray(d.availableModes))
              modeStrings = d.availableModes.slice()
            out.push({
              name: d.name, displayLabel: d.displayLabel, displayAlias: d.displayAlias,
              displayIdentity: d.displayIdentity, namingReason: d.namingReason,
              width: d.width, height: d.height,
              x: d.x, y: d.y,
              scale: d.scale, transform: d.transform, refreshRate: d.refreshRate,
              focused: !!d.focused,
              modes: modeStrings
            })
          }
          root.monitors = out
          if (!out.some(function(m) { return m.name === root.selected })) {
            root.selected = ""
            for (var k = 0; k < out.length; k++) if (out[k].focused) root.selected = out[k].name
            if (!root.selected && out.length) root.selected = out[0].name
          }
          var selected = root.selectedMonitor()
          if (!nameField.dirty || nameField.identity !== (selected ? selected.displayIdentity : "")) root.loadNameField()
        } catch (e) { root.namesReadError = "Could not read display identities" }
      }
    }
  }

  Process {
    id: nameAction
    stdout: StdioCollector { waitForEnd: true }
    stderr: StdioCollector { id: nameStderr; waitForEnd: true }
    onExited: function(code, status) {
      if (code !== 0 || status !== 0) root.namesError = String(nameStderr.text || "Could not save display name").trim()
      else { root.nameEditing = false; nameField.dirty = false; keyCatcher.forceActiveFocus(); root.refresh() }
    }
  }

  Process {
    id: termProc
    command: [root.scriptDir + "/omarchy-display-terminal", "list", "--json"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        try { root.terminalSizes = JSON.parse(String(text || "{}")) }
        catch (e) { /* ignore */ }
      }
    }
  }

  Process {
    id: installProc
    command: [root.scriptDir + "/../install", "--silent"]
    stdout: StdioCollector { waitForEnd: true }
  }

  Process {
    id: actionProc
    stdout: StdioCollector { id: actionOutput; waitForEnd: true }
    stderr: StdioCollector { id: actionStderr; waitForEnd: true }
    onExited: function(code, status) {
      if (code !== 0 || status !== 0) {
        root.actionError = String(actionStderr.text || actionOutput.text || "Change failed").trim()
        Qt.callLater(function() { root.reveal(actionMessage) })
      }
      root.refresh()
    }
  }

  Process {
    id: brightnessRead
    property string monitor: ""
    stdout: StdioCollector { id: brightnessOutput; waitForEnd: true }
    stderr: StdioCollector { waitForEnd: true }
    onExited: function(code, status) {
      if (monitor !== root.selected) { root.refreshBrightness(); return }
      var raw = String(brightnessOutput.text || "").trim()
      var valid = code === 0 && status === 0 && /^[0-9]+$/.test(raw) && Number(raw) <= 100
      root.brightnessAvailable = valid
      if (valid && root.pendingBrightness < 0 && !brightnessSlider.dragging) root.brightnessPercent = Number(raw)
      root.flushBrightness()
      root.brightnessMessage = valid ? "" : "Brightness unavailable for " + root.displayName(monitor)
    }
  }

  Process {
    id: brightnessWrite
    property string monitor: ""
    stdout: StdioCollector { waitForEnd: true }
    stderr: StdioCollector { waitForEnd: true }
    onExited: function(code, status) {
      if (monitor === root.selected && (code !== 0 || status !== 0)) {
        root.pendingBrightness = -1
        root.brightnessAvailable = false
        root.brightnessMessage = "Could not change brightness on " + root.displayName(monitor)
      } else if (root.pendingBrightness >= 0) root.flushBrightness()
      else root.refreshBrightness()
    }
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: Quickshell.screens.length > 1 ? "󰍺" : "󰍹"
    onPressed: function(b) { root.toggle() }
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(440))
    contentHeight: panel.fittedContentHeight(panelColumn.implicitHeight, Style.space(640))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      blocked: nameField.activeFocus || profileNameField.activeFocus || profileDropdown.popupOpen || resolutionDropdown.popupOpen
      onMoveRequested: function(dx, dy) { root.moveCursor(dx, dy) }
      onActivateRequested: root.activateCursor()
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }

    ScrollView {
      id: scrollArea
      anchors.fill: parent
      clip: true
      Binding {
        target: scrollArea.contentItem
        property: "interactive"
        value: panelColumn.implicitHeight > scrollArea.height
      }
      ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
      ScrollBar.vertical.policy: panelColumn.implicitHeight > height ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff

      Column {
        id: panelColumn
        width: scrollArea.availableWidth
        spacing: Style.space(14)

        // ---------- Hero ----------
        Item {
          width: parent.width
          implicitHeight: heroIcon.implicitHeight
          Text {
            id: heroIcon
            text: "󰍹"
            color: root.bar.foreground
            font.family: root.bar.fontFamily
            font.pixelSize: Style.font.display
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
          }
          Text {
            text: "Better Displays"
            color: root.bar.foreground
            font.family: root.bar.fontFamily
            font.pixelSize: Style.font.title
            font.bold: true
            anchors.left: heroIcon.right
            anchors.leftMargin: Style.space(14)
            anchors.verticalCenter: parent.verticalCenter
          }
        }

        // ---------- Monitor selector ----------
        PanelSeparator { foreground: root.bar.foreground }
        PanelSectionHeader { text: "MONITOR"; foreground: root.bar.foreground; fontFamily: root.bar.fontFamily }

        Flow {
          width: parent.width
          spacing: Style.spacing.xs
          Repeater {
            model: root.monitors
            NavigationButton {
              required property int index
              navRow: 0
              navColumn: index
              required property var modelData
              text: modelData.displayLabel
              tooltipText: modelData.name
              foreground: root.bar.foreground
              fontFamily: root.bar.fontFamily
              fontSize: Style.font.caption
              bordered: true
              active: root.selected === modelData.name
              onClicked: root.selected = modelData.name
            }
          }
        }

        PanelSectionHeader { text: "DISPLAY NAME"; foreground: root.bar.foreground; fontFamily: root.bar.fontFamily }
        NavigationButton {
          navRow: 1
          text: "Edit Display Name"
          visible: !root.nameEditing
          enabled: !root.restoreBusy && !!root.selectedMonitor() && !!root.selectedMonitor().displayIdentity
          foreground: root.bar.foreground
          fontFamily: root.bar.fontFamily
          onClicked: { root.loadNameField(); root.nameEditing = true; Qt.callLater(function() { nameField.forceActiveFocus() }) }
        }
        TextField {
          id: nameField
          visible: root.nameEditing
          property string identity: ""
          property bool dirty: false
          property int navRow: 1
          property int navColumn: 0
          hasCursor: root.cursorOn(nameField)
          onHoveredChanged: if (hovered) root.pointCursor(nameField)
          onTextEdited: dirty = true
          function activate() { forceActiveFocus() }
          Keys.onEscapePressed: function(event) { root.nameEditing = false; root.loadNameField(); keyCatcher.forceActiveFocus(); event.accepted = true }
          Keys.onTabPressed: function(event) {
            keyCatcher.forceActiveFocus()
            root.cursorRow = 2; root.cursorColumn = 0; root.cursorActive = true
            event.accepted = true
          }
          width: parent.width
          foreground: root.bar.foreground
          placeholderText: "Name this display (up to 20 characters)"
          maximumLength: 20
          enabled: !!root.selectedMonitor() && !!root.selectedMonitor().displayIdentity && !nameAction.running && !root.restoreBusy
          onAccepted: root.editName(false)
        }
        Row {
          visible: root.nameEditing
          spacing: Style.spacing.xs
          NavigationButton {
            navRow: 2
            navColumn: 0
            text: "Save"
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
            enabled: nameField.enabled && nameField.text.trim().length > 0
            onClicked: root.editName(false)
          }
          NavigationButton {
            navRow: 2
            navColumn: 1
            text: "Reset"
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
            enabled: nameField.enabled
            onClicked: root.editName(true)
          }
          NavigationButton {
            navRow: 2
            navColumn: 2
            text: "Cancel"
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
            onClicked: { root.nameEditing = false; root.loadNameField() }
          }
        }
        Text {
          width: parent.width
          textFormat: Text.PlainText
          text: root.namesError || root.namesReadError || (root.selectedMonitor() ? root.selectedMonitor().namingReason : "")
          visible: text !== ""
          color: root.bar.foreground
          font.family: root.bar.fontFamily
          font.pixelSize: Style.font.caption
          wrapMode: Text.Wrap
        }

        PanelSeparator { foreground: root.bar.foreground }
        PanelSectionHeader { text: "BRIGHTNESS — " + root.displayName(root.selected); foreground: root.bar.foreground; fontFamily: root.bar.fontFamily }
        Text {
          width: parent.width
          textFormat: Text.PlainText
          text: root.brightnessMessage || Math.round(brightnessSlider.dragging ? brightnessSlider.liveValue : root.brightnessPercent) + "%"
          color: root.bar.foreground
          font.family: root.bar.fontFamily
          font.pixelSize: Style.font.body
          wrapMode: Text.Wrap
        }
        CursorSurface {
          id: brightnessRow
          property int navRow: 3
          property int navColumn: 0
          width: parent.width
          implicitHeight: brightnessSlider.implicitHeight + Style.space(8)
          visible: root.brightnessAvailable
          enabled: !root.restoreBusy
          foreground: root.bar.foreground
          hasCursor: brightnessSlider.activeFocus || root.cursorOn(brightnessRow)
          function activate() { /* Left/right adjusts this row, as in Display. */ }
          HoverHandler { onHoveredChanged: if (hovered) root.pointCursor(brightnessRow) }
        ClickSlider {
          id: brightnessSlider
          anchors.fill: parent
          anchors.margins: Style.space(4)
          bar: root.bar
          visible: root.brightnessAvailable
          enabled: root.brightnessAvailable
          minimum: 1
          maximum: 100
          step: 1
          integer: true
          value: root.brightnessPercent
          property string dragMonitor: ""
          Keys.onEscapePressed: keyCatcher.forceActiveFocus()
          Keys.onLeftPressed: root.setBrightness(root.brightnessPercent - 5)
          Keys.onRightPressed: root.setBrightness(root.brightnessPercent + 5)
          Keys.onUpPressed: { keyCatcher.forceActiveFocus(); root.moveCursor(0, -1) }
          Keys.onDownPressed: { keyCatcher.forceActiveFocus(); root.moveCursor(0, 1) }
          onDraggingChanged: if (dragging) dragMonitor = root.selected
          onReleased: function(v) { if (!brightnessSlider.dragging && (brightnessSlider.activeFocus || dragMonitor === root.selected)) root.setBrightness(v) }
        }
        }
        Text {
          width: parent.width
          id: actionMessage
          visible: root.actionError !== ""
          text: root.actionError
          textFormat: Text.PlainText
          color: root.bar.foreground
          font.family: root.bar.fontFamily
          font.pixelSize: Style.font.body
          wrapMode: Text.Wrap
        }

        // ---------- Resolution / Scale / Position / Orientation ----------
        PanelSeparator { foreground: root.bar.foreground }
        Column {
          width: parent.width
          spacing: Style.space(10)
          PanelSectionHeader { text: "RESOLUTION"; foreground: root.bar.foreground; fontFamily: root.bar.fontFamily }
          SearchableDropdown {
            id: resolutionDropdown
            enabled: !root.restoreBusy && !actionProc.running
            property int navRow: 4
            property int navColumn: 0
            hasCursor: root.cursorOn(resolutionDropdown)
            onHovered: function(inside) { if (inside) root.pointCursor(resolutionDropdown) }
            onPopupOpenChanged: if (!popupOpen) keyCatcher.forceActiveFocus()
            function activate() { open() }
            width: parent.width
            foreground: root.bar.foreground
            value: root.currentModeString(root.selectedMonitor())
            options: root.modeOptions(root.selectedMonitor())
            onChanged: function(v) { root.setMonitor("--mode", v) }
          }

          PanelSectionHeader { text: "SCALE"; foreground: root.bar.foreground; fontFamily: root.bar.fontFamily }
          Row {
            width: parent.width
            spacing: Style.spacing.xs
            Repeater {
              model: root.scalePresets
              NavigationButton {
                required property int index
                navRow: 5
                navColumn: index
                required property string modelData
                text: modelData + "x"
                enabled: !root.restoreBusy && !actionProc.running && root.validScale(modelData)
                foreground: root.bar.foreground
                fontFamily: root.bar.fontFamily
                fontSize: Style.font.caption
                bordered: true
                active: {
                  var m = root.selectedMonitor()
                  m && Math.abs(Number(m.scale) - Number(modelData)) < 0.001
                }
                onClicked: root.setMonitor("--scale", modelData)
              }
            }
          }

          Text {
            width: parent.width
            text: "Scaling adjusts neighboring positions in rows and columns, preserving gaps. Disabled scales do not fit this resolution exactly."
            color: root.bar.foreground
            font.family: root.bar.fontFamily
            font.pixelSize: Style.font.caption
            wrapMode: Text.Wrap
          }
          PanelSectionHeader { text: "POSITION"; foreground: root.bar.foreground; fontFamily: root.bar.fontFamily }
          Flow {
            width: parent.width
            spacing: Style.spacing.xs
            NavigationButton {
              navRow: 6
              text: "Auto"
              foreground: root.bar.foreground
              fontFamily: root.bar.fontFamily
              fontSize: Style.font.caption
              bordered: true
              onClicked: root.setMonitor("--pos", "auto")
            }
            Repeater {
              model: root.positionButtons()
              NavigationButton {
                required property int index
                navRow: 6
                navColumn: index + 1
                required property var modelData
                text: modelData.label
                foreground: root.bar.foreground
                fontFamily: root.bar.fontFamily
                fontSize: Style.font.caption
                bordered: true
                onClicked: {
                  var m = root.selectedMonitor()
                  var other = root.monitorByName(modelData.other)
                  if (m && other) root.setMonitor("--pos", root.posFor(m, other, modelData.dir))
                }
              }
            }
          }

          PanelSectionHeader { text: "ORIENTATION"; foreground: root.bar.foreground; fontFamily: root.bar.fontFamily }
          Row {
            width: parent.width
            spacing: Style.spacing.xs
            Repeater {
              model: root.transformPresets
              NavigationButton {
                required property int index
                navRow: 7
                navColumn: index
                required property string modelData
                text: ({ "0": "0°", "1": "90°", "2": "180°", "3": "270°" })[modelData]
                foreground: root.bar.foreground
                fontFamily: root.bar.fontFamily
                fontSize: Style.font.caption
                bordered: true
                active: {
                  var m = root.selectedMonitor()
                  m && Number(m.transform) === Number(modelData)
                }
                onClicked: root.setMonitor("--transform", modelData)
              }
            }
          }
        }

        // ---------- Terminal fonts ----------
        PanelSeparator { foreground: root.bar.foreground }
        PanelSectionHeader { text: "TERMINAL FONT"; foreground: root.bar.foreground; fontFamily: root.bar.fontFamily }
        Column {
          width: parent.width
          spacing: Style.space(8)
          Repeater {
            model: root.terminals
            Row {
              id: terminalRow
              required property int index
              required property string modelData
              width: parent.width
              spacing: Style.spacing.sm
              Text {
                text: modelData
                color: root.bar.foreground
                font.family: root.bar.fontFamily
                font.pixelSize: Style.font.body
                width: Style.space(86)
                elide: Text.ElideRight
                anchors.verticalCenter: parent.verticalCenter
              }
              NavigationButton {
                navRow: 8 + terminalRow.index
                navColumn: 0
                text: "−"
                foreground: root.bar.foreground
                fontFamily: root.bar.fontFamily
                fontSize: Style.font.body
                bordered: true
                onClicked: root.stepTerminal(modelData, -1)
              }
              Text {
                text: String(root.terminalSizes[modelData] || "—")
                color: root.bar.foreground
                font.family: root.bar.fontFamily
                font.pixelSize: Style.font.body
                horizontalAlignment: Text.AlignHCenter
                width: Style.space(34)
                anchors.verticalCenter: parent.verticalCenter
              }
              NavigationButton {
                navRow: 8 + terminalRow.index
                navColumn: 1
                text: "+"
                foreground: root.bar.foreground
                fontFamily: root.bar.fontFamily
                fontSize: Style.font.body
                bordered: true
                onClicked: root.stepTerminal(modelData, 1)
              }
            }
          }
        }

        PanelSeparator { foreground: root.bar.foreground }
        PanelSectionHeader { text: "Manage Profiles"; foreground: root.bar.foreground; fontFamily: root.bar.fontFamily }
        Flow {
          width: parent.width
          spacing: Style.spacing.xs
          NavigationButton {
            bordered: true
            navRow: 13; navColumn: 0
            width: Style.space(150)
            text: "Make Preferred"
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
            active: !!root.selectedProfile && root.selectedProfile === root.preferredProfile
            enabled: !root.restoreBusy && !!root.selectedProfile
            onClicked: root.profileAction("toggle-preferred", "", root.selectedProfile)
          }
          NavigationButton {
            bordered: true
            navRow: 13; navColumn: 1
            text: "Delete"
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
            enabled: !root.restoreBusy && !!root.selectedProfile
            onClicked: {
              root.deleteProfileId = root.selectedProfile
              root.deleteProfileLabel = root.selectedProfile
              for (var i = 0; i < root.profiles.length; i++)
                if (root.profiles[i].value === root.selectedProfile) root.deleteProfileLabel = root.profiles[i].label
              root.profileEditing = false
              Qt.callLater(function() { root.reveal(deleteConfirmation) })
            }
          }
        }
          NavigationButton {
            bordered: true
            navRow: 14; navColumn: 0
            text: "Save Current Setup"
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
            enabled: !root.restoreBusy && !actionProc.running && !nameAction.running && !brightnessWrite.running && root.pendingBrightness < 0
            onClicked: { root.profileEditing = !root.profileEditing; root.deleteProfileId = ""; root.previewText = ""; if (root.profileEditing) Qt.callLater(function() { profileNameField.forceActiveFocus(); root.reveal(profileEditor) }) }
          }
        Column {
          id: profileEditor
          width: parent.width
          spacing: Style.spacing.xs
          visible: root.profileEditing
          TextField {
            id: profileNameField
            property int navRow: 15
            property int navColumn: 0
            width: parent.width
            maximumLength: 40
            placeholderText: "Setup name (up to 40 characters)"
            foreground: root.bar.foreground
            enabled: !root.restoreBusy
            hasCursor: root.cursorOn(profileNameField)
            onHoveredChanged: if (hovered) root.pointCursor(profileNameField)
            function activate() { forceActiveFocus() }
            onAccepted: root.profileAction("save", "", "")
            Keys.onEscapePressed: { root.profileEditing = false; keyCatcher.forceActiveFocus() }
            Keys.onTabPressed: { keyCatcher.forceActiveFocus(); root.cursorRow = 16; root.cursorColumn = 0; root.cursorActive = true }
          }
          Flow {
            width: parent.width
            spacing: Style.spacing.xs
            NavigationButton {
            bordered: true
              navRow: 16; navColumn: 0
              text: root.saveBrightness ? "✓ Include brightness" : "Include brightness"
              active: root.saveBrightness
              foreground: root.bar.foreground
              fontFamily: root.bar.fontFamily
              onClicked: root.saveBrightness = !root.saveBrightness
            }
            NavigationButton {
            bordered: true
              navRow: 16; navColumn: 1
              text: root.saveTerminals ? "✓ Include terminal fonts" : "Include terminal fonts"
              active: root.saveTerminals
              foreground: root.bar.foreground
              fontFamily: root.bar.fontFamily
              onClicked: root.saveTerminals = !root.saveTerminals
            }
          }
          Row {
            spacing: Style.spacing.xs
            NavigationButton {
            bordered: true
              navRow: 17; navColumn: 0
              text: "Save New Profile"
              foreground: root.bar.foreground
              fontFamily: root.bar.fontFamily
              enabled: !root.restoreBusy && profileNameField.text.trim().length > 0
              onClicked: root.profileAction("save", "", "")
            }
            NavigationButton {
            bordered: true
              navRow: 17; navColumn: 1
              text: "Cancel"
              foreground: root.bar.foreground
              fontFamily: root.bar.fontFamily
              onClicked: root.profileEditing = false
            }
          }
        }
        Column {
          id: deleteConfirmation
          width: parent.width
          spacing: Style.spacing.xs
          visible: root.deleteProfileId !== ""
          Text {
            width: parent.width
            text: "Delete “" + root.deleteProfileLabel + "”? Current display settings stay unchanged."
            textFormat: Text.PlainText
            wrapMode: Text.Wrap
            color: root.bar.foreground
            font.family: root.bar.fontFamily
            font.pixelSize: Style.font.caption
          }
          Row {
            spacing: Style.spacing.xs
            NavigationButton {
              navRow: 18; navColumn: 0
              text: "Confirm Delete"
              bordered: true
              foreground: root.bar.foreground
              fontFamily: root.bar.fontFamily
              onClicked: root.profileAction("delete", "", root.deleteProfileId)
            }
            NavigationButton {
              navRow: 18; navColumn: 1
              text: "Cancel"
              bordered: true
              foreground: root.bar.foreground
              fontFamily: root.bar.fontFamily
              onClicked: root.deleteProfileId = ""
            }
          }
        }
        Text {
          id: manageFeedback
          width: parent.width
          text: root.manageMessage
          visible: text !== ""
          textFormat: Text.PlainText
          wrapMode: Text.Wrap
          color: root.bar.foreground
          font.family: root.bar.fontFamily
          font.pixelSize: Style.font.caption
        }
        PanelSeparator { foreground: root.bar.foreground }
        PanelSectionHeader { text: "Restore"; foreground: root.bar.foreground; fontFamily: root.bar.fontFamily }
        SearchableDropdown {
          id: profileDropdown
          property int navRow: 19
          property int navColumn: 0
          width: parent.width
          foreground: root.bar.foreground
          placeholderText: "No saved setups"
          options: root.profiles
          value: root.selectedProfile
          enabled: !root.restoreBusy && root.profiles.length > 0
          hasCursor: root.cursorOn(profileDropdown)
          function activate() { open() }
          onHovered: function(inside) { if (inside) root.pointCursor(profileDropdown) }
          onPopupOpenChanged: if (!popupOpen) keyCatcher.forceActiveFocus()
          onChanged: function(v) { root.selectedProfile = v; root.previewText = ""; root.deleteProfileId = "" }
        }
        Flow {
          width: parent.width
          spacing: Style.spacing.xs
          NavigationButton {
            bordered: true
            navRow: 20; navColumn: 0
            text: "Restore Setup"
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
            enabled: !root.restoreBusy && !!root.selectedProfile && !actionProc.running && !nameAction.running && !brightnessWrite.running && root.pendingBrightness < 0
            onClicked: root.profileAction("preview", "profile", root.selectedProfile)
          }
          NavigationButton {
            bordered: true
            navRow: 20; navColumn: 1
            text: "Restore Omarchy Defaults"
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
            enabled: !root.restoreBusy && !actionProc.running && !nameAction.running && !brightnessWrite.running && root.pendingBrightness < 0
            onClicked: root.profileAction("preview", "defaults", "")
          }
        }
        NavigationButton {
            bordered: true
          navRow: 21
          text: "Undo Last Restore"
          foreground: root.bar.foreground
          fontFamily: root.bar.fontFamily
          enabled: root.canUndo && !root.restoreBusy && !actionProc.running && !nameAction.running && !brightnessWrite.running && root.pendingBrightness < 0
          onClicked: root.profileAction("preview", "undo", "")
        }
        Text {
          width: parent.width
          text: root.previewText
          visible: text !== "" && !root.restoreBusy
          textFormat: Text.PlainText
          color: root.bar.foreground
          font.family: root.bar.fontFamily
          font.pixelSize: Style.font.caption
          wrapMode: Text.Wrap
        }
        Row {
          id: previewActions
          visible: root.previewText !== "" && !root.restoreBusy
          spacing: Style.spacing.xs
          NavigationButton {
            bordered: true
            navRow: 22; navColumn: 0
            text: "Apply and Test"
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
            enabled: !actionProc.running && !nameAction.running && !brightnessWrite.running && root.pendingBrightness < 0
            onClicked: root.profileAction("start", root.previewKind, root.previewId)
          }
          NavigationButton {
            bordered: true
            navRow: 22; navColumn: 1
            text: "Cancel"
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
            onClicked: root.previewText = ""
          }
        }
        Text {
          width: parent.width
          text: root.defaultsMessage || (root.restoreState.status === "waiting" ? "Keep this setup? Reverting in " + root.restoreState.remaining + " seconds." : root.restoreState.message || "")
          visible: text !== ""
          textFormat: Text.PlainText
          color: root.bar.foreground
          font.family: root.bar.fontFamily
          font.pixelSize: Style.font.caption
          wrapMode: Text.Wrap
        }
        Row {
          id: confirmationRow
          visible: root.restoreState.status === "waiting"
          onVisibleChanged: if (visible) Qt.callLater(function() { root.reveal(confirmationRow) })
          spacing: Style.spacing.xs
          NavigationButton {
            bordered: true
            navRow: 23; navColumn: 0
            text: "Keep Changes"
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
            enabled: !defaultsProc.running && root.restoreState.remaining > 0
            onClicked: root.profileAction("keep", "", "")
          }
          NavigationButton {
            bordered: true
            navRow: 23; navColumn: 1
            text: "Revert Now"
            foreground: root.bar.foreground
            fontFamily: root.bar.fontFamily
            enabled: !defaultsProc.running
            onClicked: root.profileAction("revert", "", "")
          }
        }
        Item { width: parent.width; height: Style.space(4) }
      }
    }
  }
  }
}
