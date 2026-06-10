import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

ApplicationWindow {
    id: win
    width: 1120
    height: 780
    minimumWidth: 940
    minimumHeight: 600
    visible: true
    title: "Wacom Control Panel"

    Material.theme: Material.Dark
    Material.accent: Material.Blue

    readonly property color barColor: "#2a2a2e"
    readonly property color barText: "#e6e6e6"

    property string status: controller.tabletName

    Connections {
        target: controller
        function onStatusMessage(msg) { win.status = msg }
    }

    // ---- profile bar -----------------------------------------------------
    header: ToolBar {
        background: Rectangle { color: win.barColor }
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 10
            anchors.rightMargin: 10
            spacing: 8

            Label { text: "Profile:"; color: win.barText }
            ComboBox {
                id: profileCombo
                Layout.minimumWidth: 200
                model: controller.profileNames
                currentIndex: Math.max(0, controller.profileNames.indexOf(controller.activeProfile))
                onActivated: controller.selectProfile(currentText)
            }
            Button { text: "New"; onClicked: nameDialog.open("new", "New profile", "") }
            Button { text: "Duplicate"; onClicked: nameDialog.open("duplicate", "Duplicate profile",
                                                                    controller.activeProfile + " copy") }
            Button { text: "Rename"; onClicked: nameDialog.open("rename", "Rename profile",
                                                                 controller.activeProfile) }
            Button { text: "Delete"; onClicked: deleteDialog.open() }
            Item { Layout.fillWidth: true }
            Label { text: controller.tabletName; color: "#aab2bb"; font.pixelSize: 12 }
        }
    }

    // ---- body ------------------------------------------------------------
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

        // ---- controls ----------------------------------------------------
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

                RowLayout {
                    Layout.fillWidth: true
                    Button { text: "Apply"; highlighted: true; onClicked: controller.apply() }
                    Button { text: "Revert"; onClicked: controller.revert() }
                    Item { Layout.fillWidth: true }
                    Button { text: "Save"; onClicked: controller.save() }
                }
            }
            }
        }
    }

    // ---- footer ----------------------------------------------------------
    footer: ToolBar {
        background: Rectangle { color: win.barColor }
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 10
            anchors.rightMargin: 10
            CheckBox {
                text: "Reapply active profile on login & device replug"
                checked: controller.persistInstalled
                onToggled: controller.setPersist(checked)
            }
            Item { Layout.fillWidth: true }
            Label { text: win.status; color: win.barText }
        }
    }

    // ---- dialogs ---------------------------------------------------------
    Dialog {
        id: nameDialog
        anchors.centerIn: parent
        modal: true
        standardButtons: Dialog.Ok | Dialog.Cancel
        property string action: ""
        title: "Profile"

        function open(act, heading, preset) {
            action = act
            title = heading
            nameField.text = preset
            visible = true
            nameField.forceActiveFocus()
            nameField.selectAll()
        }

        ColumnLayout {
            anchors.fill: parent
            Label { text: "Name:" }
            TextField {
                id: nameField
                Layout.fillWidth: true
                Layout.minimumWidth: 260
                onAccepted: nameDialog.accept()
            }
        }

        onAccepted: {
            var name = nameField.text.trim()
            if (name === "") return
            if (action === "new") controller.newProfile(name)
            else if (action === "duplicate") controller.duplicateProfile(name)
            else if (action === "rename") controller.renameProfile(name)
        }
    }

    Dialog {
        id: deleteDialog
        anchors.centerIn: parent
        modal: true
        title: "Delete profile"
        standardButtons: Dialog.Yes | Dialog.No
        Label { text: "Delete “" + controller.activeProfile + "”?" }
        onAccepted: controller.deleteProfile()
    }
}
