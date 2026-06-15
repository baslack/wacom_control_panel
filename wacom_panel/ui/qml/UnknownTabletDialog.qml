// Opt-in prompt shown when an unrecognised tablet is detected (at launch or hotplugged while the
// window is open). The setup wizard is never forced — the user explicitly chooses to run it or to
// dismiss and accept defaults. Opening the wizard is wired by the parent (see Main.qml).
import QtQuick
import QtQuick.Controls
import QtQuick.Controls.Material
import QtQuick.Layouts

Dialog {
    id: dialog
    anchors.centerIn: parent
    modal: true
    width: 480
    title: "Unidentified tablet detected"
    // A deliberate choice — don't let a stray click outside dismiss it.
    closePolicy: Popup.NoAutoClose

    // Emitted when the user opts in; the parent opens the setup wizard.
    signal setupRequested()

    ColumnLayout {
        anchors.fill: parent
        spacing: 14

        Label {
            text: "“" + controller.tabletName + "” isn’t set up yet."
            font.pixelSize: 16; font.bold: true; color: "#e8e8ea"
            wrapMode: Text.WordWrap; Layout.fillWidth: true
        }
        Label {
            text: "Linux doesn’t know where this tablet’s buttons are. The setup wizard walks you "
                  + "through pressing each one — it only takes a moment, and you only do it once."
            wrapMode: Text.WordWrap; Layout.fillWidth: true; color: "#b8b8be"
        }
        Label {
            text: "If you close this, the panel falls back to default settings and may not work as "
                  + "expected for this tablet. You can run the wizard later from the Pad tab."
            wrapMode: Text.WordWrap; Layout.fillWidth: true
            color: "#caa05a"; font.pixelSize: 12
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 6
            Button {
                text: "Close — use defaults"
                onClicked: dialog.close()
            }
            Item { Layout.fillWidth: true }
            Button {
                text: "Set up this tablet"
                highlighted: true
                onClicked: { dialog.setupRequested(); dialog.close() }
            }
        }
    }
}
