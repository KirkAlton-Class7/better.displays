.pragma library

// Hidden positioners may still have y/height=0 on their first callLater.
// Finish nested layouts before asking ancestors for the target's coordinates.
function finishLayout(item) {
    for (var i = 0; i < item.children.length; i++) finishLayout(item.children[i])
    if (typeof item.forceLayout === "function") item.forceLayout()
}

function reveal(flick, item) {
    if (!item || !item.visible) return
    finishLayout(item)
    for (var parent = item.parent; parent && parent !== flick.contentItem; parent = parent.parent)
        if (typeof parent.forceLayout === "function") parent.forceLayout()
    var top = item.mapToItem(flick.contentItem, 0, 0).y
    var next = flick.contentY
    if (item.height > flick.height || top < next) next = top - 6
    else if (top + item.height > next + flick.height) next = top + item.height - flick.height + 6
    flick.contentY = Math.max(0, Math.min(Math.max(0, flick.contentHeight - flick.height), next))
}
