// Pad: a spatial mock of the physical ExpressKeys + touch ring on the left (scrolls if
// needed); the action editor sits fixed on the right so it's always visible — click a key
// or ring direction and bind its action without scrolling back up.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: page

    // Current selection: a "button" (express key / ring centre) or a "wheel" (ring direction).
    property string selKind: ""      // "" | "button" | "wheel"
    property int selButton: -1
    property string selDirection: "" // "cw" | "ccw"
    property string selLabel: ""
    property string actKind: "disabled"
    property string actValue: ""

    function selectButton(num, label, kind, value) {
        page.selKind = "button"
        page.selButton = num
        page.selLabel = label
        page.actKind = kind
        page.actValue = value
    }
    function selectWheel(direction, label, kind, value) {
        page.selKind = "wheel"
        page.selDirection = direction
        page.selLabel = label
        page.actKind = kind
        page.actValue = value
    }
    function commit(kind, value) {
        page.actKind = kind
        page.actValue = value
        if (page.selKind === "button")
            controller.pad.setButton(page.selButton, kind, value)
        else if (page.selKind === "wheel")
            controller.pad.setWheel(page.selDirection, kind, value)
    }

    // Friendly one-liner for an action, used as the caption under each key.
    function actionCaption(kind, value) {
        if (kind === "disabled" || value === "") return "—"
        if (kind === "doubleclick") return "Double click"
        if (kind === "key") {
            var keys = { "Up": "Scroll up ↑", "Down": "Scroll down ↓",
                         "Prior": "Page up", "Next": "Page down" }
            if (keys[value] !== undefined) return keys[value]
            if (value.indexOf("+") >= 0)  // held-modifier combo: "+ctrl +shift"
                return "Hold " + value.replace(/\+/g, "").replace(/\s+/g, "+")
            return "⌨ " + value
        }
        return "Mouse " + value  // shouldn't occur on the pad
    }

    component KeyButton: Rectangle {
        id: key
        property int num: -1
        property string label: ""
        property string kind: "disabled"
        property string value: ""
        property bool selected: page.selKind === "button" && page.selButton === num
        Layout.fillWidth: true
        Layout.preferredHeight: 38
        radius: 6
        color: selected ? "#3949ab" : "#2b2b30"
        border.color: selected ? "#7986cb" : "#454550"
        border.width: 1

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 8
            anchors.rightMargin: 8
            spacing: 8
            Label {
                text: key.label
                color: "#e8e8ea"
                font.pixelSize: 12
                font.bold: true
                Layout.preferredWidth: 48
                elide: Text.ElideRight
            }
            Label {
                text: page.actionCaption(key.kind, key.value)
                color: "#9aa"
                font.pixelSize: 11
                Layout.fillWidth: true
                horizontalAlignment: Text.AlignRight
                elide: Text.ElideRight
            }
        }
        MouseArea {
            anchors.fill: parent
            cursorShape: Qt.PointingHandCursor
            onClicked: page.selectButton(key.num, key.label, key.kind, key.value)
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 10

        Label {
            text: controller.pad.displayName
            color: "#e8e8ea"
            font.pixelSize: 16
            font.bold: true
        }
        Label {
            visible: !controller.pad.hasPad
            text: "No pad / ExpressKeys detected on this tablet."
            color: "#9aa"
        }
        Label {
            visible: controller.pad.hasPad && !controller.pad.layoutMatched
            text: "Unknown model — showing a generic flat key list. Add a layout JSON "
                  + "under wacom_panel/layouts/ to arrange it spatially."
            color: "#caa05a"
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }

        RowLayout {
            visible: controller.pad.hasPad
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 24

            // ---- Left: scrollable spatial mock of the pad --------------------
            ScrollView {
                id: padScroll
                Layout.preferredWidth: 250
                Layout.fillHeight: true
                contentWidth: availableWidth
                clip: true

                ColumnLayout {
                    width: padScroll.availableWidth
                    spacing: 6

                    Repeater {
                        model: controller.pad.topKeys
                        delegate: KeyButton {
                            required property var modelData
                            num: modelData.num
                            label: modelData.label
                            kind: modelData.kind
                            value: modelData.value
                        }
                    }

                    // ---- Touch ring ---------------------------------------
                    Item {
                        visible: controller.pad.hasRing
                        Layout.alignment: Qt.AlignHCenter
                        Layout.topMargin: 4
                        Layout.bottomMargin: 4
                        implicitWidth: 168
                        implicitHeight: 168

                        Rectangle {  // outer ring
                            anchors.fill: parent
                            radius: width / 2
                            color: "#26262b"
                            border.color: "#454550"
                            border.width: 2
                        }

                        // Clockwise (top arc)
                        Rectangle {
                            width: 88; height: 26; radius: 6
                            anchors.horizontalCenter: parent.horizontalCenter
                            anchors.top: parent.top
                            anchors.topMargin: 12
                            color: (page.selKind === "wheel" && page.selDirection === "cw")
                                   ? "#3949ab" : "#2b2b30"
                            border.color: "#454550"
                            Label {
                                anchors.centerIn: parent
                                text: "↻ CW"
                                color: "#e8e8ea"; font.pixelSize: 12
                            }
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: page.selectWheel("cw", "Ring — clockwise",
                                    controller.pad.cwKind, controller.pad.cwValue)
                            }
                        }

                        // Counter-clockwise (bottom arc)
                        Rectangle {
                            width: 88; height: 26; radius: 6
                            anchors.horizontalCenter: parent.horizontalCenter
                            anchors.bottom: parent.bottom
                            anchors.bottomMargin: 12
                            color: (page.selKind === "wheel" && page.selDirection === "ccw")
                                   ? "#3949ab" : "#2b2b30"
                            border.color: "#454550"
                            Label {
                                anchors.centerIn: parent
                                text: "↺ CCW"
                                color: "#e8e8ea"; font.pixelSize: 12
                            }
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: page.selectWheel("ccw", "Ring — counter-clockwise",
                                    controller.pad.ccwKind, controller.pad.ccwValue)
                            }
                        }

                        // Centre mode button
                        Rectangle {
                            id: center
                            visible: controller.pad.ringCenterNum >= 0
                            anchors.centerIn: parent
                            width: 72; height: 72; radius: width / 2
                            color: (page.selKind === "button"
                                    && page.selButton === controller.pad.ringCenterNum)
                                   ? "#3949ab" : "#2b2b30"
                            border.color: "#454550"; border.width: 1
                            ColumnLayout {
                                anchors.centerIn: parent
                                spacing: 1
                                width: parent.width - 10
                                Label {
                                    text: controller.pad.ringCenterLabel
                                    color: "#e8e8ea"; font.pixelSize: 12; font.bold: true
                                    Layout.alignment: Qt.AlignHCenter
                                }
                                Label {
                                    text: page.actionCaption(controller.pad.ringCenterKind,
                                                             controller.pad.ringCenterValue)
                                    color: "#9aa"; font.pixelSize: 10
                                    horizontalAlignment: Text.AlignHCenter
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                            }
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: page.selectButton(controller.pad.ringCenterNum,
                                    controller.pad.ringCenterLabel,
                                    controller.pad.ringCenterKind, controller.pad.ringCenterValue)
                            }
                        }
                    }

                    Repeater {
                        model: controller.pad.bottomKeys
                        delegate: KeyButton {
                            required property var modelData
                            num: modelData.num
                            label: modelData.label
                            kind: modelData.kind
                            value: modelData.value
                        }
                    }
                }
            }

            // ---- Right: fixed action editor (always visible) -----------------
            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.alignment: Qt.AlignTop
                spacing: 10

                Label {
                    text: page.selKind === "" ? "Select a key or ring direction"
                                              : page.selLabel
                    color: "#e8e8ea"
                    font.pixelSize: 15
                    font.bold: true
                }

                ActionEditor {
                    visible: page.selKind !== ""
                    Layout.fillWidth: true
                    keyboardOnly: true
                    actKind: page.actKind
                    actValue: page.actValue
                    onEdited: function (kind, value) { page.commit(kind, value) }
                }

                Label {
                    text: "Pad keys send keystrokes only — mouse-button and scroll-wheel "
                          + "actions don’t reach apps from the pad on X, so this menu "
                          + "offers keys. The ring scrolls a line per detent via ↑/↓ "
                          + "(Page up/down jumps a whole page)."
                    color: "#caa05a"
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }
                Label {
                    visible: controller.pad.hasRing
                    text: "The touch ring sends one Clockwise and one Counter-clockwise "
                          + "action. xsetwacom can’t store a different ring action per "
                          + "mode — that LED-cycling is a proprietary-driver feature — so "
                          + "the centre button here is just a normal bindable key."
                    color: "#9aa"
                    font.pixelSize: 12
                    wrapMode: Text.WordWrap
                    Layout.fillWidth: true
                }

                // ---- Ring daemon: real scroll instead of keystrokes ----------
                Rectangle {
                    visible: controller.pad.hasRing
                    Layout.fillWidth: true
                    Layout.topMargin: 6
                    implicitHeight: ringDaemonCol.implicitHeight + 20
                    radius: 6
                    color: "#26262b"
                    border.color: "#454550"

                    ColumnLayout {
                        id: ringDaemonCol
                        anchors.fill: parent
                        anchors.margins: 10
                        spacing: 6

                        CheckBox {
                            text: "Scroll with the background daemon (real wheel)"
                            checked: controller.pad.ringDaemon
                            onToggled: controller.pad.ringDaemon = checked
                        }
                        Label {
                            text: "Emits real REL_WHEEL scroll via a small userspace daemon, "
                                  + "so the ring scrolls smoothly like a mouse wheel instead of "
                                  + "tapping arrow keys. The CW/CCW keystrokes above are ignored "
                                  + "while this is on. One-time setup: run "
                                  + "‘wacom-panel --install-ring-daemon’, then log out and back in."
                            color: "#9aa"
                            font.pixelSize: 11
                            wrapMode: Text.WordWrap
                            Layout.fillWidth: true
                        }
                    }
                }

                Item { Layout.fillHeight: true }
            }
        }
    }
}
