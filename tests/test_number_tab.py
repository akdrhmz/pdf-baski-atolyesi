"""NumberTab tek başına: tüm uygulama olmadan, sahte bağlamla kurulup denenir (Adım 2.3)."""

from __future__ import annotations

from ui import qt_compat as ctk
import pytest

from tests.fake_context import FakeContext
from ui.tabs import BaseTab
from ui.tabs.number import NumberTab
from ui.theme import COLOR_OK, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY


@pytest.fixture(scope="module")
def root():
    window = ctk.CTk()
    window.withdraw()
    yield window
    try:
        window.destroy()
    except Exception:
        pass


@pytest.fixture()
def built(root):
    ctx = FakeContext()
    frame = ctk.CTkFrame(root)
    frame.put("v", fill="both", expand=True)  # yerleşmemiş widget odak alamaz
    tab = NumberTab("Sayfa Numaraları", ctx, frame)
    tab.ensure_built()
    ctx.calls.clear()  # kurulum çağrılarını ayrıca test ediyoruz
    yield tab, ctx
    frame.destroy()


def test_is_a_base_tab_and_exposes_all_declared_widgets(root):
    ctx = FakeContext()
    frame = ctk.CTkFrame(root)
    tab = NumberTab("Sayfa Numaraları", ctx, frame)
    assert isinstance(tab, BaseTab) and not tab.built
    tab.ensure_built()
    assert tab.built
    missing = [name for name in ("lbl_pnum_status", "seg_pos", "menu_format", "f_font_size", "f_start_page", "f_start_num", "f_num_bottom", "f_num_side", "lbl_side_hint", "entry_number_template", "entry_skip_pages", "chk_continuous") if not hasattr(tab, name)]
    assert missing == []
    frame.destroy()


def test_build_reports_state_to_the_shell_once(root):
    ctx = FakeContext()
    frame = ctk.CTkFrame(root)
    NumberTab("Sayfa Numaraları", ctx, frame).ensure_built()
    assert ctx.names().count("bind_wraplength") == 1, "yalnızca açıklama metni (durum artık rozet)"
    assert ctx.names().count("on_field_changed") == 1
    assert "enable_module" not in ctx.names(), "kurulum modülü kendiliğinden açmamalı"
    frame.destroy()


def test_defaults(built):
    tab, _ = built
    assert tab.menu_format.get() == "1, 2, 3"
    assert tab.f_font_size.entry.get() == "10"
    assert tab.f_start_page.entry.get() == "1" and tab.f_start_num.entry.get() == "1"
    assert tab.entry_number_template.get() == "" and tab.entry_skip_pages.get() == ""
    assert tab.chk_continuous.get() == 1


def test_change_while_module_off_enables_the_module(built):
    tab, ctx = built
    assert ctx.module_enabled("pnum") is False
    tab.on_changed()
    assert ctx.names() == ["enable_module"] and ctx.module_enabled("pnum") is True


def test_change_while_module_on_just_refreshes(built):
    tab, ctx = built
    ctx.modules["pnum"] = True
    tab.on_changed()
    assert ctx.names() == ["on_field_changed"]


def test_center_position_disables_side_margin_and_shows_hint(built):
    tab, ctx = built
    ctx.modules["pnum"] = True
    tab.seg_pos.set("Alt orta")
    tab.on_position_changed()
    assert tab.f_num_side.entry.cget("state") == "disabled"
    assert tab.f_num_side.label.cget("text_color") == COLOR_TEXT_SECONDARY
    assert tab.lbl_side_hint.cget("text") != ""
    assert ctx.names() == ["on_field_changed"]

    tab.seg_pos.set("Dış kenar (Tek sağ / Çift sol)")
    tab.on_position_changed()
    assert tab.f_num_side.entry.cget("state") == "normal"
    assert tab.f_num_side.label.cget("text_color") == COLOR_TEXT_PRIMARY
    assert tab.lbl_side_hint.cget("text") == ""


def test_show_active_updates_status_label(built):
    tab, _ = built
    tab.show_active(True)
    assert tab.lbl_pnum_status.cget("text").startswith("Etkin")
    assert tab.lbl_pnum_status.cget("text_color") == COLOR_OK
    tab.show_active(False)
    assert tab.lbl_pnum_status.cget("text").startswith("Devre dışı")
    assert tab.lbl_pnum_status.cget("text_color") == COLOR_TEXT_SECONDARY


def test_typing_in_template_or_skip_entry_notifies_the_shell(root, built):
    tab, ctx = built
    ctx.modules["pnum"] = True
    # CTkEntry olayları iç Tk girdisine bağlar; klavye olayı yalnızca odaklı girdiye gider.
    for entry in (tab.entry_skip_pages, tab.entry_number_template):
        inner = entry._entry
        root.deiconify()
        root.update()
        inner.focus_force()
        root.update()
        inner.event_generate("<KeyRelease>", when="now")
    assert ctx.names() == ["on_field_changed", "on_field_changed"]


def test_on_show_scrolls_to_top_via_base_default(built):
    tab, _ = built
    tab.on_show()  # kaydırılabilir çerçeve bulunur ve hata vermez
