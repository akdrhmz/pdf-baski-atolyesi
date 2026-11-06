"""Madde 36 / adım 1: hangi denetim hangi ebat modunda + hangi 'Taşarsa ne olsun' seçiminde etkili?"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymupdf
import gutter_engine as ge
import page_layout_model as plm

doc = pymupdf.open(); pg = doc.new_page(width=595.28, height=841.89)
pg.draw_rect(pymupdf.Rect(0.5, 0.5, 594.8, 841.4), fill=(0, 0, 0))   # içerik hemen hemen sayfa boyunda
page = doc[0]

def cfg(mode, choice, w=225, h=297, safe=0.0, top=4.0, bottom=10.0, gutter=15.0, margins_on=True):
    ov, bm = plm.CHOICE_TO_ENGINE[choice]
    c = ge.PdfProcessConfig()
    c.page_boxes = ge.PageBoxSettings(enabled=True, target_width_mm=w, target_height_mm=h,
        odd_x_mm=gutter, size_mode=mode, overflow_mode=ov, safe_edge_mm=safe)
    c.margins = ge.MarginSettings(enabled=margins_on, extra_top_mm=top, extra_bottom_mm=bottom, bottom_mode=bm)
    return c

def measure(c):
    lay = ge.compute_layout(page.rect.width, page.rect.height, c, 0)
    l, r, t, b = ge.clip_edges_for_page(page, lay)
    return dict(w=round(ge.pt_to_mm(lay.target_w), 1), h=round(ge.pt_to_mm(lay.target_h), 1),
                scale=round(lay.scale, 3), clip=round(l + r + t + b, 1), clip_edges=[round(x,1) for x in (l,r,t,b)])

CONTROLS = {
    "Hedef ebat (genişlik/yükseklik)": dict(w=250, h=330),
    "Güvenli kenar": dict(safe=8.0),
    "Taşarsa ne olsun (seçim)": None,  # özel
    "Alt/üst boşluk": dict(top=14.0, bottom=30.0),
}
out = {}
for mode in ("fixed", "auto"):
    for choice in (plm.CHOICE_EXTEND, plm.CHOICE_SHRINK, plm.CHOICE_CLIP):
        base = measure(cfg(mode, choice))
        row = {"base": base}
        for name, delta in CONTROLS.items():
            if delta is None:
                alts = [measure(cfg(mode, c2)) for c2 in (plm.CHOICE_EXTEND, plm.CHOICE_SHRINK, plm.CHOICE_CLIP) if c2 != choice]
                row[name] = any(a != base for a in alts)
            else:
                row[name] = measure(cfg(mode, choice, **delta)) != base
        out[f"{mode}/{choice}"] = row
        print(mode, choice, base)
        print("   ", {k: v for k, v in row.items() if k != "base"})

# boşluk kapalı iken seçim etkisi
print("\n-- alt/üst boşluk 0 iken 'taşarsa' seçimi (auto)")
for choice in (plm.CHOICE_EXTEND, plm.CHOICE_SHRINK, plm.CHOICE_CLIP):
    print(choice, measure(cfg("auto", choice, top=0, bottom=0)))
print("-- fixed, boşluk 0")
for choice in (plm.CHOICE_EXTEND, plm.CHOICE_SHRINK, plm.CHOICE_CLIP):
    print(choice, measure(cfg("fixed", choice, top=0, bottom=0)))
