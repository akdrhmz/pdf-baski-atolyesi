"""P2-36: "Sayfa boyutu ve sığdırma" bölümünün çözümleme tablosu (motorda ölçülmüş) ve sonuç cümlesi.

Tablo ``docs/app-bolme-plani.md`` madde 36'dadır; buradaki testler onu motora bağlar. Böylece
bir denetim "etkili" ya da "ilgisiz" sayılırken motor davranışı değişirse test düşer.
"""

from __future__ import annotations

import pymupdf
import pytest

import gutter_engine as ge
import page_layout_model as plm

EXTEND, SHRINK, CLIP = plm.CHOICE_EXTEND, plm.CHOICE_SHRINK, plm.CHOICE_CLIP


@pytest.fixture(scope="module")
def page():
    """Siyah dolgusu sayfanın kenarına kadar uzanan A4 sayfa (kırpma en kötü durumda ölçülür)."""
    doc = pymupdf.open()
    pg = doc.new_page(width=595.28, height=841.89)
    pg.draw_rect(pymupdf.Rect(0.5, 0.5, 594.8, 841.4), fill=(0, 0, 0))
    yield doc[0]
    doc.close()


def _cfg(mode, choice, *, w=225.0, h=297.0, safe=0.0, top=4.0, bottom=10.0, gutter=15.0,
         margins_on=True):
    ov, bm = plm.CHOICE_TO_ENGINE[choice]
    cfg = ge.PdfProcessConfig()
    cfg.page_boxes = ge.PageBoxSettings(
        enabled=True, target_width_mm=w, target_height_mm=h, odd_x_mm=gutter,
        size_mode=mode, overflow_mode=ov, safe_edge_mm=safe)
    cfg.margins = ge.MarginSettings(enabled=margins_on, extra_top_mm=top,
                                    extra_bottom_mm=bottom, bottom_mode=bm)
    return cfg


def _measure(page, cfg):
    lay = ge.compute_layout(page.rect.width, page.rect.height, cfg, 0)
    clip = sum(ge.clip_edges_for_page(page, lay))
    return (round(ge.pt_to_mm(lay.target_w), 1), round(ge.pt_to_mm(lay.target_h), 1),
            round(lay.scale, 3), round(clip, 1))


# --- Çözümleme tablosu ------------------------------------------------------
@pytest.mark.parametrize("mode", ("fixed", "auto"))
def test_overflow_choice_changes_output_whenever_margin_pay_exists(page, mode):
    """Kaynak ebat modunda da seçim sonucu değiştirir (alt/üst boşluk üzerinden)."""
    outs = {c: _measure(page, _cfg(mode, c)) for c in (EXTEND, SHRINK, CLIP)}
    assert len(set(outs.values())) == 3
    assert outs[EXTEND][3] == 0 and outs[SHRINK][3] == 0     # kırpmaz
    assert outs[CLIP][3] > 0                                  # kırpar (bulgu: 9 sayfada "üst 4.0 mm")


def test_auto_mode_clips_top_with_clip_choice_even_though_row_looked_disabled(page):
    top = ge.clip_edges_for_page(page, ge.compute_layout(
        page.rect.width, page.rect.height, _cfg("auto", CLIP), 0))[2]
    assert top > 0


@pytest.mark.parametrize("mode", ("fixed", "auto"))
def test_overflow_choice_is_irrelevant_without_margin_pay_when_everything_fits(page, mode):
    outs = {_measure(page, _cfg(mode, c, top=0, bottom=0)) for c in (EXTEND, SHRINK, CLIP)}
    assert len(outs) == 1


def test_overflow_choice_is_irrelevant_in_auto_mode_when_margin_module_is_off(page):
    outs = {_measure(page, _cfg("auto", c, margins_on=False)) for c in (EXTEND, SHRINK, CLIP)}
    assert len(outs) == 1


def test_target_size_only_matters_in_fixed_mode(page):
    for choice in (EXTEND, SHRINK, CLIP):
        assert _measure(page, _cfg("auto", choice)) == _measure(page, _cfg("auto", choice, w=250, h=330))
        assert _measure(page, _cfg("fixed", choice)) != _measure(page, _cfg("fixed", choice, w=250, h=330))


