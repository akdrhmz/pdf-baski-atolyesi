"""MarginTab tek başına: tüm uygulama olmadan, sahte bağlamla kurulup denenir (Adım 2.4)."""

from __future__ import annotations

import gc

from ui import qt_compat as ctk
import pytest

from gutter_engine import format_measure
from tests.fake_context import FakeContext
from ui.tabs import BaseTab
from ui.tabs.margin import MarginTab
from ui.theme import COLOR_ERROR, COLOR_OK, COLOR_TEXT_SECONDARY, MARGIN_PRESETS_MM, MODE_LABELS


@pytest.fixture(scope="module")
def root():
    window = ctk.CTk()
    window.withdraw()
    yield window
    try:
        window.destroy()
    except Exception:
        pass
    # Yok edilen köke bağlı widget nesneleri, sonraki modülün çalışan iş parçacıklarında
    # (birleştirme işçisi) toplanıp Tk'ya dokunmasın diye burada, ana iş parçacığında toplanır.
    gc.collect()


def _make(root, unit="mm"):
    ctx = FakeContext(unit=unit)
    frame = ctk.CTkFrame(root)
    frame.pack(fill="both", expand=True)
    tab = MarginTab("Kenar Boşlukları", ctx, frame)
    tab.ensure_built()
    return tab, ctx, frame


@pytest.fixture()
def built(root):
    tab, ctx, frame = _make(root)
    ctx.calls.clear()  # kurulum çağrılarını ayrıca test ediyoruz
    yield tab, ctx
    frame.destroy()


def _preset_buttons(row):
    return row._buttons[:len(MARGIN_PRESETS_MM)]


def test_is_a_base_tab_and_exposes_all_declared_widgets(root):
    ctx = FakeContext()
    frame = ctk.CTkFrame(root)
    tab = MarginTab("Kenar Boşlukları", ctx, frame)
    assert isinstance(tab, BaseTab) and not tab.built
    tab.ensure_built()
    assert tab.built
    assert [name for name in MarginTab.EXPOSED if not hasattr(tab, name)] == []
    frame.destroy()


def test_build_reports_state_to_the_shell_once(root):
    tab, ctx, frame = _make(root)
    assert ctx.names().count("bind_wraplength") == 2, "durum etiketi + açıklama notu"
    assert ctx.names().count("on_field_changed") == 1
    assert "enable_module" not in ctx.names(), "kurulum modülü kendiliğinden açmamalı"
    frame.destroy()


def test_defaults(built):
    tab, _ = built
    assert tab.f_bottom.entry.get() == "0" and tab.f_top.entry.get() == "0"
    assert tab.entry_exclude_margin.get() == ""
    assert tab.chk_pad4.get() == 0
    assert tab.lbl_margin_status.cget("text").startswith("Devre dışı")


def test_pay_while_module_off_enables_the_module(built):
    tab, ctx = built
    tab.f_bottom.set_value("20")
    tab.on_changed()
    assert ctx.names() == ["enable_module"] and ctx.calls[0][1] == ("margin",)
    assert ctx.module_enabled("margin") is True


def test_zero_pay_while_module_off_only_refreshes(built):
    tab, ctx = built
    tab.f_bottom.set_value("0")
    tab.on_changed()
    assert ctx.names() == ["on_field_changed"] and ctx.module_enabled("margin") is False


def test_top_pay_alone_also_enables_the_module(built):
    tab, ctx = built
    tab.f_top.set_value("5")
    tab.on_changed()
    assert ctx.names() == ["enable_module"]


def test_invalid_field_is_skipped_when_looking_for_pay(built):
    tab, ctx = built
    tab.f_bottom.set_value("abc")
    tab.f_top.set_value("12")
    tab.on_changed()
    assert ctx.names() == ["enable_module"], "hatalı alan atlanır, geçerli üst pay sayılır"
    ctx.calls.clear()
    ctx.modules["margin"] = False
    tab.f_top.set_value("0")
    tab.on_changed()
    assert ctx.names() == ["on_field_changed"]


def test_change_while_module_on_just_refreshes(built):
    tab, ctx = built
    ctx.modules["margin"] = True
    tab.f_bottom.set_value("20")
    tab.on_changed()
    assert ctx.names() == ["on_field_changed"]


@pytest.mark.parametrize("label, text_part, color", [
    ("Kaydır (kırpabilir)", "Kaydır modu", COLOR_ERROR),
    ("Sığdır (orantılı küçült)", "Sığdır modu", COLOR_TEXT_SECONDARY),
    ("Uzat (kırpmaz, önerilen)", "Uzat modu", COLOR_TEXT_SECONDARY),
])
def test_mode_change_updates_warning_and_refreshes(built, label, text_part, color):
    tab, ctx = built
    assert label in MODE_LABELS, "test etiketi tablo ile uyumlu olmalı"
    tab.seg_bottom_mode.set(label)
    tab.on_mode_changed()
    assert text_part in tab.lbl_mode_warning.cget("text")
    assert tab.lbl_mode_warning.cget("text_color") == color
    assert ctx.names() == ["on_field_changed"]


def test_preset_button_writes_value_and_enables_module(built):
    tab, ctx = built
    tab.set_bottom(15.0)
    assert tab.f_bottom.get_mm() == 15.0
    assert ctx.names() == ["enable_module"] and ctx.module_enabled("margin")
    tab.set_top(25.0)
    assert tab.f_top.get_mm() == 25.0
    assert ctx.names() == ["enable_module", "on_field_changed"], "modül zaten açık: yalnızca yenile"


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
    assert expected_pt != expected
    for row in (tab._bottom_preset_row, tab._top_preset_row):
        assert [b.cget("text") for b in _preset_buttons(row)] == expected_pt
    frame.destroy()


def test_show_active_updates_status_label(built):
    tab, _ = built
    tab.show_active(True)
    assert tab.lbl_margin_status.cget("text").startswith("Etkin")
    assert tab.lbl_margin_status.cget("text_color") == COLOR_OK
    tab.show_active(False)
    assert tab.lbl_margin_status.cget("text").startswith("Devre dışı")
    assert tab.lbl_margin_status.cget("text_color") == COLOR_TEXT_SECONDARY


def test_pad4_checkbox_and_exclude_entry_notify_the_shell(root, built):
    tab, ctx = built
    tab.chk_pad4.toggle()
    assert ctx.names() == ["on_field_changed"]
    ctx.calls.clear()
    inner = tab.entry_exclude_margin._entry
    root.deiconify()
    root.update()
    inner.focus_force()
    root.update()
    inner.event_generate("<KeyRelease>", when="now")
    assert ctx.names() == ["on_field_changed"]


def test_on_show_scrolls_to_top_via_base_default(built):
    tab, _ = built
    tab.on_show()
