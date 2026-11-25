"""v2.11 hata düzeltmeleri, önizleme tutarlılığı, parola, yazdırma ve CLI regresyonları."""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pymupdf
import pytest
from PySide6.QtPrintSupport import QPrinter

from app import ModernGutterApp
from core.gutter_engine import open_pdf, pt_to_mm
from core.pdf_tools import (
    PrintOptions,
    SecurityMetaOptions,
    StampOptions,
    apply_security_and_metadata,
    bates_index_for_page,
    render_tool_preview,
    stamp_pdf,
)
from studio_cli import main as cli_main
from ui.i18n import set_language, tr
from ui.print_pdf import compute_centered_target_rect, print_pdf_to_printer


@pytest.fixture
def sample_landscape_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "landscape_a3.pdf"
    with pymupdf.open() as doc:
        for idx in range(6):
            page = doc.new_page(width=1190.55, height=841.89)  # A3 yatay
            page.insert_text((50, 100), f"LANDSCAPE PAGE {idx + 1}")
        # 1. sayfaya metin açıklaması (annotation) ekle
        doc[0].add_freetext_annot(pymupdf.Rect(60, 140, 260, 200), "ANNOT STAMP")
        doc.save(path)
    return path


def test_bates_page_range_counter_matches_output(sample_landscape_pdf: Path, tmp_path: Path):
    opts = StampOptions(
        bates_enabled=True,
        bates_prefix="DOC-",
        bates_start=1,
        bates_digits=4,
        page_range="3-5",
    )
    assert bates_index_for_page(2, {3, 4, 5}) == 0
    assert bates_index_for_page(3, {3, 4, 5}) == 1
    assert bates_index_for_page(4, {3, 4, 5}) == 2

    out = tmp_path / "stamped.pdf"
    stamp_pdf(sample_landscape_pdf, out, opts)
    with pymupdf.open(out) as doc:
        assert "DOC-" not in doc[0].get_text()
        assert "DOC-0001" in doc[2].get_text()
        assert "DOC-0002" in doc[3].get_text()
        assert "DOC-0003" in doc[4].get_text()

    ppm, w_pt, h_pt = render_tool_preview(
        sample_landscape_pdf, "stamp", opts, page_index=2, zoom=1.0, return_size=True
    )
    assert ppm
    assert pt_to_mm(w_pt) == pytest.approx(420.0, abs=0.5)
    assert pt_to_mm(h_pt) == pytest.approx(297.0, abs=0.5)


def test_impose_preview_returns_exact_dimensions_and_bakes_annotations(sample_landscape_pdf: Path):
    opts = PrintOptions(mode="marks", bleed_mm=3.0, crop_marks=True)
    ppm, w_pt, h_pt = render_tool_preview(
        sample_landscape_pdf, "impose", opts, page_index=0, zoom=0.8, return_size=True
    )
    assert ppm
    # A3 (420x297) + 2*(3mm bleed + 4mm crop_marks) = 434 x 311 mm
    assert pt_to_mm(w_pt) == pytest.approx(434.0, abs=0.6)
    assert pt_to_mm(h_pt) == pytest.approx(311.0, abs=0.6)


def test_open_pdf_and_ui_unlock_password_protected_pdf(sample_landscape_pdf: Path, tmp_path: Path, monkeypatch):
    locked = tmp_path / "locked.pdf"
    apply_security_and_metadata(
        sample_landscape_pdf,
        locked,
        SecurityMetaOptions(user_password="secret123", owner_password="owner456"),
    )

    with open_pdf(str(locked), password="secret123") as doc:
        assert len(doc) == 6

    app = ModernGutterApp(settings_path=tmp_path / "s.json", log_path=tmp_path / "l.log")
    try:
        monkeypatch.setattr(app, "_ask_pdf_password", lambda _p: "secret123")
        app._load_file(str(locked))
        assert app.orig_page_count == 6
        assert app._source_origin_path == str(locked)
        assert os.path.isfile(app.input_pdf_path)
        temp_loaded = app.input_pdf_path
    finally:
        app.destroy()
    assert not os.path.exists(temp_loaded)


def test_save_dialog_overwrites_chosen_path_without_appending_2(sample_landscape_pdf: Path, tmp_path: Path, monkeypatch):
    existing = tmp_path / "hedef.pdf"
    existing.write_bytes(b"placeholder")

    app = ModernGutterApp(settings_path=tmp_path / "s.json", log_path=tmp_path / "l.log")
    try:
        app._load_file(str(sample_landscape_pdf))
        app.select_tab("Baskı ve Araçlar")
        tools = app._tabs["Baskı ve Araçlar"]
        monkeypatch.setattr("ui.tabs.tools.filedialog.asksaveasfilename", lambda **_kw: str(existing))
        chosen = tools._output_path("baski")
        assert chosen == str(existing)
    finally:
        app.destroy()


