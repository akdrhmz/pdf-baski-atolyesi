"""
PDF Baskı & Cilt Stüdyosu - Geometri, Numaralandırma ve Birleştirme Motoru
Geliştirici: Abdülkadir Hamza (support@kadirhamza.com)

PyMuPDF ile vektörel (yeniden örneklemesiz) PDF dönüşümleri yapar.

Tasarım ilkeleri
- Tek doğruluk kaynağı: ``compute_layout`` ve ``numbering_plan`` hem işleme,
  hem kırpma taraması, hem doğrulama, hem de arayüz önizlemesi tarafından
  kullanılır. Böylece önizlenen sonuç ile üretilen dosya aynı olur.
- Kaynak dosyaya asla yazılmaz; çıktı önce geçici dosyaya yazılır, başarılı
  olursa asıl yola taşınır (atomik kayıt).
- Kullanıcıya gösterilecek hatalar ``StudioError`` türevleridir ve Türkçedir.
"""

from __future__ import annotations

import os
import re
import tempfile
import threading
from functools import wraps
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple, Union

import pymupdf

PDF_LOCK = threading.RLock()


def pdf_operation(function):
    """MuPDF işlemlerini önizleme/küçük resim/çıktı işçileri arasında sıralar."""
    @wraps(function)
    def locked(*args, **kwargs):
        with PDF_LOCK:
            return function(*args, **kwargs)
    return locked

# ---------------------------------------------------------------------------
# Birimler
# ---------------------------------------------------------------------------
# 1 PostScript noktası = 1/72 inç, 1 inç = 25.4 mm
PT_PER_MM = 72.0 / 25.4
MM_PER_PT = 25.4 / 72.0

# birim kodu -> (arayüz etiketi, 1 birimin mm karşılığı)
UNITS: Dict[str, Tuple[str, float]] = {
    "mm": ("mm", 1.0),
    "cm": ("cm", 10.0),
    "in": ("inç", 25.4),
    "pt": ("pt", MM_PER_PT),
}


def mm_to_pt(mm: float) -> float:
    """Milimetreyi PDF noktasına (point) çevirir."""
    return mm * PT_PER_MM


def pt_to_mm(pt: float) -> float:
    """PDF noktasını milimetreye çevirir."""
    return pt * MM_PER_PT


def mm_to_unit(mm: float, unit: str) -> float:
    """Milimetreyi seçili arayüz birimine çevirir."""
    return mm / UNITS.get(unit, UNITS["mm"])[1]


def unit_to_mm(value: float, unit: str) -> float:
    """Seçili arayüz birimini milimetreye çevirir."""
    return value * UNITS.get(unit, UNITS["mm"])[1]


def format_measure(mm: float, unit: str) -> str:
    """Sayıyı birim duyarlılığında kısa metne çevirir (ör. 15, 2.54, 0.59)."""
    value = mm_to_unit(mm, unit)
    if unit == "in":
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return f"{value:.2f}".rstrip("0").rstrip(".")


# ---------------------------------------------------------------------------
# Hata türleri (hepsi kullanıcıya gösterilebilir Türkçe mesaj taşır)
# ---------------------------------------------------------------------------
class StudioError(Exception):
    """Uygulamanın bildiği, kullanıcıya olduğu gibi gösterilebilecek hata."""


class PdfOpenError(StudioError):
    """PDF açılamadı ya da bozuk."""


class PdfPasswordError(PdfOpenError):
    """PDF parola ile korunuyor."""


class OutputPathError(StudioError):
    """Çıktı yolu geçersiz ya da kaynakla çakışıyor."""


class ConfigError(StudioError):
    """Ayarlar geçersiz. ``problems`` alanı ayrıntıları listeler."""

    def __init__(self, problems: List[str]):
        self.problems = list(problems)
        super().__init__("Ayarlar geçersiz:\n• " + "\n• ".join(self.problems))


class ProcessCancelled(StudioError):
    """Kullanıcı işlemi iptal etti."""


# ---------------------------------------------------------------------------
# Yardımcılar
# ---------------------------------------------------------------------------
MAX_PAGE_NUMBER = 100_000  # "1-99999999" gibi girişler arayüzü kilitlemesin


def _normalize_range_text(text: str) -> str:
    """Word'den yapıştırılan uzun tire ve noktalı virgülü standart karakterlere çevirir."""
    for dash in ("\u2013", "\u2014", "\u2212", "\u2010", "\u2011"):
        text = text.replace(dash, "-")
    return text.replace(";", ",")


def parse_page_ranges(range_str: str) -> Set[int]:
    """
    '1, 2, 5, 10-12, 20' gibi virgüllü ve aralıklı sayfa numarası
    dizelerini bir tamsayı kümesine {1, 2, 5, 10, 11, 12, 20} dönüştürür.
    Hatalı karakterler girilse bile çökmeye karşı dayanıklıdır. Uzun tire (–)
    ve noktalı virgül kabul edilir; MAX_PAGE_NUMBER üstü değerler yok sayılır.
    """
    pages: Set[int] = set()
    if not range_str or not range_str.strip():
        return pages

    parts = [p.strip() for p in _normalize_range_text(range_str).split(",") if p.strip()]
    for part in parts:
        match_range = re.match(r"^(\d+)\s*-\s*(\d+)$", part)
        if match_range:
            start, end = sorted((int(match_range.group(1)), int(match_range.group(2))))
            start = max(start, 1)
            end = min(end, MAX_PAGE_NUMBER)
            if start <= end:
                pages.update(range(start, end + 1))
            continue

        match_single = re.match(r"^(\d+)$", part)
        if match_single:
            value = int(match_single.group(1))
            if 1 <= value <= MAX_PAGE_NUMBER:
                pages.add(value)

    return pages


def invalid_range_tokens(range_str: str) -> List[str]:
    """Sayfa aralığı girişinde anlaşılamayan parçaları döndürür (arayüz uyarısı için)."""
    bad: List[str] = []
    for part in (p.strip() for p in _normalize_range_text(range_str or "").split(",")):
        if part and not re.match(r"^\d+(\s*-\s*\d+)?$", part):
            bad.append(part)
    return bad


def sanitize_toc(toc: List[list]) -> List[list]:
    """
    PyMuPDF ``set_toc`` ilk girdinin seviye 1 olmasını ve seviyelerin en fazla
    1 artmasını ister. Aralık seçimi veya birleştirme sonrası bu bozulabilir;
    seviyeleri düzelterek tüm yer imlerini korur.
    """
    fixed: List[list] = []
    prev = 0
    for entry in toc:
        level = int(entry[0])
        level = max(1, min(level, prev + 1))
        fixed.append([level] + list(entry[1:]))
        prev = level
    return fixed


def same_path(a: str, b: str) -> bool:
    """İki yolun aynı dosyayı gösterip göstermediğini (büyük/küçük harf duyarsız) söyler."""
    try:
        return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))
    except (OSError, ValueError):
        return False


def unique_output_path(path: str) -> str:
    """Dosya varsa 'ad (2).pdf', 'ad (3).pdf' ... şeklinde boş bir ad döndürür."""
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    for index in range(2, 1000):
        candidate = f"{base} ({index}){ext}"
        if not os.path.exists(candidate):
            return candidate
    return f"{base} ({os.getpid()}){ext}"


