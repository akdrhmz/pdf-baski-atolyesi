"""v2.7.0: yatayı dikeye döndürme, yalnız-eşitleme işi, birleştirmede yön ayarı, Yeni iş, hız."""

from __future__ import annotations

import io

import pymupdf
import pytest
from PIL import Image

import gutter_engine as ge
from gutter_engine import PdfProcessConfig, mm_to_pt, pt_to_mm
from tests.test_fit_and_merge_fixes import _mixed, _sizes
from tests.test_gui_headless import app  # noqa: F401


def _cfg(**kw):
    return PdfProcessConfig(fit_mode="a4", **kw)


# -- Motor -------------------------------------------------------------------------
def test_keep_orientation_leaves_landscape_landscape(tmp_path):
    out = str(tmp_path / "o.pdf")
    ge.build_fitted_pdf(_mixed(str(tmp_path / "m.pdf")), out, _cfg(fit_keep_orientation=True))
    assert _sizes(out) == [(210, 297), (297, 210), (210, 297), (297, 210)]


def test_landscape_rotated_to_portrait_fills_page(tmp_path):
    src = _mixed(str(tmp_path / "m.pdf"))
    out = str(tmp_path / "o.pdf")
    cfg = _cfg(fit_keep_orientation=False, fit_rotate_landscape=True)
    ge.build_fitted_pdf(src, out, cfg)
    assert _sizes(out) == [(210, 297)] * 4
    with pymupdf.open(out) as doc:
        # 2. sayfa (A4 yatay, tam siyah): döndürülünce dikey sayfayı kenara kadar doldurur
        pix = doc[1].get_pixmap(matrix=pymupdf.Matrix(0.3, 0.3), colorspace=pymupdf.csGRAY)
        px = pix.samples
        black = sum(1 for v in px if v < 40) / len(px)
        assert black > 0.97


def test_landscape_not_rotated_is_shrunk_not_filled(tmp_path):
    src = _mixed(str(tmp_path / "m.pdf"))
    out = str(tmp_path / "o.pdf")
    ge.build_fitted_pdf(src, out, _cfg(fit_keep_orientation=False, fit_rotate_landscape=False))
    with pymupdf.open(out) as doc:
        pix = doc[1].get_pixmap(matrix=pymupdf.Matrix(0.3, 0.3), colorspace=pymupdf.csGRAY)
        black = sum(1 for v in pix.samples if v < 40) / len(pix.samples)
        assert 0.3 < black < 0.6


def test_rotate_option_ignored_while_keeping_orientation(tmp_path):
    out = str(tmp_path / "o.pdf")
    ge.build_fitted_pdf(_mixed(str(tmp_path / "m.pdf")), out,
                        _cfg(fit_keep_orientation=True, fit_rotate_landscape=True))
    assert _sizes(out)[1] == (297, 210)


def test_rotated_links_follow_content(tmp_path):
    path = str(tmp_path / "l.pdf")
    doc = pymupdf.open()
    page = doc.new_page(width=mm_to_pt(297), height=mm_to_pt(210))
    page.insert_link({"kind": pymupdf.LINK_URI, "from": pymupdf.Rect(0, 0, 100, 50),
                      "uri": "http://x.test"})
    doc.save(path)
    doc.close()
    out = str(tmp_path / "o.pdf")
    ge.build_fitted_pdf(path, out, _cfg(fit_keep_orientation=False, fit_rotate_landscape=True))
    with pymupdf.open(out) as res:
        rect = res[0].get_links()[0]["from"]
        # sol-üst köşe, saat yönünün tersine 90° dönünce sol-alt köşeye gider
        assert rect.x0 < res[0].rect.width * 0.1 and rect.y1 > res[0].rect.height * 0.8


def test_rotate_setting_roundtrip():
    cfg = _cfg(fit_keep_orientation=False, fit_rotate_landscape=True)
    back = ge.config_from_dict(ge.config_to_dict(cfg))
    assert back.fit_rotate_landscape and not back.fit_keep_orientation
    assert ge.config_from_dict({}).fit_rotate_landscape is False


def test_cache_distinguishes_rotation(tmp_path):
    src = _mixed(str(tmp_path / "m.pdf"))
    a = ge.prepared_source(src, _cfg(fit_keep_orientation=False, fit_rotate_landscape=False))
    b = ge.prepared_source(src, _cfg(fit_keep_orientation=False, fit_rotate_landscape=True))
    assert a != b


