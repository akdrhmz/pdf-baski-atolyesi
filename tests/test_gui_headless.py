"""
Arayüz testleri: varsayılanlar, tek ayar kaynağı, birim dönüşümü, doğrulama,
canlı önizleme, taşma denetimi ve ayar kalıcılığı.

Tk penceresi gerçek olarak kurulur; sanal ekran gerekmez.
"""

from __future__ import annotations

import gc
import json
import os
import subprocess
import sys
import textwrap

import time

from ui import qt_compat as ctk
import pytest
import pymupdf

from app import COLOR_CARD, COLOR_ON_ACCENT, ModernGutterApp
import core.page_layout_model as plm
from core.gutter_engine import config_from_dict, config_to_dict, mm_to_unit, pt_to_mm
from tests.pdf_factory import create_sample_a4_pdf

# "mbcs" kod sayfası yalnızca Windows'ta vardır (Linux'ta LookupError verir).
requires_mbcs = pytest.mark.skipif(
    sys.platform != "win32", reason="mbcs kodlaması yalnızca Windows'ta var")


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    folder = tmp_path_factory.mktemp("gui_session")
    application = ModernGutterApp(
        settings_path=folder / "settings.json",
        log_path=folder / "studio.log",
    )
    # 2.9 bekçisi: fresh_state eski takma adlara dokunup diğer sekmeleri kurmadan
    # hemen önce açılış durumunu ve kurulmamış _build_config çıktısını kaydet.
    application._startup_built_tabs = {name: tab.built for name, tab in application._tabs.items()}
    application._startup_config_unbuilt = config_to_dict(application._build_config(notify=False))
    application.update()
    yield application
    try:
        application.destroy()
    except Exception:
        pass
    gc.collect()
    time.sleep(0.2)


@pytest.fixture(autouse=True)
def fresh_state(app, request):
    """Her testten önce arayüzü bilinen, modülsüz başlangıç durumuna getirir."""
    assert app.winfo_exists(), "Uygulama penceresi kapanmış"
    assert app._closing is False, "Uygulama kapanış bayrağı erken açılmış"
    app._reset_gutter_to_original()
    app.switch_margin.deselect()
    app._layout_tab().f_bottom.set_mm(0.0)
    app._layout_tab().f_top.set_mm(0.0)
    app._toggle_margin_fields()
    app.switch_pnum.deselect()
    app._number_tab().f_start_page.set_value("1")
    app._number_tab().f_start_num.set_value("1")
    app._number_tab().f_num_bottom.set_mm(12.0)
    app._number_tab().f_num_side.set_mm(15.0)
    app._number_tab().entry_skip_pages.delete(0, "end")
    app._number_tab().chk_continuous.select()
    app._toggle_pnum_fields()
    layout_tab(app).set_rules([])
    app._merge_tab().chk_merge_apply_pipeline.deselect()
    app._merge_tab().chk_merge_bookmarks.select()
    app._output_quality = "print"
    app._flatten_annotations = True
    app._layout_tab().chk_pad4.deselect()
    app.merge_files.clear()
    app.selected_merge_idx = None
    app._refresh_merge_listbox()
    app.input_pdf_path = ""
    app.output_pdf_path = ""
    app.output_pdf_path = ""
    app.tabview.set("Sayfa Düzeni")
    app.unit = "mm"
    for row in app._all_field_rows():
        row.reset_unit("mm")
    layout = layout_tab(app)
    layout.menu_overflow.set(plm.OVERFLOW_CHOICES[plm.CHOICE_EXTEND][0])
    layout._loaded_pair = None
    app.store.data["unit"] = "mm"
    app.update()
    yield
    try:
        assert app.winfo_exists()
    except Exception:
        print(f"DESTROYED AFTER: {request.node.name}")


def wait_until(predicate, timeout: float = 12.0, pump=None) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pump is not None:
            pump()
        if predicate():
            return True
        time.sleep(0.05)
    return False


NUMBER_WIDGETS = (
    "lbl_pnum_status", "seg_pos", "menu_format", "f_font_size", "f_start_page", "f_start_num",
    "f_num_bottom", "f_num_side", "lbl_side_hint", "entry_number_template", "entry_skip_pages",
    "chk_continuous",
)
MERGE_WIDGETS = (
    "merge_list_frame", "merge_summary_badge", "chk_merge_apply_pipeline", "chk_merge_bookmarks",
)


def layout_tab(app):
    return app._tabs["Sayfa Düzeni"]


def set_overflow(app, choice: str) -> None:
    layout_tab(app).set_overflow_choice(choice)


def test_opt_in_defaults_and_shortcuts(app):
    assert app.switch_gutter.get() == 0
    assert app.switch_margin.get() == 0
    assert app.switch_pnum.get() == 0
    assert app.btn_main_action.cget("state") == "disabled"
    assert "PDF" in app.btn_main_action.cget("text")
    assert not app.btn_preflight.isVisible()
    assert app._number_tab().chk_continuous.get() == 1
    assert app._flatten_annotations is True
    assert app._output_quality == "print"
    assert app._merge_tab().chk_merge_apply_pipeline.get() == 0


def test_gutter_preset_builds_single_config(app):
    app._apply_gutter_preset(15.0)
    app.update()
    assert app.switch_gutter.get() == 1
    assert app._layout_tab().f_odd_x.get_value() == 15.0
    assert app._layout_tab().f_width.get_value() == 225.0
    assert "PDF" in app.btn_main_action.cget("text")

    config = app._build_config(notify=False)
    assert config is not None
    assert config.page_boxes.enabled
    assert config.page_boxes.odd_x_mm == pytest.approx(15.0)
    assert config.margins.enabled is False
    assert config.page_numbers.enabled is False

    app._reset_gutter_to_original()
    app.update()
    assert app.switch_gutter.get() == 0
    assert app.btn_main_action.cget("state") == "disabled"


def test_primary_action_requires_a_real_source_and_then_shows_preflight(app, tmp_path):
    app._apply_gutter_preset(15.0)
    app._update_pipeline_summary()
    assert app.btn_main_action.cget("state") == "disabled"
    assert "PDF" in app.btn_main_action.cget("text")
    source = create_sample_a4_pdf(str(tmp_path / "source.pdf"))
    app._load_file(source)
    assert app.btn_main_action.cget("state") == "normal"
    assert not app.btn_preflight.isHidden()


def test_merge_action_waits_until_two_files_are_queued(app):
    app.tabview.set("Birleştirme")
    merge = app._merge_tab()
    merge.files[:] = [dict(path="one.pdf", name="one.pdf", pages=1, size_mb=0.1,
                           rotation=0, page_range="")]
    app._update_pipeline_summary()
    assert app.btn_main_action.cget("state") == "disabled"
    assert "2 PDF" in app.btn_main_action.cget("text")
    merge.files.append(dict(path="two.pdf", name="two.pdf", pages=1, size_mb=0.1,
                            rotation=0, page_range=""))
    app._update_pipeline_summary()
    assert app.btn_main_action.cget("state") == "normal"
    assert not app.btn_preflight.isHidden()


def test_primary_action_requires_a_real_source_and_then_shows_preflight(app, tmp_path):
    app._apply_gutter_preset(15.0)
    app._update_pipeline_summary()
    assert app.btn_main_action.cget("state") == "disabled"
    assert "PDF" in app.btn_main_action.cget("text")
    source = create_sample_a4_pdf(str(tmp_path / "source.pdf"))
    app._load_file(source)
    assert app.btn_main_action.cget("state") == "normal"
    assert not app.btn_preflight.isHidden()


