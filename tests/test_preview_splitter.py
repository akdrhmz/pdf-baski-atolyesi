"""Önizleme ayracı (``QSplitter``, P3 13b) ve iç alan yerleşimi senaryoları (13e)."""

from __future__ import annotations

import gc
import time

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QScrollArea, QSplitter

from app import ModernGutterApp
from ui.shell_build import PreviewSplitter


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    folder = tmp_path_factory.mktemp("preview_splitter")
    application = ModernGutterApp(
        settings_path=folder / "settings.json", log_path=folder / "studio.log")
    application.resize(1500, 880)
    application.show()
    _pump()
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
    app.resize(1500, 880)
    app._set_preview_width(PreviewSplitter.DEFAULT_WIDTH)
    _pump()
    yield
    app._set_preview_display("docked")


def _pump(times: int = 6) -> None:
    for _ in range(times):
        QApplication.processEvents()
        time.sleep(0.01)


def _sizes(app):
    return app._preview_splitter.sizes()


def test_splitter_is_a_real_qsplitter_with_content_and_preview(app):
    split = app._preview_splitter
    assert isinstance(split, QSplitter) and split.count() == 2
    assert split.widget(0) is app._content_frame
    assert split.widget(1) is app.preview_panel.card
    assert not split.childrenCollapsible()
    assert split.handleWidth() == PreviewSplitter.HANDLE_W


def test_saved_width_is_applied_on_startup(app):
    # Varsayılan kayıtlı genişlik (480) ilk yerleşimde uygulanmış olmalı.
    assert _sizes(app)[1] == PreviewSplitter.DEFAULT_WIDTH


def test_drag_is_clamped_between_min_and_max_and_center_is_kept(app):
    split = app._preview_splitter
    split.moveSplitter(0, 1)                      # en sola: önizleme olabildiğince geniş
    _pump()
    center, preview = _sizes(app)
    assert center >= app.CENTER_MIN
    assert PreviewSplitter.MIN_WIDTH <= preview <= PreviewSplitter.MAX_WIDTH
    split.moveSplitter(split.width() + 500, 1)    # en sağa: önizleme olabildiğince dar
    _pump()
    assert _sizes(app)[1] == PreviewSplitter.MIN_WIDTH


def test_real_mouse_drag_updates_preferred_width_and_saves(app):
    handle = app._preview_splitter.handle(1)
    start = handle.rect().center()
    QTest.mousePress(handle, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(handle, QPoint(start.x() - 100, start.y()))
    QTest.mouseRelease(handle, Qt.MouseButton.LeftButton, pos=QPoint(start.x() - 100, start.y()))
    _pump()
    preview = _sizes(app)[1]
    assert preview == pytest.approx(PreviewSplitter.DEFAULT_WIDTH + 100, abs=4)
    assert app._preview_width == preview
    assert app.store.preview_width == preview     # bırakınca kaydedilir


def test_preferred_width_returns_after_window_shrinks_and_grows(app):
    app._set_preview_width(600)
    _pump()
    wanted = app._preview_width
    app.resize(1260, 780)
    _pump(10)
    center, preview = _sizes(app)
    assert center >= app.CENTER_MIN and preview < wanted   # dar pencerede ezilmez
    app.resize(1700, 900)
    _pump(10)
    assert _sizes(app)[1] == wanted                        # tercih geri gelir


def test_double_click_toggles_default_and_wide(app):
    handle = app._preview_splitter.handle(1)
    QTest.mouseDClick(handle, Qt.MouseButton.LeftButton, pos=handle.rect().center())
    _pump()
    wide = _sizes(app)[1]
    assert wide > PreviewSplitter.DEFAULT_WIDTH + 100
    assert _sizes(app)[0] >= app.CENTER_MIN
    QTest.mouseDClick(handle, Qt.MouseButton.LeftButton, pos=handle.rect().center())
    _pump()
    assert _sizes(app)[1] == PreviewSplitter.DEFAULT_WIDTH


def test_window_mode_gives_content_full_width_and_returns(app):
    app._set_preview_display("window")
    _pump(10)
    split = app._preview_splitter
    assert split.preview_index() == -1
    assert app._content_frame.width() == split.width()
    app._set_preview_display("docked")
    _pump(10)
    assert split.preview_index() == 1 and app.preview_panel.card.isVisibleTo(app._workspace)
    assert _sizes(app)[1] == app._effective_preview_width()


def test_fullscreen_card_fills_workspace_and_restores(app):
    app._set_preview_display("fullscreen")
    _pump(10)
    card = app.preview_panel.card
    assert not app._content_frame.isVisibleTo(app._workspace)
    assert card.width() == app._preview_splitter.width() > PreviewSplitter.MAX_WIDTH
    app._set_preview_display("docked")
    _pump(10)
    assert app._content_frame.isVisibleTo(app._workspace)
    assert card.maximumWidth() == PreviewSplitter.MAX_WIDTH
    assert _sizes(app)[0] >= app.CENTER_MIN


@pytest.mark.parametrize("window", [(1260, 780), (1500, 880)])
def test_wide_preview_never_pushes_tab_controls_out(app, window):
    """13e: önizleme en geniş, pencere dar iken sekme içeriği yatay kaymaz, düğmeler görünür kalır."""
    app.resize(*window)
    app.select_tab("Sayfa Düzeni")
    app._set_preview_width(PreviewSplitter.MAX_WIDTH)
    _pump(12)
    tab = app._tabs["Sayfa Düzeni"]
    tab.ensure_built()
    assert app._content_frame.width() >= app.CENTER_MIN
    for scroll in tab.frame.findChildren(QScrollArea):
        assert scroll.horizontalScrollBar().maximum() == 0
        viewport_w = scroll.viewport().width()
        for row in (tab._gutter_preset_row, tab._preset_row):
            buttons = row.findChildren(type(app.btn_main_action))
            assert len(buttons) >= 4                      # İnce/Standart/Geniş/Sıfırla ya da şablonlar
            for button in buttons:
                right = button.mapTo(scroll.viewport(), QPoint(button.width(), 0)).x()
                assert right <= viewport_w, f"{button.text()} taşıyor ({right} > {viewport_w})"