def test_fit_only_process_without_any_module(tmp_path):
    src = _mixed(str(tmp_path / "m.pdf"))
    cfg = _cfg()
    cfg.page_boxes.enabled = cfg.margins.enabled = cfg.page_numbers.enabled = False
    out = str(tmp_path / "o.pdf")
    ge.process_pdf(src, out, cfg)
    assert _sizes(out) == [(210, 297), (297, 210), (210, 297), (297, 210)]
    assert not ge.verify_output(src, out, cfg).size_mismatches


def test_preview_bytes_are_fast_ppm_and_decodable(tmp_path):
    src = _mixed(str(tmp_path / "m.pdf"))
    pages = ge.render_preview(src, PdfProcessConfig(), pages=(0, 1), zoom=1.0)
    for page in pages:
        assert page.png[:2] == b"P6"
        assert Image.open(io.BytesIO(page.png)).size[0] > 0
    plain, _ = ge.render_plain_preview(src, pages=(0,), zoom=1.0)
    assert Image.open(io.BytesIO(plain[0].png)).size[0] > 0


def test_render_check_still_detects_a_wrong_placement(tmp_path):
    """Hızlandırılmış blok karşılaştırması bozuk yerleşimi hâlâ yakalamalı."""
    src = str(tmp_path / "a.pdf")
    doc = pymupdf.open()
    page = doc.new_page(width=300, height=400)
    for i in range(10):
        page.draw_rect(pymupdf.Rect(20 + i * 25, 30, 35 + i * 25, 370), fill=(0, 0, 0))
    doc.save(src)
    doc.close()
    cfg = PdfProcessConfig()
    cfg.page_boxes.enabled = True
    cfg.page_boxes.odd_x_mm = 10
    out = str(tmp_path / "b.pdf")
    ge.process_pdf(src, out, cfg)
    assert ge.verify_output(src, out, cfg).render_mismatch_pages == []
    # çıktıyı kaydırılmış/çarpık bir sayfayla değiştir → uyuşmazlık beklenir
    bad = pymupdf.open()
    ref = pymupdf.open(out)
    bp = bad.new_page(width=ref[0].rect.width, height=ref[0].rect.height)
    bp.draw_rect(pymupdf.Rect(0, 0, 60, 60), fill=(0, 0, 0))
    bad_path = str(tmp_path / "bad.pdf")
    bad.save(bad_path)
    assert ge.verify_output(src, bad_path, cfg).render_mismatch_pages == [1]


# -- Arayüz ------------------------------------------------------------------------
def test_fit_alone_counts_as_an_active_operation(app, tmp_path):  # noqa: F811
    layout = app._layout_tab()
    for key in ("gutter", "margin", "pnum"):
        app._module_switch(key).deselect()
    layout.menu_fit.set([k for k, v in __import__("ui.theme", fromlist=["x"]).FIT_LABELS.items()
                         if v == "a4"][0])
    app._load_file(_mixed(str(tmp_path / "fit-source.pdf")))
    app.update()
    assert app._fit_active() is True
    app._update_pipeline_summary()
    assert app.btn_main_action.isEnabled()  # Etkin ayar ve gerçek kaynak PDF var.
    assert "Eşitlenmiş" in app.btn_main_action.text()
    assert "Eşitlenmiş" in app.btn_main_action.text()
    layout.menu_fit.set([k for k, v in __import__("ui.theme", fromlist=["x"]).FIT_LABELS.items()
                         if v == "off"][0])
    app._update_pipeline_summary()
    assert not app.btn_main_action.isEnabled()


def test_rotate_checkbox_follows_keep_orientation(app):  # noqa: F811
    layout = app._layout_tab()
    layout.chk_fit_orient.select()
    layout.update_fit_state()
    assert not layout.chk_fit_rotate.isEnabled()
    layout.chk_fit_orient.deselect()
    layout.update_fit_state()
    assert layout.chk_fit_rotate.isEnabled()
    layout.chk_fit_rotate.select()
    cfg = app._build_config(notify=False)
    assert cfg.fit_rotate_landscape and not cfg.fit_keep_orientation
    layout.chk_fit_orient.select()
    layout.update_fit_state()
    assert app._build_config(notify=False).fit_rotate_landscape is False


def test_new_job_resets_document_but_keeps_settings(app, tmp_path):  # noqa: F811
    src = _mixed(str(tmp_path / "m.pdf"))
    app._load_file(src)
    app.output_pdf_path = str(tmp_path / "x.pdf")
    app.btn_open_pdf.configure(state="normal")
    app._layout_tab().f_odd_x.set_mm(12)
    app._new_job()
    assert app.input_pdf_path == "" and app.output_pdf_path == ""
    assert app.orig_page_count == 0
    assert not app.btn_open_pdf.isEnabled() and not app.btn_open_folder.isEnabled()
    assert "seçilmedi" in app.info_badge.text()
    assert abs(app._row_mm(app._layout_tab().f_odd_x) - 12) < 0.01


