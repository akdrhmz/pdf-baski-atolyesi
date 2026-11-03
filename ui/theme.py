"""Tasarım ölçüleri, renkler ve etiket tabloları (tek kaynak)."""

# ---------------------------------------------------------------------------
# Tasarım ölçüleri (tek kaynak: tüm yazı boyutları buradan gelir)
# ---------------------------------------------------------------------------
FONT_FAMILY = "Segoe UI"
FS_TITLE = 22
FS_SUBTITLE = 15
FS_BODY = 14
FS_SMALL = 12
FS_TINY = 11
BODY_MIN_PX = 12

# Açık / koyu tema renk çiftleri
COLOR_BG = ("#F6F8FA", "#0D1117")
COLOR_CARD = ("#FFFFFF", "#161B22")
COLOR_SUBCARD = ("#F6F8FA", "#1F242C")
COLOR_BORDER = ("#D0D7DE", "#30363D")
COLOR_TEXT_PRIMARY = ("#1F2328", "#F0F6FC")
COLOR_TEXT_SECONDARY = ("#656D76", "#8B949E")
COLOR_ACCENT = ("#0969DA", "#58A6FF")
COLOR_ACCENT_HOVER = ("#0854C4", "#79B8FF")
COLOR_SOLID = ("#0969DA", "#1F6FEB")
COLOR_SOLID_HOVER = ("#0854C4", "#1857B8")
COLOR_ON_ACCENT = ("#FFFFFF", "#FFFFFF")
COLOR_SELECTED = ("#B7DCFF", "#17456E")
COLOR_SELECTED_HOVER = ("#9FCDF8", "#1D527F")
COLOR_BTN_SUBTLE = ("#F3F4F6", "#21262D")
COLOR_BTN_SUBTLE_HOVER = ("#E5E7EB", "#30363D")
COLOR_OK = ("#1A7F37", "#3FB950")
COLOR_OK_BG = ("#DAFBE1", "#133E1D")
COLOR_WARN = ("#9A6700", "#D29922")
COLOR_WARN_BG = ("#FFF8C5", "#3D2C00")
COLOR_ERROR = ("#CF222E", "#FF7B72")
COLOR_ERROR_BG = ("#FFEBE9", "#3D1A1C")

POSITION_LABELS = {
    "Dış kenar (Tek sağ / Çift sol)": "outer",
    "Alt orta": "center",
    "İç kenar": "inner",
}
POSITION_CODES = {v: k for k, v in POSITION_LABELS.items()}
FORMAT_LABELS = {
    "1, 2, 3": "number",
    "- 1 -": "dash",
    "1 / Toplam": "total",
    "Sayfa 1": "label",
    "i, ii, iii": "roman",
    "I, II, III": "roman_upper",
}
FORMAT_CODES = {v: k for k, v in FORMAT_LABELS.items()}
MODE_LABELS = {
    "Uzat (kırpmaz, önerilen)": "expand",
    "Sığdır (orantılı küçült)": "fit",
    "Kaydır (kırpabilir)": "shift",
}
MODE_CODES = {v: k for k, v in MODE_LABELS.items()}
SIZE_MODE_LABELS = {
    "Hedef ebat sabit": "fixed",
    "Kaynak ebat + cilt payı": "auto",
}
SIZE_MODE_CODES = {v: k for k, v in SIZE_MODE_LABELS.items()}
OVERFLOW_LABELS = {
    "Kırp": "clip",
    "Sayfaya sığdır": "shrink",
}
OVERFLOW_CODES = {v: k for k, v in OVERFLOW_LABELS.items()}
MARGIN_PRESETS_MM = (10.0, 15.0, 20.0, 25.0)
PAPER_SIZES = {
    "A4 (210 × 297)": (210.0, 297.0),
    "A5 (148 × 210)": (148.0, 210.0),
    "B5 (176 × 250)": (176.0, 250.0),
    "Letter (8.5 × 11 inç)": (215.9, 279.4),
}
# İnç şimdilik arayüzde kapalı; motor desteği ileride açılmak üzere duruyor.
DISPLAY_UNITS = ("mm", "cm", "pt")