def open_pdf(path: str) -> pymupdf.Document:
    """PDF'i açar; sorun varsa anlaşılır Türkçe hata fırlatır."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Dosya bulunamadı: {path}")
    if os.path.isdir(path):
        raise PdfOpenError(f"'{path}' bir klasör; PDF dosyası seçin.")
    name = os.path.basename(path)
    try:
        doc = pymupdf.open(path)
    except Exception as exc:  # PyMuPDF çok çeşitli istisnalar fırlatabilir
        raise PdfOpenError(
            f"'{name}' açılamadı. Dosya bozuk ya da PDF değil olabilir.\n({exc})"
        ) from exc
    if doc.needs_pass:
        doc.close()
        raise PdfPasswordError(
            f"'{name}' parola ile korunuyor. Parolayı kaldırıp (ör. tarayıcıda "
            "'PDF olarak yazdır' ile) yeniden deneyin."
        )
    if not doc.is_pdf:
        doc.close()
        raise PdfOpenError(f"'{name}' bir PDF belgesi değil.")
    if len(doc) == 0:
        doc.close()
        raise PdfOpenError(f"'{name}' hiç sayfa içermiyor.")
    return doc


def _pdf_box(doc: pymupdf.Document, page: pymupdf.Page, key: str) -> Optional[pymupdf.Rect]:
    """Sayfa sözlüğündeki MediaBox/CropBox değerini PDF koordinatında okur."""
    try:
        kind, value = doc.xref_get_key(page.xref, key)
        if kind != "array":
            return None
        numbers = [float(part) for part in value.strip("[]").split()]
        if len(numbers) != 4:
            return None
        return pymupdf.Rect(*numbers)
    except Exception:
        return None


def _pdf_box_text(rect: pymupdf.Rect) -> str:
    return f"[{rect.x0:g} {rect.y0:g} {rect.x1:g} {rect.y1:g}]"


def _prepend_content(page: pymupdf.Page, command: str) -> None:
    """Sayfanın ilk içerik akışının başına ham PDF komutu ekler (yalnızca bellekte)."""
    doc = page.parent
    try:
        xrefs = page.get_contents()
    except Exception:
        return
    if not xrefs:
        return
    xref = xrefs[0]
    try:
        data = doc.xref_stream(xref)
        doc.update_stream(xref, command.encode("ascii") + data)
    except Exception:
        return


def normalize_page_rotations(doc: pymupdf.Document) -> int:
    """
    ``/Rotate`` değeri sıfırdan farklı sayfaları görünür hâle getirir: içerik
    derotasyon matrisiyle içeriğe işlenir, sayfa 0° olur. Görünür alan aynı kalır.

    PyMuPDF'in ``show_pdf_page`` fonksiyonu kaynak sayfanın ``/Rotate`` değerini
    uygulamaz; döndürülmüş sayfa, döndürülmemiş koordinatlarıyla yerleştirilir ve
    alt kısmı kırpılır. İşleme ve önizleme bu yüzden önce burada normalize eder.

    ``remove_rotation`` CropBox'u taşımadığı için kırpılmış sayfada önce görünür
    alan (CropBox ∩ MediaBox) içerik kaydırılarak sayfa köşesine taşınır; böylece
    döndürme + kırpma kombinasyonu da piksel piksel korunur. Yalnızca bellekteki
    kopya değişir; kaynak dosya hiçbir zaman yazılmaz. Değiştirilen sayfa sayısını
    döndürür.
    """
    changed = 0
    for pno in range(len(doc)):
        page = doc[pno]
        try:
            if not page.rotation:
                continue
            media = _pdf_box(doc, page, "MediaBox")
            crop = _pdf_box(doc, page, "CropBox")
        finally:
            del page  # kutular değişecekse taze sayfa nesnesi gerekir

        if media is not None and crop is not None:
            visible = crop & media
            if visible != media and not visible.is_empty:
                page = doc[pno]
                _prepend_content(page, f"1 0 0 1 {-visible.x0:g} {-visible.y0:g} cm ")
                box = _pdf_box_text(pymupdf.Rect(0, 0, visible.width, visible.height))
                doc.xref_set_key(page.xref, "MediaBox", box)
                doc.xref_set_key(page.xref, "CropBox", box)
                del page

        page = doc[pno]
        try:
            page.remove_rotation()
        except Exception as exc:
            raise PdfOpenError(
                f"Sayfa {pno + 1} döndürmesi düzeltilemedi. Dosyayı başka bir PDF "
                "programında 'PDF olarak yazdır' ile yeniden kaydedip tekrar deneyin."
                f"\n({exc})"
            ) from exc
        changed += 1
    return changed


# ---------------------------------------------------------------------------
# Ayar sınıfları
# ---------------------------------------------------------------------------
@dataclass
class PageBoxSettings:
    """
    Sayfa kutusu ve cilt payı yerleşim ayarları.

    size_mode:
      - 'fixed': hedef genişlik/yükseklik sabittir (Acrobat 'Sabit Boyut').
      - 'auto' : her sayfanın hedef ebadı kendi ebadı + cilt payı olur; karışık
                 ebatlı belgelerde de hiçbir sayfa istemeden kırpılmaz.

    overflow_mode (yalnızca 'fixed'):
      - 'clip'  : hedefe sığmayan içerik kırpılır (eski davranış).
      - 'shrink': içerik hedefe sığacak kadar küçültülür; hiçbir şey kırpılmaz.
                 En-boy oranı her zaman korunur.
    safe_edge_mm: küçültmede kenarda bırakılacak ek güvenlik payı.

    exclude_pages_str/set: bu sayfalara cilt payı uygulanmaz (sayfa numaralandırma
    ve kenar boşluğu ayarlarından bağımsızdır).
    """
    enabled: bool = True
    target_width_mm: float = 225.0
    target_height_mm: float = 297.0
    odd_x_mm: float = 15.0
    odd_y_mm: float = 0.0
    even_x_mm: float = 0.0
    even_y_mm: float = 0.0
    size_mode: str = "fixed"
    overflow_mode: str = "clip"
    safe_edge_mm: float = 0.0
    exclude_pages_str: str = ""
    exclude_pages_set: Set[int] = field(default_factory=set)
    binding: str = "left"


@dataclass
class MarginSettings:
    """
    Sayfa altı ve üstü ekstra boşluk ayarları.

    bottom_mode:
      - 'expand': Sayfa yüksekliğine payı ekler. İçerik %100 ölçekte kalır,
                  hiçbir şey kırpılmaz (Acrobat davranışı).
      - 'fit'   : Sayfa ebadı sabit kalır, içerik orantılı küçülür. Kırpma yok.
      - 'shift' : Sayfa ebadı sabit kalır, içerik kaydırılır. Sayfa dışına
                  taşan kısım KIRPILIR (tarama bunu önceden bildirir).

    exclude_pages_str/set: bu sayfalara alt/üst pay uygulanmaz (cilt payından
    bağımsızdır; örn. cilt payı verilip kenar boşluğu verilmeyen ara kapak).
    """
    enabled: bool = True
    extra_bottom_mm: float = 0.0
    extra_top_mm: float = 0.0
    bottom_mode: str = "expand"
    exclude_pages_str: str = ""
    exclude_pages_set: Set[int] = field(default_factory=set)


@dataclass
class PageNumberSettings:
    """Sayfa numarası yerleşim, biçimlendirme ve ara kapak atlama ayarları."""
    enabled: bool = True
    position: str = "outer"           # "outer" (Dış Kenar), "center" (Orta), "inner" (İç Kenar)
    vertical_pos: str = "bottom"      # "bottom" (Alt Kenar), "top" (Üst Kenar)
    format_style: str = "number"      # number, dash, total, label, roman, roman_upper
    text_template: str = ""           # {n}, {N}, {roman}, {ROMAN}, {label}
    font_path: str = ""               # boşsa gerekirse Windows Unicode yazı tipi bulunur
    start_num: int = 1                # İlk sayfaya verilecek numara
    start_page: int = 1               # Numaralandırmanın başlayacağı sayfa sırası (örn: 2 = kapağı atla)
    font_size: float = 10.0
    font_color: tuple = (0.0, 0.0, 0.0)
    bottom_margin_mm: float = 12.0    # Metnin taban çizgisinin sayfa altından uzaklığı
    side_margin_mm: float = 15.0      # Dış kenarlardan yan boşluk
    skip_pages_str: str = ""          # Numarasız ara kapaklar / boş sayfalar metni
    skip_pages_set: Set[int] = field(default_factory=set)
    continuous_numbering: bool = True  # Kapak atlandığında numara ötelenmez (90 -> Kapak -> 91)
    sections: List[dict] = field(default_factory=list)


#: Sayfa eşitleme kipleri; sabit kağıtlar mm (genişlik, yükseklik), dikey.
FIT_PAPERS_MM = {"a5": (148.0, 210.0), "a4": (210.0, 297.0), "a3": (297.0, 420.0)}
FIT_MODES = ("off", "first", "largest", "custom") + tuple(FIT_PAPERS_MM)


@dataclass
class PdfProcessConfig:
    """Tüm PDF işleme ayarlarını barındıran üst yapılandırma sınıfı."""
    page_boxes: PageBoxSettings = field(default_factory=PageBoxSettings)
    margins: MarginSettings = field(default_factory=MarginSettings)
    page_numbers: PageNumberSettings = field(default_factory=PageNumberSettings)
    # "print": dosya yapısına dokunmadan kaydet; "standard": kullanılmayan
    # nesneleri temizleyerek dosya boyutunu küçült. İkisi de içerik kaybettirmez.
    quality_mode: str = "print"
    # Açıklamalar (not, vurgu) ve form alanları yeni sayfaya taşınamaz; True ise
    # görünümleri sayfa içeriğine gömülür (artık düzenlenemez ama görünür kalır).
    flatten_annotations: bool = True
    # 0 = kapalı. 4 verilirse sona boş sayfa eklenerek toplam 4'ün katına tamamlanır.
    pad_to_multiple: int = 0
    # Sayfaları eşit ebada sığdırma (Acrobat'taki "Yazdır > Sığdır" karşılığı; yazdırmadan):
    # "off" | "first" (ilk sayfa) | "largest" (en büyük sayfa) | "a5" | "a4" | "a3".
    # İçerik oranı bozulmadan hedefe sığdırılır ve ortalanır; cilt payı/boşluk/numara
    # bundan SONRA, eşitlenmiş sayfalara uygulanır.
    fit_mode: str = "off"
    # True: yatay sayfa yatay hedefe, dikey sayfa dikey hedefe sığar.
    fit_keep_orientation: bool = True
    # ``fit_keep_orientation`` kapalıyken: True → yatay sayfa 90° döndürülüp dikey hedefi
    # doldurur; False → yatay sayfa dikey hedefe döndürülmeden küçülerek sığar.
    fit_rotate_landscape: bool = False
    fit_width_mm: float = 210.0
    fit_height_mm: float = 297.0
    fit_margin_mm: float = 0.0

    @property
    def optimize(self) -> bool:
        return self.quality_mode != "print"


def excluded_pages(settings: Union[PageBoxSettings, MarginSettings]) -> Set[int]:
    """Bir modülün (cilt payı veya kenar boşluğu) uygulanmayacağı sayfalar."""
    pages = set(settings.exclude_pages_set)
    if settings.exclude_pages_str:
        pages.update(parse_page_ranges(settings.exclude_pages_str))
    return pages


def config_to_dict(config: PdfProcessConfig) -> Dict[str, Any]:
    """Ayarları JSON'a yazılabilir sözlüğe çevirir (profil ve son ayar kaydı)."""
    data = asdict(config)
    data["page_numbers"]["skip_pages_set"] = sorted(config.page_numbers.skip_pages_set)
    data["page_boxes"]["exclude_pages_set"] = sorted(config.page_boxes.exclude_pages_set)
    data["margins"]["exclude_pages_set"] = sorted(config.margins.exclude_pages_set)
    return data


def config_from_dict(data: Optional[Dict[str, Any]]) -> PdfProcessConfig:
    """``config_to_dict`` çıktısını (veya eski/eksik profilleri) güvenle geri yükler."""
    data = data or {}

    def _safe_color(raw) -> tuple:
        try:
            values = tuple(float(component) for component in (raw or (0.0, 0.0, 0.0)))
        except (TypeError, ValueError):
            return (0.0, 0.0, 0.0)
        if len(values) != 3:
            return (0.0, 0.0, 0.0)
        return tuple(min(1.0, max(0.0, component)) for component in values)

    boxes_raw = data.get("page_boxes") or {}
    margins_raw = data.get("margins") or {}
    numbers_raw = data.get("page_numbers") or {}

    def _page_set(raw: Dict[str, Any], key: str) -> Set[int]:
        result = set()
        for value in raw.get(key) or []:
            try:
                result.add(int(value))
            except (TypeError, ValueError):
                continue
        return result

    def pick(raw: Dict[str, Any], key: str, default: Any, cast: Callable = float) -> Any:
        value = raw.get(key, default)
        try:
            return cast(value)
        except (TypeError, ValueError):
            return default

    # Eski sürümlerde tek bir global dışlama listesi vardı; iki modüle taşınır.
    legacy_exclude = str(data.get("exclude_pages_str", ""))
    legacy_exclude_set = _page_set(data, "exclude_pages_set")

    boxes = PageBoxSettings(
        enabled=bool(boxes_raw.get("enabled", True)),
        target_width_mm=pick(boxes_raw, "target_width_mm", 225.0),
        target_height_mm=pick(boxes_raw, "target_height_mm", 297.0),
        odd_x_mm=pick(boxes_raw, "odd_x_mm", 15.0),
        odd_y_mm=pick(boxes_raw, "odd_y_mm", 0.0),
        even_x_mm=pick(boxes_raw, "even_x_mm", 0.0),
        even_y_mm=pick(boxes_raw, "even_y_mm", 0.0),
        size_mode=str(boxes_raw.get("size_mode", "fixed")),
        binding=str(boxes_raw.get("binding", "left")),
        overflow_mode=str(boxes_raw.get("overflow_mode", "clip")),
        safe_edge_mm=pick(boxes_raw, "safe_edge_mm", 0.0),
        exclude_pages_str=str(boxes_raw.get("exclude_pages_str", legacy_exclude)),
        exclude_pages_set=(_page_set(boxes_raw, "exclude_pages_set")
                           if "exclude_pages_set" in boxes_raw else legacy_exclude_set),
    )
    margins = MarginSettings(
        enabled=bool(margins_raw.get("enabled", True)),
        extra_bottom_mm=pick(margins_raw, "extra_bottom_mm", 0.0),
        extra_top_mm=pick(margins_raw, "extra_top_mm", 0.0),
        bottom_mode=str(margins_raw.get("bottom_mode", "expand")),
        exclude_pages_str=str(margins_raw.get("exclude_pages_str", legacy_exclude)),
        exclude_pages_set=(_page_set(margins_raw, "exclude_pages_set")
                           if "exclude_pages_set" in margins_raw else legacy_exclude_set),
    )
    skip_set = _page_set(numbers_raw, "skip_pages_set")
    numbers = PageNumberSettings(
        sections=[dict(start_page=pick(section, "start_page", 1, int),
                       start_num=pick(section, "start_num", 1, int),
                       format_style=str(section.get("format_style", "number")),
                       hide_first=bool(section.get("hide_first", False)),
                       blank_before=bool(section.get("blank_before", False)))
                  for section in numbers_raw.get("sections", []) if isinstance(section, dict)]
                 if isinstance(numbers_raw.get("sections", []), list) else [],
        enabled=bool(numbers_raw.get("enabled", True)),
        position=str(numbers_raw.get("position", "outer")),
        vertical_pos=("top" if str(numbers_raw.get("vertical_pos", "bottom")) == "top" else "bottom"),
        format_style=str(numbers_raw.get("format_style", "number")),
        text_template=str(numbers_raw.get("text_template", "")),
        font_path=str(numbers_raw.get("font_path", "")),
        start_num=pick(numbers_raw, "start_num", 1, int),
        start_page=pick(numbers_raw, "start_page", 1, int),
        font_size=pick(numbers_raw, "font_size", 10.0),
        font_color=_safe_color(numbers_raw.get("font_color")),
        bottom_margin_mm=pick(numbers_raw, "bottom_margin_mm", 12.0),
        side_margin_mm=pick(numbers_raw, "side_margin_mm", 15.0),
        skip_pages_str=str(numbers_raw.get("skip_pages_str", "")),
        skip_pages_set=skip_set,
        continuous_numbering=bool(numbers_raw.get("continuous_numbering", True)),
    )
    quality = str(data.get("quality_mode", "print"))
    if quality not in ("print", "standard"):
        quality = "print"
    fit_mode = str(data.get("fit_mode", "off"))
    if fit_mode not in FIT_MODES:
        fit_mode = "off"
    return PdfProcessConfig(
        page_boxes=boxes,
        margins=margins,
        page_numbers=numbers,
        quality_mode=quality,
        flatten_annotations=bool(data.get("flatten_annotations", True)),
        pad_to_multiple=pick(data, "pad_to_multiple", 0, int),
        fit_mode=fit_mode,
        fit_keep_orientation=bool(data.get("fit_keep_orientation", True)),
        fit_rotate_landscape=bool(data.get("fit_rotate_landscape", False)),
        fit_width_mm=pick(data, "fit_width_mm", 210.0),
        fit_height_mm=pick(data, "fit_height_mm", 297.0),
        fit_margin_mm=pick(data, "fit_margin_mm", 0.0),
    )