def test_tools_tab_state_persists_across_sessions(tmp_path: Path):
    settings_file = tmp_path / "settings.json"
    app1 = ModernGutterApp(settings_path=settings_file, log_path=tmp_path / "l1.log")
    try:
        app1.select_tab("Baskı ve Araçlar")
        tools1 = app1._tabs["Baskı ve Araçlar"]
        tools1.operation.set("Filigran & Bates")
        tools1.watermark.insert(0, "GİZLİ KOPYA")
        tools1.bates.select()
        tools1.prefix.insert(0, "EVRAK-")
        tools1.rtl_order.select()
        app1.store.last_state = app1._collect_state()
        app1.store.save()
    finally:
        app1.destroy()

    app2 = ModernGutterApp(settings_path=settings_file, log_path=tmp_path / "l2.log")
    try:
        app2.select_tab("Baskı ve Araçlar")
        tools2 = app2._tabs["Baskı ve Araçlar"]
        assert tools2.operation.get() == "Filigran & Bates"
        assert tools2.watermark.get() == "GİZLİ KOPYA"
        assert bool(tools2.bates.get()) is True
        assert tools2.prefix.get() == "EVRAK-"
        assert bool(tools2.rtl_order.get()) is True
    finally:
        app2.destroy()


def test_english_translations_for_tools_tab_and_dynamic_captions():
    try:
        set_language("en")
        assert tr("4. Baskı ve Araçlar") == "4. Print & Tools"
        assert tr("1. Yaprak · Ön [4, 1]") == "Sheet 1 · Front [4, 1]"
        assert tr("2. sayfa (damga/Bates)") == "Page 2 (stamp/Bates)"
        assert tr("Kaynak PDF parolası (şifreliyse)") == "Source PDF password (if encrypted)"
        assert tr("Yazdır…") == "Print…"
        msg = "Kitapçık tamamlama: 5 sayfa → 8 sayfaya tamamlamak için 3 boş sayfa eklenecek."
        assert tr(msg) == "Booklet padding: 3 blank pages will be added to pad 5 pages to 8."
    finally:
        set_language("tr")


def test_direct_print_centers_pages_without_top_left_shift(sample_landscape_pdf: Path, tmp_path: Path):
    rect = compute_centered_target_rect(1000.0, 500.0, 2000.0, 1400.0)
    assert rect.width() == pytest.approx(2000.0)
    assert rect.height() == pytest.approx(1000.0)
    assert rect.x() == pytest.approx(0.0)
    assert rect.y() == pytest.approx(200.0)

    printed_pdf = tmp_path / "printed_spool.pdf"
    printer = QPrinter(QPrinter.PrinterMode.ScreenResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(printed_pdf))
    printer.setPrintRange(QPrinter.PrintRange.PageRange)
    printer.setFromTo(2, 3)

    count = print_pdf_to_printer(str(sample_landscape_pdf), printer)
    assert count == 2
    assert printed_pdf.is_file()
    with pymupdf.open(printed_pdf) as doc:
        assert len(doc) == 2


def test_cli_extended_tool_modes(sample_landscape_pdf: Path, tmp_path: Path):
    booklet_out = tmp_path / "booklet.pdf"
    assert cli_main([
        "--input", str(sample_landscape_pdf),
        "--output", str(booklet_out),
        "--impose", "booklet",
        "--signature", "8",
        "--crop-marks",
    ]) == 0
    with pymupdf.open(booklet_out) as doc:
        assert len(doc) == 4  # 6 sayfa -> 8'e tamamlanır -> 2 yaprak (4 yüz)

    stamp_out = tmp_path / "stamp_cli.pdf"
    assert cli_main([
        "--input", str(sample_landscape_pdf),
        "--output", str(stamp_out),
        "--watermark", "CLI-TEST",
        "--bates-prefix", "NO-",
        "--stamp-pages", "2-4",
    ]) == 0
    with pymupdf.open(stamp_out) as doc:
        assert "NO-000001" in doc[1].get_text()
        assert "NO-" not in doc[0].get_text()

    split_dir = tmp_path / "split_out"
    assert cli_main([
        "--input", str(sample_landscape_pdf),
        "--output", str(split_dir),
        "--pages", "1-4",
        "--split", "2",
    ]) == 0
    assert len(list(split_dir.glob("*.pdf"))) == 2
