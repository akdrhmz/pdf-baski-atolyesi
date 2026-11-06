"""Birleştirme listesi: çoklu seçim, Ctrl+A, çoklu silme/döndürme, blok taşıma ve sürükleme."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tests.pdf_factory import create_sample_a4_pdf
from tests.test_merge_tab import _make, root  # noqa: F401  (fikstür ve yardımcılar)
from ui.theme import COLOR_CARD, COLOR_SOLID


@pytest.fixture()
def five(root, tmp_path):  # noqa: F811
    tab, ctx, frame = _make(root)
    tab.ensure_built()
    for index in range(1, 6):  # dosya i, i sayfa: sayfa sayısı kimlik gibi kullanılır
        path = str(tmp_path / f"f{index}.pdf")
        create_sample_a4_pdf(path, pages=index)
        tab.append_file(path)
    tab.refresh_list()
    ctx.calls.clear()
    yield tab, ctx
    frame.destroy()


def _ids(tab):
    return [item["pages"] for item in tab.files]


def _sel(tab):
    return [tab.files[i]["pages"] for i in tab.selection()]


def _fire(row, event_name, **fields):
    ev = SimpleNamespace(widget=row, x_root=0, y_root=fields.pop("y_root", 0),
                         ctrl=fields.pop("ctrl", False), shift=fields.pop("shift", False))
    for cb in row._bindings[event_name]:
        cb(ev)


def _highlighted(tab):
    return [i for i, row in enumerate(tab.rows)
            if row.cget("fg_color") == COLOR_SOLID]


def test_plain_click_is_single_selection(five):
    tab, _ = five
    tab.select_item(1)
    tab.select_item(3)
    assert tab.selection() == [3] and tab.selected_idx == 3
    assert _highlighted(tab) == [3]


def test_ctrl_click_adds_and_removes(five):
    tab, _ = five
    tab.select_item(0)
    tab.select_item(2, ctrl=True)
    tab.select_item(4, ctrl=True)
    assert tab.selection() == [0, 2, 4] and tab.selected_idx == 4
    assert _highlighted(tab) == [0, 2, 4]
    tab.select_item(2, ctrl=True)  # çıkar
    assert tab.selection() == [0, 4]
    tab.select_item(4, ctrl=True)
    tab.select_item(0, ctrl=True)
    assert tab.selection() == [] and tab.selected_idx is None


def test_shift_click_selects_range_from_anchor(five):
    tab, _ = five
    tab.select_item(1)
    tab.select_item(3, shift=True)
    assert tab.selection() == [1, 2, 3] and tab.selected_idx == 3
    tab.select_item(0, shift=True)  # çapa 1'de kalır
    assert tab.selection() == [0, 1]


def test_select_all_and_summary_count(five):
    tab, ctx = five
    tab.select_item(2)
    tab.select_all()
    assert tab.selection() == [0, 1, 2, 3, 4] and tab.selected_idx == 2
    assert "5 seçili" in tab.merge_summary_badge.cget("text")
    assert "schedule_preview" in [c[0] if isinstance(c, tuple) else c for c in ctx.calls] or ctx.calls
    tab.select_item(1)
    assert "seçili" not in tab.merge_summary_badge.cget("text")


def test_select_all_on_empty_list_is_noop(root):  # noqa: F811
    tab, _ctx, frame = _make(root)
    tab.ensure_built()
    tab.select_all()
    assert tab.selection() == [] and tab.selected_idx is None
    frame.destroy()


def test_remove_selected_removes_all_selected(five):
    tab, _ = five
    tab.select_item(0)
    tab.select_item(2, ctrl=True)
    tab.select_item(3, ctrl=True)
    tab.remove_selected()
    assert _ids(tab) == [2, 5] and tab.selection() == [] and len(tab.rows) == 2


def test_remove_after_select_all_empties_list(five):
    tab, _ = five
    tab.select_all()
    tab.remove_selected()
    assert tab.files == [] and tab.rows == []


def test_rotate_applies_to_every_selected(five):
    tab, _ = five
    tab.select_item(0)
    tab.select_item(2, ctrl=True)
    tab.rotate_selected(90)
    assert [item["rotation"] for item in tab.files] == [90, 0, 90, 0, 0]


def test_rotate_without_selection_warns(five):
    tab, ctx = five
    tab.selected_idx = None
    tab.rotate_selected(90)
    assert all(item["rotation"] == 0 for item in tab.files)


def test_move_block_up_keeps_relative_order_and_selection(five):
    tab, _ = five
    tab.select_item(2)
    tab.select_item(3, ctrl=True)   # 3. ve 4. dosya (sayfa 3, 4)
    tab.move_up()
    assert _ids(tab) == [1, 3, 4, 2, 5]
    assert _sel(tab) == [3, 4] and tab.selection() == [1, 2]
    assert tab.selected_idx == 2  # ana seçim da aynı dosyada kaldı
    assert [int(r._number_label.cget("text")) for r in tab.rows] == [1, 2, 3, 4, 5]


def test_move_block_down_with_gap(five):
    tab, _ = five
    tab.select_item(0)
    tab.select_item(2, ctrl=True)
    tab.move_down()
    assert _ids(tab) == [2, 1, 4, 3, 5]
    assert _sel(tab) == [1, 3] and tab.selection() == [1, 3]


def test_move_block_blocked_at_edges(five):
    tab, _ = five
    tab.select_item(0)
    tab.select_item(3, ctrl=True)
    tab.move_up()                       # biri en üstte: hiçbiri hareket etmez
    assert _ids(tab) == [1, 2, 3, 4, 5]
    tab.select_item(4, ctrl=True)
    tab.move_down()                     # biri en altta
    assert _ids(tab) == [1, 2, 3, 4, 5]


def test_single_selection_move_unchanged(five):
    tab, _ = five
    tab.selected_idx = 1
    tab.move_up()
    assert _ids(tab) == [2, 1, 3, 4, 5] and tab.selected_idx == 0
    tab.move_down()
    tab.move_down()
    assert _ids(tab) == [1, 3, 2, 4, 5] and tab.selected_idx == 2


def test_direct_selected_idx_assignment_clears_extras(five):
    tab, _ = five
    tab.select_all()
    tab.selected_idx = 3
    assert tab.selection() == [3]


def test_ctrl_press_on_row_toggles_without_drag(five):
    tab, _ = five
    _fire(tab.rows[0], "<Button-1>")
    _fire(tab.rows[0], "<ButtonRelease-1>")
    _fire(tab.rows[2], "<Button-1>", ctrl=True)
    assert tab.selection() == [0, 2] and tab.drag_idx is None
    _fire(tab.rows[4], "<Button-1>", shift=True)  # çapa: son Ctrl+tık (satır 2)
    assert tab.selection() == [2, 3, 4]


def test_press_release_on_selected_row_collapses_selection(five):
    tab, _ = five
    tab.select_item(0)
    tab.select_item(1, ctrl=True)
    _fire(tab.rows[1], "<Button-1>")          # çoklu seçimde sürüklemesiz tıklama
    assert tab.selection() == [0, 1]          # basarken seçim korunur
    _fire(tab.rows[1], "<ButtonRelease-1>")
    assert tab.selection() == [1]


def test_drag_moves_whole_block_on_release(five, monkeypatch):
    tab, _ = five
    tab.select_item(0)
    tab.select_item(1, ctrl=True)
    monkeypatch.setattr(tab, "slot_at", lambda y: 4)  # fare 4. ile 5. satır arasına gelir
    _fire(tab.rows[1], "<Button-1>", y_root=100)
    assert tab.drag_idx == 1
    _fire(tab.rows[1], "<B1-Motion>", y_root=300)
    assert _ids(tab) == [1, 2, 3, 4, 5], "sürüklerken sıra değişmez; yalnız çizgi taşınır"
    assert tab._dragged and tab._drag_slot == 4
    _fire(tab.rows[1], "<ButtonRelease-1>", y_root=300)
    assert _ids(tab) == [3, 4, 1, 2, 5] and tab.selection() == [2, 3]
    assert tab.drag_idx is None and not tab._dragged
    assert [int(r._number_label.cget("text")) for r in tab.rows] == [1, 2, 3, 4, 5]


def test_rows_stay_in_sync_with_files_after_block_ops(five):
    tab, _ = five
    rows_before = list(tab.rows)
    tab.select_item(1)
    tab.select_item(2, ctrl=True)
    tab._move_block(1)
    tab.reorder_rows()
    assert tab.rows[2] is rows_before[1] and tab.rows[3] is rows_before[2]
    assert _highlighted(tab) == [2, 3]
    assert tab.rows[0].cget("fg_color") == COLOR_CARD


def test_worker_items_follow_new_order(five):
    tab, _ = five
    tab.select_item(4)
    tab.select_item(3, ctrl=True)
    tab.move_up()
    tab.move_up()
    names = [i["path"].replace("\\", "/").rsplit("/", 1)[-1] for i in tab.worker_items()]
    assert names == ["f1.pdf", "f4.pdf", "f5.pdf", "f2.pdf", "f3.pdf"]


def test_merge_list_margins_are_explicit(five):
    tab, _ctx = five
    m = tab.merge_list_frame._ensure_layout("grid").contentsMargins()
    assert (m.left(), m.top(), m.right(), m.bottom()) == (0, 10, 0, 10)
    r = tab.rows[0]._ensure_layout("grid").contentsMargins()
    assert (r.left(), r.top(), r.right(), r.bottom()) == (4, 5, 8, 5)


def test_merge_empty_list_keeps_same_margins(five):
    tab, _ctx = five
    tab.clear()
    m = tab.merge_list_frame._ensure_layout("grid").contentsMargins()
    assert (m.left(), m.top(), m.right(), m.bottom()) == (0, 10, 0, 10)
