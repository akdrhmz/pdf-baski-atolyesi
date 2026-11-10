"""Birleştirme listesi sürükle-bırak (P3-40): bırakma çizgisi, otomatik kaydırma, tutamaktan sürükleme."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication

from tests.pdf_factory import create_sample_a4_pdf
from tests.test_merge_tab import _make, root  # noqa: F401  (fikstür ve yardımcılar)
from ui.tabs.merge_drag import autoscroll_step, reorder_for_drop
from ui.theme import DRAG_SCROLL_MAX_STEP, DRAG_SCROLL_ZONE, DRAG_START_PX


@pytest.fixture()
def shown(root, tmp_path):  # noqa: F811
    """30 dosyalı, gerçekten yerleşmiş (görünür) liste: kaydırma çubuğu ve geometri var."""
    tab, ctx, frame = _make(root)
    tab.ensure_built()
    for index in range(1, 31):
        path = str(tmp_path / f"d{index:02d}.pdf")
        create_sample_a4_pdf(path, pages=index)
        tab.append_file(path)
    tab.refresh_list()
    root.show()
    root.resize(900, 700)
    frame.show()
    for _ in range(5):
        QApplication.processEvents()
    ctx.calls.clear()
    yield tab, ctx
    tab._end_drag()
    frame.destroy()


def _fire(widget, name, y, **extra):
    ev = SimpleNamespace(widget=widget, x_root=0, y_root=y, ctrl=False, shift=False, **extra)
    for cb in widget._bindings[name]:
        cb(ev)


def _ids(tab):
    return [item["pages"] for item in tab.files]


def _mid(row):
    return row.winfo_rooty() + row.winfo_height() // 2


def _gap_before(tab, index):
    """``index``. satırın hemen önündeki aralığın ekran y'si."""
    row = tab.rows[index]
    return row.winfo_rooty() - 1


# -- Saf mantık ---------------------------------------------------------------------
@pytest.mark.parametrize("chosen, slot, expected", [
    ([0], 3, [1, 2, 0, 3, 4]),          # tek satır aşağı
    ([3], 1, [0, 3, 1, 2, 4]),          # tek satır yukarı
    ([2], 5, [0, 1, 3, 4, 2]),          # en sona
    ([2], 0, [2, 0, 1, 3, 4]),          # en başa
    ([1, 2], 5, [0, 3, 4, 1, 2]),       # blok en sona
    ([0, 2], 4, [1, 3, 0, 2, 4]),       # bitişik olmayan seçim bir araya gelir, kendi sırası korunur
    ([1], 1, [0, 1, 2, 3, 4]),          # kendi önüne: değişmez
    ([1], 2, [0, 1, 2, 3, 4]),          # kendi sonrasına: değişmez
    ([1, 2], 2, [0, 1, 2, 3, 4]),       # bloğun içine: değişmez
])
def test_reorder_for_drop(chosen, slot, expected):
    assert reorder_for_drop(5, chosen, slot) == expected


def test_autoscroll_step_zones():
    top, bottom = 100, 400
    assert autoscroll_step(250, top, bottom) == 0                       # ortada kaydırma yok
    assert autoscroll_step(top + DRAG_SCROLL_ZONE + 1, top, bottom) == 0
    assert autoscroll_step(top, top, bottom) == -DRAG_SCROLL_MAX_STEP   # üst kenarda en hızlı
    assert autoscroll_step(top - 500, top, bottom) == -DRAG_SCROLL_MAX_STEP  # dışarıda da sınırlı
    assert autoscroll_step(bottom, bottom=bottom, top=top) == DRAG_SCROLL_MAX_STEP
    slow = autoscroll_step(top + DRAG_SCROLL_ZONE - 2, top, bottom)
    fast = autoscroll_step(top + 4, top, bottom)
    assert slow < 0 and fast < slow, "kenara yaklaştıkça hız artar"
    assert autoscroll_step(10, 50, 50) == 0                              # boş görünüm


