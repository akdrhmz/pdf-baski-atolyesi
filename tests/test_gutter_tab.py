"""Sayfa Düzeni sekmesinin cilt payı bölümü: sahte bağlamla, pencere olmadan denenir."""

from __future__ import annotations

import gc

from ui import qt_compat as ctk
import pytest

from core.settings_store import PRESETS
from tests.fake_context import FakeContext
from ui.theme import COLOR_OK, COLOR_SELECTED, SIZE_MODE_CODES, SIZE_MODE_LABELS
from ui.tabs import BaseTab
from ui.tabs.page_layout import PageLayoutTab, CHOICE_LABELS
import core.page_layout_model as plm


@pytest.fixture(scope="module")
def root():
    window = ctk.CTk()
    window.withdraw()
    yield window
    try:
        window.destroy()
    except Exception:
        pass
    # Yok edilen köke bağlı widget nesneleri sonraki modülde Tk'ya dokunmasın.
    gc.collect()


def _make(root):
    ctx = FakeContext()
    frame = ctk.CTkFrame(root)
    frame.put("v", fill="both", expand=True)
    tab = PageLayoutTab("Sayfa Düzeni", ctx, frame)
    tab.ensure_built()
    return tab, ctx, frame


@pytest.fixture()
def built(root):
    tab, ctx, frame = _make(root)
    ctx.calls.clear()
    yield tab, ctx
    frame.destroy()


def test_is_a_base_tab_and_exposes_all_declared_widgets(root):
    ctx = FakeContext()
    frame = ctk.CTkFrame(root)
    tab = PageLayoutTab("Sayfa Düzeni", ctx, frame)
    assert isinstance(tab, BaseTab) and not tab.built
    tab.ensure_built()
    assert tab.built
    assert [name for name in ("switch_gutter", "switch_margin") if not hasattr(tab, name)] == []
    frame.destroy()


def test_build_reports_state_to_the_shell_once(root):
    tab, ctx, frame = _make(root)
    assert ctx.names().count("on_field_changed") == 1
    assert "enable_module" not in ctx.names() and "disable_module" not in ctx.names()
    frame.destroy()


def test_defaults(built):
    tab, _ = built
    assert tab.switch_gutter.get() == 1 and tab.switch_margin.get() == 1
    assert tab.f_width.entry.get() == "210" and tab.f_height.entry.get() == "297"
    assert tab.f_safe_edge.entry.get() == "0"
    for row in (tab.f_odd_x, tab.f_odd_y, tab.f_even_x, tab.f_even_y):
        assert row.entry.get() == "0"
    assert tab.rules() == []
    assert tab.lbl_gutter_status.cget("text").startswith("Etkin")
    assert tab.lbl_margin_status.cget("text").startswith("Etkin")
    assert tab.orientation_menu.get() == "Dikey"


def test_profile_and_quick_buttons_exist(built):
    tab, _ = built
    assert len(tab._preset_row._buttons) == len(PRESETS)
    assert len(tab._gutter_preset_row._buttons) == 4


def test_preset_buttons_leave_room_for_their_text(built):
    tab, _ = built
    for button in tab._preset_row._buttons + tab._gutter_preset_row._buttons:
        needed = button.fontMetrics().horizontalAdvance(button.text()) + 10
        assert button.sizeHint().width() >= needed


def test_size_source_row_only_appears_for_mixed_documents(built):
    tab, ctx = built
    assert tab._size_source_row.isHidden()
    ctx.mixed_sizes = True
    tab.sync_size_source()
    assert not tab._size_source_row.isHidden()
    tab._on_size_source_changed("En büyük sayfa")
    assert ctx.calls[-1] == ("set_page_size_policy", ("largest",))


def test_profile_button_hands_the_preset_to_the_shell(built):
    tab, ctx = built
    name = next(iter(PRESETS))
    tab._preset_row._buttons[0].invoke()
    assert ctx.calls == [("apply_named_preset", (name,))]


def test_quick_gutter_buttons_apply_the_preset(built):
    tab, ctx = built
    tab._gutter_preset_row._buttons[1].invoke()  # 15 mm
    assert tab.f_width.get_mm() == 225.0 and tab.f_height.get_mm() == 297.0
    assert tab.f_odd_x.get_mm() == 15.0
    assert tab.f_odd_y.get_mm() == tab.f_even_x.get_mm() == tab.f_even_y.get_mm() == 0.0
    assert ctx.names() == ["enable_module"] and ctx.module_enabled("gutter")


