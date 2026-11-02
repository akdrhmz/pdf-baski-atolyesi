"""Ayarlar/profil deposu testleri: bozuk JSON, atomik yazma, profil yaşam döngüsü."""

from __future__ import annotations

import json

import pytest

from gutter_engine import PageBoxSettings, PdfProcessConfig
from settings_store import SettingsStore


def test_defaults_and_units(tmp_path):
    store = SettingsStore(tmp_path / "settings.json")
    assert store.unit == "mm"
    assert store.theme == "Sistem"
    assert store.profile_names() == []
    store.unit = "cm"
    store.theme = "Koyu"
    store.save()

    reloaded = SettingsStore(tmp_path / "settings.json")
    assert reloaded.unit == "cm"
    assert reloaded.theme == "Koyu"
    # Geçersiz değerler sessizce varsayılana döner.
    reloaded.unit = "kilometre"
    assert reloaded.unit == "cm"


def test_corrupt_json_is_backed_up_and_defaults_used(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{bozuk json", encoding="utf-8")
    store = SettingsStore(path)
    assert store.unit == "mm"
    assert store.theme == "Sistem"
    backups = list(tmp_path.glob("*.bozuk-*.json"))
    assert backups, "Bozuk dosya yedeklenmeli"


def test_profile_save_load_delete(tmp_path):
    path = tmp_path / "settings.json"
    store = SettingsStore(path)
    config = PdfProcessConfig(
        page_boxes=PageBoxSettings(odd_x_mm=18.0, size_mode="auto"),
    )
    store.save_profile("Benim Profilim", config)
    store.save()

    reloaded = SettingsStore(path)
    assert reloaded.profile_names() == ["Benim Profilim"]
    raw = reloaded.get_profile("Benim Profilim")
    assert raw["page_boxes"]["odd_x_mm"] == 18.0
    assert raw["page_boxes"]["size_mode"] == "auto"

    assert reloaded.delete_profile("Benim Profilim") is True
    assert reloaded.delete_profile("Benim Profilim") is False
    assert reloaded.profile_names() == []

    with pytest.raises(ValueError):
        store.save_profile("   ", config)


def test_last_state_and_recent_files(tmp_path):
    path = tmp_path / "settings.json"
    store = SettingsStore(path)
    store.last_state = {"unit": "mm", "theme": "Koyu"}
    assert store.last_state == {"unit": "mm", "theme": "Koyu"}

    for index in range(15):
        store.add_recent_file(f"C:/belge/{index}.pdf")
    store.add_recent_file("C:/belge/5.pdf")
    assert store.recent_files[0] == "C:/belge/5.pdf"
    assert len(store.recent_files) == 10
    StoreReload = SettingsStore(path)
    StoreReload.save()
    assert "recent_files" in json.loads(path.read_text(encoding="utf-8"))