# -- Bırakma çizgisi ----------------------------------------------------------------
def test_rows_stay_put_while_dragging_and_line_follows_pointer(shown):
    tab, _ = shown
    first = tab.rows[0]
    _fire(first, "<Button-1>", _mid(first))
    target = _gap_before(tab, 5)
    _fire(first, "<B1-Motion>", target)
    assert _ids(tab)[:3] == [1, 2, 3], "sürüklerken satırlar yer değiştirmez"
    assert tab._dragged and tab._drag_slot == 5
    line = tab._drop_line
    assert line is not None and line.isVisible()
    assert line.height() == 3
    expected_mid = tab.drop_line_y(5)
    assert line.y() + line.height() // 2 == pytest.approx(expected_mid, abs=1)
    assert tab.rows[4].y() < expected_mid < tab.rows[5].y() + 1
    # Çizgi başka aralığa kayar:
    _fire(first, "<B1-Motion>", _gap_before(tab, 2))
    assert tab._drag_slot == 2
    assert line.y() < expected_mid


def test_release_moves_to_the_line_and_hides_it(shown):
    tab, ctx = shown
    first = tab.rows[0]
    _fire(first, "<Button-1>", _mid(first))
    _fire(first, "<B1-Motion>", _gap_before(tab, 5))
    ctx.calls.clear()
    _fire(first, "<ButtonRelease-1>", _gap_before(tab, 5))
    assert _ids(tab)[:6] == [2, 3, 4, 5, 1, 6]
    assert tab.selection() == [4] and tab.selected_idx == 4
    assert [int(r._number_label.cget("text")) for r in tab.rows[:6]] == [1, 2, 3, 4, 5, 6]
    assert not tab._drop_line.isVisible()
    assert tab.drag_idx is None and not tab._dragged and not tab._drag_timer.isActive()
    assert any(call[0] == "schedule_preview" for call in ctx.calls), "taşıma sonrası önizleme yenilenir"


def test_release_at_own_position_changes_nothing(shown):
    tab, _ = shown
    row = tab.rows[3]
    _fire(row, "<Button-1>", _mid(row))
    _fire(row, "<B1-Motion>", _mid(row) + DRAG_START_PX + 1)
    _fire(row, "<ButtonRelease-1>", _mid(row) + DRAG_START_PX + 1)
    assert _ids(tab)[:5] == [1, 2, 3, 4, 5] and tab.selected_idx == 3


def test_small_movement_is_a_click_not_a_drag(shown):
    tab, _ = shown
    row = tab.rows[2]
    _fire(row, "<Button-1>", _mid(row))
    _fire(row, "<B1-Motion>", _mid(row) + DRAG_START_PX - 1)
    assert not tab._dragged and (tab._drop_line is None or not tab._drop_line.isVisible())
    _fire(row, "<ButtonRelease-1>", _mid(row))
    assert _ids(tab)[:4] == [1, 2, 3, 4] and tab.selected_idx == 2


def test_block_drag_to_end_keeps_selection_and_order(shown):
    tab, _ = shown
    tab.select_item(1)
    tab.select_item(2, ctrl=True)
    last = tab.rows[-1]
    row = tab.rows[1]
    _fire(row, "<Button-1>", _mid(row))
    _fire(row, "<B1-Motion>", last.winfo_rooty() + last.winfo_height())
    assert tab._drag_slot == len(tab.files)
    _fire(row, "<ButtonRelease-1>", last.winfo_rooty() + last.winfo_height())
    assert _ids(tab)[-2:] == [2, 3] and _ids(tab)[:3] == [1, 4, 5]
    assert tab.selection() == [28, 29]


def test_refresh_list_mid_drag_ends_the_drag(shown):
    tab, _ = shown
    row = tab.rows[0]
    _fire(row, "<Button-1>", _mid(row))
    _fire(row, "<B1-Motion>", _gap_before(tab, 4))
    assert tab._dragged
    tab.refresh_list()
    assert not tab._dragged and tab.drag_idx is None
    assert not tab._drag_timer.isActive() and not tab._drop_line.isVisible()
    assert len(tab.rows) == 30


