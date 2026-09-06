// Adapted from Omarchy PanelSlider input handling; see licenses/omarchy-license.txt.
import QtQuick

MouseArea {
    required property var slider
    anchors.fill: parent
    hoverEnabled: true
    cursorShape: Qt.PointingHandCursor
    acceptedButtons: Qt.LeftButton | Qt.RightButton
    scrollGestureEnabled: false

    function valueFromX(x) {
      var clamped = Math.max(0, Math.min(slider.width, x))
      var raw = slider.minimum + (clamped / slider.width) * slider.range
      if (slider.integer) raw = Math.round(raw)
      return Math.max(slider.minimum, Math.min(slider.maximum, raw))
    }

    onPressed: function(mouse) {
      if (mouse.button !== Qt.LeftButton) return
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
    onCanceled: {
      slider.dragging = false
      slider.liveValue = slider.value
    }
    onWheel: function(wheel) {
      wheel.accepted = false
    }
  }
