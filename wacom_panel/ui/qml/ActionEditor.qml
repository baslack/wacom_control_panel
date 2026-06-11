// Reusable editor for a button action, with human-named presets plus
// "Mouse button…" (arbitrary number), "Keystroke…", "Modifier hold…", and "Disabled".
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

RowLayout {
    id: editor
    property string actKind: "button"
    property string actValue: ""
    signal edited(string kind, string value)

    spacing: 6

    // The held-modifier keysyms we offer (xsetwacom names). "+mod" = press on button-down,
    // auto-released on button-up — i.e. hold the key/express-key to hold the modifier.
    readonly property var modifiers: [["ctrl", "Ctrl"], ["shift", "Shift"],
                                      ["alt", "Alt"], ["super", "Super"]]

    // custom: undefined = fixed preset; "button" = show number; "key" = text field;
    //         "modifier" = show modifier checkboxes.
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
        { label: "Modifier hold…", kind: "key", value: "", custom: "modifier" },
        { label: "Disabled", kind: "disabled", value: "" }
    ]

    // A "key" action is a held-modifier combo iff every token is one of our "+mod" tokens.
    function isModifierAction() {
        if (actKind !== "key" || actValue.trim() === "") return false
        var toks = actValue.trim().split(/\s+/)
        var known = editor.modifiers.map(function (m) { return "+" + m[0] })
        for (var i = 0; i < toks.length; i++)
            if (known.indexOf(toks[i]) < 0) return false
        return true
    }

    function hasMod(mod) {
        return actKind === "key" && (" " + actValue + " ").indexOf("+" + mod + " ") >= 0
    }

    function presetIndex() {
        if (actKind === "key") return isModifierAction() ? 10 : 9
        if (actKind === "disabled") return 11
        if (actKind === "doubleclick") return 3
        for (var i = 0; i < presets.length; i++)
            if (presets[i].kind === "button" && presets[i].custom === undefined
                    && presets[i].value === actValue)
                return i
        return 8  // arbitrary mouse button
    }

    // Push the current checkbox state out as a single "key +a +b" action.
    function rebuildMods() {
        if (modRow.syncing) return
        var parts = []
        for (var i = 0; i < modBoxes.count; i++) {
            var box = modBoxes.itemAt(i)
            if (box.checked) parts.push("+" + box.modKey)
        }
        editor.edited("key", parts.join(" "))
    }

    // Reflect actValue into the checkboxes without re-emitting (guarded against feedback).
    function syncMods() {
        if (!modBoxes) return
        modRow.syncing = true
        for (var i = 0; i < modBoxes.count; i++) {
            var box = modBoxes.itemAt(i)
            box.checked = editor.hasMod(box.modKey)
        }
        modRow.syncing = false
    }

    onActValueChanged: syncMods()
    onActKindChanged: syncMods()
    Component.onCompleted: syncMods()

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
                editor.edited("key", editor.actKind === "key" && !editor.isModifierAction()
                                     ? editor.actValue : "")
            else if (p.custom === "modifier")
                editor.edited("key", editor.isModifierAction() && editor.actValue.trim() !== ""
                                     ? editor.actValue : "+ctrl")
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
        text: editor.actKind === "key" && !editor.isModifierAction() ? editor.actValue : ""
        onEditingFinished: editor.edited("key", text)
    }

    RowLayout {
        id: modRow
        visible: editor.presets[combo.currentIndex].custom === "modifier"
        property bool syncing: false
        spacing: 8

        Repeater {
            id: modBoxes
            model: editor.modifiers
            delegate: CheckBox {
                required property var modelData
                readonly property string modKey: modelData[0]
                text: modelData[1]
                onToggled: editor.rebuildMods()
            }
        }
    }

    Item {
        Layout.fillWidth: true
        visible: editor.presets[combo.currentIndex].custom === undefined
    }
}