def test_new_job_is_blocked_while_busy(app, tmp_path):  # noqa: F811
    app._load_file(_mixed(str(tmp_path / "m.pdf")))
    app._busy = True
    try:
        app._new_job()
        assert app.input_pdf_path
    finally:
        app._busy = False
        app._new_job()


# -- Birleştirme listesi: hedefli ekleme/silme (P3-38 ilk dilim) --------------------
def _tab_with(app, tmp_path, n):  # noqa: F811
    tab = app._tabs["Birleştirme"]
    tab.ensure_built()
    tab.clear()
    paths = []
    for i in range(n):
        path = str(tmp_path / f"f{i}.pdf")
        doc = pymupdf.open()
        for _ in range(i + 1):
            doc.new_page()
        doc.save(path)
        doc.close()
        paths.append(path)
    return tab, paths


def test_rows_added_builds_only_new_rows(app, tmp_path):  # noqa: F811
    tab, paths = _tab_with(app, tmp_path, 4)
    for p in paths[:2]:
        tab.append_file(p)
    tab.refresh_list()
    old_rows = list(tab.rows)
    for p in paths[2:]:
        tab.append_file(p)
    tab.rows_added(2)
    assert len(tab.rows) == 4 and tab.rows[:2] == old_rows
    assert tab._rows_match_files()
    assert "4 dosya" in tab.merge_summary_badge.text()


def test_targeted_remove_keeps_other_rows_and_renumbers(app, tmp_path):  # noqa: F811
    tab, paths = _tab_with(app, tmp_path, 5)
    for p in paths:
        tab.append_file(p)
    tab.refresh_list()
    keep = [tab.rows[i] for i in (0, 2, 4)]
    tab._set_selection([1, 3], 1)
    tab.remove_selected()
    assert tab.rows == keep and len(tab.files) == 3
    assert [r._number_label.text().strip() for r in tab.rows] == ["1", "2", "3"]
    assert [f["name"] for f in tab.files] == ["f0.pdf", "f2.pdf", "f4.pdf"]


def test_removing_last_files_shows_empty_message(app, tmp_path):  # noqa: F811
    tab, paths = _tab_with(app, tmp_path, 2)
    for p in paths:
        tab.append_file(p)
    tab.refresh_list()
    tab._set_selection([0, 1], 0)
    tab.remove_selected()
    assert tab.files == [] and tab.rows == []


# -- Birleştirme önizlemesi sonucu gösterir (P3-39a) ---------------------------------
def test_plain_preview_with_fit_shows_equalized_size(tmp_path):
    src = _mixed(str(tmp_path / "m.pdf"))
    pages, total = ge.render_plain_preview(src, pages=(0, 1, 3), zoom=0.5,
                                           fit=("a4", False, True))
    assert total == 4
    assert [(round(p.width_mm), round(p.height_mm)) for p in pages] == [(210, 297)] * 3
    pages, _ = ge.render_plain_preview(src, pages=(1,), zoom=0.5, fit=("a4", True, False))
    assert (round(pages[0].width_mm), round(pages[0].height_mm)) == (297, 210)
    plain, _ = ge.render_plain_preview(src, pages=(3,), zoom=0.5)
    assert round(plain[0].width_mm) == 420          # fit yokken olduğu gibi


def test_merge_result_preview_applies_settings(tmp_path):
    from ui.preview import render_merge_result_preview
    src = _mixed(str(tmp_path / "m.pdf"))
    cfg = PdfProcessConfig(fit_mode="a4")
    cfg.page_boxes.enabled = True
    cfg.page_boxes.odd_x_mm = 15.0
    pages = render_merge_result_preview(src, 0, "1-2", cfg, (0,))
    assert round(pages[0].width_mm) == 225          # A4 + 15 mm cilt payı


def test_merge_variant_follows_checkboxes(app, tmp_path):  # noqa: F811
    tab, paths = _tab_with(app, tmp_path, 1)
    app.tabview.set("PDF Birleştirme")
    tab.append_file(paths[0])
    tab.refresh_list()
    tab.select_item(0)
    host = app.preview_panel.host
    tab.chk_merge_fit.deselect()
    tab.chk_merge_apply_pipeline.deselect()
    assert host.preview_variant()[2:4] == (None, None)
    tab.chk_merge_fit.select()
    assert host.preview_variant()[2][0] in ge.FIT_MODES
    tab.chk_merge_fit.deselect()
    app.tabview.set("Sayfa Düzeni")


