import QtQuick
import QtTest
import "../.." as Plugin

TestCase {
  name: "ProfileFeedback"
  Plugin.TransientMessage { id: message; duration: 100 }
  Plugin.RestoreFeedback { id: restore; duration: 100 }
  function cleanup() { message.clear(); restore.reset() }
  function test_message_expires_and_empty_stays_empty() {
    message.show("Profile deleted")
    compare(message.text, "Profile deleted")
    tryCompare(message, "text", "", 500)
    message.show("")
    compare(message.text, "")
  }
  function test_repeat_action_gets_fresh_timeout() {
    message.show("Saved")
    wait(70)
    message.show("Saved")
    wait(50)
    compare(message.text, "Saved")
    tryCompare(message, "text", "", 500)
  }
  function test_historical_restore_is_silent() {
    restore.observe({status:"reverted", token:"old", message:"Previous setup restored"}, true, false)
    compare(restore.text, "")
  }
  function test_observed_restore_completion_shown_once() {
    restore.observe({status:"waiting", token:"current"}, true, false)
    compare(restore.text, "")
    var done = {status:"reverted", token:"current", message:"Previous setup restored"}
    restore.observe(done, true, false)
    compare(restore.text, done.message)
    tryCompare(restore, "text", "", 500)
    restore.observe(done, true, false)
    compare(restore.text, "")
  }
  function test_close_discards_completion_and_history() {
    restore.observe({status:"waiting", token:"current"}, true, false)
    restore.reset()
    restore.observe({status:"reverted", token:"current", message:"Previous setup restored"}, false, false)
    restore.observe({status:"reverted", token:"current", message:"Previous setup restored"}, true, false)
    compare(restore.text, "")
  }
  function test_direct_result_expires() {
    restore.observe({status:"kept", token:"current", message:"Setup kept"}, true, true)
    compare(restore.text, "Setup kept")
    tryCompare(restore, "text", "", 500)
  }
}
