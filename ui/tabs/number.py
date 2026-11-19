"""Sayfa Numaraları sekmesi: kurulum, konum/biçim davranışları ve durum etiketi.

Sekme kendi widget'larını ve davranışını taşır; modül anahtarı ("Sayfa numarası"
onay kutusu), özet ve önizleme gibi kabuk işleri ``ctx`` üzerinden yapılır.
Alanlara pencereden değil sekme üzerinden erişilir (``app._number_tab().f_start_page``);
pencere takma adı köprüsü (``EXPOSED`` / ``__getattr__``) v2.6.20'de kaldırıldı.
"""

from __future__ import annotations

from ui import qt_compat as ctk

from ui.tabs.base import BaseTab
from ui.theme import *  # noqa: F401,F403
from ui.widgets import FieldRow


class NumberTab(BaseTab):
    """Sayfa numaralandırma ayarları."""

    #: Birim (mm/cm/inç) değişiminde dolaşılan alan satırları.
    FIELD_ROWS = ("f_font_size", "f_start_page", "f_start_num", "f_num_bottom", "f_num_side")

    def build(self) -> None:
        scroll = self.make_scroll()
        container = scroll

        # -- Numara konumu, biçimi ve yazı boyutu -------------------------------------
        pos = self.section(container, 0, "Numara konumu ve mesafeler")
        self.lbl_pnum_status = self.badge(pos)
        form = self.form_grid(pos, 0)

        cell = self.form_row(form, 0, "Yatay konum")
        self.seg_pos = ctk.CTkSegmentedButton(
            cell, values=list(POSITION_LABELS.keys()), height=26,
            border_width=0, fg_color=COLOR_SUBCARD, bg_color=COLOR_SUBCARD,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            selected_color=COLOR_SELECTED, selected_hover_color=COLOR_SELECTED_HOVER,
            unselected_color=COLOR_CARD, unselected_hover_color=COLOR_SUBCARD,
            text_color=COLOR_TEXT_PRIMARY, command=lambda _v: self.on_position_changed(),
        )
        self.seg_pos.put("h")

        cell_v = self.form_row(form, 1, "Dikey konum")
        self.seg_vpos = ctk.CTkSegmentedButton(
            cell_v, values=list(VPOS_LABELS.keys()), height=26,
            border_width=0, fg_color=COLOR_SUBCARD, bg_color=COLOR_SUBCARD,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            selected_color=COLOR_SELECTED, selected_hover_color=COLOR_SELECTED_HOVER,
            unselected_color=COLOR_CARD, unselected_hover_color=COLOR_SUBCARD,
            text_color=COLOR_TEXT_PRIMARY, command=lambda _v: self.on_vpos_changed(),
        )
        self.seg_vpos.set("Alt kenar")
        self.seg_vpos.put("h")

        cell = self.form_row(form, 2, "Görünüm biçimi")
        self.menu_format = ctk.CTkOptionMenu(
            cell, values=list(FORMAT_LABELS.keys()), width=170, height=26,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            fg_color=COLOR_CARD, text_color=COLOR_TEXT_PRIMARY,
            button_color=COLOR_SUBCARD, button_hover_color=COLOR_BTN_SUBTLE_HOVER,
            dropdown_fg_color=COLOR_CARD, dropdown_hover_color=COLOR_SELECTED,
            dropdown_text_color=COLOR_TEXT_PRIMARY,
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            command=lambda _v: self.on_changed(),
        )
        self.menu_format.set("1, 2, 3")
        self.menu_format.put("h")

        cell_style = self.form_row(form, 3, "Yazı boyutu")
        self.f_font_size = FieldRow(cell_style, "", "10", unit="pt", convert=False, width=64,
                                    minimum=1, maximum=72, on_change=self.on_changed)
        self.f_font_size.put("h", margins=(0, 0, SP_M, 0))

        self.num_color = (0.08, 0.08, 0.08)
        self.btn_num_color = ctk.CTkButton(
            cell_style, text="Yazı rengi", width=88, height=26,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            fg_color="#141414", text_color="#FFFFFF",
            border_width=1, border_color=COLOR_BORDER,
            command=self._pick_num_color,
        )
        self.btn_num_color.setToolTip("Sayfa numarası yazı rengi")
        self.btn_num_color.put("h")

        # Mesafeler tablosu
        self.sub_label(pos, 1, "Başlangıç ve kenar mesafeleri")
        grid = ctk.CTkFrame(pos, fg_color="transparent")
        grid.place(2, 0, expand_x=True)
        grid.grid_columnconfigure(3, weight=1)
        # Tablo, başlığa göre SP_M içeriden başlar (açık kenar boşluğu).
        grid.set_padding(SP_M, 0, 0, 0, spacing=SP_S)

        self.f_start_page = FieldRow(grid, "Başlangıç sayfası", "1", convert=False, width=72,
                                     minimum=1, maximum=100000, integer=True,
                                     suffix="", label_width=FORM_LABEL_W, on_change=self.on_changed)
        self.f_start_page.place(0, 0, align="w")
        self.f_start_num = FieldRow(grid, "İlk numara", "1", convert=False, width=72,
                                     minimum=0, maximum=100000, integer=True,
                                     suffix="", label_width=FORM_LABEL_W, on_change=self.on_changed)
        self.f_start_num.place(0, 1, align="w")

        self.f_num_bottom = FieldRow(grid, "Alt kenar uzaklığı", "12", width=72, minimum=0, maximum=5000,
                                     label_width=FORM_LABEL_W, on_change=self.on_changed)
        self.f_num_bottom.place(1, 0, align="w")
        self.f_num_side = FieldRow(grid, "Yan boşluk", "15", width=72, minimum=0, maximum=5000,
                                   label_width=FORM_LABEL_W, on_change=self.on_changed)
        self.f_num_side.place(1, 1, align="w")

        self.lbl_side_hint = ctk.CTkLabel(
            pos, text="", font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, anchor="w",
        )
        self.lbl_side_hint.place(3, 0, align="w")

        # -- 2. Kart: Numarasız sayfalar ve özel şablon -----------------------------
        extra = self.section(container, 1, "Numarasız sayfalar ve özel şablon")
        form2 = self.form_grid(extra, 0)

        cell = self.form_row(form2, 0, "Numarasız sayfalar", stretch=True)
        self.entry_skip_pages = ctk.CTkEntry(
            cell, placeholder_text="Örn: 1, 2, 15, 24-26 (kapak veya bölüm başlıkları)", height=26,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_BODY),
            fg_color=COLOR_CARD, border_color=COLOR_BORDER, text_color=COLOR_TEXT_PRIMARY,
        )
        self.entry_skip_pages.setMaximumWidth(ENTRY_MAX_W)
        self.entry_skip_pages.put("h", fill="x", expand=True)
        self.entry_skip_pages.bind("<KeyRelease>", lambda e: self.on_changed())

        chk_row = ctk.CTkFrame(extra, fg_color="transparent")
        chk_row.place(1, 0, align="w")
        self.chk_continuous = ctk.CTkCheckBox(
            chk_row,
            text="Numarasız kapak sayfalarında sayacı dondur",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_PRIMARY, hover_color=COLOR_ACCENT,
            fg_color=COLOR_SOLID, command=self.on_changed,
        )
        self.chk_continuous.select()
        self.chk_continuous.setToolTip("Örn. 90 → kapak → 91 olarak devam etsin.")
        self.chk_continuous.put("h")

        form3 = self.form_grid(extra, 2)
        cell = self.form_row(form3, 0, "Özel şablon", stretch=True)
        self.entry_number_template = ctk.CTkEntry(
            cell, placeholder_text="Örn: {n} / {N}  •  {roman}  •  Sayfa {n}",
            height=26, font=ctk.CTkFont(family=FONT_FAMILY, size=FS_BODY),
            fg_color=COLOR_CARD, border_color=COLOR_BORDER, text_color=COLOR_TEXT_PRIMARY,
        )
        self.entry_number_template.setMaximumWidth(ENTRY_MAX_W)
        self.entry_number_template.put("h", fill="x", expand=True)
        self.entry_number_template.bind("<KeyRelease>", lambda e: self.on_changed())

        tmpl_help = ctk.CTkLabel(
            extra,
            text="Boş bırakılırsa seçili numara biçimi kullanılır. Değişkenler: {n} numara, {N} toplam sayfa, "
                 "{roman}/{ROMAN} Romen rakamı.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=NOTE_WRAP_W_WIDE,
        )
        tmpl_help.place(3, 0)
        self.ctx.bind_wraplength(tmpl_help, extra, 24)

        from ui.section_editor import SectionEditor
        sections = self.section(container, 2, "Bölüm numaralandırması")
        self.section_editor = SectionEditor(sections, self.on_changed)
        self.section_editor.place(0, 0, expand_x=True)
        controls = ctk.CTkFrame(sections, fg_color="transparent")
        controls.place(1, 0, align="w")
        ctk.CTkButton(controls, text="Bölüm ekle", command=self.section_editor.add_section).put("h")
        ctk.CTkButton(controls, text="Bölümü kaldır", command=self.section_editor.remove_selected).put("h")
        ctk.CTkLabel(sections, text="Bölüm eklenirse üstteki başlangıç ve biçim yerine bölüm tablosu kullanılır. Sağ sayfada başla seçeneği gerektiğinde önüne boş sayfa ekler.",
                      wraplength=500, anchor="w", justify="left").place(2, 0, expand_x=True)

        # Açılış durumu: rozet modül anahtarına göre kurulur, özet ve önizleme güncellenir.
        self.show_active(self.ctx.module_enabled("pnum"))
        self.ctx.on_field_changed()

    # =====================================================================
    # Davranışlar
    # =====================================================================
    def on_changed(self) -> None:
        """Sayfa numarası alanı değişince: modül kapalıysa açar, değilse yeniler."""
        if not self.ctx.module_enabled("pnum"):
            self.ctx.enable_module("pnum")
        else:
            self.ctx.on_field_changed()

    def on_position_changed(self) -> None:
        """Alt orta seçiliyken yan boşluk anlamsızdır; alanı devre dışı bırakıp açıklar."""
        self.update_side_state()
        self.on_changed()

    def on_vpos_changed(self) -> None:
        """Dikey konum değişince kenar uzaklığı etiketini günceller."""
        self.update_vpos_state()
        self.on_changed()

    def update_vpos_state(self) -> None:
        vpos = VPOS_LABELS.get(self.seg_vpos.get(), "bottom")
        self.f_num_bottom.label.configure(
            text="Üst kenar uzaklığı" if vpos == "top" else "Alt kenar uzaklığı"
        )

    def set_num_color(self, rgb: tuple) -> None:
        r, g, b = (max(0.0, min(1.0, float(c))) for c in rgb[:3])
        self.num_color = (r, g, b)
        hex_color = f"#{int(r * 255):02X}{int(g * 255):02X}{int(b * 255):02X}"
        lum = 0.299 * r + 0.587 * g + 0.114 * b
        fg_text = "#111111" if lum > 0.55 else "#FFFFFF"
        self.btn_num_color.configure(fg_color=hex_color, text_color=fg_text)

    def _pick_num_color(self) -> None:
        from PySide6.QtGui import QColor
        from PySide6.QtWidgets import QColorDialog
        initial = QColor.fromRgbF(*self.num_color)
        chosen = QColorDialog.getColor(initial, self.btn_num_color, "Sayfa numarası rengi")
        if chosen.isValid():
            self.set_num_color((chosen.redF(), chosen.greenF(), chosen.blueF()))
            self.on_changed()

    def update_side_state(self) -> None:
        """Modülü tetiklemeden yalnızca 'Yan boşluk' alanının etkinliğini günceller."""
        pos = POSITION_LABELS.get(self.seg_pos.get(), "outer")
        if pos == "center":
            self.f_num_side.set_enabled(False)
            self.f_num_side.label.configure(text_color=COLOR_TEXT_SECONDARY)
            self.lbl_side_hint.configure(text="Alt orta konumunda yan boşluk kullanılmaz.")
        else:
            self.f_num_side.set_enabled(True)
            self.f_num_side.label.configure(text_color=COLOR_TEXT_PRIMARY)
            self.lbl_side_hint.configure(text="")

    def show_active(self, active: bool) -> None:
        """Modül anahtarının durumunu bölüm başlığındaki rozete yazar."""
        self.set_badge(self.lbl_pnum_status, active)
