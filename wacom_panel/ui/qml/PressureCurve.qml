// Pressure response editor: a cubic curve from light (lower-left) to firm (upper-right)
// with two draggable Bézier control points (xsetwacom PressureCurve, 0–100).
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
    function toX(pix) { return Math.max(0, Math.min(100, (pix - m) / (width - 2 * m) * 100)) }
    function toY(piy) { return Math.max(0, Math.min(100, ((height - m) - piy) / (height - 2 * m) * 100)) }

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

            // Control handle lines.
            ctx.strokeStyle = "#5a5a60"
            ctx.beginPath(); ctx.moveTo(root.px(0), root.py(0))
            ctx.lineTo(root.px(root.p1x), root.py(root.p1y)); ctx.stroke()
            ctx.beginPath(); ctx.moveTo(root.px(100), root.py(100))
            ctx.lineTo(root.px(root.p2x), root.py(root.p2y)); ctx.stroke()

            // The curve.
            ctx.strokeStyle = "#5aa0ff"
            ctx.lineWidth = 2
            ctx.beginPath()
            ctx.moveTo(root.px(0), root.py(0))
            ctx.bezierCurveTo(root.px(root.p1x), root.py(root.p1y),
                              root.px(root.p2x), root.py(root.p2y),
                              root.px(100), root.py(100))
            ctx.stroke()

            // Handles.
            ctx.fillStyle = "#5aa0ff"
            ctx.beginPath(); ctx.arc(root.px(root.p1x), root.py(root.p1y), 6, 0, 2 * Math.PI); ctx.fill()
            ctx.beginPath(); ctx.arc(root.px(root.p2x), root.py(root.p2y), 6, 0, 2 * Math.PI); ctx.fill()
        }
    }

    MouseArea {
        anchors.fill: parent
        property int activeHandle: 0  // 1 or 2

        function updateFrom(mx, my) {
            var x = Math.round(root.toX(mx))
            var y = Math.round(root.toY(my))
            if (activeHandle === 1) {
                controller.pen.p1x = x
                controller.pen.p1y = y
            } else if (activeHandle === 2) {
                controller.pen.p2x = x
                controller.pen.p2y = y
            }
        }

        onPressed: function (mouse) {
            var d1 = Math.hypot(mouse.x - root.px(root.p1x), mouse.y - root.py(root.p1y))
            var d2 = Math.hypot(mouse.x - root.px(root.p2x), mouse.y - root.py(root.p2y))
            activeHandle = (d1 <= d2 && d1 < 28) ? 1 : (d2 < 28 ? 2 : 0)
            if (activeHandle !== 0)
                updateFrom(mouse.x, mouse.y)
        }
        onPositionChanged: function (mouse) {
            if (activeHandle !== 0)
                updateFrom(mouse.x, mouse.y)
        }
        onReleased: activeHandle = 0
    }
}
