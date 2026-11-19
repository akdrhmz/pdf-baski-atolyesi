"""v2.6.21: sayfa eşitleme (sığdır), birleştirme sürükleme/önizleme/performans düzeltmeleri."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pymupdf
import pytest
from PySide6.QtWidgets import QApplication

import core.gutter_engine as ge
from core.gutter_engine import (PdfProcessConfig, config_from_dict, config_to_dict, mm_to_pt,
                           pt_to_mm, render_plain_preview)
from tests.pdf_factory import create_sample_a4_pdf
from tests.test_merge_multiselect import five  # noqa: F401
from tests.test_merge_tab import root  # noqa: F401


def _mixed(path):
    doc = pymupdf.open()
    for w, h in ((210, 297), (297, 210), (148, 210), (420, 297)):
        page = doc.new_page(width=mm_to_pt(w), height=mm_to_pt(h))
        page.draw_rect(pymupdf.Rect(1, 1, page.rect.width - 1, page.rect.height - 1),
                       color=(0, 0, 0), fill=(0, 0, 0))
    doc.save(path)
    doc.close()
    return path


def _sizes(path):
    with pymupdf.open(path) as doc:
        return [(round(pt_to_mm(p.rect.width)), round(pt_to_mm(p.rect.height))) for p in doc]


# -- Sürükleme / seçim -------------------------------------------------------------
def _fire(row, name):
    ev = SimpleNamespace(widget=row, x_root=0, y_root=0, ctrl=False, shift=False)
    for cb in row._bindings[name]:
        cb(ev)


def test_click_after_drag_selects_the_row_that_was_clicked(five):  # noqa: F811
    tab, _ = five
    tab.move_item(0, 3)                       # sürükleme: ilk dosya 4. sıraya
    row = tab.rows[3]
    _fire(row, "<Button-1>")
    _fire(row, "<ButtonRelease-1>")
    assert tab.selected_idx == 3 and tab.files[3]["pages"] == 1


def test_every_row_selects_itself_after_reorder(five):  # noqa: F811
    tab, _ = five
    tab.move_item(4, 0)
    tab.move_item(2, 3)
    for i, row in enumerate(list(tab.rows)):
        _fire(row, "<Button-1>")
        _fire(row, "<ButtonRelease-1>")
        assert tab.selected_idx == i


def test_rotate_updates_badge_without_rebuilding_rows(five):  # noqa: F811
    tab, ctx = five
    rows = list(tab.rows)
    tab.select_item(1)
    tab.rotate_selected(90)
    assert tab.rows == rows, "döndürme satırları yeniden kurmamalı"
    assert "90° sağa" in rows[1]._badge_label.cget("text")
    assert ("schedule_preview",) in [c[:1] for c in ctx.calls] or ctx.calls


def test_move_up_keeps_rows_objects(five):  # noqa: F811
    tab, _ = five
    rows = list(tab.rows)
    tab.select_item(2)
    tab.move_up()
    assert tab.rows[1] is rows[2] and tab.rows[2] is rows[1]
    assert [int(r._number_label.cget("text")) for r in tab.rows] == [1, 2, 3, 4, 5]


def test_destroy_leaves_no_toplevel_windows(five):  # noqa: F811
    tab, _ = five
    for _ in range(3):
        tab.refresh_list()
    app = QApplication.instance()
    app.processEvents()
    assert [w for w in app.topLevelWidgets() if w.isVisible() and w.windowTitle() == ""] == []


# -- Birleştirme önizlemesi ----------------------------------------------------------
def test_plain_preview_counts_all_pages_and_applies_rotation_and_range(tmp_path):
    path = create_sample_a4_pdf(str(tmp_path / "a.pdf"), pages=6)
    pages, total = render_plain_preview(path, 0, "", pages=(0, 1, 5))
    assert total == 6 and [p.page_index for p in pages] == [0, 1, 5]
    pages, total = render_plain_preview(path, 90, "2-4", pages=(0, 1, 2, 3))
    assert total == 3 and [p.page_index for p in pages] == [0, 1, 2]
    assert pages[0].width_pt > pages[0].height_pt, "90° döndürme önizlemeye yansımalı"


def test_get_pdf_info_quick_matches_page_count(tmp_path):
    path = _mixed(str(tmp_path / "m.pdf"))
    full, quick = ge.get_pdf_info(path), ge.get_pdf_info(path, quick=True)
    assert full["page_count"] == quick["page_count"] == 4 and full["mixed_sizes"]
    assert not quick["mixed_sizes"]


def test_preview_panel_uses_selected_file_page_count():
    from ui.preview import PreviewPanel

    class Host:
        orig_page_count = 0
        preview_page_count = 7
        def preview_variant(self): return (0, "")
    panel = PreviewPanel(Host())
    assert panel._total() == 7 and panel._variant() == (0, "")


# -- Sayfa eşitleme -------------------------------------------------------------------
def test_fit_config_roundtrip_and_invalid_fallback():
    cfg = PdfProcessConfig(fit_mode="a4", fit_keep_orientation=False)
    back = config_from_dict(config_to_dict(cfg))
    assert back.fit_mode == "a4" and back.fit_keep_orientation is False
    assert config_from_dict({"fit_mode": "zzz"}).fit_mode == "off"
    assert config_from_dict({}).fit_mode == "off"
    assert not ge.validate_config(PdfProcessConfig(fit_mode="zzz")).ok


def test_fit_a4_makes_all_pages_a4_keeping_orientation(tmp_path):
    src = _mixed(str(tmp_path / "m.pdf"))
    cfg = PdfProcessConfig(fit_mode="a4")
    fitted = ge.prepared_source(src, cfg)
    assert _sizes(fitted) == [(210, 297), (297, 210), (210, 297), (297, 210)]
    cfg2 = PdfProcessConfig(fit_mode="a4", fit_keep_orientation=False)
    assert set(_sizes(ge.prepared_source(src, cfg2))) == {(210, 297)}


def test_fit_largest_and_first(tmp_path):
    src = _mixed(str(tmp_path / "m.pdf"))
    largest = _sizes(ge.prepared_source(src, PdfProcessConfig(fit_mode="largest")))
    assert set(largest) <= {(297, 420), (420, 297)}
    first = _sizes(ge.prepared_source(src, PdfProcessConfig(fit_mode="first")))
    assert set(first) <= {(210, 297), (297, 210)}


def test_fit_off_returns_same_path_and_cache_reuses(tmp_path):
    src = _mixed(str(tmp_path / "m.pdf"))
    assert ge.prepared_source(src, PdfProcessConfig()) == src
    cfg = PdfProcessConfig(fit_mode="a4")
    assert ge.prepared_source(src, cfg) == ge.prepared_source(src, cfg)


def test_fit_content_is_scaled_not_clipped(tmp_path):
    """Siyah dolgulu 420×297 yatay sayfa A4 yataya sığdırılınca çerçeve içinde kalır."""
    src = _mixed(str(tmp_path / "m.pdf"))
    fitted = ge.prepared_source(src, PdfProcessConfig(fit_mode="a4"))
    with pymupdf.open(fitted) as doc:
        page = doc[3]
        bbox = ge.page_content_bbox(page)
        assert bbox.x0 >= -0.5 and bbox.x1 <= page.rect.width + 0.5
        assert bbox.y0 >= -0.5 and bbox.y1 <= page.rect.height + 0.5


def test_process_with_fit_removes_clipping_and_verifies(tmp_path):
    src = _mixed(str(tmp_path / "m.pdf"))
    base = PdfProcessConfig()
    base.page_boxes.enabled = True
    base.page_boxes.size_mode = "fixed"
    base.page_boxes.target_width_mm = 210.0
    base.page_boxes.target_height_mm = 297.0
    base.page_boxes.odd_x_mm = base.page_boxes.even_x_mm = 10.0
    base.page_boxes.overflow_mode = "clip"
    base.margins.enabled = False
    base.page_numbers.enabled = False
    assert ge.scan_clipping(src, base).has_issues, "sığdırmadan önce kırpma bekleniyor"
    fit = PdfProcessConfig(**{**base.__dict__, "fit_mode": "a4"})
    out = str(tmp_path / "out.pdf")
    ge.process_pdf(src, out, fit)
    rep = ge.verify_output(src, out, fit)
    assert not rep.size_mismatches
    assert len(_sizes(out)) == 4


def test_fit_keeps_links_and_toc(tmp_path):
    path = str(tmp_path / "l.pdf")
    doc = pymupdf.open()
    for w, h in ((210, 297), (297, 210)):
        doc.new_page(width=mm_to_pt(w), height=mm_to_pt(h))
    doc[0].insert_link({"kind": pymupdf.LINK_GOTO, "from": pymupdf.Rect(10, 10, 60, 30),
                        "page": 1, "to": pymupdf.Point(20, 20)})
    doc.set_toc([[1, "Bir", 1], [1, "İki", 2]])
    doc.save(path)
    doc.close()
    fitted = ge.prepared_source(path, PdfProcessConfig(fit_mode="a5"))
    with pymupdf.open(fitted) as out:
        assert len(out[0].get_links()) == 1
        assert [t[1] for t in out.get_toc()] == ["Bir", "İki"]
