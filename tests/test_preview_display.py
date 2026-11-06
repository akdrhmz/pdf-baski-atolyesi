"""Önizleme paneli: ortayı ezmeme, tam alan / ayrı pencere / üstte tut, akordeon menü."""

from __future__ import annotations

import gc
import time

import pytest

from app import ModernGutterApp


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    folder = tmp_path_factory.mktemp("preview_display")
    application = ModernGutterApp(
        settings_path=folder / "settings.json", log_path=folder / "studio.log")
    application.show()
    for _ in range(4):
        application.update()
    yield application
    try:
        application.destroy()
    except Exception:
        pass
    gc.collect()
    time.sleep(0.2)


@pytest.fixture(autouse=True)
def docked(app):
    app._set_preview_display("docked")
    yield
    app._set_preview_display("docked")


def test_center_area_never_below_minimum(app):
    app.resize(1300, 800)
    for _ in range(3):
        app.update()
    app._set_preview_width(980)
    for _ in range(3):
        app.update()
    center = app._content_frame.width()
    assert center >= app.CENTER_MIN - 10, f"Orta alan {center} < {app.CENTER_MIN - 10}"
    card = app.preview_panel.card
    assert card.geometry().left() >= app._content_frame.geometry().right()


def test_modules_default_on_and_switches_in_sidebar(app):
    assert app.switch_gutter.get() == 1 and app.switch_margin.get() == 1
    assert app.switch_pnum.get() == 0
    tab = app._tabs["Sayfa Düzeni"]
    tab.ensure_built()
    assert tab.switch_gutter is app.switch_gutter
    # Anahtarlar sayfa içinde değil, yan menüde (akordeon) durur.
    assert not tab.frame.isAncestorOf(tab.switch_gutter)
    assert not tab.frame.isAncestorOf(tab.switch_margin)
    assert app._layout_sub.isAncestorOf(app.switch_gutter)


def test_accordion_toggles_on_second_click(app):
    app.select_tab("Sayfa Düzeni")
    app.update()
    assert app._layout_sub.isVisibleTo(app._layout_sub.window())
    app._on_tab_button("Sayfa Düzeni")
    assert not app._layout_sub.isVisibleTo(app._layout_sub.window())
    app._on_tab_button("Sayfa Düzeni")
    assert app._layout_sub.isVisibleTo(app._layout_sub.window())
    app.select_tab("Sayfa Numaraları")
    assert not app._layout_sub.isVisibleTo(app._layout_sub.window())
    app.select_tab("Sayfa Düzeni")


def test_fullscreen_roundtrip(app):
    app._set_preview_display("fullscreen")
    app.update()
    assert not app._content_frame.isVisibleTo(app._workspace)
    assert app.preview_panel.card.isVisibleTo(app._workspace)
    assert app.preview_panel.btn_full.cget("text") == "Küçült"
    app._on_escape()
    app.update()
    assert app._preview_display == "docked"
    assert app._content_frame.isVisibleTo(app._workspace)


def test_separate_window_and_always_on_top(app):
    from PySide6.QtCore import Qt

    app.store.preview_on_top = True
    app._set_preview_display("window")
    app.update()
    win = app._preview_win
    assert win is not None and win.isVisible()
    assert app.preview_panel.card.window() is win
    assert win.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert app.preview_panel.btn_pin.isVisibleTo(win)
    app._toggle_preview_on_top()
    app.update()
    assert not (win.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
    assert app.store.preview_on_top is False
    app._toggle_preview_on_top()
    assert win.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    win.close()  # kapatınca panel yerine döner
    app.update()
    assert app._preview_display == "docked" and app._preview_win is None
    assert app.preview_panel.card.window() is app
    assert not app.preview_panel.btn_pin.isVisibleTo(app)


def test_separate_window_has_no_owner_so_it_can_fall_behind_main(app):
    """Hata (v2.5.1): ayrı önizleme penceresi ana pencerenin SAHİPLİ penceresiydi.

    Windows sahipli pencereyi 'Üstte tut' kapalıyken bile sahibinin önünde tutar. Pencere
    sahipsiz (bağımsız üst düzey) olmalı; böylece kapalıyken ana pencerenin arkasına düşebilir.
    """
    from PySide6.QtCore import Qt

    for on_top in (False, True):
        app.store.preview_on_top = on_top
        app._set_preview_display("window")
        app.update()
        win = app._preview_win
        assert win is not None
        assert win.parent() is None and win.parentWidget() is None
        assert win.windowHandle().transientParent() is None
        assert bool(win.windowFlags() & Qt.WindowType.WindowStaysOnTopHint) is on_top
        assert win.isWindow()
        app._set_preview_display("docked")


def test_toggling_on_top_off_keeps_window_ownerless(app):
    app.store.preview_on_top = True
    app._set_preview_display("window")
    app.update()
    app._toggle_preview_on_top()  # kapat
    app.update()
    win = app._preview_win
    assert win.parent() is None and win.windowHandle().transientParent() is None
    app._toggle_preview_on_top()  # aç
    app.update()
    assert win.parent() is None
    app._set_preview_display("docked")


def test_main_close_also_closes_ownerless_preview_window(app):
    app.store.preview_on_top = False
    app._set_preview_display("window")
    app.update()
    win = app._preview_win
    assert win.isVisible()
    app._close_preview_window()  # uygulama kapanırken çağrılan yol
    assert not win.isVisible()
    app._preview_display = "window"  # fikstür geri yerleştirme için tutarlı kalsın
    app._preview_win = None
    app._set_preview_display("docked")
