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

    // ---- profile bar + tabs ---------------------------------------------
    header: ColumnLayout {
        spacing: 0
        ToolBar {
            Layout.fillWidth: true
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
        TabBar {
            id: tabs
            Layout.fillWidth: true
            TabButton { text: "Mapping" }
            TabButton { text: "Pen" }
            TabButton { text: "Pad" }
            TabButton { text: "Touch" }
        }
    }

    // ---- body: one page per tab -----------------------------------------
    StackLayout {
        anchors.fill: parent
        currentIndex: tabs.currentIndex
        MappingPage {}
        PenPage {}
        PadPage {}
        TouchPage {}
    }

    // ---- footer: global actions + persistence + status ------------------
    footer: ToolBar {
        background: Rectangle { color: win.barColor }
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 10
            anchors.rightMargin: 10
            spacing: 8
            Button { text: "Apply"; highlighted: true; onClicked: controller.apply() }
            Button { text: "Revert"; onClicked: controller.revert() }
            Button { text: "Save"; onClicked: controller.save() }
            ToolSeparator {}
            CheckBox {
                text: "Reapply on login & replug"
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
