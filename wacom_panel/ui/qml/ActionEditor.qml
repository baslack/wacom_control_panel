// Reusable editor for a button action, with human-named presets plus
// "Mouse button…" (arbitrary number), "Keystroke…", and "Disabled".
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

RowLayout {
    id: editor
    property string actKind: "button"
    property string actValue: ""
    signal edited(string kind, string value)

    spacing: 6

    // custom: undefined = fixed preset; "button" = show number; "key" = show text field.
    readonly property var presets: [
        { label: "Left click", kind: "button", value: "1" },
        { label: "Right click", kind: "button", value: "3" },
        { label: "Middle click", kind: "button", value: "2" },
        { label: "Double click", kind: "doubleclick", value: "" },
        { label: "Back", kind: "button", value: "8" },
        { label: "Forward", kind: "button", value: "9" },
        { label: "Scroll up", kind: "button", value: "4" },
        { label: "Scroll down", kind: "button", value: "5" },
        { label: "Mouse button…", kind: "button", value: "", custom: "button" },
        { label: "Keystroke…", kind: "key", value: "", custom: "key" },
        { label: "Disabled", kind: "disabled", value: "" }
    ]

    function presetIndex() {
        if (actKind === "key") return 9
        if (actKind === "disabled") return 10
        if (actKind === "doubleclick") return 3
        for (var i = 0; i < presets.length; i++)
            if (presets[i].kind === "button" && presets[i].custom === undefined
                    && presets[i].value === actValue)
                return i
        return 8  // arbitrary mouse button
    }

    ComboBox {
        id: combo
        Layout.preferredWidth: 150
        textRole: "label"
        model: editor.presets
        currentIndex: editor.presetIndex()
        onActivated: {
            var p = editor.presets[currentIndex]
            if (p.custom === "button")
                editor.edited("button", (parseInt(editor.actValue) || 1).toString())
            else if (p.custom === "key")
                editor.edited("key", editor.actKind === "key" ? editor.actValue : "")
            else
                editor.edited(p.kind, p.value)
        }
    }

    SpinBox {
        visible: editor.presets[combo.currentIndex].custom === "button"
        from: 1
        to: 32
        value: parseInt(editor.actValue) || 1
        onValueModified: editor.edited("button", value.toString())
    }

    TextField {
        visible: editor.presets[combo.currentIndex].custom === "key"
        Layout.fillWidth: true
        placeholderText: "e.g. ctrl z"
        text: editor.actKind === "key" ? editor.actValue : ""
        onEditingFinished: editor.edited("key", text)
    }

    Item {
        Layout.fillWidth: true
        visible: editor.presets[combo.currentIndex].custom === undefined
    }
}