# ---------------------------------------------------------------------------
# Doğrulama
# ---------------------------------------------------------------------------
@dataclass
class ValidationResult:
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


MAX_DIM_MM = 5000.0


def validate_config(config: PdfProcessConfig) -> ValidationResult:
    """İşlemden önce ayarların mantıksal tutarlılığını denetler."""
    res = ValidationResult()
    b, m, n = config.page_boxes, config.margins, config.page_numbers

    if config.fit_mode not in FIT_MODES:
        res.errors.append(f"Bilinmeyen sayfa eşitleme kipi: {config.fit_mode}")
    if config.fit_mode != "off":
        if config.fit_mode == "custom" and not (0 < config.fit_width_mm <= MAX_DIM_MM and 0 < config.fit_height_mm <= MAX_DIM_MM):
            res.errors.append("Eşitleme genişliği/yüksekliği geçerli ve pozitif olmalı.")
        if not (0 <= config.fit_margin_mm <= MAX_DIM_MM / 2):
            res.errors.append("Eşitleme kenar payı geçerli ve negatif olmayan bir sayı olmalı.")
        if config.fit_mode == "custom" and 2 * config.fit_margin_mm >= min(config.fit_width_mm, config.fit_height_mm):
            res.errors.append("Eşitleme kenar payı hedef ebadın yarısından küçük olmalı.")
        if config.fit_mode in FIT_PAPERS_MM and 2 * config.fit_margin_mm >= min(FIT_PAPERS_MM[config.fit_mode]):
            res.errors.append("Eşitleme kenar payı seçilen kâğıda sığmıyor.")
    if b.enabled:
        if b.binding not in ("left", "right", "top"):
            res.errors.append("Cilt yeri sol, sağ veya üst olmalı.")
        if b.size_mode not in ("fixed", "auto"):
            res.errors.append(f"Bilinmeyen sayfa ebadı modu: {b.size_mode}")
        if b.size_mode == "fixed":
            if not (0 < b.target_width_mm <= MAX_DIM_MM):
                res.errors.append(f"Hedef genişlik 0 ile {MAX_DIM_MM:.0f} mm arasında olmalı.")
            if not (0 < b.target_height_mm <= MAX_DIM_MM):
                res.errors.append(f"Hedef yükseklik 0 ile {MAX_DIM_MM:.0f} mm arasında olmalı.")
        for label, val in (("Tek sayfa X ofseti", b.odd_x_mm), ("Tek sayfa Y ofseti", b.odd_y_mm),
                           ("Çift sayfa X ofseti", b.even_x_mm), ("Çift sayfa Y ofseti", b.even_y_mm)):
            if abs(val) > MAX_DIM_MM:
                res.errors.append(f"{label} çok büyük.")
        if min(b.odd_x_mm, b.even_x_mm, b.odd_y_mm, b.even_y_mm) < 0:
            res.warnings.append("Negatif ofset içeriği sayfanın dışına iter; kenarlar kırpılabilir.")
        if b.size_mode == "fixed" and (b.odd_x_mm > b.target_width_mm or b.even_x_mm > b.target_width_mm):
            res.errors.append("Cilt payı ofseti hedef genişlikten büyük olamaz.")
        if b.overflow_mode not in ("clip", "shrink"):
            res.errors.append(f"Bilinmeyen taşma davranışı: {b.overflow_mode}")
        if not (0 <= b.safe_edge_mm <= MAX_DIM_MM / 2):
            res.errors.append(f"Güvenlik payı 0 ile {MAX_DIM_MM / 2:.0f} mm arasında olmalı.")

    if m.enabled:
        if m.extra_bottom_mm < 0 or m.extra_top_mm < 0:
            res.errors.append("Alt ve üst pay negatif olamaz.")
        if m.extra_bottom_mm > MAX_DIM_MM or m.extra_top_mm > MAX_DIM_MM:
            res.errors.append("Alt/üst pay çok büyük.")
        if m.bottom_mode not in ("expand", "fit", "shift"):
            res.errors.append(f"Bilinmeyen alt pay modu: {m.bottom_mode}")
        if m.bottom_mode == "shift" and (m.extra_bottom_mm > 0 or m.extra_top_mm > 0):
            res.warnings.append(
                "'Kaydır' modu sayfa dışına taşan içeriği kırpar. Kırpmasız seçenek: 'Uzat' veya 'Sığdır'."
            )
        if m.bottom_mode == "fit" and b.enabled and b.size_mode == "fixed":
            if m.extra_bottom_mm + m.extra_top_mm >= b.target_height_mm:
                res.errors.append("Alt+üst pay, hedef yükseklikten küçük olmalı.")

    if n.enabled:
        seen_sections = set()
        for section in n.sections:
            try:
                start, first = int(section.get("start_page", 1)), int(section.get("start_num", 1))
                if start < 1 or start > MAX_PAGE_NUMBER or first < 0 or start in seen_sections:
                    raise ValueError
                if section.get("format_style", "number") not in ("number", "dash", "total", "label", "roman", "roman_upper"):
                    raise ValueError
                seen_sections.add(start)
            except (ValueError, TypeError):
                res.errors.append("Bölüm başlangıçları benzersiz pozitif sayfalar ve geçerli numaralar içermeli.")
        if n.font_size <= 0 or n.font_size > 72:
            res.errors.append("Punto 1 ile 72 arasında olmalı.")
        if n.start_page < 1:
            res.errors.append("Başlangıç sayfası en az 1 olmalı.")
        if n.start_num < 0:
            res.errors.append("İlk numara negatif olamaz.")
        if n.bottom_margin_mm < 0 or n.side_margin_mm < 0:
            res.errors.append("Numara boşlukları negatif olamaz.")
        if n.position not in ("outer", "center", "inner"):
            res.errors.append(f"Bilinmeyen numara konumu: {n.position}")
        if n.format_style not in ("number", "dash", "total", "label", "roman", "roman_upper"):
            res.errors.append(f"Bilinmeyen numara biçimi: {n.format_style}")
        if len(n.text_template) > 200:
            res.errors.append("Özel numara metni en fazla 200 karakter olabilir.")
        if n.font_path and not os.path.exists(n.font_path):
            res.errors.append(f"Yazı tipi dosyası bulunamadı: {n.font_path}")
        if len(n.font_color) < 3:
            res.errors.append("Numara rengi geçersiz.")

    if config.pad_to_multiple not in (0, 2, 4, 8, 16, 32):
        res.errors.append("Sayfa tamamlama katı 2, 4, 8, 16 veya 32 olmalı.")

    return res


# ---------------------------------------------------------------------------
# Yerleşim (tek doğruluk kaynağı)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PageLayout:
    """Bir kaynak sayfanın hedef sayfa üzerindeki yeri (tüm değerler pt)."""
    target_w: float
    target_h: float
    content: pymupdf.Rect   # kaynak sayfanın hedef sayfada kapladığı dikdörtgen
    scale: float            # 1.0 = ölçeksiz
    is_odd: bool            # kitap düzeninde sağ (tek) sayfa mı


def _mode(config: PdfProcessConfig) -> str:
    m = config.margins
    if not m.enabled:
        return "expand"
    return m.bottom_mode if m.bottom_mode in ("expand", "fit", "shift") else "expand"


def compute_layout(src_w: float, src_h: float, config: PdfProcessConfig, pno: int) -> PageLayout:
    """
    ``pno`` (0 tabanlı) sayfası için hedef ebat ve içerik konumunu hesaplar.
    İşleme, kırpma taraması, doğrulama ve önizleme bu fonksiyonu ortak kullanır.
    """
    boxes, margins = config.page_boxes, config.margins
    is_odd = (pno % 2 == 0)
    page_1based = pno + 1
    use_boxes = boxes.enabled and page_1based not in excluded_pages(boxes)
    use_margins = margins.enabled and page_1based not in excluded_pages(margins)

    top = mm_to_pt(margins.extra_top_mm) if use_margins else 0.0
    bottom = mm_to_pt(margins.extra_bottom_mm) if use_margins else 0.0
    mode = _mode(config) if use_margins else "expand"

    if use_boxes:
        ox = mm_to_pt(boxes.odd_x_mm if is_odd else boxes.even_x_mm)
        oy = mm_to_pt(boxes.odd_y_mm if is_odd else boxes.even_y_mm)
        if boxes.binding == "top":
            ox, oy = oy, ox
        if boxes.size_mode == "auto":
            tw = src_w + mm_to_pt(max(boxes.odd_x_mm, boxes.even_x_mm, 0.0))
            th = src_h + mm_to_pt(max(boxes.odd_y_mm, boxes.even_y_mm, 0.0))
            if boxes.binding == "top":
                tw = src_w + mm_to_pt(max(boxes.odd_y_mm, boxes.even_y_mm, 0.0))
                th = src_h + mm_to_pt(max(boxes.odd_x_mm, boxes.even_x_mm, 0.0))
        else:
            tw = mm_to_pt(boxes.target_width_mm)
            th = mm_to_pt(boxes.target_height_mm)
    else:
        ox = oy = 0.0
        tw, th = src_w, src_h

    # Sabit hedefte taşan içeriği kırpmak yerine küçült ("cilt payına sığdır").
    shrink = 1.0
    if (use_boxes and boxes.size_mode != "auto" and boxes.overflow_mode == "shrink"
            and src_w > 0 and src_h > 0):
        safe = mm_to_pt(max(0.0, boxes.safe_edge_mm))
        avail_w = tw - max(ox, 0.0) - safe
        avail_h = th - top - bottom - max(oy, 0.0) - safe
        if avail_w > 1.0 and avail_h > 1.0:
            shrink = min(1.0, avail_w / src_w, avail_h / src_h)
            shrink = max(shrink, 0.05)

    scale = shrink
    if mode == "expand":
        th += top + bottom
        content = pymupdf.Rect(ox, oy + top, ox + src_w * shrink, oy + top + src_h * shrink)
    elif mode == "shift":
        y0 = oy + top - bottom
        content = pymupdf.Rect(ox, y0, ox + src_w * shrink, y0 + src_h * shrink)
    else:  # fit
        avail_h = th - top - bottom - max(oy, 0.0)
        avail_w = tw - max(ox, 0.0)
        s = min(1.0, avail_h / src_h if src_h else 1.0, avail_w / src_w if src_w else 1.0)
        # "shrink" zaten güvenli kenar dahil aynı kısıtı hesaplar; ikinci kez çarpmak
        # ölçeği gereğinden fazla küçültürdü (v2.5.0, P3 13f).
        s = min(s, shrink)
        scale = max(s, 0.05)
        sw, sh = src_w * scale, src_h * scale
        cx = ox + max(0.0, (avail_w - sw) / 2.0)
        cy = top + max(oy, 0.0) + ((avail_h - sh) / 2.0 if scale < 1.0 else 0.0)
        content = pymupdf.Rect(cx, cy, cx + sw, cy + sh)

    if use_boxes and boxes.binding == "right":
        content = pymupdf.Rect(tw - content.x1, content.y0, tw - content.x0, content.y1)
    return PageLayout(target_w=tw, target_h=th, content=content, scale=scale, is_odd=is_odd)


