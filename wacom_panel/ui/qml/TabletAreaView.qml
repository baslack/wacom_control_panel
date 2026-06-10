// Tablet surface with a draggable / resizable active-area rectangle.
import QtQuick
import QtQuick.Controls.Material

Rectangle {
    id: root
    radius: 8
    color: "#262628"
    clip: true

    readonly property real pad: 18
    property int tw: controller.mapping.tabletWidth
    property int th: controller.mapping.tabletHeight
    property real s: Math.min((width - 2 * pad) / Math.max(1, tw),
                              (height - 2 * pad) / Math.max(1, th))
    property real ox: pad + (width - 2 * pad - tw * s) / 2
    property real oy: pad + (height - 2 * pad - th * s) / 2

    function devToPxX(v) { return ox + v * s }
    function devToPxY(v) { return oy + v * s }

    // Tablet surface.
    Rectangle {
        x: root.ox
        y: root.oy
        width: root.tw * root.s
        height: root.th * root.s
        radius: 6
        color: "#343438"
        border.color: "#666666"
        border.width: 2
        Text {
            anchors.top: parent.top
            anchors.left: parent.left
            anchors.margins: 6
            text: "Tablet " + root.tw + "×" + root.th
            color: "#bbbbbb"
            font.pixelSize: 11
        }
    }

    // Active area (bound to the view-model; updates live as it recomputes).
    Rectangle {
        id: area
        x: root.devToPxX(controller.mapping.areaX1)
        y: root.devToPxY(controller.mapping.areaY1)
        width: (controller.mapping.areaX2 - controller.mapping.areaX1) * root.s
        height: (controller.mapping.areaY2 - controller.mapping.areaY1) * root.s
        color: "#702c4a6e"
        border.color: Material.accent
        border.width: 2

        Text {
            anchors.centerIn: parent
            text: (controller.mapping.areaX2 - controller.mapping.areaX1) + "×"
                  + (controller.mapping.areaY2 - controller.mapping.areaY1)
            color: "#eeeeee"
            font.pixelSize: 11
        }

        // Resize affordance (bottom-right).
        Rectangle {
            width: 12
            height: 12
            color: Material.accent
            anchors.right: parent.right
            anchors.bottom: parent.bottom
        }
    }

    // Single hit-tested interaction layer (mirrors the device-coordinate math).
    MouseArea {
        anchors.fill: parent
        property string mode: ""
        property real startDevX: 0
        property real startDevY: 0
        property var startArea: [0, 0, 0, 0]

        function devX(px) { return (px - root.ox) / root.s }
        function devY(py) { return (py - root.oy) / root.s }

        onPressed: function (mouse) {
            var ax1 = controller.mapping.areaX1
            var ay1 = controller.mapping.areaY1
            var ax2 = controller.mapping.areaX2
            var ay2 = controller.mapping.areaY2
            startArea = [ax1, ay1, ax2, ay2]
            startDevX = devX(mouse.x)
            startDevY = devY(mouse.y)
            var hx = root.devToPxX(ax2)
            var hy = root.devToPxY(ay2)
            if (Math.abs(mouse.x - hx) < 16 && Math.abs(mouse.y - hy) < 16)
                mode = "resize"
            else if (startDevX >= ax1 && startDevX <= ax2 && startDevY >= ay1 && startDevY <= ay2)
                mode = "move"
            else
                mode = ""
        }

        onPositionChanged: function (mouse) {
            if (mode === "")
                return
            var ddx = devX(mouse.x) - startDevX
            var ddy = devY(mouse.y) - startDevY
            var a = startArea
            if (mode === "move") {
                var w = a[2] - a[0]
                var h = a[3] - a[1]
                var nx = Math.max(0, Math.min(a[0] + ddx, root.tw - w))
                var ny = Math.max(0, Math.min(a[1] + ddy, root.th - h))
                controller.mapping.setAreaFromCanvas(Math.round(nx), Math.round(ny),
                                                     Math.round(nx + w), Math.round(ny + h))
            } else {
                var neww = Math.max(1, (a[2] - a[0]) + ddx)
                var newh
                if (controller.mapping.forceProportions) {
                    var aspect = (a[2] - a[0]) / Math.max(1, a[3] - a[1])
                    newh = neww / aspect
                } else {
                    newh = Math.max(1, (a[3] - a[1]) + ddy)
                }
                var x2 = Math.min(root.tw, a[0] + neww)
                var y2 = Math.min(root.th, a[1] + newh)
                controller.mapping.setAreaFromCanvas(a[0], a[1], Math.round(x2), Math.round(y2))
            }
        }
    }
}
