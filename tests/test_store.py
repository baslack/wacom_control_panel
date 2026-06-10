"""Tests for profile serialisation and the on-disk store."""

from wacom_panel.core.profile import MappingConfig, Profile
from wacom_panel.core.store import ProfileStore


def test_profile_roundtrip(tmp_path):
    p = Profile(name="My Setup",
                mapping=MappingConfig(output="DP-4", area=[0, 1397, 44704, 26543]))
    path = tmp_path / "p.json"
    p.save(path)
    loaded = Profile.load(path)
    assert loaded.name == "My Setup"
    assert loaded.mapping.output == "DP-4"
    assert loaded.mapping.area == [0, 1397, 44704, 26543]


def test_store_crud_and_active(tmp_path):
    store = ProfileStore(root=tmp_path)
    default = store.ensure_default()
    assert default.name == "Default"
    assert store.get_active() == "Default"

    store.save(Profile(name="Drawing"))
    store.set_active("Drawing")
    assert store.get_active() == "Drawing"
    assert set(store.names()) == {"Default", "Drawing"}

    store.rename("Drawing", "Art")
    assert "Art" in store.names()
    assert "Drawing" not in store.names()
    assert store.get_active() == "Art"  # active follows the rename

    store.delete("Art")
    assert "Art" not in store.names()
    # Active falls back to a remaining profile.
    assert store.get_active() == "Default"


def test_store_slugifies_filenames(tmp_path):
    store = ProfileStore(root=tmp_path)
    store.save(Profile(name="Big Tablet / Left!"))
    # Reloadable by its display name despite the slugged filename.
    assert store.load("Big Tablet / Left!") is not None