# -- Birleşik dizi gezintisi + aralık yazarken önizleme (P3-39b, 39c) -------------------
def _seq_tab(app, tmp_path, counts):  # noqa: F811
    tab = app._tabs["Birleştirme"]
    tab.ensure_built()
    tab.clear()
    app.tabview.set("PDF Birleştirme")
    for i, n in enumerate(counts):
        path = str(tmp_path / f"d{i}.pdf")
        doc = pymupdf.open()
        for _ in range(n):
            doc.new_page()
        doc.save(path)
        doc.close()
        tab.append_file(path)
    tab.refresh_list()
    return tab


def test_sequence_total_and_captions(app, tmp_path):  # noqa: F811
    from ui.preview import render_sequence_preview
    tab = _seq_tab(app, tmp_path, [2, 3])
    host = app.preview_panel.host
    tab.ctx.store.merge_preview_sequence = False
    tab.select_item(0)
    assert host.preview_page_count == 2
    tab.ctx.store.merge_preview_sequence = True
    assert host.preview_page_count == 5
    variant = host.preview_variant()
    assert variant[4] and len(variant[4]) == 2
    items = host.sequence_items()
    counts = [host.item_count(i) for i in items]
    pages = render_sequence_preview(items, counts, None, None, (1, 2))
    assert [p.page_index for p in pages] == [1, 2]
    assert "d0.pdf (2/2)" in pages[0].caption and "▶" not in pages[0].caption
    assert "▶ d1.pdf (1/3)" in pages[1].caption
    tab.ctx.store.merge_preview_sequence = False
    app.tabview.set("Sayfa Düzeni")


def test_sequence_follows_order_range_and_rotation(app, tmp_path):  # noqa: F811
    from ui.preview import render_sequence_preview
    tab = _seq_tab(app, tmp_path, [2, 3])
    tab.files[1]["page_range"] = "1-2"
    tab.files[0]["rotation"] = 90
    host = app.preview_panel.host
    tab.ctx.store.merge_preview_sequence = True
    assert host.preview_page_count == 4
    items = host.sequence_items()
    counts = [host.item_count(i) for i in items]
    pages = render_sequence_preview(items, counts, None, None, (0,))
    assert pages[0].width_pt > pages[0].height_pt          # 90° döndürülmüş dikey sayfa yatay görünür
    tab.move_item(1, 0)
    assert host.sequence_items()[0]["name"] == "d1.pdf"
    tab.ctx.store.merge_preview_sequence = False
    app.tabview.set("Sayfa Düzeni")


def test_sequence_fit_uses_whole_merged_document(app, tmp_path):  # noqa: F811
    from ui.preview import render_sequence_preview
    a = _mixed(str(tmp_path / "x.pdf"))
    tab = app._tabs["Birleştirme"]
    tab.ensure_built()
    tab.clear()
    tab.append_file(a)
    tab.refresh_list()
    app.tabview.set("PDF Birleştirme")
    tab.ctx.store.merge_preview_sequence = True
    host = app.preview_panel.host
    items = host.sequence_items()
    pages = render_sequence_preview(items, [4], ("a4", False, True), None, (1, 3))
    assert [(round(p.width_mm), round(p.height_mm)) for p in pages] == [(210, 297)] * 2
    tab.ctx.store.merge_preview_sequence = False
    app.tabview.set("Sayfa Düzeni")


def test_half_typed_range_does_not_refresh_preview(app, tmp_path, monkeypatch):  # noqa: F811
    tab = _seq_tab(app, tmp_path, [4])
    calls = []
    monkeypatch.setattr(tab.ctx, "schedule_preview", lambda: calls.append(1))
    entry = type("E", (), {"get": lambda self: "1-", "configure": lambda self, **k: None})()
    tab.on_range_changed(tab.files[0], entry)
    assert calls == []                      # geçersiz yarım aralık: son önizleme kalır
    entry2 = type("E", (), {"get": lambda self: "1-2", "configure": lambda self, **k: None})()
    tab.on_range_changed(tab.files[0], entry2)
    assert calls == [1]


def test_preview_page_clamped_when_range_shrinks(app, tmp_path):  # noqa: F811
    tab = _seq_tab(app, tmp_path, [6])
    tab.select_item(0)
    panel = app.preview_panel
    panel.page = 5
    tab.files[0]["page_range"] = "1-2"
    panel.refresh_now()
    app.update()
    assert panel.page <= 1
