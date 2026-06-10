// Pen: pressure response, tip threshold, and pen-button actions.
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

            GroupBox {
                title: "Pressure curve"
                Layout.fillWidth: true
                ColumnLayout {
                    anchors.fill: parent
                    spacing: 8
                    PressureCurve {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 260
                    }
                    Label {
                        text: "Drag the two points — lower-left is a light touch, upper-right is firm."
                        color: "#9aa"
                        font.pixelSize: 12
                    }
                    RowLayout {
                        spacing: 8
                        Label { text: "Presets:" }
                        Button {
                            text: "Soft"
                            onClicked: { controller.pen.p1x = 0; controller.pen.p1y = 30;
                                         controller.pen.p2x = 70; controller.pen.p2y = 100 }
                        }
                        Button {
                            text: "Linear"
                            onClicked: { controller.pen.p1x = 0; controller.pen.p1y = 0;
                                         controller.pen.p2x = 100; controller.pen.p2y = 100 }
                        }
                        Button {
                            text: "Firm"
                            onClicked: { controller.pen.p1x = 30; controller.pen.p1y = 0;
                                         controller.pen.p2x = 100; controller.pen.p2y = 70 }
                        }
                    }
                }
            }

            GroupBox {
                title: "Tip feel"
                Layout.fillWidth: true
                RowLayout {
                    anchors.fill: parent
                    spacing: 8
                    Label { text: "Tip threshold:" }
                    Slider {
                        id: thr
                        Layout.fillWidth: true
                        from: 0; to: 2047; stepSize: 1
                        value: controller.pen.threshold
                        onMoved: controller.pen.threshold = Math.round(value)
                    }
                    Label { text: Math.round(thr.value); Layout.preferredWidth: 40 }
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
}
