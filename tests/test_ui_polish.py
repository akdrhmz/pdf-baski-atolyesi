"""v2.5.2: yerleşim testleri (14c/14d), ince kaydırma çubuğu, sol menü ipucu, tema sabitleri."""

from __future__ import annotations

import gc
import time

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel

from app import ModernGutterApp
from ui import theme
from ui.qt_compat import QtScrollableFrame, _ThinScrollBar
from core.version import APP_NAME, VERSION


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    folder = tmp_path_factory.mktemp("polish")
    application = ModernGutterApp(
        settings_path=folder / "settings.json", log_path=folder / "studio.log")
    application.resize(1300, 800)
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


def _label(app, text):
    return next(w for w in app.findChildren(QLabel) if w.text().strip() == text)


def _x_range(app, widget):
    left = widget.mapTo(app, QPoint(0, 0)).x()
    return left, left + widget.width()


def test_header_items_left_to_right_and_adjacent(app):
    """14c: simge, başlık, sürüm soldan sağa dizilir ve birbirine yakındır."""
    title, version = _label(app, APP_NAME), _label(app, f"v{VERSION}")
    t_left, t_right = _x_range(app, title)
    v_left, _ = _x_range(app, version)
    assert t_left < v_left
    assert 0 <= v_left - t_right <= 24, f"başlık-sürüm aralığı {v_left - t_right}px"
    icons = [w for w in app.findChildren(QLabel)
             if w.text() == "" and w.pixmap() is not None and not w.pixmap().isNull()
             and w.mapTo(app, QPoint(0, 0)).y() < 60]
    if icons:  # simge varsa başlığın solunda ve bitişik olmalı
        i_left, i_right = _x_range(app, icons[0])
        assert i_left < t_left
        assert 0 <= t_left - i_right <= 24, f"simge-başlık aralığı {t_left - i_right}px"
    assert t_left < 400, "başlık bloğu sola yığılmış olmalı"


def test_step_buttons_have_visible_gap(app):
    """14d: adım düğmeleri arası en az 6 px."""
    buttons = [app._tab_buttons[name] for name in app._tab_buttons]
    boxes = []
    for button in buttons:
        top = button.mapTo(app, QPoint(0, 0)).y()
        boxes.append((top, top + button.height()))
    boxes.sort()
    for (_, bottom), (top, _) in zip(boxes, boxes[1:]):
        assert top - bottom >= 6, f"adım düğmeleri arası {top - bottom}px < 6"


def test_sidebar_hint_explains_fixed_order(app):
    hint = app.lbl_steps_hint.text()
    assert "Sıra sabit" in hint and "Birleştirme" in hint
    assert app.lbl_steps_hint.isVisibleTo(app)
    # ipucu, adım düğmelerinin altında kalmalı
    last_button = max(b.mapTo(app, QPoint(0, 0)).y() for b in app._tab_buttons.values())
    assert app.lbl_steps_hint.mapTo(app, QPoint(0, 0)).y() > last_button


def test_merge_section_titled_clearly(app):
    tab = app._tabs["Birleştirme"]
    tab.ensure_built()
    texts = [w.text() for w in tab.frame.findChildren(QLabel)]
    assert "Birleştirilecek dosyalar" in texts


def test_thin_scrollbar_geometry_and_drag(qtbot=None):
    frame = QtScrollableFrame(None)
    bar = frame.verticalScrollBar()
    assert isinstance(bar, _ThinScrollBar)
    assert bar.width() <= _ThinScrollBar.THICKNESS + 6
    bar.setRange(0, 400)
    bar.setPageStep(100)
    bar.resize(bar.width(), 200)
    thumb = bar.thumb_rect()
    assert thumb is not None and thumb.height() >= _ThinScrollBar.MIN_THUMB
    assert abs(thumb.height() - 200 * 100 / 500) < 1.0  # sayfa/(aralık+sayfa) oranı
    # oluğa tıklama: bir sayfa aşağı
    bar.setValue(0)
    QTest.mouseClick(bar, Qt.MouseButton.LeftButton, pos=QPoint(8, 190))
    assert bar.value() == 100
    # sürükleme: tutamağı sonuna çek
    bar.setValue(0)
    thumb = bar.thumb_rect()
    start = QPoint(8, int(thumb.center().y()))
    QTest.mousePress(bar, Qt.MouseButton.LeftButton, pos=start)
    QTest.mouseMove(bar, QPoint(8, 400))
    QTest.mouseRelease(bar, Qt.MouseButton.LeftButton, pos=QPoint(8, 400))
    assert bar.value() == bar.maximum()


