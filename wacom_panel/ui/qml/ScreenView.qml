// Monitor layout drawn to scale; click a monitor to target it.
import QtQuick
import QtQuick.Controls.Material

Rectangle {
    id: root
    radius: 8
    color: "#262628"
    clip: true

    readonly property real pad: 16
    property var rects: controller.mapping.outputRects
    property var bounds: controller.mapping.desktopBounds
    property real s: Math.min((width - 2 * pad) / Math.max(1, bounds.width),
                              (height - 2 * pad) / Math.max(1, bounds.height))
    property real ox: pad + (width - 2 * pad - bounds.width * s) / 2
    property real oy: pad + (height - 2 * pad - bounds.height * s) / 2

    Repeater {
        model: root.rects
        delegate: Rectangle {
            id: mon
            required property var modelData
            x: root.ox + (modelData.x - root.bounds.x) * root.s
            y: root.oy + (modelData.y - root.bounds.y) * root.s
            width: modelData.width * root.s
            height: modelData.height * root.s
            radius: 6
            color: modelData.selected ? "#2c4a6e" : "#343438"
            border.color: modelData.selected ? Material.accent : "#666666"
            border.width: modelData.selected ? 2 : 1

            Column {
                anchors.centerIn: parent
                spacing: 2
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: mon.modelData.name
                    color: "#eeeeee"
                    font.bold: true
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: mon.modelData.width + "×" + mon.modelData.height
                          + (mon.modelData.primary ? "  ★" : "")
                    color: "#bbbbbb"
                    font.pixelSize: 11
                }
            }

            MouseArea {
                anchors.fill: parent
                onClicked: controller.mapping.selectOutputByName(mon.modelData.name)
            }
        }
    }

    Text {
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.margins: 8
        text: "Click a monitor to target it  ·  or pick “Whole desktop”"
        color: "#777777"
        font.pixelSize: 11
    }
}
