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

# Boşluk ölçeği (tek kaynak). Not: qt_compat ``grid``/``pack`` içindeki padx/pady'yi
# aralık olarak uygulamaz; aralık kapsayıcının ``set_padding(spacing=...)`` değeriyle verilir.
SP_XS = 4
SP_S = 8
SP_M = 12
SP_L = 20
FORM_LABEL_W = 138      # form satırlarında etiket sütunu genişliği
CONTENT_MAX_W = 820     # sekme içeriğinin azami genişliği
FIELD_W = 72            # sayı alanı kutusu genişliği
BTN_H = 28              # ikincil düğme yüksekliği
STACK_LABEL_TOP = 6     # alt alta form satırında etiketin ilk satırla dikey ortalanması (px)
BTN_W = 90              # ikincil düğme genişliği
BTN_W_PRIMARY = 110     # birincil (dolgulu) düğme genişliği

# Yerleşim sabitleri (eskiden dosyalara dağınık "sihirli sayılardı")
SIDEBAR_W = 230         # sol menü sütunu genişliği
ACTION_BTN_W = 230      # alt çubuktaki ana işlem düğmesi genişliği
CENTER_MIN_W = 540      # ortadaki içerik alanının asgari genişliği
CENTER_MAX_W = 620      # ortadaki içerik alanının tercih edilen üst sınırı
PREVIEW_MIN_W = 360     # önizleme panelinin asgari genişliği
PREVIEW_MAX_W = 850     # önizleme panelinin azami genişliği
PREVIEW_DEFAULT_W = 480 # önizleme panelinin varsayılan genişliği
PREVIEW_STORE_MIN_W = 280   # kayıtlı genişlik için alt sınır (settings_store aynı değeri kullanır)
PREVIEW_STORE_MAX_W = 900   # kayıtlı genişlik için üst sınır
ROW_MAX_W = 580         # düğme satırlarının azami genişliği
ENTRY_MAX_W = 460       # tek satırlık metin kutularının azami genişliği
NOTE_WRAP_W = 520       # not/uyarı metinlerinin satır kırma genişliği
NOTE_WRAP_W_WIDE = 580  # geniş kart içindeki notların satır kırma genişliği
DIALOG_MIN_W = 480      # iletişim kutusu asgari genişliği
DIALOG_MIN_H = 320      # iletişim kutusu asgari yüksekliği

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

# --- Metin / kırpma riski diyalogları (P2-35) ---
CLIP_DIALOG_TITLE = "Kırpma riski"   # tarama ve onay diyaloğu aynı pencere başlığını taşır
TEXT_DIALOG_W = 620                  # metin diyaloğu genişliği
TEXT_DIALOG_BOX_MIN_H = 60           # metin kutusu asgari yüksekliği
TEXT_DIALOG_BOX_MAX_H = 300          # içerik bundan uzunsa kutu kaydırılır
TEXT_DIALOG_CHROME_H = 130           # başlık + düğme satırı + kenar boşlukları



#: "Sayfaları eşitle" menüsü: etiket → ``PdfProcessConfig.fit_mode`` (sıra menü sırasıdır).
FIT_LABELS = {
    "Kapalı (sayfalar olduğu gibi)": "off",
    "İlk sayfanın ebadına": "first",
    "En büyük sayfanın ebadına": "largest",
    "A5'e": "a5",
    "A4'e": "a4",
    "A3'e": "a3",
}
FIT_CODES = {code: label for label, code in FIT_LABELS.items()}

# --- Birleştirme listesi sürükle-bırak (P3-40) ---
DRAG_START_PX = 4        # bu kadar piksel oynamadan tıklama sayılır, sürükleme başlamaz
DROP_LINE_H = 3          # bırakma yeri çizgisinin kalınlığı
DRAG_SCROLL_ZONE = 28    # liste alt/üst kenarında otomatik kaydırma şeridi (px)
DRAG_SCROLL_MAX_STEP = 18  # tek adımda en çok kaydırılan piksel (kenara/ötesine gelince)
DRAG_SCROLL_MS = 30      # otomatik kaydırma zamanlayıcı aralığı
