// Touch: enable, gestures, and scroll/zoom/tap tuning.
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
            width: Math.min(scroll.availableWidth, 600)
            spacing: 12

            GroupBox {
                title: "Finger touch"
                Layout.fillWidth: true
                ColumnLayout {
                    anchors.fill: parent
                    spacing: 8
                    CheckBox {
                        text: "Enable touch"
                        checked: controller.touch.enabled
                        onToggled: controller.touch.enabled = checked
                    }
                    CheckBox {
                        text: "Enable multi-touch gestures"
                        enabled: controller.touch.enabled
                        checked: controller.touch.gestures
                        onToggled: controller.touch.gestures = checked
                    }
                }
            }

            GroupBox {
                title: "Gesture tuning"
                Layout.fillWidth: true
                enabled: controller.touch.enabled
                GridLayout {
                    anchors.fill: parent
                    columns: 3
                    columnSpacing: 10
                    rowSpacing: 10

                    Label { text: "Scroll distance:" }
                    Slider {
                        id: scrollDist
                        Layout.fillWidth: true
                        from: 1; to: 300; stepSize: 1
                        value: controller.touch.scrollDistance
                        onMoved: controller.touch.scrollDistance = Math.round(value)
                    }
                    Label { text: Math.round(scrollDist.value); Layout.preferredWidth: 40 }

                    Label { text: "Zoom distance:" }
                    Slider {
                        id: zoomDist
                        Layout.fillWidth: true
                        from: 1; to: 300; stepSize: 1
                        value: controller.touch.zoomDistance
                        onMoved: controller.touch.zoomDistance = Math.round(value)
                    }
                    Label { text: Math.round(zoomDist.value); Layout.preferredWidth: 40 }

                    Label { text: "Tap time (ms):" }
                    Slider {
                        id: tapTime
                        Layout.fillWidth: true
                        from: 0; to: 1000; stepSize: 10
                        value: controller.touch.tapTime
                        onMoved: controller.touch.tapTime = Math.round(value)
                    }
                    Label { text: Math.round(tapTime.value); Layout.preferredWidth: 40 }
                }
            }

            Item { Layout.fillHeight: true }
        }
    }
}
