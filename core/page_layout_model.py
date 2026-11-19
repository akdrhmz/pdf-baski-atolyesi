"""Birleşik "Sayfa Düzeni" sekmesinin ayar modeli (P3 madde 13d, 1. parça).

Bu modül Qt'ye ve motora bağımlı DEĞİLDİR; yalnızca ``gutter_engine`` içindeki
ayar sınıflarını okur/yazar. Motor (``compute_layout``, ``validate_config``) ve
``settings.json`` biçimi değişmez: birleşik arayüz, aşağıdaki iki eşlemeyi
kullanarak eski iki ayrı ayar kümesine (``page_boxes`` / ``margins``) yazar.

1. **Taşarsa ne olsun** — ``boxes.overflow_mode`` (clip/shrink) ile
   ``margins.bottom_mode`` (expand/fit/shift) tek seçimde birleşir
   (:data:`OVERFLOW_CHOICES`). Eşleme tablosu :data:`CHOICE_TO_ENGINE` içinde açık
   yazılıdır; çıktı ebadı bu tabloya bağlıdır (``tests/test_page_layout_model.py``).
2. **Özel sayfalar** — her sayfa grubu için tek kural ("hiçbir pay yok / yalnız cilt
   payı / yalnız alt-üst boşluk"); kurallar iki motor listesine
   (``boxes.exclude_pages_*``, ``margins.exclude_pages_*``) eşlenir.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set, Tuple

from core.gutter_engine import (
    MAX_PAGE_NUMBER,
    MarginSettings,
    PageBoxSettings,
    PdfProcessConfig,
    compute_layout,
    excluded_pages,
    invalid_range_tokens,
    mm_to_pt,
    parse_page_ranges,
    pt_to_mm,
)

# ---------------------------------------------------------------------------
# 1) Taşarsa ne olsun
# ---------------------------------------------------------------------------
CHOICE_EXTEND = "extend"   # sayfa uzasın, hiçbir şey küçülmez/kesilmez
CHOICE_SHRINK = "shrink"   # içerik küçülür, sayfa ebadı sabit, kırpma yok
CHOICE_CLIP = "clip"       # sayfa ebadı sabit, taşan kısım kırpılabilir

#: Arayüzde gösterilen sıra, etiket ve açıklama.
OVERFLOW_CHOICES: Dict[str, Tuple[str, str]] = {
    CHOICE_EXTEND: (
        "Sayfa uzasın (kırpmaz, önerilen)",
        "Alt/üst boşluk sayfa boyunu uzatır; içerik %100 ölçekte kalır.",
    ),
    CHOICE_SHRINK: (
        "İçerik küçülsün (kırpmaz)",
        "Sayfa ebadı sabit kalır; içerik orantılı küçülür, hiçbir şey kesilmez.",
    ),
    CHOICE_CLIP: (
        "Taşan kırpılsın (kırpabilir)",
        "Sayfa ebadı sabit kalır; sığmayan kısım kesilir (önizlemede kırmızı uyarı).",
    ),
}

#: Seçim -> (boxes.overflow_mode, margins.bottom_mode). AÇIK EŞLEME TABLOSU.
CHOICE_TO_ENGINE: Dict[str, Tuple[str, str]] = {
    CHOICE_EXTEND: ("clip", "expand"),
    CHOICE_SHRINK: ("shrink", "fit"),
    CHOICE_CLIP: ("clip", "shift"),
}

#: Arayüzdeki seçim adları (etiketin parantezsiz hali). Uyarı, diyalog ve ipucu metinleri
#: seçimlerden hep bu adlarla söz eder (P2-35: tek sözlük).
CHOICE_NAMES: Dict[str, str] = {
    key: label.split(" (")[0] for key, (label, _note) in OVERFLOW_CHOICES.items()
}

_ENGINE_SHIFT_WARNING = "'Kaydır' modu"


def ui_warning(message: str) -> str:
    """Motor uyarısını arayüz terimleriyle yazar; tanımadığı metni aynen döndürür.

    Motor, arayüzdeki seçim adlarını bilmez (``bottom_mode='shift'`` ...); eşleme burada
    yapılır, motor çıktısı ve testleri değişmez.
    """
    if message.startswith(_ENGINE_SHIFT_WARNING):
        return (f"“{CHOICE_NAMES[CHOICE_CLIP]}” seçimi sayfa dışına taşan içeriği kırpar. "
                f"Kırpmasız seçenekler: “{CHOICE_NAMES[CHOICE_EXTEND]}” veya "
                f"“{CHOICE_NAMES[CHOICE_SHRINK]}”.")
    return message


# ---------------------------------------------------------------------------
# Hangi denetim hangi durumda etkili (P2-36, çözümleme tablosu)
# ---------------------------------------------------------------------------
SIZE_FIXED = "fixed"
SIZE_AUTO = "auto"


@dataclass(frozen=True)
class Relevance:
    """"Sayfa boyutu ve sığdırma" bölümünde hangi satırın görüneceği.

    Kural, motorda ölçülmüş davranıştan gelir (``docs/app-bolme-plani.md`` madde 36):

    * ``target``  — hedef ebat (hazır kağıt, genişlik, yükseklik): yalnız **sabit** ebatta.
    * ``overflow`` — "Taşarsa ne olsun": sabit ebatta her zaman; **kaynak ebat** modunda
      yalnız alt/üst boşluk varsa (seçim ``margins.bottom_mode``'u da belirler; sayfa
      yüksekliği kaynakla aynı kalacağı için boşluk sığmayabilir).
    * ``safe_edge`` — güvenli kenar: yalnız sabit ebat **ve** "İçerik küçülsün".
    """
    target: bool
    overflow: bool
    safe_edge: bool


def relevance(size_mode: str, choice: str, margin_pay_active: bool) -> Relevance:
    """Ebat moduna, taşma seçimine ve alt/üst boşluğun etkinliğine göre görünür satırlar."""
    fixed = size_mode == SIZE_FIXED
    return Relevance(
        target=fixed,
        overflow=fixed or margin_pay_active,
        safe_edge=fixed and choice == CHOICE_SHRINK,
    )


def final_height_mm(size_mode: str, choice: str, *, target_h_mm: float, top_mm: float,
                    bottom_mm: float, engine_pair: Optional[Tuple[str, str]] = None) -> float:
    """Alt/üst boşluk dahil oluşacak sayfa yüksekliği (sabit ebatta; motorun yerleşiminden)."""
    ov, bm = engine_pair if engine_pair is not None else choice_to_engine(choice)
    cfg = PdfProcessConfig()
    cfg.page_boxes = PageBoxSettings(enabled=True, target_width_mm=100.0,
                                     target_height_mm=target_h_mm, size_mode=size_mode,
                                     overflow_mode=ov)
    cfg.margins = MarginSettings(enabled=True, extra_top_mm=top_mm,
                                 extra_bottom_mm=bottom_mm, bottom_mode=bm)
    lay = compute_layout(mm_to_pt(100.0), mm_to_pt(target_h_mm), cfg, 0)
    return round(pt_to_mm(lay.target_h), 1)


def result_sentence(size_mode: str, choice: str, *, src_w_mm: float, src_h_mm: float,
                    gutter_enabled: bool, target_w_mm: float, target_h_mm: float,
                    odd_x_mm: float, even_x_mm: float, odd_y_mm: float, even_y_mm: float,
                    safe_edge_mm: float, margin_enabled: bool, top_mm: float,
                    bottom_mm: float, engine_pair: Optional[Tuple[str, str]] = None) -> str:
    """Geçerli seçimin sonucunu tek cümleyle yazar (motorun kendi yerleşiminden hesaplanır).

    Sayfa içeriğinin kaynak sayfanın kenarına kadar uzandığı en kötü durum varsayılır:
    kırpma tahmini bu yüzden "kesilebilir" der; gerçek tarama ``scan_clipping``'dedir.
    """
    ov, bm = engine_pair if engine_pair is not None else choice_to_engine(choice)
    cfg = PdfProcessConfig()
    cfg.page_boxes = PageBoxSettings(
        enabled=gutter_enabled, target_width_mm=target_w_mm, target_height_mm=target_h_mm,
        odd_x_mm=odd_x_mm, odd_y_mm=odd_y_mm, even_x_mm=even_x_mm, even_y_mm=even_y_mm,
        size_mode=size_mode, overflow_mode=ov, safe_edge_mm=safe_edge_mm)
    cfg.margins = MarginSettings(
        enabled=margin_enabled, extra_top_mm=top_mm, extra_bottom_mm=bottom_mm, bottom_mode=bm)
    lay = compute_layout(mm_to_pt(src_w_mm), mm_to_pt(src_h_mm), cfg, 0)
    tol = 0.3
    over = {
        "sol": pt_to_mm(max(0.0, -lay.content.x0)),
        "sağ": pt_to_mm(max(0.0, lay.content.x1 - lay.target_w)),
        "üst": pt_to_mm(max(0.0, -lay.content.y0)),
        "alt": pt_to_mm(max(0.0, lay.content.y1 - lay.target_h)),
    }
    over = {k: v for k, v in over.items() if v > tol}
    parts = [f"Sayfa {pt_to_mm(lay.target_w):.1f} × {pt_to_mm(lay.target_h):.1f} mm olur"]
    if lay.scale < 0.9995:
        parts.append(f"içerik %{lay.scale * 100:.0f} ölçeğine küçülür")
    else:
        parts.append("içerik %100 ölçekte kalır")
    if over:
        edges = ", ".join(f"{k} {v:.1f} mm" for k, v in over.items())
        parts.append(f"sığmayan kısım kesilebilir ({edges})")
    else:
        parts.append("hiçbir şey kesilmez")
    return f"{parts[0]}; {parts[1]}, {parts[2]}."


#: Ters tablo (yalnızca kanonik üç çift).
ENGINE_TO_CHOICE: Dict[Tuple[str, str], str] = {v: k for k, v in CHOICE_TO_ENGINE.items()}

#: Motorun kabul ettiği ama üç seçime TAM oturmayan eski birleşimlerin en yakın seçimi.
#: Bu çiftler yüklenince ``exact=False`` döner ve kullanıcı seçim değiştirene kadar
#: aynen korunur (kayıtlı ayarın çıktısı sessizce değişmesin).
LEGACY_NEAREST: Dict[Tuple[str, str], str] = {
    ("shrink", "expand"): CHOICE_SHRINK,
    ("shrink", "shift"): CHOICE_SHRINK,
    ("clip", "fit"): CHOICE_SHRINK,
}

VALID_OVERFLOW = ("clip", "shrink")
VALID_BOTTOM = ("expand", "fit", "shift")


@dataclass(frozen=True)
class OverflowState:
    """Motor çiftinin birleşik karşılığı."""
    choice: str
    exact: bool   # False: eski birleşim; en yakın seçim gösterilir, çift korunur


def choice_to_engine(choice: str) -> Tuple[str, str]:
    """Birleşik seçimi ``(overflow_mode, bottom_mode)`` çiftine çevirir."""
    try:
        return CHOICE_TO_ENGINE[choice]
    except KeyError:
        raise ValueError(f"Bilinmeyen taşma seçimi: {choice!r}") from None


def engine_to_choice(overflow_mode: str, bottom_mode: str) -> OverflowState:
    """Motor çiftini birleşik seçime çevirir; bilinmeyen değerler varsayılana düşer."""
    if overflow_mode not in VALID_OVERFLOW:
        overflow_mode = "clip"
    if bottom_mode not in VALID_BOTTOM:
        bottom_mode = "expand"
    pair = (overflow_mode, bottom_mode)
    if pair in ENGINE_TO_CHOICE:
        return OverflowState(ENGINE_TO_CHOICE[pair], True)
    return OverflowState(LEGACY_NEAREST[pair], False)


def resolve_engine_pair(choice: str, loaded: Optional[Tuple[str, str]] = None) -> Tuple[str, str]:
    """Arayüzdeki seçimden motor çiftini üretir.

    ``loaded``: dosyadan yüklenen özgün çift. Seçim, o çiftin gösterdiği seçimle
    aynıysa (kullanıcı dokunmadıysa) özgün çift AYNEN döner; böylece eski bir
    "shrink + expand" ayarı kaydedip açınca çıktı değişmez.
    """
    if loaded is not None:
        state = engine_to_choice(*loaded)
        if not state.exact and state.choice == choice:
            return (loaded[0] if loaded[0] in VALID_OVERFLOW else "clip",
                    loaded[1] if loaded[1] in VALID_BOTTOM else "expand")
    return choice_to_engine(choice)


# ---------------------------------------------------------------------------
# 2) Özel sayfalar
# ---------------------------------------------------------------------------
MODE_NONE = "none"             # hiçbir pay uygulanmasın
MODE_GUTTER_ONLY = "gutter"    # yalnızca cilt payı (alt/üst boşluk yok) — ara kapak
MODE_MARGIN_ONLY = "margin"    # yalnızca alt/üst boşluk (cilt payı yok)

#: Arayüzdeki sıra ve etiketler.
SPECIAL_MODES: Dict[str, str] = {
    MODE_NONE: "Hiçbir pay uygulanmasın",
    MODE_GUTTER_ONLY: "Yalnızca cilt payı uygulansın (alt/üst boşluk yok)",
    MODE_MARGIN_ONLY: "Yalnızca alt/üst boşluk uygulansın",
}


@dataclass(frozen=True)
class SpecialRule:
    """Bir sayfa grubu ve ona uygulanacak pay türü. ``pages``: '1, 5, 9-10'."""
    pages: str
    mode: str = MODE_GUTTER_ONLY


def ara_kapak_rule(pages: str) -> SpecialRule:
    """Hızlı düğme "Ara kapak: yalnız cilt payı"."""
    return SpecialRule(pages, MODE_GUTTER_ONLY)


class RuleError(ValueError):
    """Özel sayfa kuralı anlaşılamadı; ``tokens`` anlaşılamayan parçalar."""

    def __init__(self, message: str, tokens: Optional[List[str]] = None):
        super().__init__(message)
        self.tokens = list(tokens or [])


def compact_ranges(pages: Iterable[int]) -> str:
    """{1, 5, 9, 10} -> '1, 5, 9-10' (sıralı, ardışıklar aralığa çevrilir)."""
    ordered = sorted({int(p) for p in pages if 1 <= int(p) <= MAX_PAGE_NUMBER})
    parts: List[str] = []
    i = 0
    while i < len(ordered):
        j = i
        while j + 1 < len(ordered) and ordered[j + 1] == ordered[j] + 1:
            j += 1
        parts.append(str(ordered[i]) if i == j else f"{ordered[i]}-{ordered[j]}")
        i = j + 1
    return ", ".join(parts)


def _parse_rule_pages(rule: SpecialRule) -> Set[int]:
    if rule.mode not in SPECIAL_MODES:
        raise RuleError(f"Bilinmeyen özel sayfa seçimi: {rule.mode!r}")
    bad = invalid_range_tokens(rule.pages)
    if bad:
        raise RuleError("Anlaşılamayan sayfa aralığı: " + ", ".join(bad), bad)
    return parse_page_ranges(rule.pages)


def rules_to_excludes(rules: Iterable[SpecialRule]) -> Tuple[str, str]:
    """Kuralları motor listelerine çevirir: ``(boxes_exclude, margins_exclude)``.

    * ``none``   -> iki listeye de girer.
    * ``gutter`` -> yalnızca ``margins`` listesine girer (cilt payı uygulanır).
    * ``margin`` -> yalnızca ``boxes`` listesine girer (alt/üst boşluk uygulanır).

    Bir sayfa birden çok kuralda geçerse dışlamalar BİRLEŞİR (``gutter`` + ``margin``
    = ikisi de dışlanır = ``none``); :func:`overlapping_pages` bunu arayüze bildirir.
    """
    boxes: Set[int] = set()
    margins: Set[int] = set()
    for rule in rules:
        pages = _parse_rule_pages(rule)
        if rule.mode in (MODE_NONE, MODE_MARGIN_ONLY):
            boxes |= pages
        if rule.mode in (MODE_NONE, MODE_GUTTER_ONLY):
            margins |= pages
    return compact_ranges(boxes), compact_ranges(margins)


def overlapping_pages(rules: Iterable[SpecialRule]) -> List[int]:
    """Birden çok kuralda geçen sayfalar (arayüz uyarısı için)."""
    seen: Set[int] = set()
    dup: Set[int] = set()
    for rule in rules:
        pages = _parse_rule_pages(rule)
        dup |= pages & seen
        seen |= pages
    return sorted(dup)


def excludes_to_rules(boxes: PageBoxSettings, margins: MarginSettings) -> List[SpecialRule]:
    """Kayıtlı iki muaf listesini birleşik kurallara çevirir (``*_str`` ve ``*_set`` birlikte).

    Kurallar sabit sırada döner: önce ``none``, sonra ``gutter``, sonra ``margin``.
    Boş gruplar atlanır.
    """
    box_pages = excluded_pages(boxes)
    margin_pages = excluded_pages(margins)
    groups = (
        (MODE_NONE, box_pages & margin_pages),
        (MODE_GUTTER_ONLY, margin_pages - box_pages),
        (MODE_MARGIN_ONLY, box_pages - margin_pages),
    )
    return [SpecialRule(compact_ranges(pages), mode) for mode, pages in groups if pages]


def apply_rules(boxes: PageBoxSettings, margins: MarginSettings,
                rules: Iterable[SpecialRule]) -> None:
    """Kuralları iki ayar nesnesine yazar (``*_str`` yazılır, ``*_set`` boşaltılır).

    ``*_set`` boşaltılır çünkü :func:`excludes_to_rules` onu zaten kurallara kattı;
    metin tek doğruluk kaynağı olur ve eski küme sessizce geri gelmez.
    """
    boxes_text, margins_text = rules_to_excludes(rules)
    boxes.exclude_pages_str, boxes.exclude_pages_set = boxes_text, set()
    margins.exclude_pages_str, margins.exclude_pages_set = margins_text, set()


# ---------------------------------------------------------------------------
# Birleşik okuma/yazma (tek çağrı)
# ---------------------------------------------------------------------------
def read_unified(boxes: PageBoxSettings, margins: MarginSettings
                 ) -> Tuple[OverflowState, List[SpecialRule]]:
    """Kayıtlı iki ayar kümesinden birleşik sekmenin başlangıç durumunu çıkarır."""
    return (engine_to_choice(boxes.overflow_mode, margins.bottom_mode),
            excludes_to_rules(boxes, margins))


def write_unified(boxes: PageBoxSettings, margins: MarginSettings, choice: str,
                  rules: Iterable[SpecialRule],
                  loaded_pair: Optional[Tuple[str, str]] = None) -> None:
    """Birleşik sekmenin durumunu iki ayar kümesine yazar."""
    boxes.overflow_mode, margins.bottom_mode = resolve_engine_pair(choice, loaded_pair)
    apply_rules(boxes, margins, rules)
