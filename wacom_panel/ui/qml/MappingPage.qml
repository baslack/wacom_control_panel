// Tablet-to-display mapping: linked screen/tablet canvases + precise controls.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    RowLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 12

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 12

            GroupBox {
                title: "Target display"
                Layout.fillWidth: true
                Layout.fillHeight: true
                ScreenView { anchors.fill: parent }
            }
            GroupBox {
                title: "Tablet active area"
                Layout.fillWidth: true
                Layout.fillHeight: true
                TabletAreaView { anchors.fill: parent }
            }
        }

        Frame {
            Layout.preferredWidth: 340
            Layout.fillHeight: true
            padding: 6

            ScrollView {
                id: controlsScroll
                anchors.fill: parent
                contentWidth: availableWidth
                clip: true

                ColumnLayout {
                    width: controlsScroll.availableWidth
                    spacing: 8

                    GridLayout {
                        columns: 2
                        columnSpacing: 8
                        rowSpacing: 8
                        Layout.fillWidth: true

                        Label { text: "Output:" }
                        ComboBox {
                            Layout.fillWidth: true
                            model: controller.mapping.outputNames
                            currentIndex: controller.mapping.outputIndex
                            onActivated: controller.mapping.outputIndex = currentIndex
                        }

                        CheckBox {
                            Layout.columnSpan: 2
                            text: "Force proportions (no stretch)"
                            checked: controller.mapping.forceProportions
                            onToggled: controller.mapping.forceProportions = checked
                        }

                        Label { text: "Rotation:" }
                        ComboBox {
                            Layout.fillWidth: true
                            model: controller.mapping.rotations
                            currentIndex: Math.max(0, model.indexOf(controller.mapping.rotate))
                            onActivated: controller.mapping.rotate = currentText
                        }

                        Label { text: "Mode:" }
                        ComboBox {
                            Layout.fillWidth: true
                            model: controller.mapping.modes
                            currentIndex: Math.max(0, model.indexOf(controller.mapping.mode))
                            onActivated: controller.mapping.mode = currentText
                        }

                        Label { text: "Anchor:" }
                        ComboBox {
                            Layout.fillWidth: true
                            model: controller.mapping.anchors
                            currentIndex: Math.max(0, model.indexOf(controller.mapping.anchor))
                            onActivated: controller.mapping.anchor = currentText
                        }

                        Label { text: "Zoom:" }
                        RowLayout {
                            Layout.fillWidth: true
                            Slider {
                                id: zoom
                                Layout.fillWidth: true
                                from: 10; to: 100; stepSize: 1
                                value: controller.mapping.zoomPercent
                                onMoved: controller.mapping.zoomPercent = Math.round(value)
                            }
                            Label { text: Math.round(zoom.value) + "%" }
                        }

                        CheckBox {
                            Layout.columnSpan: 2
                            text: "Also map touch"
                            checked: controller.mapping.applyToTouch
                            onToggled: controller.mapping.applyToTouch = checked
                        }
                    }

                    GroupBox {
                        title: "Area (device units)"
                        Layout.fillWidth: true
                        GridLayout {
                            anchors.fill: parent
                            columns: 2
                            columnSpacing: 8
                            Label { text: "Left (x1):" }
                            SpinBox {
                                Layout.fillWidth: true; editable: true; from: 0; to: 1000000; stepSize: 100
                                value: controller.mapping.areaX1
                                onValueModified: controller.mapping.setAreaX1(value)
                            }
                            Label { text: "Top (y1):" }
                            SpinBox {
                                Layout.fillWidth: true; editable: true; from: 0; to: 1000000; stepSize: 100
                                value: controller.mapping.areaY1
                                onValueModified: controller.mapping.setAreaY1(value)
                            }
                            Label { text: "Right (x2):" }
                            SpinBox {
                                Layout.fillWidth: true; editable: true; from: 0; to: 1000000; stepSize: 100
                                value: controller.mapping.areaX2
                                onValueModified: controller.mapping.setAreaX2(value)
                            }
                            Label { text: "Bottom (y2):" }
                            SpinBox {
                                Layout.fillWidth: true; editable: true; from: 0; to: 1000000; stepSize: 100
                                value: controller.mapping.areaY2
                                onValueModified: controller.mapping.setAreaY2(value)
                            }
                        }
                    }

                    Item { Layout.fillHeight: true }
                }
            }
        }
    }
}
