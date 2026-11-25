"""Yeni geliştirmelerin çıktı ve gerçek kullanıcı etkileşimi regresyonları."""
import json
from pathlib import Path

import pymupdf
import pytest

import core.gutter_engine as ge
from core.pdf_tools import (export_pages, split_pages, stamp_pdf, impose_pdf, StampOptions,
                       PrintOptions, booklet_order)


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "source.pdf"
    with pymupdf.open() as doc:
        for index in range(5):
            page = doc.new_page(width=300, height=420)
            page.insert_text((30, 80), f"ORIGINAL PAGE {index + 1}")
        doc[0].insert_link({"kind": pymupdf.LINK_GOTO, "from": pymupdf.Rect(30, 50, 140, 90), "page": 4,
                            "to": pymupdf.Point(30, 80)})
        doc.set_toc([[1, "First", 1], [1, "Last", 5]])
        doc.save(path)
    return path


def test_custom_fit_margin_and_links(source, tmp_path):
    output = tmp_path / "fitted.pdf"
    config = ge.PdfProcessConfig(fit_mode="custom", fit_width_mm=160, fit_height_mm=230,
                                 fit_margin_mm=12, fit_keep_orientation=False)
    ge.build_fitted_pdf(str(source), str(output), config)
    with pymupdf.open(output) as doc:
        assert len(doc) == 5
        assert ge.pt_to_mm(doc[0].rect.width) == pytest.approx(160)
        bounds = doc[0].get_text("words")[0]
        assert bounds[0] > ge.mm_to_pt(12)
        assert doc[0].get_links()[0]["page"] == 4


def test_section_blank_numbering_and_verification(source, tmp_path):
    output = tmp_path / "sections.pdf"
    config = ge.PdfProcessConfig()
    config.page_boxes.enabled = config.margins.enabled = False
    config.page_numbers.sections = [dict(start_page=1, start_num=1, format_style="roman"),
                                    dict(start_page=2, start_num=1, format_style="number",
                                         blank_before=True, hide_first=True)]
    ge.process_pdf(str(source), str(output), config)
    assert ge.numbering_plan(6, config) == ["i", None, None, "2", "3", "4"]
    with pymupdf.open(output) as doc:
        assert len(doc) == 6
        assert not doc[1].get_text().strip()
        assert "ORIGINAL PAGE 2" in doc[2].get_text()
        assert doc[0].get_links()[0]["page"] == 5
    assert ge.verify_output(str(source), str(output), config).ok


@pytest.mark.parametrize("binding", ["right", "top"])
def test_binding_geometry(binding):
    config = ge.PdfProcessConfig()
    config.page_boxes.binding = binding
    config.page_boxes.size_mode = "auto"
    config.page_boxes.odd_x_mm = 15
    config.margins.enabled = False
    layout = ge.compute_layout(300, 420, config, 0)
    if binding == "right":
        assert layout.content.x0 == pytest.approx(0)
        assert layout.target_w - layout.content.x1 == pytest.approx(ge.mm_to_pt(15))
    else:
        assert layout.content.y0 == pytest.approx(ge.mm_to_pt(15))
        assert layout.target_h == pytest.approx(420 + ge.mm_to_pt(15))


def test_export_and_split_preserve_sources(source, tmp_path):
    original = source.read_bytes()
    output = tmp_path / "pages.pdf"
    ge_path = export_pages(source, output, [(4, 90), (0, 0)])
    assert Path(ge_path).is_file()
    with pymupdf.open(output) as doc:
        assert len(doc) == 2
        assert doc[0].rotation == 90
        assert "PAGE 5" in doc[0].get_text()
        assert doc[1].get_links()[0]["page"] == 0
    paths = split_pages(source, tmp_path / "parts", [(i, 0) for i in range(5)], 2)
    counts = []
    for path in paths:
        with pymupdf.open(path) as doc:
            counts.append(len(doc))
    assert counts == [2, 2, 1]
    assert source.read_bytes() == original


