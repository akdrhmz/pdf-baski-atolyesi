"""GutterTab tek başına: tüm uygulama olmadan, sahte bağlamla kurulup denenir (Adım 2.5)."""

from __future__ import annotations

import gc

from ui import qt_compat as ctk
import pytest

from settings_store import PRESETS
from tests.fake_context import FakeContext
from ui.tabs import BaseTab
from ui.tabs.gutter import GutterTab
from ui.theme import (
    COLOR_OK, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY, OVERFLOW_LABELS, PAPER_SIZES,
    SIZE_MODE_LABELS,
)


@pytest.fixture(scope="module")
def root():
    window = ctk.CTk()
    window.withdraw()
    yield window
    try:
        window.destroy()
    except Exception:
        pass
    # Yok edilen köke bağlı widget nesneleri, sonraki modülün iş parçacıklarında toplanıp
    # Tk'ya dokunmasın diye burada, ana iş parçacığında toplanır.
    gc.collect()


def _make(root):
    ctx = FakeContext()
    frame = ctk.CTkFrame(root)
    frame.pack(fill="both", expand=True)
    tab = GutterTab("Cilt Payı", ctx, frame)
    tab.ensure_built()
    return tab, ctx, frame


@pytest.fixture()
def built(root):
    tab, ctx, frame = _make(root)
    ctx.calls.clear()  # kurulum çağrılarını ayrıca test ediyoruz
    yield tab, ctx
    frame.destroy()


def test_is_a_base_tab_and_exposes_all_declared_widgets(root):
    ctx = FakeContext()
    frame = ctk.CTkFrame(root)
    tab = GutterTab("Cilt Payı", ctx, frame)
    assert isinstance(tab, BaseTab) and not tab.built
    tab.ensure_built()
    assert tab.built
    assert [name for name in GutterTab.EXPOSED if not hasattr(tab, name)] == []
    frame.destroy()


def test_build_reports_state_to_the_shell_once(root):
    tab, ctx, frame = _make(root)
    assert ctx.names().count("bind_wraplength") == 1, "yalnızca durum etiketi"
    assert ctx.names().count("on_field_changed") == 1
    assert "enable_module" not in ctx.names() and "disable_module" not in ctx.names()
    frame.destroy()


def test_defaults(built):
    tab, _ = built
    assert tab.f_width.entry.get() == "210" and tab.f_height.entry.get() == "297"
    assert tab.f_safe_edge.entry.get() == "0"
    for row in (tab.f_odd_x, tab.f_odd_y, tab.f_even_x, tab.f_even_y):
        assert row.entry.get() == "0"
    assert tab.entry_exclude_pages.get() == ""
    assert tab.lbl_gutter_status.cget("text").startswith("Devre dışı")
    assert tab.paper_menu.get() == list(PAPER_SIZES)[0] and tab.orientation_menu.get() == "Dikey"


def test_profile_buttons_exist_for_every_preset(built):
    tab, _ = built
    assert len(tab._preset_row._buttons) == len(PRESETS)
    assert len(tab._gutter_preset_row._buttons) == 4


def test_profile_button_hands_the_preset_to_the_shell(built):
    tab, ctx = built
    name = next(iter(PRESETS))
    tab._preset_row._buttons[0].invoke()
    assert ctx.calls == [("apply_named_preset", (name,))]


def test_quick_gutter_buttons_apply_the_preset(built):
    tab, ctx = built
    tab._gutter_preset_row._buttons[1].invoke()  # 15 mm duplex (standart)
    assert tab.f_width.get_mm() == 225.0 and tab.f_height.get_mm() == 297.0
    assert tab.f_odd_x.get_mm() == 15.0
    assert tab.f_odd_y.get_mm() == tab.f_even_x.get_mm() == tab.f_even_y.get_mm() == 0.0
    assert SIZE_MODE_LABELS[tab.seg_size_mode.get()] == "fixed"
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
    assert ctx.names() == ["enable_module"], "kabuk durum etiketini ve özeti her zaman yeniler"


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


@pytest.mark.parametrize("paper, orientation, expected", [
    ("A5 (148 × 210)", "Dikey", (148.0, 210.0)),
    ("A5 (148 × 210)", "Yatay", (210.0, 148.0)),
])
def test_paper_size_sets_dimensions_enables_module_and_reports_status(built, paper, orientation, expected):
    tab, ctx = built
    tab.paper_menu.set(paper)
    tab.orientation_menu.set(orientation)
    tab.apply_paper_size()
    assert (tab.f_width.get_mm(), tab.f_height.get_mm()) == expected
    assert [n for n in ctx.names()] == ["enable_module", "set_status"]
    text, color = ctx.calls[1][1]
    assert text == f"Kağıt boyutu {expected[0]:g} × {expected[1]:g} mm olarak ayarlandı."
    assert color == COLOR_TEXT_PRIMARY
    assert SIZE_MODE_LABELS[tab.seg_size_mode.get()] == "fixed"


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
    tab, ctx = built
    fixed = next(k for k, v in SIZE_MODE_LABELS.items() if v == "fixed")
    auto = next(k for k, v in SIZE_MODE_LABELS.items() if v == "auto")
    shrink = next(k for k, v in OVERFLOW_LABELS.items() if v == "shrink")
    clip = next(k for k, v in OVERFLOW_LABELS.items() if v == "clip")
    cases = [(fixed, shrink, "normal"), (fixed, clip, "disabled"),
             (auto, shrink, "disabled"), (auto, clip, "disabled")]
    for size_mode, overflow, state in cases:
        tab.seg_size_mode.set(size_mode)
        tab.seg_overflow.set(overflow)
        tab.on_changed()
        assert tab.f_safe_edge.entry.cget("state") == state, (size_mode, overflow)


def test_show_active_updates_status_label(built):
    tab, _ = built
    tab.show_active(True)
    assert tab.lbl_gutter_status.cget("text").startswith("Etkin")
    assert tab.lbl_gutter_status.cget("text_color") == COLOR_OK
    tab.show_active(False)
    assert tab.lbl_gutter_status.cget("text").startswith("Devre dışı")
    assert tab.lbl_gutter_status.cget("text_color") == COLOR_TEXT_SECONDARY


def test_typing_in_exclude_entry_notifies_the_shell(root, built):
    tab, ctx = built
    inner = tab.entry_exclude_pages._entry
    root.deiconify()
    root.update()
    inner.focus_force()
    root.update()
    inner.event_generate("<KeyRelease>", when="now")
    assert ctx.names() == ["on_field_changed"]


def test_on_show_scrolls_to_top_via_base_default(built):
    tab, _ = built
    tab.on_show()
