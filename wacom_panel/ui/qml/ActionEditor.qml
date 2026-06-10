// Reusable editor for a button action: mouse button, keystroke, or disabled.
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

RowLayout {
    id: editor
    property string actKind: "button"
    property string actValue: ""
    signal edited(string kind, string value)

    spacing: 6

    ComboBox {
        id: typeCombo
        Layout.preferredWidth: 130
        model: ["Mouse button", "Keystroke", "Disabled"]
        currentIndex: editor.actKind === "key" ? 1
                      : editor.actKind === "disabled" ? 2 : 0
        onActivated: {
            if (currentIndex === 0) {
                var n = parseInt(editor.actValue)
                editor.edited("button", isNaN(n) ? "1" : n.toString())
            } else if (currentIndex === 1) {
                editor.edited("key", editor.actKind === "key" ? editor.actValue : "")
            } else {
                editor.edited("disabled", "")
            }
        }
    }

    SpinBox {
        visible: typeCombo.currentIndex === 0
        from: 1
        to: 32
        value: parseInt(editor.actValue) || 1
        onValueModified: editor.edited("button", value.toString())
    }

    TextField {
        visible: typeCombo.currentIndex === 1
        Layout.fillWidth: true
        placeholderText: "e.g. ctrl z"
        text: editor.actKind === "key" ? editor.actValue : ""
        onEditingFinished: editor.edited("key", text)
    }

    Item { visible: typeCombo.currentIndex === 2; Layout.fillWidth: true }
}