# -- Otomatik kaydırma -------------------------------------------------------------
def test_autoscroll_scrolls_at_edges_even_without_mouse_motion(shown):
    tab, _ = shown
    frame = tab.merge_list_frame
    bar = frame.verticalScrollBar()
    assert bar.maximum() > 0, "30 satır görünüme sığmamalı (testin önkoşulu)"
    viewport = frame.viewport()
    top = viewport.mapToGlobal(QPoint(0, 0)).y()
    bottom = top + viewport.height()
    row = tab.rows[0]
    _fire(row, "<Button-1>", _mid(row))
    _fire(row, "<B1-Motion>", bottom - 2)           # alt kenar şeridi
    assert tab._drag_timer.isActive()
    before, slot_before = bar.value(), tab._drag_slot
    tab._tick_autoscroll()                          # fare kımıldamadan zamanlayıcı kaydırır
    assert bar.value() > before
    assert tab._drag_slot >= slot_before, "kaydırınca bırakma aralığı yeniden hesaplanır"
    # Üst kenara dönünce geri kayar:
    _fire(row, "<B1-Motion>", top + 2)
    mid_value = bar.value()
    tab._tick_autoscroll()
    assert bar.value() < mid_value
    # Ortada kaydırma yok:
    _fire(row, "<B1-Motion>", (top + bottom) // 2)
    stable = bar.value()
    tab._tick_autoscroll()
    assert bar.value() == stable
    _fire(row, "<ButtonRelease-1>", (top + bottom) // 2)
    assert not tab._drag_timer.isActive()


def test_autoscroll_stops_at_the_end_of_the_list(shown):
    tab, _ = shown
    bar = tab.merge_list_frame.verticalScrollBar()
    bar.setValue(bar.maximum())
    viewport = tab.merge_list_frame.viewport()
    bottom = viewport.mapToGlobal(QPoint(0, 0)).y() + viewport.height()
    row = tab.rows[-1]
    _fire(row, "<Button-1>", _mid(row))
    _fire(row, "<B1-Motion>", bottom + 50)
    tab._tick_autoscroll()
    assert bar.value() == bar.maximum()
    _fire(row, "<ButtonRelease-1>", bottom + 50)


# -- Yalnız tutamaktan sürükleme -----------------------------------------------------
def test_handle_only_off_by_default_any_part_drags(shown):
    tab, _ = shown
    assert not tab.handle_only()
    row = tab.rows[0]
    _fire(row._title_label, "<Button-1>", _mid(row))
    assert tab.drag_idx == 0
    tab._end_drag()


def test_handle_only_requires_the_handle(shown):
    tab, _ = shown
    tab.ctx.store.merge_handle_only = True
    assert tab.handle_only()
    row = tab.rows[0]
    # Satır gövdesi: seçer ama sürüklemez.
    _fire(row._title_label, "<Button-1>", _mid(row))
    assert tab.drag_idx is None and tab.selected_idx == 0
    _fire(row._title_label, "<B1-Motion>", _gap_before(tab, 5))
    assert not tab._dragged
    _fire(row._title_label, "<ButtonRelease-1>", _gap_before(tab, 5))
    assert _ids(tab)[:3] == [1, 2, 3]
    # Tutamak: sürükler.
    _fire(row._handle_label, "<Button-1>", _mid(row))
    assert tab.drag_idx == 0
    _fire(row._handle_label, "<B1-Motion>", _gap_before(tab, 5))
    _fire(row._handle_label, "<ButtonRelease-1>", _gap_before(tab, 5))
    assert _ids(tab)[:6] == [2, 3, 4, 5, 1, 6]


def test_handle_only_click_on_body_of_multiselected_row_still_collapses_selection(shown):
    tab, _ = shown
    tab.ctx.store.merge_handle_only = True
    tab.select_item(0)
    tab.select_item(1, ctrl=True)
    row = tab.rows[1]
    _fire(row._title_label, "<Button-1>", _mid(row))
    assert tab.selection() == [0, 1] and tab.drag_idx is None
    _fire(row._title_label, "<ButtonRelease-1>", _mid(row))
    assert tab.selection() == [1]
