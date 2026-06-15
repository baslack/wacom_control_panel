// First-run tablet setup wizard: walks the user through pressing each pad button so the app can
// learn an unknown tablet's layout. Modal; driven entirely by controller.setup.* state.
import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

Dialog {
    id: wizard
    anchors.centerIn: parent
    modal: true
    width: 560
    title: "Set up your tablet"
    // First-run hand-holding: don't let a click-outside dismiss it by accident.
    closePolicy: Popup.NoAutoClose

    readonly property var setup: controller.setup
    readonly property string step: setup.currentStep
    readonly property bool capturing: step === "above" || step === "below"
                                      || step === "center" || step === "all"

    onOpened: setup.start()
    onClosed: setup.cancel()

    // Flash the indicator each time a button is captured.
    Connections {
        target: controller.setup
        function onCaptured() { flash.restart() }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 14

        // ---- Intro ------------------------------------------------------
        ColumnLayout {
            visible: wizard.step === "intro"
            spacing: 10
            Label {
                text: "Let’s set up your " + wizard.setup.tabletLabel + "."
                font.pixelSize: 17; font.bold: true; color: "#e8e8ea"
            }
            Label {
                text: "Linux doesn’t know where this tablet’s buttons are yet. I’ll ask you to "
                      + "press each one so your shortcuts land in the right place. It only takes "
                      + "a moment, and you only have to do it once."
                wrapMode: Text.WordWrap; Layout.fillWidth: true; color: "#b8b8be"
            }
            // Real mouse-button capture needs to read the pad's evdev node. When we can't yet,
            // offer a one-time, per-tablet permission grant (a single password prompt, no logout).
            ColumnLayout {
                visible: !wizard.setup.evdevAvailable
                spacing: 6
                Label {
                    text: "Want your express keys to act as real mouse buttons? That needs "
                          + "one-time permission to read this tablet — just this tablet, nothing "
                          + "else. Basic key shortcuts work without it."
                    wrapMode: Text.WordWrap; Layout.fillWidth: true
                    color: "#caa05a"; font.pixelSize: 12
                }
                Button {
                    text: "Grant access to this tablet…"
                    onClicked: wizard.setup.grantAccess()
                }
            }
            Label {
                visible: wizard.setup.evdevAvailable
                text: "✓ Real mouse-button capture enabled for this tablet."
                wrapMode: Text.WordWrap; Layout.fillWidth: true
                color: "#8bc34a"; font.pixelSize: 12
            }
        }

        // ---- Capture steps ---------------------------------------------
        ColumnLayout {
            visible: wizard.capturing
            spacing: 12
            Label {
                text: wizard.setup.instruction
                font.pixelSize: 16; font.bold: true; color: "#e8e8ea"
                wrapMode: Text.WordWrap; Layout.fillWidth: true
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 96
                radius: 8
                color: "#26262b"
                border.color: flash.running ? "#8bc34a" : "#454550"
                border.width: 2
                ColumnLayout {
                    anchors.centerIn: parent
                    spacing: 4
                    Label {
                        Layout.alignment: Qt.AlignHCenter
                        text: flash.running ? "✓ Got it!" : "Press a button on your tablet…"
                        color: flash.running ? "#8bc34a" : "#9aa"
                        font.pixelSize: 15
                    }
                    Label {
                        Layout.alignment: Qt.AlignHCenter
                        text: wizard.step === "center"
                              ? (wizard.setup.groupCount > 0 ? "Centre captured" : "")
                              : "Captured " + wizard.setup.groupCount + " in this group"
                        color: "#777"; font.pixelSize: 12
                    }
                }
                Timer { id: flash; interval: 450 }
            }

            RowLayout {
                Layout.fillWidth: true
                Label {
                    text: "Total captured: " + wizard.setup.totalCaptured
                          + (wizard.setup.expectedCount > 0
                             ? " of " + wizard.setup.expectedCount : "")
                    color: "#9aa"; font.pixelSize: 12
                }
                Item { Layout.fillWidth: true }
                Button {
                    text: "Undo last"
                    enabled: wizard.setup.groupCount > 0
                    onClicked: wizard.setup.undoLast()
                }
            }
        }

        // ---- Done -------------------------------------------------------
        ColumnLayout {
            visible: wizard.step === "done"
            spacing: 10
            Label {
                text: "All set!"
                font.pixelSize: 17; font.bold: true; color: "#e8e8ea"
            }
            Label {
                text: "I captured " + wizard.setup.totalCaptured + " buttons. Click Finish to "
                      + "save the layout — your Pad tab will then show your buttons where they "
                      + "physically are."
                wrapMode: Text.WordWrap; Layout.fillWidth: true; color: "#b8b8be"
            }
            Button {
                text: "Share this layout (help other users)"
                flat: true
                onClicked: Qt.openUrlExternally(
                    "https://github.com/baslack/wacom_control_panel/issues/new?title="
                    + encodeURIComponent("Layout: " + wizard.setup.tabletLabel)
                    + "&labels=layout")
            }
        }

        // ---- Footer nav -------------------------------------------------
        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 6
            Button {
                text: "Back"
                visible: !wizard.setup.isFirstStep && wizard.step !== "done"
                onClicked: wizard.setup.back()
            }
            Button {
                text: "Cancel"
                visible: wizard.step === "intro"
                onClicked: wizard.close()
            }
            Item { Layout.fillWidth: true }
            Button {
                text: wizard.step === "intro" ? "Begin" : "Next"
                highlighted: true
                visible: wizard.step !== "done"
                // Require at least one capture before leaving a capture group.
                enabled: !wizard.capturing || wizard.setup.groupCount > 0
                onClicked: wizard.setup.nextStep()
            }
            Button {
                text: "Finish"
                highlighted: true
                visible: wizard.step === "done"
                onClicked: { wizard.setup.finish(); wizard.close() }
            }
        }
    }
}
