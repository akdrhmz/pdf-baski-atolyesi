"""Sayfa Düzeni sekmesinin açık yerleştirmesi (P3-15, 8. parça, v2.6.8).

Sekme artık ``grid()``/``pack()`` sezgilerine bağlı değil: eskiden bu sezgilerle
*örtük* gelen boşluklar açıkça yazıldı, gizle/göster ``place_restore()`` ile yapılıyor.
"""

from __future__ import annotations

import pathlib
import re

import pytest

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QSizePolicy  # noqa: E402

import core.page_layout_model as plm  # noqa: E402
from ui import qt_compat as ctk  # noqa: E402
from ui.theme import SP_M, SP_S  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture()
def tab(qapp):
    from tests.fake_context import FakeContext
    from ui.tabs.page_layout import PageLayoutTab
    root = ctk.CTk()
    root.withdraw()
    frame = ctk.CTkFrame(root)
    frame.put("v", fill="both", expand=True)
    page = PageLayoutTab("Sayfa Düzeni", FakeContext(), frame)
    page.ensure_built()
    yield page
    frame.destroy()
    root.destroy()


def _grid_margins(widget):
    return widget._ensure_layout("grid").contentsMargins()


def _hbox_margins(widget):
    return widget._ensure_layout("pack_h").contentsMargins()


def test_tabs_and_shared_widgets_have_no_grid_or_pack_calls():
    """Sekmeler ve ortak bileşenler yalnızca place()/put() kullanır."""
    pattern = re.compile(r"\.(grid|pack)\(")
    offenders = {}
    files = list((ROOT / "ui" / "tabs").glob("*.py")) + [ROOT / "ui" / "widgets.py"]
    for path in files:
        hits = [i for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
                if pattern.search(line)]
        if hits:
            offenders[path.name] = hits
    assert not offenders, offenders


def test_offset_table_has_explicit_left_indent(tab):
    assert _grid_margins(tab.f_odd_x.master).left() == SP_M


def test_paper_cell_and_target_line_have_explicit_right_margin(tab):
    # v2.6.19: kağıt satırı da sarılan ``WrapButtonRow``; boşluk satırın ``gap`` değeridir.
    assert tab.paper_menu.master is tab.paper_line
    assert tab.paper_line._gap == SP_S
    # v2.6.12 (P2-33): hedef ebat satırı sarılan ``WrapButtonRow``; ögeler arası boşluk
    # artık yatay kutunun sağ kenar boşluğu değil, satırın ``gap`` değeridir.
    assert tab.f_width.master is tab.target_line
    assert tab.target_line._gap == SP_S


def test_no_other_implicit_margins_in_size_and_margin_rows(tab):
    # Alt/üst boşluk satırları ve Ebat modu hücresi eskiden de kenar boşluğu almıyordu.
    assert _hbox_margins(tab.f_bottom.master).isNull()
    assert _hbox_margins(tab.f_top.master).isNull()
    assert _hbox_margins(tab.seg_size_mode.master).isNull()


def test_legacy_note_hide_and_restore_keep_cell(tab):
    note = tab.lbl_overflow_legacy
    cell = note._grid_meta["row"], note._grid_meta["column"]
    assert tab.lbl_overflow_legacy.grid_info() == {}      # kurulumda gizli
    tab.set_unified_state(
        plm.OverflowState(choice=plm.CHOICE_SHRINK, exact=False), [],
        loaded_pair=("shrink", "expand"))
    assert note.grid_info() != {}
    assert (note.grid_info()["row"], note.grid_info()["column"]) == cell
    tab.on_overflow_changed()
    assert note.grid_info() == {}


def test_rule_error_label_hide_and_restore(tab):
    row = tab.add_rule()
    assert row.error_label.grid_info() == {}
    row.entry.insert(0, "1, x9")
    tab.check_rules()
    assert row.error_label.grid_info() != {}
    assert row.error_label.isVisibleTo(row.frame)
    row.entry.delete(0, "end")
    tab.check_rules()
    assert row.error_label.grid_info() == {}


def test_rule_overlap_warning_hide_and_restore(tab):
    tab.set_rules([])
    assert tab.lbl_rule_warning.grid_info() == {}
    tab.add_cover_rule().entry.insert(0, "1")
    tab.add_rule().entry.insert(0, "1")
    tab.on_rules_changed()
    assert tab.lbl_rule_warning.grid_info() != {}
    tab.set_rules([])
    assert tab.lbl_rule_warning.grid_info() == {}


