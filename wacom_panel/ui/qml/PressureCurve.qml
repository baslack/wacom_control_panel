// Pressure response editor: a cubic curve from light (lower-left) to firm (upper-right)
// with two draggable Bézier control points (xsetwacom PressureCurve, 0–100).
//
// Handles use DragHandler (not MouseArea) so they keep an exclusive grab through the whole
// drag — robust to stylus/tablet input, which otherwise drops a plain MouseArea grab.
import QtQuick

Item {
    id: root
    property int p1x: controller.pen.p1x
    property int p1y: controller.pen.p1y
    property int p2x: controller.pen.p2x
    property int p2y: controller.pen.p2y

    readonly property real m: 16

    function px(v) { return m + v / 100 * (width - 2 * m) }
    function py(v) { return (height - m) - v / 100 * (height - 2 * m) }
    // Convert a pixel delta to a 0–100 value delta along each axis (y is inverted).
    function dvx(dpix) { return dpix / (width - 2 * m) * 100 }
    function dvy(dpiy) { return -dpiy / (height - 2 * m) * 100 }
    function clamp(v) { return Math.max(0, Math.min(100, Math.round(v))) }

    onP1xChanged: canvas.requestPaint()
    onP1yChanged: canvas.requestPaint()
    onP2xChanged: canvas.requestPaint()
    onP2yChanged: canvas.requestPaint()
    onWidthChanged: canvas.requestPaint()
    onHeightChanged: canvas.requestPaint()

    Canvas {
        id: canvas
        anchors.fill: parent
        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            ctx.fillStyle = "#262628"
            ctx.fillRect(0, 0, width, height)

            ctx.strokeStyle = "#3a3a3e"
            ctx.lineWidth = 1
            for (var i = 0; i <= 4; i++) {
                var gx = root.px(i * 25)
                var gy = root.py(i * 25)
                ctx.beginPath(); ctx.moveTo(gx, root.py(0)); ctx.lineTo(gx, root.py(100)); ctx.stroke()
                ctx.beginPath(); ctx.moveTo(root.px(0), gy); ctx.lineTo(root.px(100), gy); ctx.stroke()
            }

            ctx.strokeStyle = "#5a5a60"
            ctx.beginPath(); ctx.moveTo(root.px(0), root.py(0))
            ctx.lineTo(root.px(root.p1x), root.py(root.p1y)); ctx.stroke()
            ctx.beginPath(); ctx.moveTo(root.px(100), root.py(100))
            ctx.lineTo(root.px(root.p2x), root.py(root.p2y)); ctx.stroke()

            ctx.strokeStyle = "#5aa0ff"
            ctx.lineWidth = 2
            ctx.beginPath()
            ctx.moveTo(root.px(0), root.py(0))
            ctx.bezierCurveTo(root.px(root.p1x), root.py(root.p1y),
                              root.px(root.p2x), root.py(root.p2y),
                              root.px(100), root.py(100))
            ctx.stroke()
        }
    }

    // ---- draggable control handles ---------------------------------------
    component Handle: Rectangle {
        property int vx: 0
        property int vy: 0
        property var commit  // function(newX, newY)
        width: 22
        height: 22
        radius: 11
        x: root.px(vx) - width / 2
        y: root.py(vy) - height / 2
        color: drag.active ? "#8fc0ff" : "#5aa0ff"
        border.color: "#ffffff"
        border.width: drag.active ? 2 : 0

        property real startX: 0
        property real startY: 0

        DragHandler {
            id: drag
            target: null
            onActiveChanged: {
                if (active) {
                    parent.startX = parent.vx
                    parent.startY = parent.vy
                }
            }
            onTranslationChanged: {
                parent.commit(root.clamp(parent.startX + root.dvx(translation.x)),
                              root.clamp(parent.startY + root.dvy(translation.y)))
            }
        }
    }

    Handle {
        vx: root.p1x; vy: root.p1y
        commit: function (nx, ny) { controller.pen.p1x = nx; controller.pen.p1y = ny }
    }
    Handle {
        vx: root.p2x; vy: root.p2y
        commit: function (nx, ny) { controller.pen.p2x = nx; controller.pen.p2y = ny }
    }
}
