"""P2 12: kayıtlı ayarlar açık modüllerle yüklendiyse durum çubuğu bunu bildirir."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app import ModernGutterApp
from gutter_engine import PdfProcessConfig, config_to_dict
from settings_store import SettingsStore


def _make(tmp_path, enable_gutter: bool):
    path = tmp_path / "settings.json"
    if enable_gutter:
        store = SettingsStore(path)
        config = PdfProcessConfig()
        config.page_boxes.enabled = True
        config.margins.enabled = False
        config.page_numbers.enabled = False
        store.last_state = config_to_dict(config)
        store.save()
    return ModernGutterApp(settings_path=path, log_path=tmp_path / "l.log")


def test_startup_notice_lists_active_modules(tmp_path):
    app = _make(tmp_path, True)
    try:
        text = app.status_label.cget("text")
        assert "Önceki oturum ayarları yüklendi" in text and "Cilt" in text
        assert "Fabrika" in text
    finally:
        app.destroy()


def test_no_notice_for_a_fresh_install(tmp_path):
    app = _make(tmp_path, False)
    try:
        assert "Önceki oturum" not in app.status_label.cget("text")
    finally:
        app.destroy()


def test_window_title_has_no_version(tmp_path):
    app = _make(tmp_path, False)
    try:
        assert app.title() == "PDF Baskı & Cilt Stüdyosu"
    finally:
        app.destroy()


def test_factory_state_resets_visible_fields(tmp_path):
    app = _make(tmp_path, True)
    try:
        app.switch_margin.select()
        app._layout_tab().f_bottom.set_mm(10.0)
        app.store.reset()
        app._apply_factory_state()
        assert app.switch_gutter.get() == 1 and app.switch_margin.get() == 1  # varsayılan: açık
        assert app._layout_tab().f_bottom.get_mm() == 0.0
    finally:
        app.destroy()
