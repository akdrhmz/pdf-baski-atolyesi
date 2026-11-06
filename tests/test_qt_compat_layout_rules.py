"""P3-15: açık yerleştirme (place/put) sözleşmesi; grid()/pack() sezgileri v2.6.11'de silindi."""
from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QSizePolicy  # noqa: E402

from ui import qt_compat as ctk  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _frame(parent=None):
    f = ctk.CTkFrame(parent, fg_color="transparent") if parent is not None else ctk.CTkFrame(None)
    return f


















def test_place_is_explicit_no_heuristics(app):
    from PySide6.QtCore import Qt
    root = _frame()
    child = _frame(root)
    child.lock_width(40)
    child.place(1, 2, align="w", margins=(12, 0, 0, 0))
    lay = root._ensure_layout("grid")
    assert lay.contentsMargins().left() == 12
    idx = lay.indexOf(child)
    r, c, rs, cs = lay.getItemPosition(idx)
    assert (r, c) == (1, 2)
    assert lay.itemAt(idx).alignment() & Qt.AlignmentFlag.AlignLeft
    assert child.width_locked  # place() sabit genişliğe dokunmaz
    assert child.grid_info()["row"] == 1


def test_place_does_not_invent_margins(app):
    root = _frame()
    child = _frame(root)
    child.place(0, 0)
    assert root._ensure_layout("grid").contentsMargins().isNull()


def test_number_tab_distance_table_has_explicit_indent():
    from ui.theme import SP_M
    from ui.tabs.number import NumberTab
    from tests.fake_context import FakeContext
    ctk_root = ctk.CTk()
    ctk_root.withdraw()
    frame = ctk.CTkFrame(ctk_root)
    frame.put("v", fill="both", expand=True)
    tab = NumberTab("Sayfa Numaraları", FakeContext(), frame)
    tab.ensure_built()
    lay = tab.f_start_page.master._ensure_layout("grid")
    assert lay.contentsMargins().left() == SP_M
    frame.destroy()
    ctk_root.destroy()


def test_place_valign_options(app):
    from PySide6.QtCore import Qt
    root = _frame()
    cases = {"n": Qt.AlignmentFlag.AlignTop, "s": Qt.AlignmentFlag.AlignBottom,
             "c": Qt.AlignmentFlag.AlignVCenter}
    lay = root._ensure_layout("grid")
    for i, (v, flag) in enumerate(cases.items()):
        child = _frame(root)
        child.place(i, 0, valign=v)
        assert lay.itemAt(lay.indexOf(child)).alignment() & flag
    fill = _frame(root)
    fill.place(9, 0, valign="fill")
    al = lay.itemAt(lay.indexOf(fill)).alignment()
    assert not (al & (Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignBottom
                      | Qt.AlignmentFlag.AlignVCenter))


def test_put_adds_in_order_without_heuristics(app):
    root = _frame()
    a, b = _frame(root), _frame(root)
    a.put("h")
    b.put("h")
    lay = root._ensure_layout("pack_h")
    assert lay.indexOf(a) < lay.indexOf(b)
    assert lay.contentsMargins().isNull()


def test_put_fill_expand_releases_lock_and_stretches(app):
    root = _frame()
    child = _frame(root)
    child.lock_width(40)
    child.put("h", fill="x", expand=True)
    lay = root._ensure_layout("pack_h")
    assert not child.width_locked
    assert child.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
    assert lay.stretch(lay.indexOf(child)) == 1


def test_put_locked_child_stays_fixed_and_margins_explicit(app):
    root = _frame()
    child = _frame(root)
    child.lock_width(3)
    child.put("h", margins=(0, 0, 8, 0))
    assert child.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Fixed
    assert root._ensure_layout("pack_h").contentsMargins().right() == 8


def test_place_records_equivalent_sticky_in_grid_info(app):
    root = _frame()
    child = _frame(root)
    child.place(0, 0, align="w", valign="n")
    assert child.grid_info()["sticky"] == "wn"


def test_grid_and_pack_heuristic_layers_are_gone(app):
    root = _frame()
    for name in ("grid", "pack", "grid_configure"):
        assert not hasattr(root, name)
    import ui.qt_compat as qc
    for name in ("_auto_margins", "_release_fixed_width", "_pad_pair"):
        assert not hasattr(qc, name)


def test_fieldrow_error_does_not_inflate_row_width(app):
    """Hata metni görününce satırın asgari/tercih genişliği büyümemeli (komşu itilmemeli)."""
    from ui.widgets import FieldRow
    root = _frame()
    row = FieldRow(root, "Alan", "10", unit="mm", width=40)
    row.place(0, 0, align="w")
    before = (row.minimumSizeHint().width(), row.sizeHint().width())
    row.set_error("Bu oldukça uzun bir hata mesajıdır ve satırı şişirmemelidir, sarılmalıdır")
    after = (row.minimumSizeHint().width(), row.sizeHint().width())
    assert after == before


def test_fieldrow_error_label_keeps_ignored_policy(app):
    from ui.widgets import FieldRow
    root = _frame()
    row = FieldRow(root, "Alan", "10")
    assert row.error_label.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Ignored
    assert row.error_label.minimumWidth() == 0


def test_place_expand_x_unlocks_and_expands(app):
    root = _frame()
    child = _frame(root)
    child.lock_width(30)
    child.place(0, 0, expand_x=True)
    assert not child.width_locked
    assert child.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding


# ---------------------------------------------------------------------------
# v2.6.20: ``QWidget.destroy()`` artık ``QtWidgetMixin.destroy()``'u gölgelemez
# ---------------------------------------------------------------------------
def test_widget_destroy_really_destroys_and_unregisters(app):
    """Satır/kart ``destroy()`` ile gerçekten yıkılır: çocuk listesinden ve yerleşimden çıkar."""
    root = ctk.CTk()
    host = ctk.CTkFrame(root)
    kids = [ctk.CTkFrame(host) for _ in range(3)]
    for index, kid in enumerate(kids):
        kid.place(index, 0)
    assert len(host.winfo_children()) == 3
    kids[1].destroy()
    assert kids[1] not in host.winfo_children()
    assert len(host.winfo_children()) == 2
    host.destroy()
    assert all(getattr(k, "_destroyed", False) for k in kids)
    root.destroy()


def test_widget_destroy_also_destroys_the_whole_subtree(app):
    root = ctk.CTk()
    outer = ctk.CTkFrame(root)
    inner = ctk.CTkFrame(outer)
    label = ctk.CTkLabel(inner, text="x")
    outer.destroy()
    assert getattr(inner, "_destroyed", False) and getattr(label, "_destroyed", False)
    root.destroy()


def test_top_level_windows_keep_qt_destroy(app):
    """Ana pencere ve diyalog Qt'nin kendi ``destroy()``'unu korur (yaşam döngüsü değişmedi)."""
    from PySide6.QtWidgets import QWidget
    assert ctk.QtMainWindow.destroy is QWidget.destroy
    assert ctk.QtToplevel.destroy is QWidget.destroy
    assert ctk.QtFrame.destroy is ctk.QtWidgetMixin.destroy