def test_safe_edge_only_matters_in_fixed_mode_with_shrink(page):
    for mode in ("fixed", "auto"):
        for choice in (EXTEND, CLIP):
            assert _measure(page, _cfg(mode, choice)) == _measure(page, _cfg(mode, choice, safe=8.0))
    assert _measure(page, _cfg("auto", SHRINK)) == _measure(page, _cfg("auto", SHRINK, safe=8.0))
    assert _measure(page, _cfg("fixed", SHRINK)) != _measure(page, _cfg("fixed", SHRINK, safe=8.0))


def test_extend_does_not_protect_a_too_narrow_fixed_target(page):
    """Bulgu: 'Sayfa uzasın' yalnız boyu uzatır; hedef genişlik yetmezse sağdan kırpar."""
    narrow = _cfg("fixed", EXTEND, w=210.0, top=0.0, bottom=0.0)
    assert _measure(page, narrow)[3] > 10
    assert _measure(page, _cfg("fixed", SHRINK, w=210.0, top=0.0, bottom=0.0))[3] == 0


# --- plm.relevance ----------------------------------------------------------
@pytest.mark.parametrize("choice", (EXTEND, SHRINK, CLIP))
def test_relevance_fixed_mode(choice):
    rel = plm.relevance("fixed", choice, margin_pay_active=False)
    assert rel.target and rel.overflow
    assert rel.safe_edge == (choice == SHRINK)


@pytest.mark.parametrize("choice", (EXTEND, SHRINK, CLIP))
def test_relevance_auto_mode(choice):
    assert plm.relevance("auto", choice, False) == plm.Relevance(False, False, False)
    assert plm.relevance("auto", choice, True) == plm.Relevance(False, True, False)


# --- plm.result_sentence ----------------------------------------------------
_KW = dict(src_w_mm=210.0, src_h_mm=297.0, gutter_enabled=True, target_w_mm=225.0,
           target_h_mm=297.0, odd_x_mm=15.0, even_x_mm=0.0, odd_y_mm=0.0, even_y_mm=0.0,
           safe_edge_mm=0.0, margin_enabled=True, top_mm=4.0, bottom_mm=10.0)


@pytest.mark.parametrize("mode", ("fixed", "auto"))
def test_result_sentence_matches_engine_layout(mode):
    ext = plm.result_sentence(mode, EXTEND, **_KW)
    assert ext == "Sayfa 225.0 × 311.0 mm olur; içerik %100 ölçekte kalır, hiçbir şey kesilmez."
    shr = plm.result_sentence(mode, SHRINK, **_KW)
    assert "225.0 × 297.0" in shr and "küçülür" in shr and "kesilmez" in shr
    clip = plm.result_sentence(mode, CLIP, **_KW)
    assert "%100 ölçekte" in clip and "kesilebilir (üst 6.0 mm)" in clip


def test_result_sentence_warns_when_fixed_width_is_too_small():
    kw = dict(_KW, target_w_mm=210.0, top_mm=0.0, bottom_mm=0.0)
    assert "kesilebilir (sağ 15.0 mm)" in plm.result_sentence("fixed", EXTEND, **kw)


def test_result_sentence_respects_a_loaded_legacy_pair():
    text = plm.result_sentence("fixed", SHRINK, engine_pair=("shrink", "expand"), **_KW)
    assert "311.0" in text   # eski birleşim "shrink + expand": sayfa uzar


def test_result_sentence_without_modules_is_the_source_page():
    kw = dict(_KW, gutter_enabled=False, margin_enabled=False)
    assert plm.result_sentence("fixed", CLIP, **kw).startswith("Sayfa 210.0 × 297.0 mm olur")


# --- Yükseklik notu: alt/üst boşluk dahil sayfa boyu (v2.6.15) -----------------
def test_final_height_includes_margin_pay_only_when_page_extends():
    kw = dict(target_h_mm=297.0, top_mm=0.0, bottom_mm=10.0)
    assert plm.final_height_mm("fixed", EXTEND, **kw) == 307.0
    assert plm.final_height_mm("fixed", SHRINK, **kw) == 297.0
    assert plm.final_height_mm("fixed", CLIP, **kw) == 297.0
