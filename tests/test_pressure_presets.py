"""Tests for the named pressure-curve preset store."""

from wacom_panel.core.pressure_presets import BUILTINS, PressurePresetStore


def test_builtins_always_present(tmp_path):
    store = PressurePresetStore(root=tmp_path)
    assert set(BUILTINS).issubset(store.names())
    assert store.get("Linear") == [0, 0, 100, 100]
    assert store.is_builtin("Linear")


def test_save_and_get_user_preset(tmp_path):
    store = PressurePresetStore(root=tmp_path)
    assert store.save("My Curve", [5, 10, 80, 95]) is True
    assert store.get("My Curve") == [5, 10, 80, 95]
    assert "My Curve" in store.names()
    assert not store.is_builtin("My Curve")
    # Built-ins sort first, user presets after.
    assert store.names().index("My Curve") >= len(BUILTINS)


def test_cannot_overwrite_builtin_or_save_empty(tmp_path):
    store = PressurePresetStore(root=tmp_path)
    assert store.save("Linear", [1, 2, 3, 4]) is False
    assert store.save("  ", [1, 2, 3, 4]) is False
    assert store.save("Bad", [1, 2, 3]) is False  # wrong length
    assert store.get("Linear") == [0, 0, 100, 100]  # unchanged


def test_delete_user_preset_only(tmp_path):
    store = PressurePresetStore(root=tmp_path)
    store.save("Temp", [0, 0, 50, 50])
    store.delete("Temp")
    assert "Temp" not in store.names()
    store.delete("Linear")  # no-op on a built-in
    assert "Linear" in store.names()


def test_persists_across_instances(tmp_path):
    PressurePresetStore(root=tmp_path).save("Persisted", [10, 20, 30, 40])
    assert PressurePresetStore(root=tmp_path).get("Persisted") == [10, 20, 30, 40]
