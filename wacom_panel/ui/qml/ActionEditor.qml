// Reusable editor for a button action.
//   default mode      — mouse + keyboard presets (pen buttons can do real mouse buttons)
//   keyboardOnly mode — keystroke presets only (pad buttons can ONLY emit keystrokes on X;
//                       mouse-button actions silently fail there, so we don't offer them)
import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

RowLayout {
    id: editor
    property string actKind: "button"
    property string actValue: ""
    property bool keyboardOnly: false
    signal edited(string kind, string value)

    spacing: 6

    readonly property var modifiers: [["ctrl", "Ctrl"], ["shift", "Shift"],
                                      ["alt", "Alt"], ["super", "Super"]]

    // custom: undefined = fixed preset; "button" = number spin; "key" = text field;
    //         "modifier" = modifier checkboxes.
    readonly property var mousePresets: [
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
    readonly property var keyPresets: [
        { label: "Scroll up (↑)", kind: "key", value: "Up" },
        { label: "Scroll down (↓)", kind: "key", value: "Down" },
        { label: "Page up", kind: "key", value: "Prior" },
        { label: "Page down", kind: "key", value: "Next" },
        { label: "Undo (Ctrl+Z)", kind: "key", value: "ctrl z" },
        { label: "Redo (Ctrl+Shift+Z)", kind: "key", value: "ctrl shift z" },
        { label: "Keystroke…", kind: "key", value: "", custom: "key" },
        { label: "Modifier hold…", kind: "key", value: "", custom: "modifier" },
        { label: "Disabled", kind: "disabled", value: "" }
    ]
    readonly property var presets: keyboardOnly ? keyPresets : mousePresets

    function findCustom(tag) {
        for (var i = 0; i < presets.length; i++)
            if (presets[i].custom === tag) return i
        return -1
    }
    function findFixedKind(k) {
        for (var i = 0; i < presets.length; i++)
            if (presets[i].kind === k && presets[i].custom === undefined) return i
        return -1
    }

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
        var i
        if (actKind === "disabled") return Math.max(0, findFixedKind("disabled"))
        if (actKind === "doubleclick") return Math.max(0, findFixedKind("doubleclick"))
        if (actKind === "key") {
            if (isModifierAction()) return Math.max(0, findCustom("modifier"))
            for (i = 0; i < presets.length; i++)
                if (presets[i].kind === "key" && presets[i].custom === undefined
                        && presets[i].value === actValue) return i
            return Math.max(0, findCustom("key"))
        }
        if (actKind === "button") {
            for (i = 0; i < presets.length; i++)
                if (presets[i].kind === "button" && presets[i].custom === undefined
                        && presets[i].value === actValue) return i
            var c = findCustom("button")
            return c >= 0 ? c : Math.max(0, findFixedKind("disabled"))
        }
        return 0
    }

    function rebuildMods() {
        if (modRow.syncing) return
        var parts = []
        for (var i = 0; i < modBoxes.count; i++) {
            var box = modBoxes.itemAt(i)
            if (box.checked) parts.push("+" + box.modKey)
        }
        editor.edited("key", parts.join(" "))
    }
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
        Layout.preferredWidth: 200
        textRole: "label"
        model: editor.presets
        currentIndex: editor.presetIndex()
        // Let the popup be as wide as its widest label so entries aren't clipped.
        popup.width: Math.max(combo.width, 240)
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