def test_preset_uses_the_source_size_from_the_shell(built):
    tab, ctx = built
    ctx.orig_width_mm, ctx.orig_height_mm = 148.0, 210.0
    tab.apply_preset(10.0)
    assert tab.f_width.get_mm() == 158.0 and tab.f_height.get_mm() == 210.0


def test_preset_enables_the_module_even_when_already_on(built):
    tab, ctx = built
    ctx.modules["gutter"] = True
    tab.apply_preset(20.0)
    assert ctx.names() == ["enable_module"]


def test_quick_reset_zeroes_values_but_keeps_the_module_on(built):
    tab, ctx = built
    ctx.orig_width_mm, ctx.orig_height_mm = 200.0, 280.0
    tab.apply_preset(15.0)
    ctx.calls.clear()
    tab.reset_values()
    assert tab.f_width.get_mm() == 200.0 and tab.f_odd_x.get_mm() == 0.0
    assert "disable_module" not in ctx.names() and ctx.module_enabled("gutter")


def test_preset_keeps_the_selected_size_mode(built):
    tab, _ = built
    tab.seg_size_mode.set(SIZE_MODE_CODES["auto"])
    tab.apply_preset(10.0)
    assert SIZE_MODE_LABELS[tab.seg_size_mode.get()] == "auto"


def test_active_preset_button_is_highlighted(built):
    tab, _ = built
    tab.apply_preset(10.0)
    buttons = tab._gutter_preset_row._buttons
    assert [b.cget("fg_color") == COLOR_SELECTED for b in buttons[:3]] == [True, False, False]
    tab.apply_preset(20.0)
    assert [b.cget("fg_color") == COLOR_SELECTED for b in buttons[:3]] == [False, False, True]


def test_reset_restores_source_size_and_disables_the_module(built):
    tab, ctx = built
    tab.apply_preset(15.0)
    ctx.calls.clear()
    ctx.orig_width_mm, ctx.orig_height_mm = 200.0, 280.0
    tab.reset_to_original()
    assert tab.f_width.get_mm() == 200.0 and tab.f_height.get_mm() == 280.0
    for row in (tab.f_odd_x, tab.f_odd_y, tab.f_even_x, tab.f_even_y):
        assert row.get_mm() == 0.0
    assert ctx.names() == ["disable_module"] and not ctx.module_enabled("gutter")


def test_apply_paper_size_sets_dimensions_and_enables_module(built):
    from ui.theme import COLOR_TEXT_PRIMARY, PAPER_SIZES
    tab, ctx = built
    tab.paper_menu.set("A5 (148 × 210)")
    tab.orientation_menu.set("Yatay")
    tab.apply_paper_size()
    assert (tab.f_width.get_mm(), tab.f_height.get_mm()) == (210.0, 148.0)
    assert ctx.names() == ["enable_module", "set_status"]
    text, color = ctx.calls[1][1]
    assert text == "Kağıt boyutu 210 × 148 mm olarak ayarlandı."
    assert color == COLOR_TEXT_PRIMARY
    assert SIZE_MODE_LABELS[tab.seg_size_mode.get()] == "fixed"
    assert "A5 (148 × 210)" in PAPER_SIZES


def test_change_while_module_off_enables_it(built):
    tab, ctx = built
    tab.on_changed()
    assert ctx.names() == ["enable_module"] and ctx.module_enabled("gutter")


def test_change_while_module_on_just_refreshes(built):
    tab, ctx = built
    ctx.modules["gutter"] = True
    tab.on_changed()
    assert ctx.names() == ["on_field_changed"]


def test_safe_edge_is_enabled_only_for_fixed_size_with_shrink(built):
    tab, _ = built
    tab.seg_size_mode.set(SIZE_MODE_CODES["fixed"])
    for choice, state in ((plm.CHOICE_CLIP, "disabled"), (plm.CHOICE_SHRINK, "normal")):
        tab.set_overflow_choice(choice)
        assert tab.f_safe_edge.entry.cget("state") == state
    tab.seg_size_mode.set(SIZE_MODE_CODES["auto"])
    tab.set_overflow_choice(plm.CHOICE_SHRINK)
    assert tab.f_safe_edge.entry.cget("state") == "disabled"