def test_thin_scrollbar_hidden_when_no_overflow():
    bar = _ThinScrollBar()
    bar.setRange(0, 0)
    assert bar.thumb_rect() is None


def test_layout_constants_live_in_theme():
    assert theme.PREVIEW_MIN_W < theme.PREVIEW_DEFAULT_W < theme.PREVIEW_MAX_W
    assert theme.CENTER_MIN_W <= theme.CENTER_MAX_W
    assert ModernGutterApp.CENTER_MIN == theme.CENTER_MIN_W
    assert ModernGutterApp.SIDEBAR_W == theme.SIDEBAR_W
    from ui.shell_build import PreviewSplitter
    assert (PreviewSplitter.MIN_WIDTH, PreviewSplitter.MAX_WIDTH, PreviewSplitter.DEFAULT_WIDTH) == (
        theme.PREVIEW_MIN_W, theme.PREVIEW_MAX_W, theme.PREVIEW_DEFAULT_W)


def test_settings_store_bounds_match_theme(tmp_path):
    from core.settings_store import SettingsStore
    store = SettingsStore(tmp_path / "s.json")
    store.preview_width = 10_000
    assert store.preview_width == theme.PREVIEW_STORE_MAX_W
    store.preview_width = 1
    assert store.preview_width == theme.PREVIEW_STORE_MIN_W


def test_normal_startup_keeps_unvisited_tabs_lazy(tmp_path):
    """Açılış ve ayar yükleme, hiç açılmamış Numara/Birleştirme sekmelerini kurmaz."""
    application = ModernGutterApp(
        settings_path=tmp_path / "s.json", log_path=tmp_path / "l.log")
    try:
        application.show()
        for _ in range(3):
            application.update()
        assert not application._tabs["Sayfa Numaraları"].built
        assert not application._tabs["Birleştirme"].built
        for name in ("Sayfa Numaraları", "Birleştirme", "Sayfa Düzeni"):
            application.select_tab(name)
            application.update()
            assert application._tabs[name].built      # açılınca kurulur
    finally:
        application.destroy()


def test_legacy_name_access_no_longer_builds_tabs(tmp_path):
    """Eski ad (``app.chk_merge_bookmarks``) artık sekmeyi sessizce kurmaz; açık erişim kurar."""
    application = ModernGutterApp(
        settings_path=tmp_path / "s.json", log_path=tmp_path / "l.log")
    try:
        assert not application._tabs["Birleştirme"].built
        with pytest.raises(AttributeError):
            _ = application.chk_merge_bookmarks
        assert not application._tabs["Birleştirme"].built
        assert application._merge_tab().chk_merge_bookmarks is not None
        assert application._tabs["Birleştirme"].built
    finally:
        application.destroy()


def test_ctrl_a_selects_all_in_merge_list(app, tmp_path):
    from tests.pdf_factory import create_sample_a4_pdf
    app.select_tab("Birleştirme")
    app.update()
    tab = app._tabs["Birleştirme"]
    tab.ensure_built()
    tab.clear()
    for index in (1, 2, 3):
        path = str(tmp_path / f"c{index}.pdf")
        create_sample_a4_pdf(path, pages=index)
        tab.append_file(path)
    tab.refresh_list()
    assert app._on_merge_select_all() == "break"
    assert tab.selection() == [0, 1, 2]
    app._on_merge_delete()
    assert tab.files == []
    # Birleştirme dışında kısayol çalışmaz
    app.select_tab("Sayfa Düzeni")
    app.update()
    assert app._on_merge_select_all() is None