def test_unit_conversion_roundtrip(app):
    app._apply_gutter_preset(15.0)
    app.update()
    app._on_unit_changed("cm")
    app.update()
    assert app.unit == "cm"
    assert app._layout_tab().f_odd_x.get_value() == pytest.approx(1.5)
    assert app._layout_tab().f_width.get_value() == pytest.approx(22.5)

    config = app._build_config(notify=False)
    assert config.page_boxes.odd_x_mm == pytest.approx(15.0)
    assert config.page_boxes.target_width_mm == pytest.approx(225.0)

    app._on_unit_changed("pt")
    app.update()
    assert app._layout_tab().f_width.get_value() == pytest.approx(637.8, abs=0.05)

    app._on_unit_changed("mm")
    app.update()
    assert app._layout_tab().f_width.get_value() == pytest.approx(225.0, abs=1e-9)
    assert app._layout_tab().f_odd_x.get_value() == pytest.approx(15.0, abs=1e-9)


def test_field_validation_marks_entry(app):
    app._apply_gutter_preset(15.0)
    app.update()
    app._layout_tab().f_width.set_value("abc")
    config = app._build_config(notify=False)
    assert config is None
    assert app._layout_tab().f_width.error_label.cget("text")

    app._layout_tab().f_width.set_value("210")
    app.update()
    config = app._build_config(notify=False)
    assert config is not None


def test_load_file_keeps_modules_off_and_previews(app, tmp_path):
    sample = str(tmp_path / "sample.pdf")
    create_sample_a4_pdf(sample, pages=3)
    app._load_file(sample)
    app.update()
    assert app.switch_gutter.get() == 0
    assert app._layout_tab().f_width.get_value() == pytest.approx(210.0)
    assert "sample.pdf" in app.info_badge.cget("text")

    app._apply_gutter_preset(15.0)
    app.switch_pnum.select()
    app._toggle_pnum_fields()
    app._refresh_preview()
    assert wait_until(lambda: len(app._preview_images) == 2, pump=app.update)
    generation = app._preview_gen

    # Aynı ayarlarla yeniden çizim yapılmaz; sekme geçişi önizlemeyi titretmez.
    app._refresh_preview()
    app.update()
    assert app._preview_gen == generation
    app.tabview.set("Sayfa Düzeni")
    app._on_tab_changed()
    app.update()
    assert app._preview_gen == generation
    info = app.preview_info.cget("text")
    assert "225.0" in info
    assert "numara" in info


def test_no_horizontal_overflow_at_minimum_size(app):
    app.geometry("1060x700")
    app.update()
    window_right = app.winfo_rootx() + app.winfo_width()

    def walk(widget):
        for child in widget.winfo_children():
            if not child.winfo_ismapped():
                continue
            right = child.winfo_rootx() + child.winfo_width()
            assert right <= window_right + 3, (
                f"{child.winfo_class()} sağ kenarı pencereden taşıyor: {right} > {window_right}"
            )
            walk(child)

    for tab_name in ("Sayfa Düzeni", "Sayfa Numaraları", "Birleştirme"):
        app.tabview.set(tab_name)
        app.update()
        walk(app)


def test_theme_change_keeps_window_and_workspace_visible(app):
    """Tema değişimi pencereyi gizlemez; içerik görünür kalır."""
    app.state("normal")
    app.update()
    for choice in ("Koyu", "Açık"):
        app._on_theme_changed(choice)
        app.update()
        assert app.state() == "normal"
        assert app._workspace.winfo_ismapped()


def test_titlebar_color_never_hides_window(app, monkeypatch):
    """Eski CTk yolu pencereyi withdraw/deiconify ile gizliyordu; artık gizlenmemeli."""
    calls = []
    monkeypatch.setattr(ctk.QtMainWindow, "withdraw", lambda self, *a, **k: calls.append("withdraw"))
    monkeypatch.setattr(ctk.QtMainWindow, "deiconify", lambda self, *a, **k: calls.append("deiconify"))
    app._windows_set_titlebar_color("Dark")
    app._windows_set_titlebar_color("Light")
    assert calls == []


def test_module_bar_controls_all_modules(app):
    app.switch_gutter.select()
    app._toggle_gutter_fields()
    app.switch_margin.select()
    app._toggle_margin_fields()
    app.switch_pnum.select()
    app._toggle_pnum_fields()
    app.update()
    # Enabled processing still requires a real input document.
    assert app.btn_main_action.cget("state") == "disabled"

    app._disable_all_modules()
    app.update()
    assert app.switch_gutter.get() == 0
    assert app.switch_margin.get() == 0
    assert app.switch_pnum.get() == 0
    assert app.btn_main_action.cget("state") == "disabled"

    app.tabview.set("PDF Birleştirme")
    assert app.tabview.get() == "Birleştirme"
    assert "2 PDF" in app.btn_main_action.cget("text")


def test_about_dialog_fits_content(app):
    from ui import qt_compat as ctk
    app._show_about_dialog()
    app.update()
    dialogs = [w for w in app.winfo_children() if isinstance(w, ctk.CTkToplevel)]
    assert len(dialogs) == 1
    dialog = dialogs[0]
    try:
        assert dialog.winfo_width() >= dialog.winfo_reqwidth()
        assert dialog.winfo_height() >= dialog.winfo_reqheight()
    finally:
        dialog.grab_release()
        dialog.destroy()


def test_preview_cache_invalidates_when_file_changes(app, tmp_path):
    sample = str(tmp_path / "cache.pdf")
    create_sample_a4_pdf(sample, pages=2)
    app._load_file(sample)
    app._refresh_preview()
    assert wait_until(lambda: len(app._preview_images) == 2, pump=app.update)
    generation = app._preview_gen

    app._refresh_preview()
    app.update()
    assert app._preview_gen == generation  # aynı dosya + aynı ayar: yeniden çizilmez

    create_sample_a4_pdf(sample, pages=3)
    stat = os.stat(sample)
    os.utime(sample, ns=(stat.st_atime_ns + 1_000_000_000,
                         stat.st_mtime_ns + 1_000_000_000))
    app._refresh_preview()
    assert app._preview_gen == generation + 1


def test_preview_navigation_single_and_spread(app, tmp_path):
    """Çift sayfa: 1-2, 3-4, son sayfa tekse tek başına (5 sayfa: 1-2, 3-4, 5)."""
    sample = str(tmp_path / "nav.pdf")
    create_sample_a4_pdf(sample, pages=5)
    app._load_file(sample)
    app.preview_page = 0
    app.preview_mode_menu.set("Çift sayfa")
    app._on_preview_mode_changed("Çift sayfa")
    assert wait_until(lambda: len(app._preview_images) == 2, pump=app.update)
    assert "1–2 / 5" in app.preview_page_label.cget("text")

    app._preview_next()
    assert wait_until(lambda: app.preview_page == 2, pump=app.update)
    assert wait_until(lambda: len(app._preview_images) == 2, pump=app.update)
    assert "3–4 / 5" in app.preview_page_label.cget("text")

    app._preview_next()
    assert wait_until(lambda: app.preview_page == 4, pump=app.update)
    assert wait_until(lambda: len(app._preview_images) == 1, pump=app.update)
    assert "5 / 5" in app.preview_page_label.cget("text")
    assert app.preview_next_btn.cget("state") == "disabled"

    app.preview_mode_menu.set("Tek sayfa")
    app._on_preview_mode_changed("Tek sayfa")
    assert wait_until(lambda: len(app._preview_images) == 1, pump=app.update)
    assert "5 / 5" in app.preview_page_label.cget("text")
    assert not app._preview_slots[1][0].winfo_ismapped()

    app._preview_previous()
    assert wait_until(lambda: app.preview_page == 3, pump=app.update)
    assert "4 / 5" in app.preview_page_label.cget("text")

    app.preview_mode_menu.set("Çift sayfa")
    app._on_preview_mode_changed("Çift sayfa")
    assert wait_until(lambda: app._preview_slots[1][0].winfo_ismapped(), pump=app.update)


def test_preview_keyboard_navigation_skips_text_focus(app, tmp_path, monkeypatch):
    sample = str(tmp_path / "kbd.pdf")
    create_sample_a4_pdf(sample, pages=5)
    app._load_file(sample)
    app.update()
    app.preview_page = 0
    entry = app.preview_panel.preview_jump_entry
    monkeypatch.setattr(app, "focus_get", lambda: entry)
    assert app._on_preview_key(1) is None   # metin kutusu odakta: gezinme yok
    assert app.preview_page == 0
    monkeypatch.setattr(app, "focus_get", lambda: None)
    assert app._on_preview_key(1) == "break"
    assert app.preview_page == 2
    assert app._on_preview_key(-1) == "break"
    assert app.preview_page == 0


