import QtQuick

TransientMessage {
  property string activeToken: ""
  function observe(state, opened, direct) {
    var active = state.status === "applying" || state.status === "waiting"
    if (opened && !active && (direct || (!!activeToken && activeToken === state.token)))
      show(state.message)
    activeToken = opened && active ? state.token : ""
  }
  function reset() { activeToken = ""; clear() }
}
