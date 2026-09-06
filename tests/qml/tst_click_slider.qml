import QtQuick
import QtQuick.Controls
import QtTest
import "../.." as Plugin

Item {
  width: 400
  height: 300
  ScrollView {
    id: scroll
    anchors.fill: parent
    contentWidth: width
    contentHeight: 1200
    Item {
      id: slider
      width: 300
      height: 30
      y: 80
      property real minimum: 1
      property real maximum: 100
      property real range: maximum - minimum
      property bool integer: true
      property real value: 50
      property real liveValue: value
      property bool dragging: false
      signal moved(real value)
      signal released(real value)
      signal rightClicked()
      Plugin.ClickSliderInput { slider: parent }
    }
  }
  SignalSpy { id: committed; target: slider; signalName: "released" }
  TestCase {
    name: "ClickSlider"
    when: windowShown
    function init() {
      scroll.contentItem.contentY = 0
      slider.value = 50
      slider.liveValue = 50
      committed.clear()
      wait(100)
    }
    function test_wheel_scrolls_parent_without_changing_value() {
      mouseMove(slider, 150, 10)
      mouseWheel(slider, 150, 10, 0, -120)
      tryVerify(function() { return scroll.contentItem.contentY > 0 })
      compare(slider.value, 50)
      compare(slider.liveValue, 50)
      compare(committed.count, 0)
    }
    function test_click_commits_once() {
      mouseClick(slider, 225, 10)
      compare(committed.count, 1)
      verify(committed.signalArguments[0][0] > 60)
      compare(slider.dragging, false)
    }
    function test_hover_does_not_commit() {
      mouseMove(slider, 20, 10)
      mouseMove(slider, 280, 10)
      compare(committed.count, 0)
      compare(slider.liveValue, 50)
    }
    function test_drag_commits_once() {
      mousePress(slider, 100, 10)
      mouseMove(slider, 240, 10, 30)
      mouseRelease(slider, 240, 10)
      compare(committed.count, 1)
      verify(committed.signalArguments[0][0] > 70)
      compare(slider.dragging, false)
    }
  }
}