def test_toggle_all_modules_button(app):
    app._toggle_all_modules()
    app.update()
    assert (app.switch_gutter.get(), app.switch_margin.get(), app.switch_pnum.get()) == (1, 1, 1)

    app._toggle_all_modules()
    app.update()
    assert (app.switch_gutter.get(), app.switch_margin.get(), app.switch_pnum.get()) == (0, 0, 0)


def test_editing_values_auto_enables_related_module(app):
    app._layout_tab().f_odd_x.set_value("15")
    app._on_gutter_changed()
    assert app.switch_gutter.get() == 1

    app.switch_gutter.deselect()
    app._toggle_gutter_fields()
    app._layout_tab().f_bottom.set_value("0")
    app._on_margin_changed()
    assert app.switch_margin.get() == 0

    app._layout_tab().f_bottom.set_value("20")
    app._on_margin_changed()
    assert app.switch_margin.get() == 1

    app._number_tab().f_start_page.set_value("2")
    app._on_number_changed()
    assert app.switch_pnum.get() == 1


def test_center_position_disables_side_margin_without_shifting(app):
    app.switch_pnum.select()
    app._toggle_pnum_fields()
    app._number_tab().seg_pos.set("Alt orta")
    app._on_number_position_changed()
    app.update()
    assert app._number_tab().f_num_side.entry.cget("state") == "disabled"
    assert app._number_tab().f_num_side.label.cget("text") == "Yan boşluk"
    x_center = app._number_tab().f_num_side.winfo_rootx()

    app._number_tab().seg_pos.set("Dış kenar (Tek sağ / Çift sol)")
    app._on_number_position_changed()
    app.update()
    assert app._number_tab().f_num_side.entry.cget("state") == "normal"
    # Yazı tipi ölçüleri platforma göre değişir: Windows'ta sıkı, Linux'ta (DejaVu/Tk
    # varsayılanı) piksel kayması daha geniş olabilir.
    tolerance = 8 if sys.platform == "win32" else 24
    assert abs(app._number_tab().f_num_side.winfo_rootx() - x_center) <= tolerance


def test_special_rules_build_config(app):
    app._apply_gutter_preset(15.0)
    tab = layout_tab(app)
    tab.set_rules([plm.SpecialRule("1, 3-4", plm.MODE_MARGIN_ONLY),
                   plm.SpecialRule("2", plm.MODE_GUTTER_ONLY)])
    app.update()
    config = app._build_config(notify=False)
    assert config is not None
    assert config.page_boxes.exclude_pages_str == "1, 3-4"
    assert config.margins.exclude_pages_str == "2"

    app._apply_config(config)
    assert [r.pages for r in tab.rules()] == ["2", "1, 3-4"]
    assert [r.mode for r in tab.rules()] == [plm.MODE_GUTTER_ONLY, plm.MODE_MARGIN_ONLY]


def test_overlapping_rules_reach_both_engine_lists(app):
    tab = layout_tab(app)
    tab.set_rules([plm.SpecialRule("4", plm.MODE_MARGIN_ONLY),
                   plm.SpecialRule("4, 6-7", plm.MODE_GUTTER_ONLY)])
    config = app._build_config(notify=False)
    assert config is not None
    assert config.page_boxes.exclude_pages_str == "4"
    assert config.margins.exclude_pages_str == "4, 6-7"
    assert "birden çok kuralda" in tab.lbl_rule_warning.cget("text")


def test_merge_list_reorder(app, tmp_path):
    for index in (1, 2, 3):
        path = str(tmp_path / f"parca{index}.pdf")
        create_sample_a4_pdf(path, pages=index)
        app._append_merge_file(path)
    app._refresh_merge_listbox()
    assert [item["pages"] for item in app.merge_files] == [1, 2, 3]

    app.selected_merge_idx = 0
    app._move_merge_file_down()
    assert [item["pages"] for item in app.merge_files] == [2, 1, 3]

    app.selected_merge_idx = 2
    app._rotate_selected_right()
    assert app.merge_files[2]["rotation"] == 90
    app._rotate_selected_left()
    assert app.merge_files[2]["rotation"] == 0

    app._remove_merge_file()
    assert len(app.merge_files) == 2
    app._clear_merge_files()
    assert app.merge_files == []


def test_merge_tab_action_label(app):
    app.tabview.set("PDF Birleştirme")
    app._on_tab_changed()
    app.update()
    assert "2 PDF" in app.btn_main_action.cget("text")

    app._merge_tab().chk_merge_apply_pipeline.select()
    app._update_pipeline_summary()
    app.update()
    assert "2 PDF" in app.btn_main_action.cget("text")


def test_paper_size_template(app):
    app._apply_gutter_preset(15.0)
    app._layout_tab().f_width.set_value("210")
    app._layout_tab().f_height.set_value("297")
    tab = layout_tab(app)
    tab.paper_menu.set("A5 (148 × 210)")
    tab.orientation_menu.set("Yatay")
    app._apply_paper_size()
    app.update()
    assert app._layout_tab().f_width.get_value() == pytest.approx(210.0)
    assert app._layout_tab().f_height.get_value() == pytest.approx(148.0)
    assert app._layout_tab().seg_size_mode.get() == "Hedef ebat sabit"