def test_watermark_bates(source, tmp_path):
    output = tmp_path / "stamp.pdf"
    stamp_pdf(source, output, StampOptions(watermark="DRAFT", bates_enabled=True,
                                          bates_prefix="CASE-", bates_start=42))
    with pymupdf.open(output) as doc:
        assert "DRAFT" in doc[0].get_text()
        assert "CASE-000042" in doc[0].get_text()
        assert "CASE-000046" in doc[4].get_text()
        assert doc[0].get_links()[0]["page"] == 4


@pytest.mark.parametrize("mode,count", [("2up", 3), ("4up", 2), ("booklet", 4), ("marks", 5)])
def test_print_imposition(source, tmp_path, mode, count):
    output = tmp_path / f"{mode}.pdf"
    impose_pdf(source, output, PrintOptions(mode=mode, crop_marks=True, bleed_mm=3, creep_mm=0.1))
    with pymupdf.open(output) as doc:
        assert len(doc) == count
        combined = " ".join(page.get_text() for page in doc)
        for number in range(1, 6):
            assert f"ORIGINAL PAGE {number}" in combined
        assert doc[0].trimbox.width < doc[0].rect.width
        assert doc[0].bleedbox.width > doc[0].trimbox.width


def test_booklet_padding_order():
    assert booklet_order(5) == [[None, 0], [1, None], [None, 2], [3, 4]]


def test_custom_landscape_target(source, tmp_path):
    config = ge.PdfProcessConfig(fit_mode="custom", fit_width_mm=250, fit_height_mm=150,
                                 fit_keep_orientation=False, fit_rotate_landscape=True)
    output = tmp_path / "landscape.pdf"
    ge.build_fitted_pdf(str(source), str(output), config)
    with pymupdf.open(output) as doc:
        assert ge.pt_to_mm(doc[0].rect.width) == pytest.approx(250)
        assert ge.pt_to_mm(doc[0].rect.height) == pytest.approx(150)


def test_cli_folder_profile(source, tmp_path, capsys):
    from studio_cli import main
    profile = tmp_path / "profile.json"
    config = ge.PdfProcessConfig()
    config.page_boxes.enabled = config.margins.enabled = config.page_numbers.enabled = False
    profile.write_text(json.dumps(ge.config_to_dict(config)), encoding="utf-8")
    output = tmp_path / "batch"
    assert main(["--input", str(source.parent), "--output", str(output), "--profile", str(profile)]) == 0
    assert (output / "source_islenmis.pdf").is_file()
    assert "OK:" in capsys.readouterr().out


def test_language_change_keeps_option_codes():
    from ui import qt_compat as ctk
    from ui.i18n import set_language, refresh_widgets
    root = ctk.CTk()
    menu = ctk.CTkOptionMenu(root, values=["Soldan cilt", "Sağdan cilt"])
    menu.set("Sağdan cilt")
    try:
        set_language("en")
        refresh_widgets(root)
        assert menu.currentText() == "Right binding"
        assert menu.get() == "Sağdan cilt"
    finally:
        set_language("tr")
        root.destroy()


def test_english_dynamic_report_and_validation():
    from ui.i18n import set_language, tr
    try:
        set_language("en")
        report = ge.VerifyReport(pages_src=5, pages_out=6, pad_pages=1)
        result = tr("\n".join(report.lines()))
        assert "source 5 (+1 blank), output 6" in result
        assert "Page sizes match" in result
        assert tr("Hedef genişlik 0 ile 2000 mm arasında olmalı.") == "Target width must be between 0 and 2000 mm."
        assert tr("Sayfa 1–3: üst 4.0 mm, sol 2.0 mm") == "Page 1–3: top 4.0 mm, left 2.0 mm"
    finally:
        set_language("tr")


