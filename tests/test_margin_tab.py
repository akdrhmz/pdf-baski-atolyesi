"""Sayfa Düzeni sekmesinin alt/üst boşluk, taşma ve özel sayfa kuralları."""

from __future__ import annotations

import gc

from ui import qt_compat as ctk
import pytest

from core.gutter_engine import format_measure
from tests.fake_context import FakeContext
from ui.tabs import BaseTab
from ui.tabs.page_layout import PageLayoutTab, CHOICE_LABELS
from ui.theme import COLOR_ERROR, COLOR_OK, COLOR_TEXT_SECONDARY, MARGIN_PRESETS_MM
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


def _make(root, unit="mm"):
    ctx = FakeContext(unit=unit)
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


def _preset_buttons(row):
    return row._buttons[:len(MARGIN_PRESETS_MM)]


def test_is_a_base_tab_and_exposes_all_declared_widgets(root):
    ctx = FakeContext()
    frame = ctk.CTkFrame(root)
    tab = PageLayoutTab("Sayfa Düzeni", ctx, frame)
    assert isinstance(tab, BaseTab) and not tab.built
    tab.ensure_built()
    assert tab.built
    assert [name for name in ("switch_gutter", "switch_margin") if not hasattr(tab, name)] == []
    frame.destroy()


def test_defaults(built):
    tab, _ = built
    assert tab.f_bottom.entry.get() == "0" and tab.f_top.entry.get() == "0"
    assert tab.chk_pad4.get() == 0
    assert tab.rules() == []
    assert tab.lbl_margin_status.cget("text").startswith("Etkin")
    assert tab.overflow_choice() == plm.CHOICE_EXTEND


def test_pay_while_module_off_enables_the_module(built):
    tab, ctx = built
    tab.f_bottom.set_value("20")
    tab.on_margin_changed()
    assert ctx.names() == ["enable_module"] and ctx.calls[0][1] == ("margin",)
    assert ctx.module_enabled("margin") is True


def test_zero_pay_while_module_off_only_refreshes(built):
    tab, ctx = built
    tab.f_bottom.set_value("0")
    tab.on_margin_changed()
    assert ctx.names() == ["on_field_changed"] and ctx.module_enabled("margin") is False


def test_top_pay_alone_also_enables_the_module(built):
    tab, ctx = built
    tab.f_top.set_value("5")
    tab.on_margin_changed()
    assert ctx.names() == ["enable_module"]


def test_invalid_field_is_skipped_when_looking_for_pay(built):
    tab, ctx = built
    tab.f_bottom.set_value("abc")
    tab.f_top.set_value("12")
    tab.on_margin_changed()
    assert ctx.names() == ["enable_module"]
    ctx.calls.clear()
    ctx.modules["margin"] = False
    tab.f_top.set_value("0")
    tab.on_margin_changed()
    assert ctx.names() == ["on_field_changed"]


def test_change_while_module_on_just_refreshes(built):
    tab, ctx = built
    ctx.modules["margin"] = True
    tab.f_bottom.set_value("20")
    tab.on_margin_changed()
    assert ctx.names() == ["on_field_changed"]


def test_preset_button_writes_value_and_enables_module(built):
    tab, ctx = built
    tab.set_bottom(15.0)
    assert tab.f_bottom.get_mm() == 15.0
    assert ctx.names() == ["enable_module"] and ctx.module_enabled("margin")
    tab.set_top(25.0)
    assert tab.f_top.get_mm() == 25.0
    assert ctx.names() == ["enable_module", "on_field_changed"]


def test_reset_button_does_not_enable_the_module(built):
    tab, ctx = built
    tab.set_bottom(0.0)
    assert tab.f_bottom.get_mm() == 0.0
    assert ctx.names() == ["on_field_changed"] and not ctx.module_enabled("margin")


def test_preset_labels_follow_the_unit(root):
    tab, ctx, frame = _make(root, unit="cm")
    expected = ["+" + format_measure(v, "cm") for v in MARGIN_PRESETS_MM]
    for row in (tab._bottom_preset_row, tab._top_preset_row):
        assert [b.cget("text") for b in _preset_buttons(row)] == expected
    ctx.unit = "pt"
    tab.update_preset_labels()
    expected_pt = ["+" + format_measure(v, "pt") for v in MARGIN_PRESETS_MM]
    for row in (tab._bottom_preset_row, tab._top_preset_row):
        assert [b.cget("text") for b in _preset_buttons(row)] == expected_pt
    frame.destroy()


