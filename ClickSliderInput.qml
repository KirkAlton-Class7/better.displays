// Adapted from Omarchy PanelSlider input handling; see licenses/omarchy-license.txt.
import QtQuick

MouseArea {
    required property var slider
    anchors.fill: parent
    hoverEnabled: true
    cursorShape: Qt.PointingHandCursor
    acceptedButtons: Qt.LeftButton | Qt.RightButton
    scrollGestureEnabled: false
    preventStealing: true

    function valueFromX(x) {
      var clamped = Math.max(0, Math.min(slider.width, x))
      var raw = slider.minimum + (clamped / slider.width) * slider.range
      if (slider.integer) raw = Math.round(raw)
      return Math.max(slider.minimum, Math.min(slider.maximum, raw))
    }

    onPressed: function(mouse) {
      if (mouse.button !== Qt.LeftButton) return
      slider.forceActiveFocus()
      slider.dragging = true
      var next = valueFromX(mouse.x)
      slider.liveValue = next
      slider.moved(next)
    }
    onClicked: function(mouse) {
      if (mouse.button === Qt.RightButton) slider.rightClicked()
    }
    onPositionChanged: function(mouse) {
      if (!slider.dragging) return
      var next = valueFromX(mouse.x)
      slider.liveValue = next
      slider.moved(next)
    }
    onReleased: function(mouse) {
      if (mouse.button !== Qt.LeftButton) return
      slider.dragging = false
      slider.released(slider.liveValue)
      slider.liveValue = slider.value
    }
    onExited: if (!slider.dragging) slider.focus = false
    onCanceled: {
      slider.dragging = false
      slider.liveValue = slider.value
    }
    onWheel: function(wheel) {
      if (!slider.activeFocus || wheel.angleDelta.y === 0) { wheel.accepted = false; return }
      var next = Math.max(slider.minimum, Math.min(slider.maximum,
          slider.liveValue + (wheel.angleDelta.y > 0 ? 5 : -5)))
      slider.liveValue = next
      slider.moved(next)
      slider.released(next)
      wheel.accepted = true
    }
  }