def pad_page_count(total_pages: int, config: PdfProcessConfig) -> int:
    """4'ün katına tamamlamak için eklenecek boş sayfa sayısı."""
    multiple = int(config.pad_to_multiple or 0)
    if multiple <= 1 or total_pages <= 0:
        return 0
    remainder = total_pages % multiple
    return 0 if remainder == 0 else multiple - remainder


def expected_output_pages(total_pages: int, config: PdfProcessConfig) -> int:
    return total_pages + pad_page_count(total_pages, config)


def format_page_number_text(style: str, current_num: int, total_numbered: int,
                            template: str = "") -> str:
    """Seçilen stile veya özel metin şablonuna göre sayfa numarası metnini üretir."""
    roman = to_roman(current_num)
    if template:
        return (template
                .replace("{n}", str(current_num))
                .replace("{N}", str(total_numbered))
                .replace("{total}", str(total_numbered))
                .replace("{roman}", roman.lower())
                .replace("{ROMAN}", roman.upper())
                .replace("{label}", f"Sayfa {current_num}"))
    if style == "dash":
        return f"- {current_num} -"
    elif style == "total":
        return f"{current_num} / {total_numbered}"
    elif style == "label":
        return f"Sayfa {current_num}"
    elif style == "roman":
        return roman.lower()
    elif style == "roman_upper":
        return roman.upper()
    return str(current_num)