def test_settings_persist_between_sessions(tmp_path):
    settings_path = tmp_path / "settings.json"
    script = textwrap.dedent(
        """
        import json, os, sys
        sys.path.insert(0, os.environ["STUDIO_ROOT"])
        from app import ModernGutterApp

        mode = sys.argv[1]
        settings = sys.argv[2]
        app = ModernGutterApp(settings_path=settings, log_path=settings + ".log")
        app.update()
        if mode == "save":
            app._on_unit_changed("cm")
            app._apply_gutter_preset(20.0)
            app.theme_segmented.set("Koyu")
            app._on_theme_changed("Koyu")
            app.store.last_state = app._collect_state()
            app.store.save()
            print("SAVED")
        else:
            print(json.dumps({
                "unit": app.unit,
                "odd_x": app._layout_tab().f_odd_x.get_value(),
                "gutter": app.switch_gutter.get(),
                "theme": app.theme_segmented.get(),
            }))
        app.destroy()
        """
    )
    env = dict(os.environ)
    env["STUDIO_ROOT"] = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

    result = subprocess.run([sys.executable, "-c", script, "save", str(settings_path)],
                            env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    assert "SAVED" in result.stdout

    result = subprocess.run([sys.executable, "-c", script, "read", str(settings_path)],
                            env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload["unit"] == "cm"
    assert payload["odd_x"] == pytest.approx(2.0)
    assert payload["gutter"] == 1
    assert payload["theme"] == "Koyu"


def test_merge_drag_move_keeps_rows_synced(app, tmp_path):
    for index in (1, 2, 3):
        path = str(tmp_path / f"sira{index}.pdf")
        create_sample_a4_pdf(path, pages=index)
        app._append_merge_file(path)
    app._refresh_merge_listbox()
    assert [item["pages"] for item in app.merge_files] == [1, 2, 3]

    app._move_merge_item(0, 2)
    assert [item["pages"] for item in app.merge_files] == [2, 3, 1]
    assert [int(row._number_label.cget("text")) for row in app._merge_rows] == [1, 2, 3]
    assert app.selected_merge_idx == 2


def test_full_process_pipeline_from_ui(app, tmp_path, monkeypatch):
    source = str(tmp_path / "pipeline_ui.pdf")
    output = str(tmp_path / "pipeline_ui_out.pdf")
    create_sample_a4_pdf(source, pages=3)
    app._load_file(source)
    app._apply_gutter_preset(15.0)
    app.switch_margin.select()
    app._layout_tab().f_bottom.set_mm(20.0)
    app._toggle_margin_fields()
    app.switch_pnum.select()
    app._toggle_pnum_fields()
    app.update()

    config = app._build_config(notify=True)
    assert config is not None
    dialogs = []
    monkeypatch.setattr(app, "_show_text_dialog",
                        lambda *args, **kwargs: dialogs.append(args))
    monkeypatch.setattr(app, "_show_error_dialog",
                        lambda *args, **kwargs: dialogs.append(("HATA",) + args))

    app._work_config = config
    app._work_paths = (source, output)
    app.output_pdf_path = output
    app._begin_work("İşleniyor...")
    app._start_process_worker(scan_first=True)
    assert wait_until(lambda: bool(dialogs) and not app._busy, timeout=60, pump=app.update)

    assert os.path.exists(output)
    doc = pymupdf.open(output)
    assert len(doc) == 3
    assert abs(pt_to_mm(doc[0].rect.width) - 225.0) < 0.2
    assert abs(pt_to_mm(doc[0].rect.height) - 317.0) < 0.2
    assert "1" in doc[0].get_text()
    doc.close()
    body = dialogs[0][2]
    assert "Sayfa sayısı" in body
    assert "✔" in body
    assert not [name for name in os.listdir(os.path.dirname(output)) if name.startswith(".~")]


def test_full_merge_apply_pipeline_from_ui(app, tmp_path, monkeypatch):
    first = str(tmp_path / "merge_ui_1.pdf")
    second = str(tmp_path / "merge_ui_2.pdf")
    output = str(tmp_path / "merge_ui_out.pdf")
    create_sample_a4_pdf(first, pages=2)
    create_sample_a4_pdf(second, pages=2)
    app._append_merge_file(first)
    app._append_merge_file(second)
    app._refresh_merge_listbox()
    app._apply_gutter_preset(15.0)
    app.update()

    config = app._build_config(notify=True)
    assert config is not None
    dialogs = []
    monkeypatch.setattr(app, "_show_text_dialog",
                        lambda *args, **kwargs: dialogs.append(args))
    monkeypatch.setattr(app, "_show_error_dialog",
                        lambda *args, **kwargs: dialogs.append(("HATA",) + args))
    clips = []
    monkeypatch.setattr("app.messagebox.askyesno",
                        lambda title, message, **kw: (clips.append(message), True)[1])

    app._work_config = config
    app._work_paths = ("", output)
    app.output_pdf_path = output
    app._begin_work("Birleştiriliyor...")
    app._start_merge_worker(scan_first=True)
    finished = wait_until(lambda: bool(dialogs) and not app._busy, timeout=60, pump=app.update)
    assert finished, (app._busy, app.status_label.cget("text"), dialogs)

    assert os.path.exists(output)
    doc = pymupdf.open(output)
    assert len(doc) == 4
    assert abs(pt_to_mm(doc[0].rect.width) - 225.0) < 0.2
    doc.close()
    assert clips == [], clips
    assert not [name for name in os.listdir(os.path.dirname(output)) if name.startswith(".~")]

    assert mm_to_unit(25.4, "in") == pytest.approx(1.0)
    assert mm_to_unit(10.0, "cm") == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Sürükle-bırak
# ---------------------------------------------------------------------------
def test_dropped_paths_are_decoded_with_fallback_encodings(app):
    turkish = "C:/Belgeler/Örnek Çalışma.pdf"
    assert app._decode_dropped(turkish) == turkish
    assert app._decode_dropped(turkish.encode("utf-8")) == turkish
    assert app._decode_dropped(123) == "123"


@requires_mbcs
def test_dropped_paths_are_decoded_from_ansi_bytes(app):
    turkish = "C:/Belgeler/Örnek Çalışma.pdf"
    assert app._decode_dropped(turkish.encode("mbcs")) == turkish


def test_overflow_mode_builds_shrink_config(app):
    app._apply_gutter_preset(15.0)
    set_overflow(app, plm.CHOICE_SHRINK)
    app.update()
    config = app._build_config(notify=False)
    assert config is not None
    assert config.page_boxes.overflow_mode == "shrink"
    assert config.margins.bottom_mode == "fit"

    set_overflow(app, plm.CHOICE_CLIP)
    app.update()
    config = app._build_config(notify=False)
    assert config.page_boxes.overflow_mode == "clip"
    assert config.margins.bottom_mode == "shift"


def test_clip_dialog_shrink_switch_updates_config(app):
    app._apply_gutter_preset(15.0)
    assert app._switch_to_shrink() is True
    assert layout_tab(app).overflow_choice() == plm.CHOICE_SHRINK
    assert app._work_config.page_boxes.overflow_mode == "shrink"


def test_merge_preview_uses_selected_file(app, tmp_path):
    first = str(tmp_path / "onizleme_1.pdf")
    second = str(tmp_path / "onizleme_2.pdf")
    create_sample_a4_pdf(first, pages=2)
    create_sample_a4_pdf(second, pages=3)
    app.tabview.set("PDF Birleştirme")
    app._append_merge_file(first)
    app._append_merge_file(second)
    app._refresh_merge_listbox()
    app.update()

    app._select_merge_item(1)
    app.update()
    assert app._preview_source_path() == second

    app._select_merge_item(None)
    app.update()
    # Seçim kalkınca ana belgeye dönülür (bu testte ana belge yok).
    assert app._preview_source_path() == app.input_pdf_path


def test_merge_selection_keeps_rotation_badge_readable(app, tmp_path):
    path = str(tmp_path / "rozet.pdf")
    create_sample_a4_pdf(path, pages=2)
    app.tabview.set("PDF Birleştirme")
    app._append_merge_file(path)
    app._append_merge_file(path)  # aynı dosya ikinci kez eklenmez
    app._refresh_merge_listbox()
    app._select_merge_item(0)
    app.update()

    row = app._merge_rows[0]
    badge = None
    for child in row.winfo_children():
        if isinstance(child, ctk.CTkLabel) and "düz" in str(child.cget("text")):
            badge = child
            break
    assert badge is not None
    assert badge.cget("text_color") != COLOR_ON_ACCENT
    assert row._title_label.cget("text_color") == COLOR_ON_ACCENT


def test_rotation_without_selection_does_not_touch_all_files(app, tmp_path):
    path = str(tmp_path / "rotasyon.pdf")
    create_sample_a4_pdf(path, pages=2)
    app.tabview.set("PDF Birleştirme")
    app._append_merge_file(path)
    app._refresh_merge_listbox()
    app.selected_merge_idx = None
    app.update()

    app._rotate_selected(90)
    app.update()
    assert app.merge_files[0]["rotation"] == 0
    assert "dosya seçin" in app.status_label.cget("text")

    app._rotate_all(90)
    app.update()
    assert app.merge_files[0]["rotation"] == 90


def test_merge_list_shortcuts_move_and_delete(app, tmp_path):
    paths = []
    for index in (1, 2):
        path = str(tmp_path / f"kisayol_{index}.pdf")
        create_sample_a4_pdf(path, pages=index + 1)
        paths.append(path)
        app._append_merge_file(path)
    app.tabview.set("PDF Birleştirme")
    app._refresh_merge_listbox()
    app.selected_merge_idx = 1
    app.update()
    app._merge_rows[1].focus_set()
    app.update()
    assert app._list_shortcuts_active()

    app._on_merge_move(-1)
    app.update()
    assert [item["path"] for item in app.merge_files] == [paths[1], paths[0]]
    assert app.selected_merge_idx == 0

    app._on_merge_delete()
    app.update()
    assert [item["path"] for item in app.merge_files] == [paths[0]]
    assert app.selected_merge_idx is None


def test_drop_callback_only_queues_work(app, tmp_path):
    """Pencere yordamı içinde Tk'ye dokunulmaz; iş kuyruğa bırakılır."""
    path = str(tmp_path / "kuyruk.pdf")
    create_sample_a4_pdf(path, pages=2)
    app.input_pdf_path = ""
    app._on_drop_files([path])
    assert app.input_pdf_path != path
    assert wait_until(lambda: app.input_pdf_path == path, pump=app.update)


def test_drop_handler_opens_first_pdf_in_single_mode(app, tmp_path, monkeypatch):
    first = str(tmp_path / "bırakılan_1.pdf")
    second = str(tmp_path / "bırakılan_2.pdf")
    create_sample_a4_pdf(first, pages=2)
    create_sample_a4_pdf(second, pages=2)
    infos = []
    monkeypatch.setattr("app.messagebox.showinfo",
                        lambda title, message, **kw: infos.append((title, message)))
    monkeypatch.setattr("app.messagebox.showerror",
                        lambda *a, **kw: infos.append(("HATA", a)))

    ansi = "mbcs" if sys.platform == "win32" else "utf-8"
    app._handle_dropped_files([first.encode("utf-8"), second.encode(ansi)])
    app.update()
    assert app.input_pdf_path == first
    assert len(app.merge_files) == 0
    assert infos == []
    assert "ilki açıldı" in app.status_label.cget("text")


def test_drop_handler_adds_every_pdf_to_merge_list(app, tmp_path):
    first = str(tmp_path / "birlesik_1.pdf")
    second = str(tmp_path / "birlesik_2.pdf")
    create_sample_a4_pdf(first, pages=2)
    create_sample_a4_pdf(second, pages=3)
    app.tabview.set("PDF Birleştirme")
    app.update()

    app._handle_dropped_files([first, second, first])
    app.update()
    assert [item["path"] for item in app.merge_files] == [first, second]
    assert "2 PDF birleştirme listesine eklendi" in app.status_label.cget("text")


def test_drop_handler_ignores_non_pdf_items(app, monkeypatch):
    infos = []
    monkeypatch.setattr("app.messagebox.showinfo",
                        lambda title, message, **kw: infos.append((title, message)))
    app._handle_dropped_files([])
    app.update()
    assert len(infos) == 1
    assert "PDF dosyası yok" in infos[0][1]



def test_invalid_page_range_blocks_config_and_marks_entry(app, tmp_path):
    app._number_tab().entry_skip_pages.delete(0, "end")
    app._number_tab().entry_skip_pages.insert(0, "1-3, abc")
    assert app._check_range_entries()
    assert app._build_config(notify=False) is None
    app._number_tab().entry_skip_pages.delete(0, "end")
    app._number_tab().entry_skip_pages.insert(0, "1–3; 5")   # uzun tire ve ; kabul edilir
    assert app._check_range_entries() == []
    app._number_tab().entry_skip_pages.delete(0, "end")


def test_pending_merge_temp_is_discarded(app, tmp_path):
    temp = tmp_path / "bekleyen.pdf.tmp"
    temp.write_bytes(b"x")
    app._pending_merge = (str(temp), [])
    app._discard_pending_merge()
    assert not temp.exists() and app._pending_merge is None


# ---------------------------------------------------------------------------
# Birleştirme sekmesi: kabuk köprüsü ve birleştirme işi (Adım 2.6)
# ---------------------------------------------------------------------------
def test_merge_tab_bridge_shares_state_and_widgets_with_the_tab(app):
    tab = app._tabs["Birleştirme"]
    assert app.merge_files is tab.files
    assert app._merge_rows is tab.rows
    app.selected_merge_idx = 3
    assert tab.selected_idx == 3
    tab.selected_idx = None
    assert app.selected_merge_idx is None
    for name in MERGE_WIDGETS:
        assert hasattr(tab, name) and name not in app.__dict__


def test_merge_list_shortcuts_ignore_other_tabs_and_busy_state(app, tmp_path):
    path = str(tmp_path / "kisayol_pasif.pdf")
    create_sample_a4_pdf(path, pages=2)
    app._append_merge_file(path)
    app._refresh_merge_listbox()
    app.selected_merge_idx = 0
    app.tabview.set("Sayfa Düzeni")
    app.update()
    assert app._on_merge_delete() is None          # başka sekme: dokunmaz
    assert len(app.merge_files) == 1

    app.tabview.set("PDF Birleştirme")
    app.update()
    app._busy = True
    try:
        assert app._on_merge_delete() is None      # işlem sürerken: dokunmaz
        assert app._on_merge_move(1) is None
    finally:
        app._busy = False
    assert len(app.merge_files) == 1


def test_start_merging_validates_before_asking_for_a_path(app, tmp_path, monkeypatch):
    first = str(tmp_path / "dogrula_1.pdf")
    second = str(tmp_path / "dogrula_2.pdf")
    create_sample_a4_pdf(first, pages=2)
    create_sample_a4_pdf(second, pages=2)
    warnings, errors, dialogs = [], [], []
    monkeypatch.setattr("app.messagebox.showwarning", lambda t, m, **kw: warnings.append(m))
    monkeypatch.setattr("app.messagebox.showerror", lambda t, m, **kw: errors.append(m))
    monkeypatch.setattr("ui.merge_job.messagebox.showwarning", lambda t, m, **kw: warnings.append(m))
    monkeypatch.setattr("ui.merge_job.messagebox.showerror", lambda t, m, **kw: errors.append(m))
    monkeypatch.setattr("ui.merge_job.filedialog.asksaveasfilename",
                        lambda **kw: dialogs.append(kw) or "")

    app._append_merge_file(first)
    app._refresh_merge_listbox()
    app._start_merging()
    assert warnings and "en az 2 PDF" in warnings[-1] and not dialogs

    app._append_merge_file(second)
    app.merge_files[1]["page_range"] = "1-2, xyz"
    app._start_merging()
    assert errors and "dogrula_2.pdf: xyz" in errors[-1] and not dialogs
    assert not app._busy

    app.merge_files[1]["page_range"] = "1"
    app._start_merging()          # doğrulama geçti; kayıt penceresi iptal edildi
    assert len(dialogs) == 1 and not app._busy


def test_plain_merge_applies_rotation_and_page_range_from_the_tab(app, tmp_path, monkeypatch):
    first = str(tmp_path / "plain_1.pdf")
    second = str(tmp_path / "plain_2.pdf")
    output = str(tmp_path / "plain_out.pdf")
    create_sample_a4_pdf(first, pages=3)
    create_sample_a4_pdf(second, pages=2)
    app._append_merge_file(first)
    app._append_merge_file(second)
    app._refresh_merge_listbox()
    app.merge_files[0]["page_range"] = "1-2"
    app.merge_files[1]["rotation"] = 90
    dialogs = []
    monkeypatch.setattr(app, "_show_text_dialog", lambda *a, **kw: dialogs.append(a))
    monkeypatch.setattr(app, "_show_error_dialog", lambda *a, **kw: dialogs.append(("HATA",) + a))

    app._work_config = None
    app._work_paths = ("", output)
    app.output_pdf_path = output
    app._begin_work("Birleştiriliyor...")
    app._start_merge_worker(scan_first=True)
    assert wait_until(lambda: bool(dialogs) and not app._busy, timeout=60, pump=app.update), dialogs

    assert dialogs and dialogs[0][0] != "HATA", dialogs
    doc = pymupdf.open(output)
    assert len(doc) == 4
    assert [page.rotation for page in doc] == [0, 0, 90, 90]
    doc.close()


# ---------------------------------------------------------------------------
# Adım 2.7: önizleme paneli kabuk bağlantıları
# ---------------------------------------------------------------------------
def test_preview_bridge_shares_state_and_widgets_with_the_panel(app):
    panel = app.preview_panel
    app.preview_page = 3
    assert panel.page == 3
    panel.page = 0
    assert app.preview_page == 0
    assert app._preview_history is panel.history and app._preview_images is panel.images
    assert app._preview_slots is panel.slots
    for name in ("preview_info", "preview_warning", "preview_page_label",
                 "preview_prev_btn", "preview_next_btn", "preview_mode_menu"):
        assert getattr(app, name) is getattr(panel, name)


def test_loading_a_file_resets_the_preview_state(app, tmp_path):
    path = str(tmp_path / "sifirla.pdf")
    create_sample_a4_pdf(path, pages=5)
    app.preview_page = 3
    generation = app.preview_panel.gen
    app._load_file(path)
    assert app.preview_page == 0
    assert app.preview_panel.gen > generation


def test_starting_work_invalidates_the_in_flight_preview(app):
    generation = app.preview_panel.gen
    app._begin_work("Deneme...")
    try:
        assert app.preview_panel.gen == generation + 1
    finally:
        app._end_work("Deneme bitti")
    assert app._busy is False


def test_theme_change_recolors_preview_labels(app):
    labels = [label for _slot, label, _caption in app.preview_panel.slots]
    try:
        app._on_theme_changed("Koyu")
        app.update()
        dark = app._apply_appearance_mode(COLOR_CARD)
        assert all(str(label.cget("bg")) == dark for label in labels)
        app._on_theme_changed("Açık")
        app.update()
        light = app._apply_appearance_mode(COLOR_CARD)
        assert light != dark
        assert all(str(label.cget("bg")) == light for label in labels)
    finally:
        app._on_theme_changed("Açık")


# ---------------------------------------------------------------------------
# Ölçüm (APP_PERF)
# ---------------------------------------------------------------------------
def test_perf_recorder_is_inert_when_disabled(app):
    assert app.perf.enabled is False
    with app.perf.measure("deneme"):
        pass
    app.perf.count("withdraw")
    assert app.perf.samples == {} and app.perf.counters == {}


def test_theme_change_never_hides_window_and_is_measured(app):
    app.perf.enabled = True
    app.perf.samples.clear()
    app.perf.counters.clear()
    app._on_theme_changed("Koyu")
    app.update()
    app._on_theme_changed("Açık")
    app.update()
    assert len(app.perf.samples["tema_degisimi"]) == 2
    assert app.perf.counters.get("withdraw", 0) == 0, "tema geçişi pencereyi gizlememeli"
    assert app.perf.widget_count(app) > 50


def test_theme_change_stays_within_time_budget(app):
    """Süre bütçesi: yavaş makinede yanlış alarm olmasın diye cömert (3 sn)."""
    app.perf.enabled = True
    app.perf.samples.clear()
    app._on_theme_changed("Koyu")
    app.update()
    app._on_theme_changed("Açık")
    app.update()
    assert max(app.perf.samples["tema_degisimi"]) < 3000.0


# ---------------------------------------------------------------------------
# Güvenli kenar (safe_edge_mm) ve önizleme belleği
# ---------------------------------------------------------------------------
def test_safe_edge_field_only_enabled_in_shrink_mode(app):
    app._layout_tab().seg_size_mode.set("Hedef ebat sabit")
    set_overflow(app, plm.CHOICE_CLIP)
    app._on_gutter_changed()
    app.update()
    assert app._layout_tab().f_safe_edge.entry.cget("state") == "disabled"
    set_overflow(app, plm.CHOICE_SHRINK)
    app._on_gutter_changed()
    app.update()
    assert app._layout_tab().f_safe_edge.entry.cget("state") == "normal"
    app._layout_tab().seg_size_mode.set("Kaynak ebat + cilt payı")
    app._on_gutter_changed()
    assert app._layout_tab().f_safe_edge.entry.cget("state") == "disabled"


def test_safe_edge_field_round_trips_through_config_and_unit_change(app):
    app._layout_tab().seg_size_mode.set("Hedef ebat sabit")
    set_overflow(app, plm.CHOICE_SHRINK)
    app._on_gutter_changed()
    app._layout_tab().f_safe_edge.set_mm(4.0)
    config = app._build_config(notify=False)
    assert config is not None and config.page_boxes.safe_edge_mm == pytest.approx(4.0)
    restored = config_from_dict(config_to_dict(config))
    assert restored.page_boxes.safe_edge_mm == pytest.approx(4.0)

    app._layout_tab().f_safe_edge.set_mm(0.0)
    app._apply_config(config)
    assert app._layout_tab().f_safe_edge.get_mm() == pytest.approx(4.0)
    assert app._layout_tab().f_safe_edge.entry.cget("state") == "normal"


def test_safe_edge_rejects_negative_value(app):
    set_overflow(app, plm.CHOICE_SHRINK)
    app._on_gutter_changed()
    app._layout_tab().f_safe_edge.entry.delete(0, "end")
    app._layout_tab().f_safe_edge.entry.insert(0, "-3")
    assert app._build_config(notify=False) is None


def test_preview_history_is_capped():
    from ui.preview import PREVIEW_HISTORY_LIMIT
    assert 6 <= PREVIEW_HISTORY_LIMIT <= 8


# ---------------------------------------------------------------------------
# Adım 2.2: BaseTab sözleşmesi ve AppContext pencereye bağlı çalışıyor
# ---------------------------------------------------------------------------

def test_tabs_are_registered_built_and_follow_contract(app):
    from ui.tabs import BaseTab
    from ui.window import TAB_NAMES
    assert list(app._tabs) == list(TAB_NAMES)
    for name, tab in app._tabs.items():
        tab.ensure_built()
        assert isinstance(tab, BaseTab) and tab.name == name
        assert tab.built, f"{name} sekmesi açılışta kurulmuş olmalı"
        assert tab.frame is app._tab_frames_map[name]


def test_select_tab_shows_only_the_selected_tab(app, monkeypatch):
    shown = []
    for name, tab in app._tabs.items():
        monkeypatch.setattr(tab, "on_show", lambda n=name: shown.append(n))
    app.select_tab("Sayfa Numaraları")
    assert shown == ["Sayfa Numaraları"]
    app.select_tab("Cilt Payı")  # eski ad: Sayfa Düzeni'ne eşlenir
    assert shown == ["Sayfa Numaraları", "Sayfa Düzeni"]
    assert app.current_tab == "Sayfa Düzeni"


def test_select_tab_builds_an_unbuilt_tab_before_raising_it(app):
    tab = app._tabs["Sayfa Numaraları"]
    original_built = tab._built
    order = []
    tab.build = lambda: order.append("build")  # örnek özniteliği: sınıf yöntemini gölgeler
    tab._built = False
    try:
        app.select_tab("Sayfa Numaraları")
        assert order == ["build"] and tab.built
        app.select_tab("Sayfa Düzeni")
        app.select_tab("Sayfa Numaraları")
        assert order == ["build"], "kurulu sekme yeniden kurulmamalı"
    finally:
        del tab.build
        tab._built = original_built
        app.select_tab("Sayfa Düzeni")


def test_theme_change_calls_apply_theme_on_every_tab_even_if_one_fails(app, monkeypatch):
    applied = []

    def boom():
        raise RuntimeError("tema düştü")

    names = list(app._tabs)
    for name in names:
        tab = app._tabs[name]
        if name == names[0]:
            monkeypatch.setattr(tab, "apply_theme", boom)
        else:
            monkeypatch.setattr(tab, "apply_theme", lambda n=name: applied.append(n))
    try:
        app._on_theme_changed("Koyu")
    finally:
        app._on_theme_changed("Açık")
    # İki tema değişimi (Koyu, Açık): hatalı ilk sekme dışındakiler her seferinde çağrılır.
    assert applied == names[1:] * 2, "hatalı sekme diğerlerinin temasını engellememeli"


def test_app_context_reads_live_state_and_forwards_callbacks(app, monkeypatch):
    from ui.context import AppContext, TabContext
    ctx = app._tabs["Sayfa Düzeni"].ctx
    assert isinstance(ctx, AppContext) and isinstance(ctx, TabContext)
    assert ctx.store is app.store and ctx.log is app.log and ctx.perf is app.perf
    assert ctx.current_tab == app.current_tab
    old_unit = app.unit
    app.unit = "pt"
    try:
        assert ctx.unit == "pt", "bağlam değeri önbelleğe almamalı, pencereden okumalı"
    finally:
        app.unit = old_unit

    seen = []
    monkeypatch.setattr(app, "_on_field_changed", lambda: seen.append("field"))
    monkeypatch.setattr(app, "_schedule_preview", lambda: seen.append("preview"))
    monkeypatch.setattr(app, "_update_pipeline_summary", lambda: seen.append("summary"))
    ctx.on_field_changed()
    ctx.schedule_preview()
    ctx.update_summary()
    assert seen == ["field", "preview", "summary"]


def test_number_tab_widgets_live_on_the_tab(app):
    from ui.tabs.number import NumberTab
    tab = app._number_tab()
    assert isinstance(tab, NumberTab)
    assert not hasattr(NumberTab, "EXPOSED")
    for name in NUMBER_WIDGETS:
        assert hasattr(tab, name), name
        assert name not in app.__dict__, f"{name} pencereye takma ad olarak bağlanmış"
    assert set(NumberTab.FIELD_ROWS) <= set(NUMBER_WIDGETS)
    for name in NumberTab.FIELD_ROWS:
        assert getattr(tab, name) in app._all_field_rows()


def test_number_shell_delegators_reach_the_tab(app, monkeypatch):
    calls = []
    tab = app._tabs["Sayfa Numaraları"]
    monkeypatch.setattr(tab, "on_changed", lambda: calls.append("changed"))
    monkeypatch.setattr(tab, "on_position_changed", lambda: calls.append("position"))
    app._on_number_changed()
    app._on_number_position_changed()
    assert calls == ["changed", "position"]


def test_toggle_pnum_fields_updates_label_modules_button_and_preview(app, monkeypatch):
    seen = []
    monkeypatch.setattr(app, "_on_field_changed", lambda: seen.append("field"))
    app.switch_pnum.select()
    app._toggle_pnum_fields()
    assert app._number_tab().lbl_pnum_status.cget("text").startswith("Etkin")
    app.switch_pnum.deselect()
    app._toggle_pnum_fields()
    assert app._number_tab().lbl_pnum_status.cget("text").startswith("Devre dışı")
    assert seen == ["field", "field"]


def test_layout_tab_shell_bridge_routes_to_the_tab(app):
    tab = layout_tab(app)
    # Takma adlar sekmenin widget'larını gösterir (config_binding ve testler bunlara dayanır).
    assert app._layout_tab().f_bottom is tab.f_bottom and app._layout_tab().f_width is tab.f_width
    assert app._layout_tab().f_safe_edge is tab.f_safe_edge
    assert app.switch_gutter is tab.switch_gutter and app.switch_margin is tab.switch_margin
    # Cilt payı anahtarı yalnızca kendi rozetini yönetir.
    app.switch_gutter.select()
    app._toggle_gutter_fields()
    assert tab.lbl_gutter_status.cget("text").startswith("Etkin")
    assert tab.lbl_margin_status.cget("text").startswith("Devre dışı")
    app.switch_gutter.deselect()
    app._toggle_gutter_fields()
    assert tab.lbl_gutter_status.cget("text").startswith("Devre dışı")
    # Boşluk anahtarı ayrı kalır.
    app.switch_margin.select()
    app._toggle_margin_fields()
    assert tab.lbl_margin_status.cget("text").startswith("Etkin")
    app.switch_margin.deselect()
    app._toggle_margin_fields()
    assert tab.lbl_margin_status.cget("text").startswith("Devre dışı")


def test_margin_preset_button_through_the_real_window_enables_module(app):
    tab = layout_tab(app)
    assert app.switch_margin.get() == 0
    tab.set_bottom(20.0)
    assert app.switch_margin.get() == 1 and app._layout_tab().f_bottom.get_mm() == 20.0
    assert tab.lbl_margin_status.cget("text").startswith("Etkin")
    tab.set_bottom(0.0)
    assert app._layout_tab().f_bottom.get_mm() == 0.0


def test_unit_change_updates_margin_preset_labels(app):
    tab = layout_tab(app)
    texts = lambda: [b.cget("text") for b in tab._bottom_preset_row._buttons][:4]
    assert texts() == ["+10", "+15", "+20", "+25"]
    try:
        app._on_unit_changed("cm")
        assert texts() == ["+1", "+1.5", "+2", "+2.5"]
    finally:
        app._on_unit_changed("mm")
    assert texts() == ["+10", "+15", "+20", "+25"]


def test_gutter_tab_shell_bridge_routes_to_the_tab(app):
    tab = layout_tab(app)
    assert app._layout_tab().f_width is tab.f_width and app._layout_tab().f_odd_x is tab.f_odd_x
    # Hızlı cilt payı: kaynak ebat kabuktan canlı okunur.
    app.orig_width_mm, app.orig_height_mm = 148.0, 210.0
    try:
        tab.apply_preset(10.0)
        assert app.switch_gutter.get() == 1
        assert (app._layout_tab().f_width.get_mm(), app._layout_tab().f_height.get_mm(), app._layout_tab().f_odd_x.get_mm()) == (158.0, 210.0, 10.0)
        tab.reset_to_original()
        assert app.switch_gutter.get() == 0
        assert (app._layout_tab().f_width.get_mm(), app._layout_tab().f_height.get_mm(), app._layout_tab().f_odd_x.get_mm()) == (148.0, 210.0, 0.0)
    finally:
        app.orig_width_mm, app.orig_height_mm = 210.0, 297.0


def test_gutter_profile_button_applies_the_named_preset_through_the_shell(app):
    from core.settings_store import PRESETS
    tab = layout_tab(app)
    name = next(iter(PRESETS))
    tab._preset_row._buttons[0].invoke()
    assert f"'{name}' öneri profili uygulandı" in app.status_label.cget("text")


def test_gutter_paper_size_reports_status_through_the_shell(app):
    tab = layout_tab(app)
    tab.paper_menu.set("A5 (148 × 210)")
    tab.orientation_menu.set("Dikey")
    tab.apply_paper_size()
    assert "Kağıt boyutu 148 × 210 mm" in app.status_label.cget("text")
    assert app.switch_gutter.get() == 1


# ---------------------------------------------------------------------------
# Adım 2.9: Tembel sekme kurulumu, açık bulgular ve geçiş dondurma
# ---------------------------------------------------------------------------

def test_only_active_tab_is_built_at_startup_and_config_matches(app):
    assert app._startup_built_tabs == {
        "Sayfa Düzeni": True,
        "Sayfa Numaraları": False,
        "Birleştirme": False,
        "Baskı ve Araçlar": False,
    }
    # Kurulmamış 3 sekmeyle üretilen açılış yapılandırması, tüm sekmeler kuruluyken
    # aynı başlangıç ayarlarıyla (_restore_settings) üretilenle birebir aynı olmalı.
    app.store.last_state = {}  # açılış varsayılanı: önceki testlerin kaydı karışmasın
    app._restore_settings()
    assert app._startup_config_unbuilt == config_to_dict(app._build_config(notify=False))


def test_unbuilt_tabs_roundtrip_config_unit_and_apply_on_build(app):
    from core.settings_store import PRESETS
    preset_cfg = config_from_dict(PRESETS["Tez (üniversite)"])
    preset_cfg.margins.exclude_pages_str = "2, 4"
    preset_cfg.page_numbers.skip_pages_str = "1, 3"
    preset_cfg.pad_to_multiple = 4

    # Tüm sekmeler kuruluyken referans çıktıyı al.
    app._apply_config(preset_cfg)
    expected_mm = config_to_dict(app._build_config(notify=False))

    # Şimdi Sayfa Numaraları ve Birleştirme'yi "henüz kurulmamış" duruma getirip farklı değerler yaz.
    app._number_tab().f_start_page.set_value("99")
    app._merge_tab().chk_merge_apply_pipeline.deselect()
    for name in ("Sayfa Numaraları", "Birleştirme"):
        app._tabs[name]._built = False
    try:
        app._apply_config(preset_cfg)
        app._set_section("Birleştirme", {"apply_pipeline": True, "bookmarks": False})
        # Sekmeler kurulmamışken _build_config ve _collect_state referansla aynı olmalı.
        assert config_to_dict(app._build_config(notify=False)) == expected_mm
        state = app._collect_state()
        assert state["apply_pipeline"] is True and state["merge_bookmarks"] is False
        assert "Boşluk: alt +20 mm" in app.pill_margin.cget("text")

        # Birim cm'ye geçtikten sonra sekmeler ilk kez kurulursa hem birim hem değer doğru aktarılır.
        app._on_unit_changed("cm")
        for name in ("Sayfa Numaraları", "Birleştirme"):
            app._tabs[name]._built = True
            app._on_tab_built(app._tabs[name])
        assert app._layout_tab().f_bottom.unit == "cm" and app._layout_tab().f_bottom.get_mm() == pytest.approx(20.0)
        assert app._number_tab().f_start_page.get_value() == pytest.approx(2.0)
        assert [r.pages for r in layout_tab(app).rules()] == ["2, 4"]
        assert app._number_tab().entry_skip_pages.get() == "1, 3"
        assert app._layout_tab().chk_pad4.get() == 1
        assert app._merge_tab().chk_merge_apply_pipeline.get() == 1
        assert app._merge_tab().chk_merge_bookmarks.get() == 0
    finally:
        for name in ("Sayfa Numaraları", "Birleştirme"):
            app._tabs[name]._built = True
        app._pending().clear()
        app._on_unit_changed("mm")


def test_legacy_widget_names_are_gone_from_the_window(app):
    """P3-16 (4. parça, v2.6.20): eski takma adlar ve ``__getattr__`` köprüsü yok."""
    from ui.config_binding import ConfigBindingMixin
    assert "__getattr__" not in ConfigBindingMixin.__dict__
    for name in NUMBER_WIDGETS + MERGE_WIDGETS:
        assert not hasattr(app, name), name
    # alanlara açık erişim: sekme üzerinden (gerekirse kurulur)
    assert app._number_tab().f_start_page is app._tabs["Sayfa Numaraları"].f_start_page
    assert app._merge_tab().chk_merge_bookmarks is app._tabs["Birleştirme"].chk_merge_bookmarks


def test_apply_config_with_center_position_updates_side_margin_state(app):
    cfg = app._build_config(notify=False)
    cfg.page_numbers.enabled = True
    cfg.page_numbers.position = "center"
    app._apply_config(cfg)
    assert app._number_tab().f_num_side.entry.cget("state") == "disabled"
    assert "kullanılmaz" in app._number_tab().lbl_side_hint.cget("text")

    cfg.page_numbers.position = "outer"
    app._apply_config(cfg)
    assert app._number_tab().f_num_side.entry.cget("state") == "normal"
    assert app._number_tab().lbl_side_hint.cget("text") == ""


def test_select_tab_keeps_only_active_frame_in_grid_and_applies_deferred_theme(app):
    app.select_tab("Sayfa Düzeni")
    assert bool(app._tab_frames_map["Sayfa Düzeni"].grid_info())
    for other in ("Sayfa Numaraları", "Birleştirme"):
        assert app._tab_frames_map[other].grid_info() == {}

    app._on_theme_changed("Koyu")
    try:
        # Gizli sekmelerin tema geri çağrıları ertelenmiş olmalı; sekmeye geçince uygulanır.
        assert "Sayfa Numaraları" in getattr(app, "_deferred_theme_cbs", {})
        app.select_tab("Sayfa Numaraları")
        assert "Sayfa Numaraları" not in getattr(app, "_deferred_theme_cbs", {})
        assert bool(app._tab_frames_map["Sayfa Numaraları"].grid_info())
        assert app._tab_frames_map["Sayfa Düzeni"].grid_info() == {}
    finally:
        app._on_theme_changed("Açık")
        app.select_tab("Sayfa Düzeni")


def test_freeze_redraw_always_unfreezes_even_on_error(app, monkeypatch):
    calls = []
    orig_set_updates = app.setUpdatesEnabled
    monkeypatch.setattr(app, "setUpdatesEnabled",
                        lambda enabled: (calls.append(("updates", enabled)), orig_set_updates(enabled)))
    with pytest.raises(RuntimeError):
        with app.freeze_redraw():
            assert not app.updatesEnabled()
            with app.freeze_redraw():
                raise RuntimeError("içeride hata")
    assert app.updatesEnabled()
    assert calls == [("updates", False), ("updates", True)]
    assert app._freeze_depth == 0


def test_tab_prewarm_builds_remaining_tabs_in_background_without_changing_active_tab(app):
    for name in ("Sayfa Numaraları", "Birleştirme"):
        app._tabs[name]._built = False
    try:
        app.select_tab("Sayfa Düzeni")
        for _ in range(3):
            app._prewarm_next_tab()
        app.cancel_tab_prewarm()
        assert all(t.built for t in app._tabs.values())
        assert app.current_tab == "Sayfa Düzeni"
        assert bool(app._tab_frames_map["Sayfa Düzeni"].grid_info())
        for other in ("Sayfa Numaraları", "Birleştirme"):
            assert app._tab_frames_map[other].grid_info() == {}
    finally:
        app.cancel_tab_prewarm()
        for name in ("Sayfa Numaraları", "Birleştirme"):
            app._tabs[name]._built = True


def test_destroy_cancels_pending_preview_before_closing(app, monkeypatch):
    cancelled = []
    monkeypatch.setattr(app.preview_panel, "cancel_pending", lambda: cancelled.append(True))
    monkeypatch.setattr(app, "_discard_pending_merge", lambda: None)
    from ui import qt_compat as ctk
    monkeypatch.setattr(ctk.CTk, "destroy", lambda self: None)
    try:
        app.destroy()
        assert cancelled == [True]
    finally:
        app._closing = False
        app._cancel_event.clear()
        if app._queue_after is None:
            app._queue_after = app.after(50, app._drain_ui_queue)


def test_exposed_bridge_only_lists_names_the_shell_still_reads(app):
    """P3-16 (1. parça, v2.6.16): köprüde yalnız dışarıdan okunan adlar kalır."""
    from ui.tabs.page_layout import PageLayoutTab
    removed = {"lbl_gutter_status", "lbl_margin_status", "lbl_target_note", "lbl_safe_edge_note",
               "menu_overflow", "lbl_overflow_note", "lbl_overflow_legacy", "paper_menu",
               "orientation_menu"}
    assert not hasattr(PageLayoutTab, "EXPOSED")
    tab = layout_tab(app)
    for name in removed:
        assert hasattr(tab, name)           # sekmede durur
        assert name not in app.__dict__     # pencereye takma ad olarak bağlanmaz


def test_layout_fields_are_no_longer_window_aliases(app):
    """P3-16 (3. parça, v2.6.18): alanlar yalnız sekme üzerinden; pencerede yalnız iki anahtar."""
    from ui.config_binding import field_row_names
    from ui.tabs.page_layout import PageLayoutTab
    from ui.widgets import FieldRow
    assert not hasattr(PageLayoutTab, "EXPOSED")
    tab = layout_tab(app)
    for name in PageLayoutTab.FIELD_ROWS:
        assert isinstance(getattr(tab, name), FieldRow)
        assert name not in app.__dict__
    assert set(field_row_names(tab)) == set(PageLayoutTab.FIELD_ROWS)
    assert app.switch_gutter is tab.switch_gutter and app.switch_margin is tab.switch_margin
    # birim değişimi yine tüm alan satırlarına ulaşır
    assert set(PageLayoutTab.FIELD_ROWS) <= {
        name for name in PageLayoutTab.FIELD_ROWS
        if getattr(tab, name) in app._all_field_rows()}


def test_fit_menu_round_trips_through_config(app):
    lt = app._layout_tab()
    lt.menu_fit.set("A4'e")
    lt.chk_fit_orient.deselect()
    cfg = app._build_config(notify=False)
    assert cfg.fit_mode == "a4" and cfg.fit_keep_orientation is False
    lt.menu_fit.set("Kapalı (sayfalar olduğu gibi)")
    lt.chk_fit_orient.select()
    app._apply_config(cfg)
    assert lt.menu_fit.get() == "A4'e" and lt.chk_fit_orient.get() == 0
    lt.menu_fit.set("Kapalı (sayfalar olduğu gibi)")
    lt.chk_fit_orient.select()