def test_rule_rows_stay_in_order_after_remove(tab):
    tab.set_rules([])
    rows = [tab.add_rule() for _ in range(3)]
    tab.remove_rule(rows[1])
    assert [r.frame.grid_info()["row"] for r in tab._rule_rows] == [0, 1]
    assert tab._rule_rows == [rows[0], rows[2]]


def test_every_rule_can_be_removed_including_the_last_one(tab):
    """v2.6.16: kural ekleyip vazgeçmek; hiçbir satır kaldırılamaz kalmaz."""
    tab.set_rules([])
    rows = [tab.add_rule() for _ in range(3)]
    for row in rows:
        tab.remove_rule(row)
    assert tab._rule_rows == []
    assert tab._rule_host.winfo_children() == []
    only = tab.add_cover_rule()
    only.remove_button.invoke()
    assert tab._rule_rows == []


def test_remove_rule_by_button_removes_exactly_that_row(tab):
    tab.set_rules([])
    rows = [tab.add_rule() for _ in range(3)]
    rows[0].remove_button.invoke()
    assert tab._rule_rows == [rows[1], rows[2]]
    rows[2].remove_button.invoke()
    assert tab._rule_rows == [rows[1]]
    rows[1].remove_button.invoke()
    assert tab._rule_rows == []


def test_rule_rows_keep_spacing_after_add_and_remove(tab):
    tab.set_rules([])
    rows = [tab.add_rule() for _ in range(3)]
    tab.remove_rule(rows[0])
    layout = tab._rule_host._ensure_layout("grid")
    assert layout.spacing() == SP_S
    assert [r.frame.grid_info()["row"] for r in tab._rule_rows] == [0, 1]


def test_rule_row_widgets_fill_and_stay_fixed_as_before(tab):
    row = tab.add_rule()
    assert row.error_label.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
    assert row.mode_menu.width_locked                    # 220 px sabit; hizası sola
    assert row.mode_menu.grid_info()["sticky"] == "w"
    assert row.remove_button.width_locked


def test_place_restore_shows_hidden_widget_in_same_cell(qapp):
    root = ctk.CTkFrame(None)
    child = ctk.CTkFrame(root)
    child.place(2, 1, align="w")
    child.grid_remove()
    assert child.grid_info() == {}
    child.place_restore()
    info = child.grid_info()
    assert (info["row"], info["column"], info["sticky"]) == (2, 1, "w")


# --- v2.6.16/17: form satırı boşlukları ve etiket hizası (saha ekran görüntüsü) ----
def test_form_grid_rows_are_separated_more_than_columns(tab):
    form = tab._row_target.master          # \"Hedef ebat\" satırının form ızgarası
    layout = form._ensure_layout("grid")
    assert layout.verticalSpacing() == SP_M
    assert layout.horizontalSpacing() == SP_S


def test_stack_row_label_is_centered_on_first_line(tab):
    from ui.theme import STACK_LABEL_TOP
    label = tab._row_target.row_label
    assert label.contentsMargins().top() == STACK_LABEL_TOP


def test_production_code_does_not_use_layout_bridge_aliases():
    """P3-16 (2. parça, v2.6.17): üretim kodu alanlara köprü takma adıyla erişmez."""
    names = ("f_width", "f_height", "f_safe_edge", "f_odd_x", "f_odd_y", "f_even_x",
             "f_even_y", "f_bottom", "f_top", "chk_pad4", "seg_size_mode")
    for rel in ("ui/document.py", "ui/pipeline.py", "ui/config_binding.py"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        code = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith(("#", '"""')))
        for name in names:
            assert not re.search(rf"\bself\.{name}\b", code), (rel, name)


def test_production_code_does_not_use_number_or_merge_bridge_aliases():
    """P3-16 (4. parça, v2.6.20): Numara/Birleştirme alanlarına ``self.<ad>`` ile erişilmez."""
    names = ("lbl_pnum_status", "seg_pos", "menu_format", "f_font_size", "f_start_page",
             "f_start_num", "f_num_bottom", "f_num_side", "lbl_side_hint",
             "entry_number_template", "entry_skip_pages", "chk_continuous",
             "merge_list_frame", "merge_summary_badge", "chk_merge_apply_pipeline",
             "chk_merge_bookmarks")
    offenders = []
    for path in list((ROOT / "ui").glob("*.py")) + [ROOT / "app.py"]:
        text = path.read_text(encoding="utf-8")
        code = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith(("#", '"""')))
        for name in names:
            if re.search(rf"\bself\.{name}\b", code):
                offenders.append((path.name, name))
    assert not offenders, offenders