_ROMAN_TABLE = (
    (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
    (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
    (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
)


def to_roman(number: int) -> str:
    """1-3999 aralığını Roma rakamına çevirir; dışındaysa sayıyı metin verir."""
    if number <= 0 or number > 3999:
        return str(number)
    result = []
    remaining = number
    for value, symbol in _ROMAN_TABLE:
        while remaining >= value:
            result.append(symbol)
            remaining -= value
    return "".join(result)


def _number_font_candidates() -> List[str]:
    candidates: List[str] = []
    windir = os.environ.get("WINDIR", r"C:\Windows")
    for name in ("segoeui.ttf", "arial.ttf", "calibri.ttf", "tahoma.ttf", "DejaVuSans.ttf"):
        candidates.append(os.path.join(windir, "Fonts", name))
    candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "DejaVuSans.ttf"))
    return candidates


def resolve_number_font(settings: PageNumberSettings,
                        texts: List[str]) -> Optional[Tuple[str, pymupdf.Font]]:
    """
    Metin Türkçe/Unicode karakter içeriyorsa gömülebilir bir yazı tipi bulur.
    Sayısal numaralarda gömme yapılmaz; dosya gereksiz büyümez.
    """
    has_unicode = any(ord(char) > 127 for text in texts for char in text)
    if not has_unicode and not settings.font_path:
        return None
    candidates = ([settings.font_path] if settings.font_path else []) + _number_font_candidates()
    for path in candidates:
        if path and os.path.exists(path):
            try:
                return path, pymupdf.Font(fontfile=path)
            except Exception:
                continue
    return None


NUMBER_FONT_NAME = "helv"


def _encodable_latin1(char: str) -> bool:
    """Yerleşik Helvetica (Latin-1) bu karakteri basabilir mi?"""
    try:
        char.encode("cp1252")
        return True
    except UnicodeEncodeError:
        return False


def number_anchor(text: str, settings: PageNumberSettings, target_w: float, target_h: float,
                  is_odd: bool, font: Optional[pymupdf.Font] = None) -> Tuple[float, float]:
    """Numara metninin sol-taban noktasını (x, baseline_y) döndürür; ölçüm gerçek yazı genişliğiyledir."""
    if font is not None:
        text_w = font.text_length(text, fontsize=settings.font_size)
    else:
        text_w = pymupdf.get_text_length(text, fontname=NUMBER_FONT_NAME,
                                         fontsize=settings.font_size)
    side = mm_to_pt(settings.side_margin_mm)
    if getattr(settings, "vertical_pos", "bottom") == "top":
        baseline = mm_to_pt(settings.bottom_margin_mm) + settings.font_size
    else:
        baseline = target_h - mm_to_pt(settings.bottom_margin_mm)

    if settings.position == "center":
        x = (target_w - text_w) / 2.0
    elif settings.position == "inner":
        x = side if is_odd else target_w - side - text_w
    else:  # outer: tek sayfa sağ, çift sayfa sol
        x = target_w - side - text_w if is_odd else side
    return x, baseline


def _compute_numbering(total_pages: int, config: PdfProcessConfig) -> Tuple[Set[int], int]:
    """(atlanacak sayfa kümesi, 'toplam' biçimi için efektif toplam) döndürür."""
    n = config.page_numbers
    skip_set = set(n.skip_pages_set)
    if n.skip_pages_str:
        skip_set.update(parse_page_ranges(n.skip_pages_str))

    if n.enabled:
        if n.continuous_numbering:
            counted = sum(1 for pno in range(total_pages)
                          if (pno + 1) >= n.start_page and (pno + 1) not in skip_set)
            total = max(1, counted)
        else:
            total = max(1, total_pages - (n.start_page - 1))
    else:
        total = total_pages
    return skip_set, total


def numbering_plan(total_pages: int, config: PdfProcessConfig) -> List[Optional[str]]:
    """
    Her sayfaya basılacak numara metnini (veya numara yoksa ``None``) döndürür.
    İşleme, önizleme ve doğrulama aynı planı kullanır; böylece sayaç kaymaz.
    """
    n = config.page_numbers
    if n.enabled and n.sections:
        sections, blanks = numbering_sections(config)
        skipped = number_skip_set(config)
        texts = [None] * total_pages
        for index, section in enumerate(sections):
            start = section["start_page"] - 1
            end = sections[index + 1]["start_page"] - 1 if index + 1 < len(sections) else total_pages
            end = min(end, total_pages)
            count = max(0, end - start - sum(start <= b < end for b in blanks)
                        - (sum(start <= p - 1 < end for p in skipped) if n.continuous_numbering else 0))
            current = int(section.get("start_num", 1))
            for page in range(start, end):
                if page in blanks:
                    continue
                if page + 1 in skipped:
                    if not n.continuous_numbering:
                        current += 1
                    continue
                if not (page == start and section.get("hide_first", False)):
                    texts[page] = format_page_number_text(section.get("format_style", "number"),
                                                           current, count, n.text_template)
                current += 1
        return texts
    skip_set, effective_total = _compute_numbering(total_pages, config)
    texts: List[Optional[str]] = [None] * total_pages
    counter = n.start_num

    for pno in range(total_pages):
        page_1based = pno + 1
        if not n.enabled or page_1based < n.start_page or page_1based in skip_set:
            continue
        if n.continuous_numbering:
            current = counter
            counter += 1
        else:
            current = n.start_num + (page_1based - n.start_page)
        texts[pno] = format_page_number_text(n.format_style, current, effective_total,
                                             n.text_template)
    return texts


def numbering_sections(config):
    """Kaynak sayfa başlangıçlarını eklenen boş sayfalarla fiziksel sıraya çevirir."""
    result, blanks, offset = [], set(), 0
    for original in sorted(config.page_numbers.sections, key=lambda s: int(s.get("start_page", 1))):
        section = dict(original)
        start = int(section.get("start_page", 1)) - 1 + offset
        if section.get("blank_before", False) and start % 2:
            blanks.add(start)
            offset += 1
            start += 1
        section["start_page"] = start + 1
        result.append(section)
    return result, blanks


def number_skip_set(config: PdfProcessConfig) -> Set[int]:
    """Numaralandırmada atlanacak 1 tabanlı sayfa kümesi (önizleme/doğrulama için)."""
    n = config.page_numbers
    skip_set = set(n.skip_pages_set)
    if n.skip_pages_str:
        skip_set.update(parse_page_ranges(n.skip_pages_str))
    if n.enabled and n.sections:
        blanks = numbering_sections(config)[1]
        mapped = set()
        for original in skip_set:
            page = original - 1
            for blank in sorted(blanks):
                if blank <= page:
                    page += 1
            mapped.add(page + 1)
        return mapped
    return skip_set


# ---------------------------------------------------------------------------
# PDF bilgisi
# ---------------------------------------------------------------------------
@pdf_operation
def get_pdf_info(pdf_path: str, quick: bool = False, size_policy: str = "dominant") -> dict:
    """PDF hakkında temel bilgileri döndürür.

    ``quick=True``: karışık ebat taraması yapılmaz (tüm sayfaları gezmez); birleştirme
    listesine çok dosya eklerken açılışı hızlandırır.
    ``size_policy``: karışık ebatlı belgede ``width_mm``/``height_mm`` seçimi —
    ``first`` (ilk sayfa), ``dominant`` (en çok kullanılan) veya ``largest`` (en büyük).
    """
    file_size_mb = round(os.path.getsize(pdf_path) / (1024 * 1024), 2) if os.path.exists(pdf_path) else 0.0
    doc = open_pdf(pdf_path)
    try:
        page_count = len(doc)
        mixed = False
        # Karışık ebatlı belgede kapak/ek sayfa çoğunluktan farklı olabilir; hedef ebat
        # ilk sayfaya değil, en çok kullanılan sayfa boyutuna göre verilir.
        counts: Dict[Tuple[int, int], int] = {}
        samples: Dict[Tuple[int, int], Any] = {}
        for i in range(1 if quick else page_count):
            r = doc[i].rect
            key = (int(round(r.width)), int(round(r.height)))
            counts[key] = counts.get(key, 0) + 1
            samples.setdefault(key, r)
        mixed = len(counts) > 1
        if size_policy == "first":
            chosen = next(iter(counts))
        elif size_policy == "largest":
            chosen = max(counts, key=lambda key: key[0] * key[1])
        else:
            chosen = max(counts, key=counts.get)
        size = samples[chosen]
        width_mm = round(pt_to_mm(size.width), 1)
        height_mm = round(pt_to_mm(size.height), 1)
        is_portrait = size.height >= size.width
    finally:
        doc.close()

    return {
        "page_count": page_count,
        "width_mm": width_mm,
        "height_mm": height_mm,
        "is_portrait": is_portrait,
        "file_size_mb": file_size_mb,
        "mixed_sizes": mixed,
    }


# ---------------------------------------------------------------------------
# İçerik sınırı ve kırpma taraması
# ---------------------------------------------------------------------------
def _is_near_white(color) -> bool:
    return bool(color) and len(color) >= 3 and all(c >= 0.97 for c in color[:3])


def page_content_bbox(page: pymupdf.Page) -> Optional[pymupdf.Rect]:
    """
    Sayfadaki görünür içeriğin sınırını (sayfa koordinatlarında) verir.
    Metin, görsel ve çizimler hesaba katılır; tüm sayfayı kaplayan beyaz zemin
    ve tamamen boş sayfalar yok sayılır. İçerik yoksa None döner.
    """
    page_rect = page.rect
    unrot_rect = page_rect * page.derotation_matrix  # çizimlerin yaşadığı uzay
    union: Optional[pymupdf.Rect] = None

    def add(r) -> None:
        nonlocal union
        r = pymupdf.Rect(r).normalize()
        if r.is_infinite:
            return
        union = r if union is None else (union | r)

    try:
        for w in page.get_text("words"):
            add(w[:4])
    except Exception:
        pass
    try:
        for info in page.get_image_info():
            add(info["bbox"])
    except Exception:
        pass
    try:
        for d in page.get_drawings():
            r = d.get("rect")
            if r is None:
                continue
            fill, stroke = d.get("fill"), d.get("color")
            covers_page = (r.width >= abs(unrot_rect.width) * 0.98
                           and r.height >= abs(unrot_rect.height) * 0.98)
            if covers_page and stroke is None and (fill is None or _is_near_white(fill)):
                continue  # beyaz zemin: görünür içerik sayılmaz
            if fill is None and stroke is None:
                continue
            add(r)
    except Exception:
        pass

    if union is None:
        return None
    # PyMuPDF bu çağrılarda döndürülmemiş sayfa uzayında koordinat verir;
    # page.rect ise döndürülmüş uzaydadır. Önce uzayları eşleştir.
    r = (union * page.rotation_matrix).normalize()
    x0, y0 = max(r.x0, page_rect.x0), max(r.y0, page_rect.y0)
    x1, y1 = min(r.x1, page_rect.x1), min(r.y1, page_rect.y1)
    if x0 > x1 or y0 > y1:
        return None  # içerik tamamen sayfa dışında: görünür bir şey yok
    return pymupdf.Rect(x0, y0, x1, y1)


@dataclass
class ClipIssue:
    """Bir sayfada içeriğin hedef sayfadan taşan miktarı (mm)."""
    page: int       # 1 tabanlı
    left_mm: float = 0.0
    right_mm: float = 0.0
    top_mm: float = 0.0
    bottom_mm: float = 0.0

    def edges_text(self) -> str:
        """Taşan kenarlar, sayfa numarasız (ör. ``üst 4.0 mm, sol 1.2 mm``)."""
        parts = []
        for name, v in (("sol", self.left_mm), ("sağ", self.right_mm),
                        ("üst", self.top_mm), ("alt", self.bottom_mm)):
            if v > 0:
                parts.append(f"{name} {v:.1f} mm")
        return ", ".join(parts)

    def describe(self) -> str:
        return f"Sayfa {self.page}: " + self.edges_text()


def group_clip_lines(entries: Iterable[Tuple[int, str]]) -> List[Tuple[int, int, str]]:
    """Ardışık, aynı taşma metnini taşıyan sayfaları aralıkta toplar (P2-35).

    ``entries``: ``(1 tabanlı sayfa, kenar metni)`` çiftleri. Dönüş: ``(ilk, son, metin)``.
    Sayfalar sıralanır; yalnızca numarası ardışık ve metni aynı olanlar birleşir.
    """
    groups: List[Tuple[int, int, str]] = []
    for page, text in sorted(entries, key=lambda e: e[0]):
        if groups and groups[-1][2] == text and groups[-1][1] + 1 == page:
            groups[-1] = (groups[-1][0], page, text)
        else:
            groups.append((page, page, text))
    return groups


def format_clip_group(first: int, last: int, text: str) -> str:
    """``Sayfa 3: üst 4.0 mm`` ya da ``Sayfa 1–9: üst 4.0 mm``."""
    label = f"Sayfa {first}" if first == last else f"Sayfa {first}–{last}"
    return f"{label}: {text}"


@dataclass
class ScanReport:
    total_pages: int = 0
    issues: List[ClipIssue] = field(default_factory=list)
    blank_pages: int = 0

    @property
    def has_issues(self) -> bool:
        return bool(self.issues)

    def summary(self, limit: int = 8) -> str:
        if not self.issues:
            return f"İçerik taşması yok ({self.total_pages} sayfa tarandı)."
        groups = group_clip_lines((i.page, i.edges_text()) for i in self.issues)
        head = [format_clip_group(*g) for g in groups[:limit]]
        more = sum(last - first + 1 for first, last, _ in groups[limit:])
        txt = f"{len(self.issues)} sayfada içerik hedef sayfanın dışına taşıyor:\n" + "\n".join(head)
        if more > 0:
            txt += f"\n… ve {more} sayfa daha."
        return txt


CLIP_TOLERANCE_PT = 0.85  # ≈0,3 mm: kenar yumuşatma gürültüsünü yok say


def clip_edges_for_page(page: pymupdf.Page, layout: PageLayout) -> Tuple[float, float, float, float]:
    """
    Bir sayfanın görünür içeriğinin hedef dikdörtgenin dışına taşma miktarı
    (sol, sağ, üst, alt) milimetre cinsinden. Hepsi sıfırsa kırpma yok.
    """
    bbox = page_content_bbox(page)
    if bbox is None:
        return (0.0, 0.0, 0.0, 0.0)
    mat = pymupdf.Matrix(layout.scale, 0, 0, layout.scale, layout.content.x0, layout.content.y0)
    r = bbox * mat
    left = pt_to_mm(max(0.0, -r.x0 - CLIP_TOLERANCE_PT))
    right = pt_to_mm(max(0.0, r.x1 - layout.target_w - CLIP_TOLERANCE_PT))
    top = pt_to_mm(max(0.0, -r.y0 - CLIP_TOLERANCE_PT))
    bottom = pt_to_mm(max(0.0, r.y1 - layout.target_h - CLIP_TOLERANCE_PT))
    return (left, right, top, bottom)


@pdf_operation
def scan_clipping(
    input_path: str,
    config: PdfProcessConfig,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> ScanReport:
    """
    Seçili ayarlarla işlenirse hangi sayfalarda görünür içeriğin hedef sayfa
    dışına taşıp KIRPILACAĞINI, dosyayı değiştirmeden önceden bildirir.
    """
    input_path = prepared_source(input_path, config)
    doc = open_pdf(input_path)
    report = ScanReport(total_pages=len(doc))
    try:
        total = len(doc)
        for pno in range(total):
            if should_cancel and should_cancel():
                raise ProcessCancelled("Tarama iptal edildi.")
            page = doc[pno]
            lay = compute_layout(page.rect.width, page.rect.height, config, pno)
            if page_content_bbox(page) is None:
                report.blank_pages += 1
            else:
                left, right, top, bottom = clip_edges_for_page(page, lay)
                if left or right or top or bottom:
                    report.issues.append(ClipIssue(pno + 1, left, right, top, bottom))
            if progress_callback:
                progress_callback(pno + 1, total)
    finally:
        doc.close()
    return report


# ---------------------------------------------------------------------------
# Önizleme (arayüz canlı paneli)
# ---------------------------------------------------------------------------
ACCENT_RGB = (0.035, 0.412, 0.851)
GUTTER_RGB = (0.035, 0.412, 0.851)
MARGIN_RGB = (0.13, 0.55, 0.36)
DANGER_RGB = (0.78, 0.13, 0.18)


@dataclass
class PreviewPage:
    """Önizleme için üretilmiş tek sayfa görüntüsü ve ölçüleri.

    ``png`` alanının adı geçmişten kalmadır: bayt dizisi artık sıkıştırılmamış PPM'dir
    (PNG kodlaması önizlemedeki en büyük yavaşlıktı). Pillow ve Qt ikisini de açar.
    """
    page_index: int          # 0 tabanlı
    png: bytes
    width_pt: float
    height_pt: float
    scale: float
    is_odd: bool
    number_text: Optional[str]
    clipped: bool
    clip_mm: Tuple[float, float, float, float]
    caption: Optional[str] = None   # birleşik dizi gezintisinde "dosya • sayfa/toplam"

    @property
    def width_mm(self) -> float:
        return pt_to_mm(self.width_pt)

    @property
    def height_mm(self) -> float:
        return pt_to_mm(self.height_pt)


def _preview_bands(layout: PageLayout, config: PdfProcessConfig) -> List[Tuple[pymupdf.Rect, tuple]]:
    """Önizlemede renklendirilecek cilt ve kenar payı bölgeleri."""
    bands: List[Tuple[pymupdf.Rect, tuple]] = []
    content = layout.content
    tw, th = layout.target_w, layout.target_h
    if config.page_boxes.enabled:
        if config.page_boxes.binding == "top" and content.y0 > 0.5:
            amount = mm_to_pt(config.page_boxes.odd_x_mm if layout.is_odd else config.page_boxes.even_x_mm)
            if amount > 0:
                bands.append((pymupdf.Rect(0, 0, tw, min(amount, content.y0)), GUTTER_RGB))
        if content.x0 > 0.5:
            bands.append((pymupdf.Rect(0, 0, content.x0, th), GUTTER_RGB))
        if content.x1 < tw - 0.5:
            bands.append((pymupdf.Rect(content.x1, 0, tw, th), GUTTER_RGB))
    if config.margins.enabled:
        if content.y0 > 0.5:
            bands.append((pymupdf.Rect(0, 0, tw, content.y0), MARGIN_RGB))
        if content.y1 < th - 0.5:
            bands.append((pymupdf.Rect(0, content.y1, tw, th), MARGIN_RGB))
    return bands


def encode_preview_pixmap(pix: "pymupdf.Pixmap") -> bytes:
    """Önizleme görüntüsünü hızlı kodlar (sıkıştırmasız PPM; PNG'den ~10 kat hızlı)."""
    try:
        return pix.tobytes("ppm")
    except Exception:
        return pix.tobytes("png")


@pdf_operation
def render_preview(
    input_path: str,
    config: PdfProcessConfig,
    pages: Tuple[int, int] = (0, 1),
    zoom: float = 1.25,
) -> List[PreviewPage]:
    """
    İlk sayfa ile karşı sayfayı (0 ve 1) cilt şeridi, alt/üst pay ve numara
    konumu işaretli olarak PNG baytları halinde üretir. Dosyaya yazmaz.
    """
    input_path = prepared_source(input_path, config)
    doc = open_pdf(input_path)
    normalize_page_rotations(doc)
    texts = numbering_plan(len(doc), config)
    font_info = resolve_number_font(config.page_numbers, [text for text in texts if text])
    number_font = font_info[1] if font_info else None
    out: List[PreviewPage] = []
    try:
        for pno in sorted({p for p in pages if 0 <= p < len(doc)}):
            src_page = doc[pno]
            lay = compute_layout(src_page.rect.width, src_page.rect.height, config, pno)
            single = pymupdf.open()
            try:
                page = single.new_page(width=lay.target_w, height=lay.target_h)
                show_pdf_page(page, lay.content, doc, pno)

                for rect, color in _preview_bands(lay, config):
                    page.draw_rect(rect, color=color, fill=color, fill_opacity=0.10,
                                   width=0.6, dashes="[3 3] 0")

                number_text = texts[pno]
                if number_text:
                    x, baseline = number_anchor(number_text, config.page_numbers,
                                                lay.target_w, lay.target_h, lay.is_odd,
                                                font=number_font)
                    if font_info:
                        page.insert_text(pymupdf.Point(x, baseline), number_text,
                                         fontsize=config.page_numbers.font_size,
                                         fontname="STUDIOFONT", fontfile=font_info[0],
                                         color=ACCENT_RGB)
                    else:
                        page.insert_text(pymupdf.Point(x, baseline), number_text,
                                         fontsize=config.page_numbers.font_size,
                                         fontname=NUMBER_FONT_NAME, color=ACCENT_RGB)
                    page.draw_line(pymupdf.Point(0, baseline + 2), pymupdf.Point(lay.target_w, baseline + 2),
                                   color=ACCENT_RGB, width=0.4, dashes="[2 3] 0")

                clip_mm = clip_edges_for_page(src_page, lay)
                clipped = any(clip_mm)
                if clipped:
                    page.draw_rect(page.rect, color=DANGER_RGB, width=2.0)
                    page.insert_text(pymupdf.Point(6, 14), "KIRPILACAK",
                                     fontsize=8, fontname=NUMBER_FONT_NAME, color=DANGER_RGB)

                pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
                out.append(PreviewPage(
                    page_index=pno,
                    png=encode_preview_pixmap(pix),
                    width_pt=lay.target_w,
                    height_pt=lay.target_h,
                    scale=lay.scale,
                    is_odd=lay.is_odd,
                    number_text=number_text,
                    clipped=clipped,
                    clip_mm=clip_mm,
                ))
            finally:
                single.close()
    finally:
        doc.close()
    return out


@pdf_operation
def render_plain_preview(
    input_path: str,
    rotation: int = 0,
    page_range: str = "",
    pages: Tuple[int, ...] = (0, 1),
    zoom: float = 1.25,
    fit: Optional[Tuple[str, bool, bool]] = None,
) -> Tuple[List[PreviewPage], int]:
    """Birleştirme önizlemesi: dosyayı olduğu gibi (cilt/boşluk/numara işaretsiz) çizer.

    ``rotation`` (90'ın katı) ve ``page_range`` birleştirme işindeki gibi uygulanır;
    ``pages`` aralık uygulanmış listenin 0 tabanlı indeksleridir. Yalnızca istenen
    sayfalar çizilir (çok sayfalı dosyada tamamı işlenmez). ``(sayfalar, toplam)`` döner.

    ``fit=(kip, yatay_kalsın, dikeye_döndür)`` verilirse sayfalar birleştirmedeki gibi
    eşitlenmiş çizilir. Sabit kâğıtlarda (a3/a4/a5) sonuç birebirdir; "ilk sayfa" ve
    "en büyük sayfa" kipleri yalnız bu dosyanın sayfalarına göre hesaplanır (yaklaşık).
    """
    doc = open_pdf(input_path)
    out: List[PreviewPage] = []
    try:
        selected = list(range(len(doc)))
        if str(page_range or "").strip():
            picked = [p for p in sorted(parse_page_ranges(page_range)) if 1 <= p <= len(doc)]
            if picked:
                selected = [p - 1 for p in picked]
        total = len(selected)
        extra = int(rotation or 0) % 360
        fit_cfg = None
        fit_ref = None
        if fit and fit[0] != "off":
            fit_cfg = PdfProcessConfig(fit_mode=fit[0], fit_keep_orientation=bool(fit[1]),
                                       fit_rotate_landscape=bool(fit[2]),
                                       fit_width_mm=fit[3] if len(fit) > 3 else 210.0,
                                       fit_height_mm=fit[4] if len(fit) > 4 else 297.0,
                                       fit_margin_mm=fit[5] if len(fit) > 5 else 0.0)
            if extra:
                for pno in selected:
                    doc[pno].set_rotation((doc[pno].rotation + extra) % 360)
            normalize_page_rotations(doc)
            fit_ref = fit_reference_size(
                [(doc[p].rect.width, doc[p].rect.height) for p in selected], fit_cfg)
            extra = 0
        for index in sorted({p for p in pages if 0 <= p < total}):
            page = doc[selected[index]]
            if extra:
                page.set_rotation((page.rotation + extra) % 360)
            if fit_cfg is not None and fit_ref is not None:
                sw, sh = page.rect.width, page.rect.height
                tw, th = fit_page_target(sw, sh, fit_ref, fit_cfg.fit_keep_orientation)
                rotate = fit_should_rotate(sw, sh, fit_cfg)
                mat = fit_matrix(sw, sh, tw, th, rotate, mm_to_pt(fit_cfg.fit_margin_mm))
                tmp = pymupdf.open()
                try:
                    tpage = tmp.new_page(width=tw, height=th)
                    dest = pymupdf.Rect(0, 0, sw, sh) * mat
                    if rotate:
                        show_pdf_page(tpage, dest, doc, selected[index], rotate=90)
                    else:
                        show_pdf_page(tpage, dest, doc, selected[index])
                    pix = tpage.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
                finally:
                    tmp.close()
                rect = pymupdf.Rect(0, 0, tw, th)
            else:
                pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
                rect = page.rect
            out.append(PreviewPage(
                page_index=index, png=encode_preview_pixmap(pix),
                width_pt=rect.width, height_pt=rect.height, scale=1.0,
                is_odd=index % 2 == 0, number_text=None, clipped=False,
                clip_mm=(0.0, 0.0, 0.0, 0.0),
            ))
    finally:
        doc.close()
    return out, total


# ---------------------------------------------------------------------------
# Kayıt
# ---------------------------------------------------------------------------
def show_pdf_page(target, rect, source, page_number, **kwargs):
    """Boş kaynak sayfa da geçerlidir; MuPDF boş içerikte hata verir."""
    if source[page_number].get_contents():
        target.show_pdf_page(rect, source, page_number, **kwargs)


def _atomic_save(doc: pymupdf.Document, output_path: str, optimize: bool) -> None:
    """Geçici dosyaya yazar, başarılıysa hedefe taşır. Yarım çıktı bırakmaz."""
    out_dir = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(out_dir, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".~", suffix=".pdf.tmp", dir=out_dir)
    os.close(fd)
    try:
        if optimize:
            doc.save(tmp, deflate=True, garbage=3)
        else:
            doc.save(tmp, deflate=True, garbage=0, clean=False)
        os.replace(tmp, output_path)
    except Exception as exc:
        try:
            os.remove(tmp)
        except OSError:
            pass
        if isinstance(exc, PermissionError):
            raise OutputPathError(
                f"'{os.path.basename(output_path)}' yazılamadı. Dosya başka bir programda açık olabilir."
            ) from exc
        raise


# ---------------------------------------------------------------------------
# Ana işlem hattı
# ---------------------------------------------------------------------------
@pdf_operation
def process_pdf(
    input_path: str,
    output_path: str,
    config: PdfProcessConfig,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> str:
    """
    Girdi PDF'i işler: cilt payı, alt/üst boşluklar ve sayfa numaralandırmayı
    vektörel olarak uygular ve çıktıyı atomik olarak kaydeder.
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Girdi dosyası bulunamadı: {input_path}")
    if same_path(input_path, output_path):
        raise OutputPathError("Çıktı dosyası, kaynak dosyayla aynı olamaz. Farklı bir ad seçin.")

    result = validate_config(config)
    if not result.ok:
        raise ConfigError(result.errors)
    if config.pad_to_multiple not in (0, 2, 4, 8, 16, 32):
        raise ConfigError([f"Geçersiz sayfa tamamlama katı: {config.pad_to_multiple}"])

    pnums = config.page_numbers
    input_path = prepared_source(input_path, config)  # sığdırma açıksa eşitlenmiş kopya
    src_doc = open_pdf(input_path)
    dst_doc = pymupdf.open()
    total_pages = len(src_doc)

    # Bağlantılar, açıklamalar gömülmeden ÖNCE toplanmalı (bake bağlantıları da etkileyebilir).
    # Toplama normalize edilmiş sayfadan değil, görünür (döndürülmüş) uzaydan yapılır:
    # hedef noktası (``to``) ancak böyle doğru kalır.
    links_by_page = _collect_links(src_doc)
    if config.flatten_annotations and count_annotations(src_doc):
        try:
            src_doc.bake(annots=True, widgets=True)  # yalnızca bellekteki kopya; kaynak dosya değişmez
        except Exception:
            pass
    # Döndürülmüş sayfalar görünür yönde sabitlenmeli; aksi hâlde show_pdf_page
    # /Rotate'i yok sayar ve sayfanın bir kısmını kırpar.
    normalize_page_rotations(src_doc)
    texts = numbering_plan(total_pages, config)
    font_info = resolve_number_font(pnums, [text for text in texts if text])
    number_font = font_info[1] if font_info else None
    if font_info is None:
        unsupported = sorted({ch for text in texts if text for ch in text
                              if not _encodable_latin1(ch)})
        if unsupported:
            src_doc.close()
            dst_doc.close()
            raise ConfigError([
                "Numara metnindeki şu karakterler için yazı tipi bulunamadı: "
                + " ".join(unsupported[:10])
                + ". 'Yazı tipi' alanından Unicode destekli bir .ttf seçin."
            ])
    layouts: List[PageLayout] = []

    try:
        for pno in range(total_pages):
            if should_cancel and should_cancel():
                raise ProcessCancelled("İşlem iptal edildi. Çıktı dosyası oluşturulmadı.")

            src_page = src_doc[pno]
            src_rect = src_page.rect
            lay = compute_layout(src_rect.width, src_rect.height, config, pno)
            layouts.append(lay)

            target_page = dst_doc.new_page(width=lay.target_w, height=lay.target_h)
            show_pdf_page(target_page, lay.content, src_doc, pno)

            number_text = texts[pno]
            if number_text:
                x, baseline = number_anchor(number_text, pnums, lay.target_w, lay.target_h,
                                            lay.is_odd, font=number_font)
                if font_info:
                    target_page.insert_text(
                        pymupdf.Point(x, baseline), number_text,
                        fontsize=pnums.font_size, fontname="STUDIOFONT",
                        fontfile=font_info[0], color=pnums.font_color,
                    )
                else:
                    target_page.insert_text(
                        pymupdf.Point(x, baseline), number_text,
                        fontsize=pnums.font_size, fontname=NUMBER_FONT_NAME,
                        color=pnums.font_color,
                    )

            if progress_callback:
                progress_callback(pno + 1, total_pages)

        # İstenirse kitapçık/cilt için toplam sayıyı 4'ün katına tamamla.
        pad_count = pad_page_count(total_pages, config)
        if pad_count:
            last = layouts[-1] if layouts else compute_layout(
                mm_to_pt(210), mm_to_pt(297), config, 0)
            for _ in range(pad_count):
                dst_doc.new_page(width=last.target_w, height=last.target_h)

        # Bağlantılar: tüm sayfalar oluştuktan sonra eklenir ki ileri sayfalara
        # giden bağlantılar da korunsun.
        _copy_links(links_by_page, dst_doc, layouts)

        try:
            metadata = src_doc.metadata
            if metadata:
                dst_doc.set_metadata(metadata)
            toc = src_doc.get_toc()
            if toc:
                dst_doc.set_toc(sanitize_toc(toc))
        except Exception:
            pass

        if should_cancel and should_cancel():
            raise ProcessCancelled("İşlem iptal edildi. Çıktı dosyası oluşturulmadı.")
        _atomic_save(dst_doc, output_path, config.optimize)
        return output_path
    finally:
        src_doc.close()
        dst_doc.close()


# ---------------------------------------------------------------------------
# Sayfa eşitleme ("sığdır") ön geçişi
# ---------------------------------------------------------------------------
def fit_reference_size(sizes: List[Tuple[float, float]], config: PdfProcessConfig
                       ) -> Optional[Tuple[float, float]]:
    """Eşitleme hedefi (genişlik, yükseklik pt, dikey); kapalıysa ``None``."""
    mode = config.fit_mode
    if mode == "off" or not sizes:
        return None
    if mode in FIT_PAPERS_MM:
        w, h = FIT_PAPERS_MM[mode]
        return (mm_to_pt(w), mm_to_pt(h))
    if mode == "custom":
        return (mm_to_pt(config.fit_width_mm), mm_to_pt(config.fit_height_mm))
    if mode == "first":
        w, h = sizes[0]
    else:  # largest
        w, h = max(sizes, key=lambda wh: wh[0] * wh[1])
    return (min(w, h), max(w, h))


def fit_page_target(src_w: float, src_h: float, ref: Tuple[float, float],
                    keep_orientation: bool) -> Tuple[float, float]:
    """Bir sayfanın eşitlenmiş ebadı: yön korunuyorsa yatay sayfa yatay hedef alır."""
    short, long_ = ref
    if keep_orientation:
        short, long_ = min(ref), max(ref)
        return (long_, short) if src_w > src_h else (short, long_)
    return (short, long_)


def fit_matrix(src_w: float, src_h: float, tw: float, th: float,
               rotate: bool = False, margin: float = 0.0) -> pymupdf.Matrix:
    """Kaynağı oranı bozmadan hedefe sığdırıp ortalayan dönüşüm (büyütme de yapar).

    ``rotate=True``: kaynak saat yönünün tersine 90° döndürülüp hedefe sığdırılır (yatay → dikey).
    """
    if margin:
        if not (0 <= margin < min(tw, th) / 2):
            raise ConfigError(["Eşitleme kenar payı sayfa ebadına sığmıyor."])
        matrix = fit_matrix(src_w, src_h, tw - 2 * margin, th - 2 * margin, rotate)
        matrix.e += margin
        matrix.f += margin
        return matrix
    if rotate:
        s = min(tw / src_h, th / src_w)
        ox = (tw - src_h * s) / 2.0
        oy = (th - src_w * s) / 2.0
        # (x, y) → (y * s + ox, (src_w - x) * s + oy)
        return pymupdf.Matrix(0, -s, s, 0, ox, src_w * s + oy)
    s = min(tw / src_w, th / src_h)
    return pymupdf.Matrix(s, 0, 0, s, (tw - src_w * s) / 2.0, (th - src_h * s) / 2.0)


def fit_should_rotate(src_w: float, src_h: float, config: PdfProcessConfig) -> bool:
    """Yatay sayfa dikey hedefe döndürülerek mi sığdırılacak?"""
    return (not config.fit_keep_orientation and config.fit_rotate_landscape
            and src_w > src_h
            and not (config.fit_mode == "custom" and config.fit_width_mm > config.fit_height_mm))


_FIT_CACHE: Dict[Tuple[Any, ...], str] = {}
_FIT_DIR: List[str] = []


def _fit_dir() -> str:
    if not _FIT_DIR:
        import atexit
        import shutil
        path = tempfile.mkdtemp(prefix="studio_fit_")
        _FIT_DIR.append(path)
        atexit.register(shutil.rmtree, path, True)
    return _FIT_DIR[0]


@pdf_operation
def build_fitted_pdf(input_path: str, output_path: str, config: PdfProcessConfig,
                     should_cancel: Optional[Callable[[], bool]] = None) -> str:
    """Tüm sayfaları ``config.fit_mode`` ebadına sığdırılmış bir kopya yazar.

    Bağlantılar, yer imleri ve meta veri taşınır; açıklamalar ``flatten_annotations``
    açıksa sayfaya gömülür (işleme hattındakiyle aynı kural). Kaynak dosya değişmez.
    """
    src = open_pdf(input_path)
    out = pymupdf.open()
    try:
        links = _collect_links(src)
        if config.flatten_annotations and count_annotations(src):
            try:
                src.bake(annots=True, widgets=True)
            except Exception:
                pass
        normalize_page_rotations(src)
        sizes = [(src[i].rect.width, src[i].rect.height) for i in range(len(src))]
        ref = fit_reference_size(sizes, config)
        if ref is None:
            raise ValueError("Sayfa eşitleme kapalı.")
        mats: List[pymupdf.Matrix] = []
        for pno, (sw, sh) in enumerate(sizes):
            if should_cancel and should_cancel():
                raise ProcessCancelled("İşlem iptal edildi.")
            tw, th = fit_page_target(sw, sh, ref, config.fit_keep_orientation)
            rotate = fit_should_rotate(sw, sh, config)
            mat = fit_matrix(sw, sh, tw, th, rotate, mm_to_pt(config.fit_margin_mm))
            mats.append(mat)
            page = out.new_page(width=tw, height=th)
            if rotate:
                # Döndürülmüş yerleşimde hedef dikdörtgen, dönmüş kaynağın kaplayacağı alandır.
                dest = pymupdf.Rect(0, 0, sw, sh) * mat
                show_pdf_page(page, dest, src, pno, rotate=90)
            else:
                show_pdf_page(page, pymupdf.Rect(0, 0, sw, sh) * mat, src, pno)
        for pno, page_links in enumerate(links):
            for link in page_links:
                try:
                    item = dict(link)
                    item.pop("xref", None)
                    item.pop("id", None)
                    if isinstance(item.get("from"), pymupdf.Rect):
                        item["from"] = item["from"] * mats[pno]
                    dest = item.get("page", -1)
                    if item.get("kind") == pymupdf.LINK_GOTO and 0 <= dest < len(mats):
                        if isinstance(item.get("to"), pymupdf.Point):
                            item["to"] = item["to"] * mats[dest]
                    out[pno].insert_link(item)
                except Exception:
                    continue
        try:
            if src.metadata:
                out.set_metadata(src.metadata)
            toc = src.get_toc()
            if toc:
                out.set_toc(sanitize_toc(toc))
        except Exception:
            pass
        _atomic_save(out, output_path, optimize=False)
        return output_path
    finally:
        src.close()
        out.close()


def prepared_source(input_path: str, config: PdfProcessConfig) -> str:
    """Eşitleme açıksa kaynağın sığdırılmış (önbellekli) kopyasının yolunu, değilse kendisini verir.

    İşleme, tarama, önizleme ve doğrulama aynı kopyayı görür; böylece sayfa ebatları her
    yerde tutarlıdır. Önbellek anahtarı dosya yolu + değişiklik zamanı + ayarlardır.
    """
    if config.page_numbers.enabled and config.page_numbers.sections:
        input_path = _prepare_sections(input_path, config)
    if getattr(config, "fit_mode", "off") == "off":
        return input_path
    st = os.stat(input_path)
    key = (os.path.abspath(input_path), st.st_mtime_ns, st.st_size,
           config.fit_mode, config.fit_keep_orientation, config.fit_rotate_landscape,
           config.flatten_annotations, config.fit_width_mm, config.fit_height_mm, config.fit_margin_mm)
    cached = _FIT_CACHE.get(key)
    if cached and os.path.exists(cached):
        return cached
    fd, tmp = tempfile.mkstemp(prefix="fit_", suffix=".pdf", dir=_fit_dir())
    os.close(fd)
    build_fitted_pdf(input_path, tmp, config)
    while len(_FIT_CACHE) >= 3:  # en eski kopyayı sil
        _, old = next(iter(_FIT_CACHE.items()))
        _FIT_CACHE.pop(next(iter(_FIT_CACHE)))
        try:
            os.remove(old)
        except OSError:
            pass
    _FIT_CACHE[key] = tmp
    return tmp


def _prepare_sections(input_path, config):
    sections, blanks = numbering_sections(config)
    with open_pdf(input_path) as check:
        if any(int(s.get("start_page", 1)) > len(check) for s in config.page_numbers.sections):
            raise ConfigError(["Bölüm başlangıcı belgenin sayfa sayısını aşamaz."])
    if not blanks:
        return input_path
    stat = os.stat(input_path)
    key = ("sections", os.path.abspath(input_path), stat.st_mtime_ns, stat.st_size,
           tuple(sorted(blanks)))
    if key in _FIT_CACHE and os.path.isfile(_FIT_CACHE[key]):
        return _FIT_CACHE[key]
    with open_pdf(input_path) as doc:
        if any(int(s.get("start_page", 1)) > len(doc) for s in config.page_numbers.sections):
            raise ConfigError(["Bölüm başlangıcı belgenin sayfa sayısını aşamaz."])
        links, toc = _collect_links(doc), doc.get_toc()
        mapping = []
        target = 0
        for original in range(len(doc)):
            while target in blanks:
                target += 1
            mapping.append(target)
            target += 1
        for position in sorted(blanks):
            ref = doc[min(position, len(doc) - 1)].rect
            doc.new_page(pno=position, width=ref.width, height=ref.height)
        for page in doc:
            for link in page.get_links():
                page.delete_link(link)
        for original, page_links in enumerate(links):
            for link in page_links:
                item = dict(link)
                item.pop("xref", None)
                item.pop("id", None)
                dest = item.get("page", -1)
                if item.get("kind") == pymupdf.LINK_GOTO and 0 <= dest < len(mapping):
                    item["page"] = mapping[dest]
                doc[mapping[original]].insert_link(item)
        if toc:
            for entry in toc:
                if 1 <= entry[2] <= len(mapping):
                    entry[2] = mapping[entry[2] - 1] + 1
            doc.set_toc(sanitize_toc(toc))
        fd, path = tempfile.mkstemp(prefix="sections_", suffix=".pdf", dir=_fit_dir())
        os.close(fd)
        try:
            _atomic_save(doc, path, False)
        except Exception:
            os.remove(path)
            raise
    while len(_FIT_CACHE) >= 3:
        old = _FIT_CACHE.pop(next(iter(_FIT_CACHE)))
        try:
            os.remove(old)
        except OSError:
            pass
    _FIT_CACHE[key] = path
    return path


def _collect_links(doc: pymupdf.Document) -> List[List[dict]]:
    out: List[List[dict]] = []
    for pno in range(len(doc)):
        try:
            out.append([dict(l) for l in doc[pno].get_links()])
        except Exception:
            out.append([])
    return out


def count_annotations(doc: pymupdf.Document) -> int:
    """Bağlantı olmayan açıklama + form alanı sayısı."""
    total = 0
    for page in doc:
        try:
            total += len(list(page.annots() or [])) + len(list(page.widgets() or []))
        except Exception:
            continue
    return total


def _copy_links(links_by_page: List[List[dict]], dst_doc: pymupdf.Document,
                layouts: List[PageLayout]) -> None:
    for pno, lay in enumerate(layouts):
        links = links_by_page[pno] if pno < len(links_by_page) else []
        mat = pymupdf.Matrix(lay.scale, 0, 0, lay.scale, lay.content.x0, lay.content.y0)
        for link in links:
            try:
                item = dict(link)
                item.pop("xref", None)
                item.pop("id", None)
                if isinstance(item.get("from"), pymupdf.Rect):
                    item["from"] = item["from"] * mat
                dest_page = item.get("page", -1)
                if item.get("kind") == pymupdf.LINK_GOTO and 0 <= dest_page < len(layouts):
                    dl = layouts[dest_page]
                    to = item.get("to")
                    if isinstance(to, pymupdf.Point):
                        dmat = pymupdf.Matrix(dl.scale, 0, 0, dl.scale, dl.content.x0, dl.content.y0)
                        item["to"] = to * dmat
                dst_doc[pno].insert_link(item)
            except Exception:
                continue  # tek bir bozuk bağlantı tüm işlemi durdurmasın


# ---------------------------------------------------------------------------
# Sonuç doğrulama
# ---------------------------------------------------------------------------
@dataclass
class VerifyReport:
    pages_src: int = 0
    pages_out: int = 0
    pad_pages: int = 0
    size_mismatches: List[int] = field(default_factory=list)   # 1 tabanlı sayfa no
    lost_words: int = 0
    lost_pages: List[int] = field(default_factory=list)
    has_text: bool = False
    links_src: int = 0
    links_out: int = 0
    dropped_annots: int = 0     # kaynakta olup çıktıda canlı olarak bulunmayan açıklama + form alanı
    flattened: bool = False     # True ise bunlar sayfaya gömüldü
    render_checked: int = 0     # görsel (piksel) karşılaştırması yapılan sayfa sayısı
    render_mismatch_pages: List[int] = field(default_factory=list)   # 1 tabanlı
    notes: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return (self.pages_src + self.pad_pages == self.pages_out
                and not self.size_mismatches and self.lost_words == 0
                and not self.render_mismatch_pages)

    def lines(self) -> List[str]:
        out = []
        expected = self.pages_src + self.pad_pages
        pad_note = f" (+{self.pad_pages} boş)" if self.pad_pages else ""
        out.append(("✔" if expected == self.pages_out else "✘")
                   + f" Sayfa sayısı: kaynak {self.pages_src}{pad_note}, çıktı {self.pages_out}")
        out.append(("✔" if not self.size_mismatches else "✘")
                   + (" Sayfa ebatları beklenen değerle uyuşuyor" if not self.size_mismatches
                      else f" {len(self.size_mismatches)} sayfanın ebadı beklenenden farklı"))
        if self.has_text:
            if self.lost_words == 0:
                out.append("✔ Kaynaktaki tüm metin çıktıda görünür durumda")
            else:
                pg = ", ".join(str(p) for p in self.lost_pages[:10])
                out.append(f"✘ {self.lost_words} sözcük çıktıda görünmüyor (sayfalar: {pg})")
        else:
            out.append("• Sayfalarda seçilebilir metin yok (taranmış/görsel PDF); metin karşılaştırması atlandı")
        if self.render_checked:
            if not self.render_mismatch_pages:
                out.append(f"✔ Görsel karşılaştırma: {self.render_checked} sayfada içerik kaynakla aynı")
            else:
                pg = ", ".join(str(p) for p in self.render_mismatch_pages[:10])
                out.append(f"✘ Görsel karşılaştırma: {len(self.render_mismatch_pages)} sayfada içerik "
                           f"kaynaktan farklı görünüyor (sayfalar: {pg})")
        if self.links_src:
            out.append(("✔" if self.links_out >= self.links_src else "•")
                       + f" Bağlantılar: kaynak {self.links_src}, çıktı {self.links_out}")
        if self.dropped_annots:
            if self.flattened:
                out.append(f"• {self.dropped_annots} açıklama/form alanı sayfaya gömüldü "
                           "(görünür, ama artık düzenlenemez)")
            else:
                out.append(f"✘ {self.dropped_annots} açıklama/form alanı yeni sayfaya taşınmadı")
        out.extend("• " + n for n in self.notes)
        return out


RENDER_CHECK_MAX_PAGES = 60     # uzun belgelerde eşit aralıklı örnekleme
RENDER_CHECK_ZOOM = 0.5
RENDER_BLOCK = 8
RENDER_INK_LEVEL = 248          # blok ortalaması bunun altındaysa blokta "mürekkep" var
RENDER_DIFF_LEVEL = 30
RENDER_MISMATCH_RATIO = 0.40
RENDER_MIN_MISMATCH_BLOCKS = 3


def _render_sample_pages(total: int) -> List[int]:
    if total <= RENDER_CHECK_MAX_PAGES:
        return list(range(total))
    step = (total - 1) / (RENDER_CHECK_MAX_PAGES - 1)
    return sorted({round(i * step) for i in range(RENDER_CHECK_MAX_PAGES)})


def _gray_pixmap(page: pymupdf.Page, clip: pymupdf.Rect, zoom: float) -> pymupdf.Pixmap:
    return page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip,
                           colorspace=pymupdf.csGRAY, alpha=False)


def render_page_differs(src_page: pymupdf.Page, out_page: pymupdf.Page,
                        lay: PageLayout) -> bool:
    """
    Kaynak sayfanın görünür içeriğini, çıktıdaki yerleştirilmiş hâliyle piksel düzeyinde
    karşılaştırır. Sayfa dışına taşan (kırpılan) bölüm kırpma taramasının konusudur;
    burada yalnızca çıktıda görünen bölüm sınanır. Döndürme/yerleşim hatalarını yakalar.
    """
    visible = lay.content & out_page.rect
    if visible.is_empty or lay.scale <= 0:
        return False
    src_clip = pymupdf.Rect(
        (visible.x0 - lay.content.x0) / lay.scale, (visible.y0 - lay.content.y0) / lay.scale,
        (visible.x1 - lay.content.x0) / lay.scale, (visible.y1 - lay.content.y0) / lay.scale,
    ) & src_page.rect
    if src_clip.is_empty:
        return False
    a = _gray_pixmap(src_page, src_clip, RENDER_CHECK_ZOOM)
    b = _gray_pixmap(out_page, visible, RENDER_CHECK_ZOOM / lay.scale)
    width, height = min(a.width, b.width), min(a.height, b.height)
    if width < 4 or height < 4 or abs(a.width - b.width) > 3 or abs(a.height - b.height) > 3:
        return abs(a.width - b.width) > 3 or abs(a.height - b.height) > 3
    # Alt-piksel kaymalarına dayanıklı olmak için 8x8 piksellik blokların ortalama
    # koyuluğu karşılaştırılır; tek tek piksel değil. Blok ortalamasını Pixmap.shrink
    # (2^n'e bölerek ortalar) C tarafında alır; Python yalnız küçük görüntüyü gezer.
    shift = RENDER_BLOCK.bit_length() - 1
    a.shrink(shift)
    b.shrink(shift)
    sa, sb = a.samples, b.samples
    wa, wb = a.width, b.width
    cols = min(wa, wb, width // RENDER_BLOCK)
    rows = min(a.height, b.height, height // RENDER_BLOCK)
    ink_blocks = bad_blocks = 0
    for by in range(rows):
        base_a, base_b = by * wa, by * wb
        row_a = sa[base_a: base_a + cols]
        row_b = sb[base_b: base_b + cols]
        for mean_a, mean_b in zip(row_a, row_b):
            if mean_a < RENDER_INK_LEVEL or mean_b < RENDER_INK_LEVEL:
                ink_blocks += 1
                if abs(mean_a - mean_b) > RENDER_DIFF_LEVEL:
                    bad_blocks += 1
    return (bad_blocks >= RENDER_MIN_MISMATCH_BLOCKS and ink_blocks > 0
            and bad_blocks / ink_blocks > RENDER_MISMATCH_RATIO)


@pdf_operation
def verify_output(
    input_path: str,
    output_path: str,
    config: PdfProcessConfig,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
    render_check: bool = True,
) -> VerifyReport:
    """
    Çıktıyı kaynakla karşılaştırır: sayfa sayısı, beklenen ebat, görünür metnin
    korunması, bağlantılar ve açıklamalar. 'Hiçbir şey kaybolmadı' iddiasının kanıtıdır.
    """
    input_path = prepared_source(input_path, config)
    src = open_pdf(input_path)
    out = open_pdf(output_path)
    rep = VerifyReport(pages_src=len(src), pages_out=len(out), flattened=config.flatten_annotations,
                       pad_pages=pad_page_count(len(src), config))
    render_src = open_pdf(input_path) if render_check else None
    try:
        n = min(len(src), len(out))
        render_pages = set(_render_sample_pages(n)) if render_check else set()
        if render_src is not None:
            normalize_page_rotations(render_src)   # çıktıdaki gibi görünür yönde karşılaştır
        for pno in range(n):
            if should_cancel and should_cancel():
                raise ProcessCancelled("Doğrulama iptal edildi.")
            sp, op = src[pno], out[pno]

            lay = compute_layout(sp.rect.width, sp.rect.height, config, pno)
            if abs(op.rect.width - lay.target_w) > 1.0 or abs(op.rect.height - lay.target_h) > 1.0:
                rep.size_mismatches.append(pno + 1)

            src_words = Counter(w[4] for w in sp.get_text("words"))
            if src_words:
                rep.has_text = True
                out_words = Counter(w[4] for w in op.get_text("words"))
                lost = src_words - out_words
                cnt = sum(lost.values())
                if cnt:
                    rep.lost_words += cnt
                    rep.lost_pages.append(pno + 1)

            if render_check and pno in render_pages:
                rep.render_checked += 1
                if render_page_differs(render_src[pno], op, lay):
                    rep.render_mismatch_pages.append(pno + 1)

            rep.links_src += len(sp.get_links())
            rep.links_out += len(op.get_links())
            s_extra = len(list(sp.annots() or [])) + len(list(sp.widgets() or []))
            o_extra = len(list(op.annots() or [])) + len(list(op.widgets() or []))
            rep.dropped_annots += max(0, s_extra - o_extra)

            if progress_callback:
                progress_callback(pno + 1, n)
    finally:
        src.close()
        out.close()
        if render_src is not None:
            render_src.close()
    return rep


# ---------------------------------------------------------------------------
# Birleştirme
# ---------------------------------------------------------------------------
def _contiguous_runs(pages: List[int]) -> List[Tuple[int, int]]:
    """Artan sayfa numaralarını ardışık (ilk, son) aralıklarına böler: [1,2,3,7,9,10] → [(1,3),(7,7),(9,10)]."""
    runs: List[Tuple[int, int]] = []
    for page in sorted(set(pages)):
        if runs and page == runs[-1][1] + 1:
            runs[-1] = (runs[-1][0], page)
        else:
            runs.append((page, page))
    return runs


@pdf_operation
def merge_pdfs(
    pdf_items: List[Union[str, dict]],
    output_path: str,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    quality_mode: str = "print",
    should_cancel: Optional[Callable[[], bool]] = None,
    warnings: Optional[List[str]] = None,
    add_bookmarks: bool = False,
) -> str:
    """
    Birden fazla PDF'i sıralı olarak tek belgede birleştirir. Her dosya için
    isteğe bağlı rotasyon (0/90/180/270) ve sayfa aralığı ("3-10, 15") uygulanır.
    Mevcut yer imleri sayfa numaraları kaydırılarak korunur; istenirse her dosya
    için dosya adından bir üst düzey yer imi eklenir. İlk dosyanın meta verisi
    korunur. Atlanan dosyalar ``warnings`` listesine yazılır.
    """
    if not pdf_items:
        raise ValueError("Birleştirilecek dosya seçilmedi.")

    def note(msg: str) -> None:
        if warnings is not None:
            warnings.append(msg)

    entries: List[dict] = []
    for item in pdf_items:
        if isinstance(item, str):
            data = {"path": item}
        elif isinstance(item, dict):
            data = dict(item)
        else:
            data = {"path": str(item)}
        path = data.get("path", "")
        try:
            rotation = int(data.get("rotation", 0))
        except (TypeError, ValueError):
            rotation = 0
        if not path or not os.path.exists(path):
            note(f"Bulunamadığı için atlandı: {path or '(boş yol)'}")
            continue
        if same_path(path, output_path):
            raise OutputPathError("Çıktı dosyası, birleştirilen dosyalardan biriyle aynı olamaz.")
        data["rotation"] = rotation
        entries.append(data)

    if not entries:
        raise StudioError("Birleştirilecek geçerli bir dosya bulunamadı.")

    merged = pymupdf.open()
    toc_out: List[list] = []
    first_metadata: Optional[dict] = None
    try:
        for idx, item in enumerate(entries):
            if should_cancel and should_cancel():
                raise ProcessCancelled("Birleştirme iptal edildi. Çıktı dosyası oluşturulmadı.")
            path = item["path"]
            extra_rot = item["rotation"]
            pages_str = str(item.get("pages", "") or "").strip()
            src = open_pdf(path)
            try:
                if first_metadata is None:
                    first_metadata = src.metadata

                selected: Optional[List[int]] = None
                if pages_str:
                    requested = sorted(parse_page_ranges(pages_str))
                    selected = [p for p in requested if 1 <= p <= len(src)]
                    if not selected:
                        note(f"Geçerli sayfa bulunmadığı için atlandı: {os.path.basename(path)} "
                             f"({pages_str})")
                        continue
                    if len(selected) == len(src):
                        selected = None  # tüm sayfalar seçili: aralık eklemeye gerek yok
                start = len(merged)

                toc = src.get_toc(simple=True)
                mapping = None
                if selected is not None:
                    mapping = {original: new_index + 1
                               for new_index, original in enumerate(selected)}

                bookmark_title = item.get("bookmark")
                if bookmark_title is None and add_bookmarks:
                    bookmark_title = os.path.splitext(os.path.basename(path))[0]
                # Dosya yer imi önce eklenir; dosyanın kendi yer imleri onun altına girer.
                nest = 1 if bookmark_title else 0
                if bookmark_title:
                    toc_out.append([1, str(bookmark_title), start + 1])
                for level, title, dest_page in toc:
                    if not isinstance(dest_page, int) or dest_page < 1:
                        continue
                    if mapping is not None:
                        mapped = mapping.get(dest_page)
                        if mapped is None:
                            continue
                        toc_out.append([level + nest, title, start + mapped])
                    else:
                        toc_out.append([level + nest, title, dest_page + start])

                # Seçili sayfalar kaynaktan ardışık aralıklar hâlinde doğrudan eklenir; dosyanın
                # tam bir geçici kopyası çıkarılmaz (yüzlerce sayfalık taramalarda bellek tasarrufu).
                if selected is not None:
                    for first, last in _contiguous_runs(selected):
                        merged.insert_pdf(src, from_page=first - 1, to_page=last - 1)
                else:
                    merged.insert_pdf(src)
            finally:
                src.close()

            if extra_rot % 360 != 0:
                for pno in range(start, len(merged)):
                    page = merged[pno]
                    page.set_rotation((page.rotation + extra_rot) % 360)
            if progress_callback:
                progress_callback(idx + 1, len(entries))

        if toc_out:
            merged.set_toc(sanitize_toc(toc_out))
        if first_metadata:
            merged.set_metadata(first_metadata)
        if len(merged) == 0:
            raise StudioError("Birleştirilecek geçerli sayfa bulunamadı.")
        _atomic_save(merged, output_path, optimize=(quality_mode != "print"))
        return output_path
    finally:
        merged.close()


if __name__ == "__main__":
    from studio_cli import main
    raise SystemExit(main())
