// Pen: pressure response (+ named presets), tip click pressure, and pen-button actions.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: page

    // Describe the tip pressure threshold (how hard you must press to register a click).
    function thresholdWord(v) {
        if (v <= 15) return "Feather"
        if (v <= 50) return "Very light"
        if (v <= 150) return "Light"
        if (v <= 400) return "Medium"
        if (v <= 900) return "Firm"
        return "Very firm"
    }

    ScrollView {
        id: scroll
        anchors.fill: parent
        anchors.margins: 12
        contentWidth: availableWidth
        clip: true

        ColumnLayout {
            // Cap the content width so the page doesn't stretch across a wide window.
            width: Math.min(scroll.availableWidth, 600)
            spacing: 12

            GroupBox {
                title: "Pressure curve"
                Layout.fillWidth: true
                ColumnLayout {
                    anchors.fill: parent
                    spacing: 8

                    PressureCurve {
                        // Always square; scales down on narrow windows.
                        property int side: Math.min(scroll.availableWidth - 60, 360)
                        Layout.preferredWidth: side
                        Layout.preferredHeight: side
                        Layout.alignment: Qt.AlignHCenter
                    }
                    Label {
                        text: "Drag the two points — lower-left is a light touch, upper-right is firm."
                        color: "#9aa"
                        font.pixelSize: 12
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Label { text: "Preset:" }
                        ComboBox {
                            id: presetCombo
                            Layout.fillWidth: true
                            model: controller.pen.presetNames
                            onActivated: controller.pen.applyPreset(currentText)
                        }
                        Button {
                            text: "Save…"
                            onClicked: { presetName.text = ""; presetDialog.open() }
                        }
                        Button {
                            text: "Delete"
                            enabled: controller.pen.canDeletePreset(presetCombo.currentText)
                            onClicked: controller.pen.deletePreset(presetCombo.currentText)
                        }
                    }
                }
            }

            GroupBox {
                title: "Tip click pressure"
                Layout.fillWidth: true
                ColumnLayout {
                    anchors.fill: parent
                    spacing: 6
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Label { text: "Click pressure:" }
                        Slider {
                            id: thr
                            Layout.fillWidth: true
                            from: 1; to: 2047; stepSize: 1
                            value: controller.pen.threshold
                            onMoved: controller.pen.threshold = Math.round(value)
                        }
                        Label {
                            Layout.preferredWidth: 90
                            text: page.thresholdWord(thr.value)
                            color: "#cfe3ff"
                        }
                    }
                    Label {
                        Layout.fillWidth: true
                        wrapMode: Text.WordWrap
                        text: "Minimum tip pressure before a click registers — lower means a "
                              + "lighter touch. (This is pressure, not double-click distance.)"
                        color: "#9aa"
                        font.pixelSize: 12
                    }
                }
            }

            GroupBox {
                title: "Pen buttons"
                Layout.fillWidth: true
                GridLayout {
                    anchors.fill: parent
                    columns: 2
                    columnSpacing: 10
                    rowSpacing: 8

                    Label { text: "Tip:" }
                    ActionEditor {
                        Layout.fillWidth: true
                        actKind: controller.pen.button1Kind
                        actValue: controller.pen.button1Value
                        onEdited: function (kind, value) { controller.pen.setButton(1, kind, value) }
                    }
                    Label { text: "Lower button:" }
                    ActionEditor {
                        Layout.fillWidth: true
                        actKind: controller.pen.button2Kind
                        actValue: controller.pen.button2Value
                        onEdited: function (kind, value) { controller.pen.setButton(2, kind, value) }
                    }
                    Label { text: "Upper button:" }
                    ActionEditor {
                        Layout.fillWidth: true
                        actKind: controller.pen.button3Kind
                        actValue: controller.pen.button3Value
                        onEdited: function (kind, value) { controller.pen.setButton(3, kind, value) }
                    }
                }
            }

            Item { Layout.fillHeight: true }
        }
    }

    Dialog {
        id: presetDialog
        anchors.centerIn: parent
        modal: true
        title: "Save pressure preset"
        standardButtons: Dialog.Ok | Dialog.Cancel

        ColumnLayout {
            anchors.fill: parent
            Label { text: "Preset name:" }
            TextField {
                id: presetName
                Layout.fillWidth: true
                Layout.minimumWidth: 240
                onAccepted: presetDialog.accept()
            }
        }
        onAccepted: {
            var n = presetName.text.trim()
            if (n === "") return
            controller.pen.savePreset(n)
            presetCombo.currentIndex = controller.pen.presetNames.indexOf(n)
        }
    }
}
