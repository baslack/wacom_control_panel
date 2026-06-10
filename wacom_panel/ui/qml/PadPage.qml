// Pad: map each ExpressKey to a mouse button, keystroke, or disable it.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    ScrollView {
        id: scroll
        anchors.fill: parent
        anchors.margins: 12
        contentWidth: availableWidth
        clip: true

        ColumnLayout {
            width: scroll.availableWidth
            spacing: 12

            Label {
                visible: !controller.pad.hasButtons
                text: "No pad / ExpressKeys detected on this tablet."
                color: "#9aa"
            }

            GroupBox {
                title: "ExpressKeys"
                Layout.fillWidth: true
                visible: controller.pad.hasButtons

                GridLayout {
                    anchors.fill: parent
                    columns: 2
                    columnSpacing: 12
                    rowSpacing: 8

                    Repeater {
                        model: controller.pad.buttonModel
                        delegate: RowLayout {
                            id: row
                            required property var modelData
                            Layout.fillWidth: true
                            Layout.columnSpan: 2
                            spacing: 10

                            Label {
                                text: row.modelData.label
                                Layout.preferredWidth: 90
                            }
                            ActionEditor {
                                Layout.fillWidth: true
                                actKind: row.modelData.kind
                                actValue: row.modelData.value
                                onEdited: function (kind, value) {
                                    controller.pad.setButton(row.modelData.num, kind, value)
                                }
                            }
                        }
                    }
                }
            }

            Label {
                visible: controller.pad.hasButtons
                text: "Tip: keystrokes use xsetwacom syntax, e.g. “ctrl z”, “shift f5”, “super”."
                color: "#9aa"
                font.pixelSize: 12
            }

            Item { Layout.fillHeight: true }
        }
    }
}
