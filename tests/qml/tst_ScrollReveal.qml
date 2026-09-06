import QtQuick
import QtQuick.Controls
import QtTest
import "../../ScrollReveal.js" as ScrollReveal

TestCase {
  id: test
  name: "ScrollReveal"
  visible: true
  width: 420; height: 300
  when: windowShown
  Component {
    id: fixture
    ScrollView {
      width: 420; height: 300
      property alias target: editor
      Column {
        width: parent.availableWidth
        Rectangle { width: 200; height: 1000 }
        Column {
          id: editor
          visible: false
          width: 200
          property int editorHeight: 100
          Row { Rectangle { width: 200; height: editor.editorHeight } }
        }
        Rectangle { width: 200; height: 200 }
      }
    }
  }
  function test_first_expansion_data() {
    return [{tag:"save_editor", height:180}, {tag:"delete_confirmation", height:100}, {tag:"oversized_editor", height:450}]
  }
  function test_first_expansion(data) {
    var scroll = createTemporaryObject(fixture, test)
    verify(scroll)
    wait(30)
    var flick = scroll.contentItem
    flick.contentY = 900
    scroll.target.editorHeight = data.height
    scroll.target.visible = true
    var done = false
    Qt.callLater(function() {
      // Reproduce the panel's deferred first-show path before render polish.
      ScrollReveal.reveal(flick, scroll.target)
      done = true
    })
    tryVerify(function() { return done })
    compare(scroll.target.y, 1000)
    verify(flick.contentY >= 900, "First expansion must not jump toward the panel top")
    verify(scroll.target.y >= flick.contentY)
    if (data.height <= flick.height) verify(scroll.target.y + scroll.target.height <= flick.contentY + flick.height)
  }
  function test_already_visible_keeps_scroll_position() {
    var scroll = createTemporaryObject(fixture, test)
    verify(scroll)
    scroll.target.visible = true
    wait(30)
    scroll.contentItem.contentY = 900
    ScrollReveal.reveal(scroll.contentItem, scroll.target)
    compare(scroll.contentItem.contentY, 900)
  }
}