def test_theme_click_paints_without_second_input(tmp_path):
    from PySide6.QtCore import QObject, QEvent, Qt
    from PySide6.QtTest import QTest
    from ui import qt_compat as ctk
    from app import ModernGutterApp
    app = ModernGutterApp(settings_path=tmp_path / "settings.json", log_path=tmp_path / "studio.log")
    app.show()
    app._on_theme_changed("Açık")
    app.theme_segmented.set("Açık")
    QTest.qWait(30)
    painted = []

    class PaintObserver(QObject):
        def eventFilter(self, watched, event):
            if event.type() == QEvent.Type.Paint:
                painted.append(ctk.get_appearance_mode())
            return False

    observer = PaintObserver(app)
    app._content_frame.installEventFilter(observer)
    try:
        QTest.mouseClick(app.theme_segmented._seg_buttons["Koyu"], Qt.MouseButton.LeftButton)
        QTest.qWait(50)
        assert app.store.theme == "Koyu"
        assert ctk.get_appearance_mode() == "Dark"
        assert "Dark" in painted
        painted.clear()
        QTest.mouseClick(app.theme_segmented._seg_buttons["Açık"], Qt.MouseButton.LeftButton)
        QTest.qWait(50)
        assert ctk.get_appearance_mode() == "Light"
        assert "Light" in painted
    finally:
        app.destroy()


def test_settings_preferences_persist_and_factory_reset(tmp_path, monkeypatch):
    from app import ModernGutterApp
    from ui import qt_compat as ctk
    from ui.qt_compat import messagebox
    app = ModernGutterApp(settings_path=tmp_path / "settings.json", log_path=tmp_path / "studio.log")
    try:
        merge = app._merge_tab()
        merge.chk_merge_apply_pipeline.select()
        merge.chk_merge_bookmarks.deselect()
        app._show_settings_dialog()
        app.update()
        dialog = [w for w in app.winfo_children() if isinstance(w, ctk.CTkToplevel)][-1]
        assert not dialog.findChildren(ctk.CTkSegmentedButton)  # Tema üst çubukta tek yerde.
        boxes = {box.cget("text"): box for box in dialog.findChildren(ctk.CTkCheckBox)}
        boxes["Dosyayı optimize et (küçük boyut)"].click()
        boxes["Açıklama ve form alanlarını sayfaya göm"].click()
        boxes["Önizlemede tüm birleşik belgeyi gez"].click()
        boxes["Satırları yalnız ⠿ tutamacından sürükle"].click()
        data = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
        assert data["last_state"]["quality_mode"] == "standard"
        assert data["last_state"]["flatten_annotations"] is False
        assert data["merge_preview_sequence"] and data["merge_handle_only"]
        monkeypatch.setattr(messagebox, "askyesno", lambda *_a, **_kw: True)
        button = next(b for b in dialog.findChildren(ctk.CTkButton) if b.cget("text") == "Fabrika değerlerine sıfırla")
        button.click()
        assert app._output_quality == "print" and app._flatten_annotations is True
        assert not app.store.merge_handle_only and not app.store.merge_preview_sequence
        assert merge.chk_merge_apply_pipeline.get() == 0 and merge.chk_merge_bookmarks.get() == 1
        dialog.destroy()
    finally:
        app.destroy()


def test_tools_tab_page_grid_rotate_and_remove(source, tmp_path):
    from PySide6.QtCore import Qt
    from app import ModernGutterApp
    app = ModernGutterApp(settings_path=tmp_path / "settings.json", log_path=tmp_path / "studio.log")
    try:
        app._load_file(str(source))
        app.select_tab("Baskı ve Araçlar")
        tools = app._tabs["Baskı ve Araçlar"]
        tools.operation.set("Sayfaları Düzenle")
        tools.update_operation()
        assert tools.grid.count() == 5
        tools.grid.item(0).setSelected(True)
        tools.rotate()
        assert tuple(tools.grid.item(0).data(Qt.ItemDataRole.UserRole)) == (0, 90)
        tools.remove()
        assert tools.grid.count() == 4
    finally:
        app.destroy()
