import QtQuick

QtObject {
  id: notice
  property string text: ""
  property int duration: 6000
  function show(message) {
    text = String(message || "").trim()
    if (text) expiry.restart()
    else expiry.stop()
  }
  function clear() { text = ""; expiry.stop() }
  property Timer expiry: Timer {
    interval: notice.duration
    onTriggered: notice.text = ""
  }
}