def test_show_active_updates_status_label(built):
    tab, _ = built
    tab.show_active(False)
    assert tab.lbl_gutter_status.cget("text").startswith("Devre dışı")
    tab.show_active(True)
    assert tab.lbl_gutter_status.cget("text").startswith("Etkin")
    assert tab.lbl_gutter_status.cget("text_color") == COLOR_OK


def test_auto_size_mode_hides_unused_target_rows(built):
    """P2-36: kaynak ebat modunda hedef ebat / hazır kağıt / güvenli kenar satırları GİZLİ."""
    tab, ctx = built
    tab.seg_size_mode.set(SIZE_MODE_CODES["auto"])
    tab.update_safe_edge_state()
    assert not tab.f_width.entry.isEnabled() and not tab.f_height.entry.isEnabled()
    for cell in (tab._row_paper, tab._row_target, tab._row_safe_edge):
        assert cell.grid_info() == {}
        assert cell.row_label.grid_info() == {}
    assert "kaynak sayfadan" in tab.lbl_size_note.cget("text")
    tab.seg_size_mode.set(SIZE_MODE_CODES["fixed"])
    tab.update_safe_edge_state()
    assert tab.f_width.entry.isEnabled()
    for cell in (tab._row_paper, tab._row_target, tab._row_overflow):
        assert cell.grid_info() != {}


def test_overflow_row_in_auto_mode_only_shows_when_margin_pay_is_active(built):
    """Ölçüm (madde 36): kaynak ebatta 'Taşarsa ne olsun' yalnız alt/üst boşlukla etkilidir."""
    tab, ctx = built
    tab.seg_size_mode.set(SIZE_MODE_CODES["auto"])
    ctx.modules["margin"] = False
    tab.update_safe_edge_state()
    assert tab._row_overflow.grid_info() == {}
    ctx.modules["margin"] = True
    tab.f_bottom.set_mm(10.0)
    tab.update_safe_edge_state()
    assert tab._row_overflow.grid_info() != {}
    tab.f_bottom.set_mm(0.0)
    tab.f_top.set_mm(0.0)
    tab.update_safe_edge_state()
    assert tab._row_overflow.grid_info() == {}


def test_safe_edge_row_is_hidden_unless_fixed_and_shrink(built):
    tab, _ = built
    tab.seg_size_mode.set(SIZE_MODE_CODES["fixed"])
    tab.set_overflow_choice(plm.CHOICE_CLIP)
    assert tab._row_safe_edge.grid_info() == {}
    tab.set_overflow_choice(plm.CHOICE_SHRINK)
    assert tab._row_safe_edge.grid_info() != {}


def test_unified_overflow_choice_round_trips(built):
    tab, _ = built
    tab.set_overflow_choice(plm.CHOICE_SHRINK)
    assert tab.overflow_choice() == plm.CHOICE_SHRINK
    assert tab.menu_overflow.get() == CHOICE_LABELS[plm.CHOICE_SHRINK]


def test_target_note_never_repeats_page_height(built):
    """v2.6.16: \"sayfa boyu 297 + 10 = 307 mm\" notu kaldırıldı (özet cümlesi zaten yazıyor)."""
    tab, ctx = built
    ctx.modules.update(gutter=True, margin=True)
    tab.seg_size_mode.set(SIZE_MODE_CODES["fixed"])
    tab.f_height.set_mm(297.0)
    tab.f_bottom.set_mm(10.0)
    tab.f_top.set_mm(0.0)
    for choice in (plm.CHOICE_EXTEND, plm.CHOICE_SHRINK, plm.CHOICE_CLIP):
        tab.set_overflow_choice(choice)
        assert tab.lbl_target_note.cget("text") == (
            "Cilt payı dahil; alt/üst boşluk sonuç yüksekliğine eklenir.")
    # sonuç cümlesi (Taşarsa ne olsun altında) sayfa boyunu yazmaya devam eder
    tab.set_overflow_choice(plm.CHOICE_EXTEND)
    assert "307" in tab.lbl_overflow_note.cget("text")