def test_show_active_updates_status_label(built):
    tab, _ = built
    tab.show_margin_active(True)
    assert tab.lbl_margin_status.cget("text").startswith("Etkin")
    assert tab.lbl_margin_status.cget("text_color") == COLOR_OK
    tab.show_margin_active(False)
    assert tab.lbl_margin_status.cget("text").startswith("Devre dışı")
    assert tab.lbl_margin_status.cget("text_color") == COLOR_TEXT_SECONDARY


def test_pad4_checkbox_notifies_the_shell(built):
    tab, ctx = built
    tab.chk_pad4.toggle()
    assert ctx.names() == ["on_field_changed"]


def test_rule_rows_map_to_both_engine_lists(built):
    tab, _ = built
    tab.set_rules([plm.SpecialRule("1", plm.MODE_NONE),
                   plm.SpecialRule("2", plm.MODE_GUTTER_ONLY),
                   plm.SpecialRule("3", plm.MODE_MARGIN_ONLY)])
    assert tab.rules() == [plm.SpecialRule("1", plm.MODE_NONE),
                           plm.SpecialRule("2", plm.MODE_GUTTER_ONLY),
                           plm.SpecialRule("3", plm.MODE_MARGIN_ONLY)]
    boxes, margins = plm.rules_to_excludes(tab.rules())
    assert boxes == "1, 3" and margins == "1-2"


def test_invalid_rule_is_reported_on_the_row(built):
    tab, _ = built
    row = tab.add_rule()
    row.entry.insert(0, "abc")
    problems = tab.check_rules()
    assert problems and problems[0][0] is row
    assert "Anlaşılamayan" in row.error_label.cget("text")
    assert row.entry.cget("border_color") == COLOR_ERROR


def test_overlapping_rules_show_a_warning(built):
    tab, _ = built
    tab.set_rules([plm.SpecialRule("4", plm.MODE_GUTTER_ONLY),
                   plm.SpecialRule("4", plm.MODE_MARGIN_ONLY)])
    assert "birden çok kuralda" in tab.lbl_rule_warning.cget("text")


def test_remove_rule_updates_rows_and_calls_shell(built):
    tab, ctx = built
    first = tab.add_rule()
    second = tab.add_rule()
    first.entry.insert(0, "1")
    second.entry.insert(0, "2")
    ctx.calls.clear()
    tab.remove_rule(first)
    assert tab._rule_rows == [second]
    assert tab.rules() == [plm.SpecialRule("2", plm.MODE_NONE)]
    assert "on_field_changed" in ctx.names()


def test_overflow_menu_sets_and_reads_the_choice(built):
    tab, ctx = built
    ctx.modules.update(gutter=True, margin=True)
    tab.f_width.set_mm(225.0)
    tab.f_odd_x.set_mm(15.0)
    tab.f_bottom.set_mm(10.0)
    for choice in (plm.CHOICE_SHRINK, plm.CHOICE_CLIP, plm.CHOICE_EXTEND):
        tab.set_overflow_choice(choice)
        assert tab.overflow_choice() == choice
        assert tab.menu_overflow.get() == CHOICE_LABELS[choice]
        text = tab.lbl_overflow_note.cget("text")
        assert text.startswith("Sayfa ") and text.endswith(".")
        assert {plm.CHOICE_EXTEND: "hiçbir şey kesilmez", plm.CHOICE_SHRINK: "küçülür",
                plm.CHOICE_CLIP: "%100 ölçekte"}[choice] in text


def test_unified_state_keeps_exact_and_legacy_pairs(built):
    tab, _ = built
    exact = plm.engine_to_choice("shrink", "fit")
    tab.set_unified_state(exact, [], ("shrink", "fit"))
    assert tab.overflow_choice() == plm.CHOICE_SHRINK
    assert tab.lbl_overflow_legacy.cget("text") == ""

    legacy = plm.engine_to_choice("shrink", "expand")
    tab.set_unified_state(legacy, [], ("shrink", "expand"))
    assert tab.overflow_choice() == plm.CHOICE_SHRINK
    assert tab.overflow_selection() == (plm.CHOICE_SHRINK, ("shrink", "expand"))
    assert "eski bir birleşim" in tab.lbl_overflow_legacy.cget("text")


def test_cover_rule_adds_gutter_only_rule(built):
    tab, _ = built
    row = tab.add_cover_rule()
    assert row.mode() == plm.MODE_GUTTER_ONLY
