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

import tkinter as tk

import customtkinter as ctk
import pytest
import pymupdf

from app import COLOR_ON_ACCENT, ModernGutterApp
from gutter_engine import mm_to_unit, pt_to_mm
from tests.pdf_factory import create_sample_a4_pdf


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    folder = tmp_path_factory.mktemp("gui_session")
    application = ModernGutterApp(
        settings_path=folder / "settings.json",
        log_path=folder / "studio.log",
    )
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
    app.f_bottom.set_mm(0.0)
    app.f_top.set_mm(0.0)
    app._toggle_margin_fields()
    app.switch_pnum.deselect()
    app.f_start_page.set_value("1")
    app.f_start_num.set_value("1")
    app.f_num_bottom.set_mm(12.0)
    app.f_num_side.set_mm(15.0)
    app.entry_skip_pages.delete(0, "end")
    app.chk_continuous.select()
    app._toggle_pnum_fields()
    app.entry_exclude_pages.delete(0, "end")
    app.entry_exclude_margin.delete(0, "end")
    app.chk_merge_apply_pipeline.deselect()
    app.chk_merge_bookmarks.select()
    app.chk_optimize.deselect()
    app.chk_flatten.select()
    app.chk_pad4.deselect()
    app.merge_files.clear()
    app.selected_merge_idx = None
    app._refresh_merge_listbox()
    app.path_entry.delete(0, "end")
    app.input_pdf_path = ""
    app.tabview.set("Cilt Payı")
    app.unit = "mm"
    app.seg_overflow.set("Kırp")
    for row in app._all_field_rows():
        row.reset_unit("mm")
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


def test_opt_in_defaults_and_shortcuts(app):
    assert app.switch_gutter.get() == 0
    assert app.switch_margin.get() == 0
    assert app.switch_pnum.get() == 0
    assert app.btn_main_action.cget("state") == "disabled"
    assert app.chk_continuous.get() == 1
    assert app.chk_flatten.get() == 1
    assert app.chk_optimize.get() == 0
    assert app.chk_merge_apply_pipeline.get() == 0


def test_gutter_preset_builds_single_config(app):
    app._apply_gutter_preset(15.0)
    app.update()
    assert app.switch_gutter.get() == 1
    assert app.f_odd_x.get_value() == 15.0
    assert app.f_width.get_value() == 225.0
    assert "Cilt" in app.btn_main_action.cget("text")

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


def test_unit_conversion_roundtrip(app):
    app._apply_gutter_preset(15.0)
    app.update()
    app.unit_menu.set("cm")
    app._on_unit_changed("cm")
    app.update()
    assert app.unit == "cm"
    assert app.f_odd_x.get_value() == pytest.approx(1.5)
    assert app.f_width.get_value() == pytest.approx(22.5)

    config = app._build_config(notify=False)
    assert config.page_boxes.odd_x_mm == pytest.approx(15.0)
    assert config.page_boxes.target_width_mm == pytest.approx(225.0)

    app.unit_menu.set("pt")
    app._on_unit_changed("pt")
    app.update()
    assert app.f_width.get_value() == pytest.approx(637.8, abs=0.05)

    app.unit_menu.set("mm")
    app._on_unit_changed("mm")
    app.update()
    assert app.f_width.get_value() == pytest.approx(225.0, abs=1e-9)
    assert app.f_odd_x.get_value() == pytest.approx(15.0, abs=1e-9)


def test_field_validation_marks_entry(app):
    app._apply_gutter_preset(15.0)
    app.update()
    app.f_width.set_value("abc")
    config = app._build_config(notify=False)
    assert config is None
    assert app.f_width.error_label.cget("text")

    app.f_width.set_value("210")
    app.update()
    config = app._build_config(notify=False)
    assert config is not None


def test_load_file_keeps_modules_off_and_previews(app, tmp_path):
    sample = str(tmp_path / "sample.pdf")
    create_sample_a4_pdf(sample, pages=3)
    app._load_file(sample)
    app.update()
    assert app.switch_gutter.get() == 0
    assert app.f_width.get_value() == pytest.approx(210.0)
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
    app.tabview.set("Kenar Boşlukları")
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

    for tab_name in ("Cilt Payı", "Kenar Boşlukları", "Sayfa Numaraları", "Birleştirme"):
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
    monkeypatch.setattr(tk.Tk, "withdraw", lambda self, *a, **k: calls.append("withdraw"))
    monkeypatch.setattr(tk.Tk, "deiconify", lambda self, *a, **k: calls.append("deiconify"))
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
    assert app.btn_main_action.cget("state") == "normal"

    app._disable_all_modules()
    app.update()
    assert app.switch_gutter.get() == 0
    assert app.switch_margin.get() == 0
    assert app.switch_pnum.get() == 0
    assert app.btn_main_action.cget("state") == "disabled"

    app.tabview.set("PDF Birleştirme")
    assert app.tabview.get() == "Birleştirme"
    assert "birleştir" in app.btn_main_action.cget("text")


