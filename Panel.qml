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
  property bool brightnessAvailable: false
  property string brightnessMessage: "Select a monitor"
  property string actionError: ""
  property string namesError: ""
  property string namesReadError: ""

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
    if (nameField.activeFocus || resolutionDropdown.popupOpen || scrollArea.contentItem.moving) return
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
    if (!m || !m.displayIdentity || nameAction.running) return
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
    root.loadNameField()
    root.brightnessAvailable = false
    root.brightnessMessage = "Reading brightness…"
    root.refreshBrightness()
  }

  function setBrightness(value) {
    if (!root.brightnessAvailable || brightnessWrite.running || brightnessRead.running) return
    brightnessWrite.monitor = root.selected
    var percent = Math.max(1, Math.min(100, Math.round(value)))
    brightnessWrite.command = ["timeout", "12", "omarchy", "brightness", "display", "--no-osd", "--monitor", brightnessWrite.monitor, percent + "%"]
    root.brightnessMessage = "Applying…"
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
    root.refreshBrightness()
  }

  function setMonitor(flag, val) {
    var m = root.selectedMonitor()
    if (!m || actionProc.running) return
    root.actionError = ""
    actionProc.command = [root.scriptDir + "/omarchy-display-monitor", "set", m.name, flag, String(val)]
    if (!actionProc.running) actionProc.running = true
  }

  function setTerminal(term, size) {
    if (actionProc.running) return
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

  onOpenedChanged: if (opened) { cursorActive = false; refresh() }

  Timer {
    interval: 4000
    running: root.opened
    repeat: true
    onTriggered: root.refresh()
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
      else { nameField.dirty = false; keyCatcher.forceActiveFocus(); root.refresh() }
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
      if (code !== 0 || status !== 0) root.actionError = String(actionStderr.text || actionOutput.text || "Change failed").trim()
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
      if (valid) root.brightnessPercent = Number(raw)
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
        root.brightnessAvailable = false
        root.brightnessMessage = "Could not change brightness on " + root.displayName(monitor)
      } else root.refreshBrightness()
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
      blocked: nameField.activeFocus || resolutionDropdown.popupOpen
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
        TextField {
          id: nameField
          property string identity: ""
          property bool dirty: false
          property int navRow: 1
          property int navColumn: 0
          hasCursor: root.cursorOn(nameField)
          onHoveredChanged: if (hovered) root.pointCursor(nameField)
          onTextEdited: dirty = true
          function activate() { forceActiveFocus() }
          Keys.onEscapePressed: function(event) { keyCatcher.forceActiveFocus(); event.accepted = true }
          Keys.onTabPressed: function(event) {
            keyCatcher.forceActiveFocus()
            root.cursorRow = 2; root.cursorColumn = 0; root.cursorActive = true
            event.accepted = true
          }
          width: parent.width
          foreground: root.bar.foreground
          placeholderText: "Name this display (up to 20 characters)"
          maximumLength: 20
          enabled: !!root.selectedMonitor() && !!root.selectedMonitor().displayIdentity && !nameAction.running
          onAccepted: root.editName(false)
        }
        Row {
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
          enabled: brightnessSlider.enabled
          foreground: root.bar.foreground
          hasCursor: root.cursorOn(brightnessRow)
          function activate() { /* Left/right adjusts this row, as in Display. */ }
          HoverHandler { onHoveredChanged: if (hovered) root.pointCursor(brightnessRow) }
        ClickSlider {
          id: brightnessSlider
          anchors.fill: parent
          anchors.margins: Style.space(4)
          bar: root.bar
          visible: root.brightnessAvailable
          enabled: !brightnessRead.running && !brightnessWrite.running
          minimum: 1
          maximum: 100
          step: 1
          integer: true
          value: root.brightnessPercent
          property string dragMonitor: ""
          onDraggingChanged: if (dragging) dragMonitor = root.selected
          onReleased: function(v) { if (dragMonitor === root.selected) root.setBrightness(v) }
        }
        }
        Text {
          width: parent.width
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
            text: "Scaling keeps screen positions. Adjust Position if gaps appear."
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

        Item { width: parent.width; height: Style.space(4) }
      }
    }
  }
  }
}