def test_about_dialog_fits_content(app):
    import customtkinter as ctk
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


def test_toggle_all_modules_button(app):
    assert app.btn_all_modules.cget("text") == "Tümünü aç"
    app._toggle_all_modules()
    app.update()
    assert (app.switch_gutter.get(), app.switch_margin.get(), app.switch_pnum.get()) == (1, 1, 1)
    assert app.btn_all_modules.cget("text") == "Tümünü kapat"

    app._toggle_all_modules()
    app.update()
    assert (app.switch_gutter.get(), app.switch_margin.get(), app.switch_pnum.get()) == (0, 0, 0)
    assert app.btn_all_modules.cget("text") == "Tümünü aç"


def test_editing_values_auto_enables_related_module(app):
    app.f_odd_x.set_value("15")
    app._on_gutter_changed()
    assert app.switch_gutter.get() == 1

    app.switch_gutter.deselect()
    app._toggle_gutter_fields()
    app.f_bottom.set_value("0")
    app._on_margin_changed()
    assert app.switch_margin.get() == 0

    app.f_bottom.set_value("20")
    app._on_margin_changed()
    assert app.switch_margin.get() == 1

    app.f_start_page.set_value("2")
    app._on_number_changed()
    assert app.switch_pnum.get() == 1


def test_center_position_disables_side_margin_without_shifting(app):
    app.switch_pnum.select()
    app._toggle_pnum_fields()
    app.seg_pos.set("Alt orta")
    app._on_number_position_changed()
    app.update()
    assert app.f_num_side.entry.cget("state") == "disabled"
    assert app.f_num_side.label.cget("text") == "Yan boşluk"
    x_center = app.f_num_side.winfo_rootx()

    app.seg_pos.set("Dış kenar (Tek sağ / Çift sol)")
    app._on_number_position_changed()
    app.update()
    assert app.f_num_side.entry.cget("state") == "normal"
    assert abs(app.f_num_side.winfo_rootx() - x_center) <= 8


def test_gutter_exclusion_field_builds_config(app):
    app._apply_gutter_preset(15.0)
    app.entry_exclude_pages.insert(0, "1, 3-4")
    app.entry_exclude_margin.insert(0, "2")
    app.update()
    config = app._build_config(notify=False)
    assert config is not None
    assert config.page_boxes.exclude_pages_str == "1, 3-4"
    assert config.margins.exclude_pages_str == "2"

    app._apply_config(config)
    assert app.entry_exclude_pages.get() == "1, 3-4"
    assert app.entry_exclude_margin.get() == "2"


def test_exclusion_lists_are_independent_between_tabs(app):
    app.entry_exclude_margin.insert(0, "2, 6-7")
    app.update()
    assert app.entry_exclude_pages.get() == ""

    config = app._build_config(notify=False)
    assert config is not None
    assert config.margins.exclude_pages_str == "2, 6-7"
    assert config.page_boxes.exclude_pages_str == ""

    app.entry_exclude_pages.insert(0, "4")
    config = app._build_config(notify=False)
    assert config is not None
    assert config.margins.exclude_pages_str == "2, 6-7"
    assert config.page_boxes.exclude_pages_str == "4"


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
    assert "birleştir" in app.btn_main_action.cget("text")

    app.chk_merge_apply_pipeline.select()
    app._update_pipeline_summary()
    app.update()
    assert "aktif ayarları" in app.btn_main_action.cget("text")


def test_paper_size_template(app):
    app._apply_gutter_preset(15.0)
    app.f_width.set_value("210")
    app.f_height.set_value("297")
    app.paper_menu.set("A5 (148 × 210)")
    app.orientation_menu.set("Yatay")
    app._apply_paper_size()
    app.update()
    assert app.f_width.get_value() == pytest.approx(210.0)
    assert app.f_height.get_value() == pytest.approx(148.0)
    assert app.seg_size_mode.get() == "Hedef ebat sabit"


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
            app.unit_menu.set("cm")
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
                "odd_x": app.f_odd_x.get_value(),
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
    app.f_bottom.set_mm(20.0)
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
    assert app._decode_dropped(turkish.encode("mbcs")) == turkish
    assert app._decode_dropped(123) == "123"


def test_overflow_mode_builds_shrink_config(app):
    app._apply_gutter_preset(15.0)
    app.seg_overflow.set("Sayfaya sığdır")
    app.update()
    config = app._build_config(notify=False)
    assert config is not None
    assert config.page_boxes.overflow_mode == "shrink"

    app.seg_overflow.set("Kırp")
    app.update()
    assert app._build_config(notify=False).page_boxes.overflow_mode == "clip"


def test_clip_dialog_shrink_switch_updates_config(app):
    app._apply_gutter_preset(15.0)
    assert app._switch_to_shrink() is True
    assert app.seg_overflow.get() == "Sayfaya sığdır"
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

    app._handle_dropped_files([first.encode("utf-8"), second.encode("mbcs")])
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
