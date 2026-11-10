"""Sayfa Düzeni sekmesi: cilt payı + alt/üst boşluk + ebat + özel sayfalar.

P3 13d'nin 2. parçası (v2.5.0). Eski ``GutterTab`` ve ``MarginTab`` burada tek
sekmede birleşti; bölümler üstten alta **Cilt payı · Alt/üst boşluk · Sayfa
boyutu ve sığdırma · Özel sayfalar**. Cilt payı ve boşluğun açma/kapama
anahtarları ve rozetleri ayrı kalır (boşluk, cilt payı olmadan da kullanılır).

Taşma kararı tek denetimdir (``page_layout_model.OVERFLOW_CHOICES``); özel
sayfalar ``SpecialRule`` satırlarıdır. Ayar dosyası ve motor değişmez: sekme
``page_layout_model.read_unified`` / ``write_unified`` üzerinden eski iki ayar
kümesine yazar.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from ui import qt_compat as ctk

import page_layout_model as plm
from gutter_engine import format_measure, invalid_range_tokens
from settings_store import PRESETS
from ui.tabs.base import BaseTab
from ui.theme import *  # noqa: F401,F403
from ui.widgets import FieldError, FieldRow, WrapButtonRow

#: Taşma denetiminin etiketleri (sıra ``OVERFLOW_CHOICES`` ile aynı).
CHOICE_LABELS = {choice: label for choice, (label, _desc) in plm.OVERFLOW_CHOICES.items()}
LABEL_TO_CHOICE = {label: choice for choice, label in CHOICE_LABELS.items()}
#: Ebat modu satırının altındaki tek cümlelik açıklama (P2-36).
SIZE_MODE_NOTES = {
    "fixed": "Her sayfa aşağıdaki hedef ebada oturur.",
    "auto": "Ebat her sayfada kaynak sayfadan + cilt payından hesaplanır; hedef ebat sorulmaz.",
}
SAFE_EDGE_NOTE = "Küçültmede kenarda bırakılacak ek boşluk."
#: Karışık ebatlı PDF'te hedef boyutun hangi sayfadan alınacağı.
SIZE_SOURCE_LABELS = {
    "Baskın sayfa (önerilen)": "dominant",
    "İlk sayfa": "first",
    "En büyük sayfa": "largest",
}
SIZE_SOURCE_CODES = {value: label for label, value in SIZE_SOURCE_LABELS.items()}

#: Özel sayfa satırındaki kısa kip etiketleri (uzun ``SPECIAL_MODES`` metni menüye sığmaz).
ROW_MODE_LABELS = {
    "Pay yok": plm.MODE_NONE,
    "Yalnız cilt payı": plm.MODE_GUTTER_ONLY,
    "Yalnız alt/üst boşluk": plm.MODE_MARGIN_ONLY,
}
MODE_TO_ROW_LABEL = {mode: label for label, mode in ROW_MODE_LABELS.items()}

_KURAL_YOK = "Kural yok: tüm sayfalara cilt payı ve/veya boşluk uygulanır."


class _RuleRow:
    """Tek özel sayfa kuralı satırı: sayfa aralığı + kip + kaldır."""

    def __init__(self, parent, on_change, pages: str = "", mode: str = plm.MODE_GUTTER_ONLY):
        self.frame = ctk.CTkFrame(parent, fg_color="transparent")
        self.frame.set_padding(0, 0, 0, 0, spacing=SP_XS)
        self.frame.grid_columnconfigure(0, weight=1)

        line = ctk.CTkFrame(self.frame, fg_color="transparent")
        line.place(0, 0, expand_x=True)
        self.entry = ctk.CTkEntry(
            line, placeholder_text="Örn: 1, 5, 9-10", height=BTN_H,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_BODY),
            fg_color=COLOR_CARD, border_color=COLOR_BORDER, text_color=COLOR_TEXT_PRIMARY,
        )
        self.entry.insert(0, pages)
        self.entry.put("h", fill="x", expand=True)
        self.entry.bind("<KeyRelease>", lambda _e: on_change())

        self.remove_button = ctk.CTkButton(
            line, text="Kaldır", width=64, height=BTN_H,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            fg_color=COLOR_CARD, text_color=COLOR_TEXT_PRIMARY,
            border_width=1, border_color=COLOR_BORDER,
            hover_color=COLOR_BTN_SUBTLE_HOVER,
        )
        self.remove_button.put("h")

        self.mode_menu = ctk.CTkOptionMenu(
            self.frame, values=list(ROW_MODE_LABELS.keys()), width=220, height=BTN_H,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            fg_color=COLOR_CARD, text_color=COLOR_TEXT_PRIMARY,
            button_color=COLOR_SUBCARD, button_hover_color=COLOR_BTN_SUBTLE_HOVER,
            dropdown_fg_color=COLOR_CARD, dropdown_hover_color=COLOR_SELECTED,
            dropdown_text_color=COLOR_TEXT_PRIMARY,
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            command=lambda _v: on_change(),
        )
        self.mode_menu.set(MODE_TO_ROW_LABEL.get(mode, MODE_TO_ROW_LABEL[plm.MODE_GUTTER_ONLY]))
        self.mode_menu.place(1, 0, align="w")

        self.error_label = ctk.CTkLabel(
            self.frame, text="",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_ERROR, anchor="w", justify="left", wraplength=NOTE_WRAP_W,
        )
        self.error_label.place(2, 0, expand_x=True)
        self.error_label.grid_remove()

    def pages(self) -> str:
        return self.entry.get().strip()

    def mode(self) -> str:
        return ROW_MODE_LABELS.get(self.mode_menu.get(), plm.MODE_GUTTER_ONLY)

    def set_error(self, message: str) -> None:
        self.error_label.configure(text=message)
        self.entry.configure(border_color=COLOR_ERROR if message else COLOR_BORDER)
        if message:
            self.error_label.place_restore()
        else:
            self.error_label.grid_remove()

    def destroy(self) -> None:
        self.frame.destroy()


class PageLayoutTab(BaseTab):
    """Cilt payı, alt/üst boşluk, ebat ve özel sayfa kuralları tek sekmede."""

    #: Pencereye takma ad olarak bağlanan widget adları (geçiş köprüsü).
    #: v2.6.16 (P3-16, 1. parça): yalnızca pencere/kabuk kodunun hâlâ okuduğu adlar kaldı;
    #: dışarıdan hiç okunmayan dokuz ad (etiketler, menüler) köprüden çıkarıldı ve
    #: yalnızca sekmenin kendi özelliği olarak erişilir (``tab.paper_menu`` gibi).
    #: v2.6.18 (P3-16, 3. parça): alan ve denetimler köprüden çıktı; yalnızca kabuğun
    #: paylaştığı iki modül anahtarı pencerede takma ad olarak kalır.

    #: Birim değişiminde (``reset_unit``) dolaşılan alan satırları.
    FIELD_ROWS = (
        "f_width", "f_height", "f_safe_edge", "f_odd_x", "f_odd_y", "f_even_x", "f_even_y",
        "f_bottom", "f_top",
        "f_fit_width", "f_fit_height", "f_fit_margin",
    )

    CUSTOM_PAPER = "Özel ölçü"

    def build(self) -> None:
        scroll = self.make_scroll()
        scroll.set_padding(SP_M, SP_M, SP_M, SP_M, spacing=SP_L)
        self._scroll = scroll
        container = scroll
        self._loaded_pair: Optional[Tuple[str, str]] = None
        self._section_widgets: dict = {}
        self._rule_rows: List[_RuleRow] = []

        self._build_gutter_section(container, 0)
        self._build_margin_section(container, 1)
        self._build_size_section(container, 2)
        self._build_special_section(container, 3)

        self.show_active(self.switch_gutter.get() == 1)
        self.show_margin_active(self.switch_margin.get() == 1)
        self.update_safe_edge_state()
        self.sync_size_source()
        self.ctx.on_field_changed()

    def _module_switch_widget(self, key: str, checked: bool):
        """Modül anahtarını yan menüden paylaşır; bağlam vermezse gizli yerel anahtar kurar."""
        getter = getattr(self.ctx, "module_switch_widget", None)
        shared = getter(key) if callable(getter) else None
        if shared is not None:
            return shared
        local = ctk.QtSwitch(
            self.frame, checked=checked, width=42, height=22,
            command=lambda: self.on_module_toggle(key),
        )
        local.hide()
        return local

    def scroll_to_section(self, key: str) -> None:
        """Yan menü alt başlığına tıklanınca ilgili bölüme kaydırır."""
        widget = self._section_widgets.get(key)
        if widget is None:
            return
        try:
            card = widget.parentWidget()
            scroll = self._scroll
            scroll.ensureWidgetVisible(card, 0, 8)
        except Exception:
            pass

    # =====================================================================
    # Bölüm: Cilt payı
    # =====================================================================
    def _build_gutter_section(self, container, row: int) -> None:
        quick = self.section(container, row, "Cilt payı")
        self._section_widgets["gutter"] = quick
        # Anahtar yan menüde (akordeon alt başlığı); sayfa içinde anahtar yok.
        self.switch_gutter = self._module_switch_widget("gutter", True)
        self.lbl_gutter_status = self.badge(quick)

        self._gutter_preset_row = WrapButtonRow(quick, stretch=True, wrap=False, gap=SP_S)
        self._gutter_preset_row.place(0, 0, align="w", expand_x=True)
        # expand_x geni?lik kilidini kald?r?r; ?st s?n?r yerle?tirmeden sonra verilir.
        self._gutter_preset_row.setMaximumWidth(720)
        for text, value in (("İnce (10 mm)", 10.0), ("Standart (15 mm)", 15.0),
                            ("Geniş (20 mm)", 20.0)):
            self._gutter_preset_row.add_button(
                text, lambda v=value: self.apply_preset(v), width=BTN_W_PRIMARY)
        self._gutter_preset_row.add_button("Sıfırla", self.reset_values, width=BTN_W)
        self._preset_values = (10.0, 15.0, 20.0)

        self.sub_label(quick, 1, "Hazır baskı şablonları")
        # Uzun profil adları ("Sıcak tutkal cilt") eşit sütunlara sığmıyordu; düğme
        # metin kadar genişler, satır tek kalır.
        self._preset_row = WrapButtonRow(quick, stretch=False, wrap=False, gap=SP_S)
        self._preset_row.place(2, 0, align="w", expand_x=True)
        # expand_x geni?lik kilidini kald?r?r; ?st s?n?r yerle?tirmeden sonra verilir.
        self._preset_row.setMaximumWidth(720)
        for preset_name in PRESETS:
            short = preset_name.split(" (")[0]
            self._preset_row.add_button(
                short, lambda name=preset_name: self.ctx.apply_named_preset(name), width=0)

        offset = ctk.CTkFrame(quick, fg_color="transparent")
        # Sol girinti (SP_M) eskiden ikinci sütundaki ``padx=(SP_M, 0)`` yüzünden grid()'in
        # gizli kuralıyla geliyordu; şimdi açıkça yazılı.
        offset.set_padding(SP_M, SP_XS, SP_XS, 0, spacing=SP_M)
        offset.place(3, 0, align="w")
        offset.grid_columnconfigure(5, weight=1)

        def _field(parent, value: str = "0", on_change=None) -> FieldRow:
            field = FieldRow(parent, "", value, width=FIELD_W, minimum=-5000, maximum=5000,
                             allow_negative=True, on_change=on_change or self.on_changed)
            return field

        def _row_label(parent, text: str):
            return ctk.CTkLabel(
                parent, text=text,
                font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
                text_color=COLOR_TEXT_PRIMARY, anchor="w", width=FORM_LABEL_W,
            )

        def _axis_tag(parent, text: str):
            return ctk.CTkLabel(
                parent, text=text, width=40, anchor="w",
                font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
                text_color=COLOR_TEXT_SECONDARY,
            )

        ctk.CTkLabel(
            offset, text="Yatay (Cilt)", font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY, weight="bold"),
            text_color=COLOR_TEXT_SECONDARY, anchor="w",
        ).place(0, 1, align="w")
        ctk.CTkLabel(
            offset, text="Dikey (Ofset)", font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY, weight="bold"),
            text_color=COLOR_TEXT_SECONDARY, anchor="w",
        ).place(0, 2, align="w")

        for r, (text, x_name, y_name) in enumerate((
            ("Tek sayfalar", "f_odd_x", "f_odd_y"),
            ("Çift sayfalar", "f_even_x", "f_even_y"),
        ), start=1):
            _row_label(offset, text).place(r, 0, align="w")
            x_field = _field(offset)
            x_field.place(r, 1, align="w")
            y_field = _field(offset)
            y_field.place(r, 2, align="w")
            setattr(self, x_name, x_field)
            setattr(self, y_name, y_field)

        note = ctk.CTkLabel(
            offset,
            text="Tek sayfa = sağ sayfa (cilt sol kenarda) • Çift sayfa = sol sayfa (cilt sağ kenarda)",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=NOTE_WRAP_W,
        )
        note.place(3, 0, columnspan=4, expand_x=True)
        self.ctx.bind_wraplength(note, offset, 30)
        self.menu_binding = ctk.CTkOptionMenu(
            quick, values=list(BINDING_LABELS), width=200,
            command=lambda _v: self.on_changed())
        self.menu_binding.set(BINDING_CODES["left"])
        self.menu_binding.place(4, 0, align="w")
        self.menu_binding.setToolTip("Üstten ciltte Yatay (Cilt) alanı üst payı, Dikey (Ofset) alanı yatay ofseti belirler. Sağdan cilt, soldan cildin yatay aynasıdır.")
        note.configure(text="Tek/çift sayfa payları ayrı uygulanır. Cilt yerini alttaki menüden seçin.")

        # Yalnız karışık ebatlı belgelerde: hedef ebat hangi sayfadan alınsın?
        self._size_source_row = ctk.CTkFrame(quick, fg_color="transparent")
        self._size_source_row.place(5, 0, align="w")
        ctk.CTkLabel(
            self._size_source_row, text="Ebat kaynağı",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
        ).put("h", margins=(0, 0, SP_S, 0))
        self.size_source_menu = ctk.CTkOptionMenu(
            self._size_source_row, values=list(SIZE_SOURCE_LABELS), width=200,
            command=self._on_size_source_changed,
        )
        self.size_source_menu.set(SIZE_SOURCE_CODES["dominant"])
        self.size_source_menu.put("h")
        self._size_source_row.setToolTip(  # type: ignore[attr-defined]
            "Karışık ebatlı PDF'te hedef ebat için kullanılacak sayfa boyutu.")
        self._size_source_row.hide()

    # =====================================================================
    # Bölüm: Alt/üst boşluk
    # =====================================================================
    def _build_margin_section(self, container, row: int) -> None:
        pay = self.section(container, row, "Boşluklar ve kitapçık")
        self._section_widgets["margin"] = pay
        self.switch_margin = self._module_switch_widget("margin", True)
        self.lbl_margin_status = self.badge(pay)

        bottom_line = ctk.CTkFrame(pay, fg_color="transparent")
        bottom_line.place(0, 0, expand_x=True)
        ctk.CTkLabel(bottom_line, text="Alt boşluk", width=95, anchor="w",
                     font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
                     text_color=COLOR_TEXT_PRIMARY).put("h")
        self.f_bottom = FieldRow(bottom_line, "", "0", width=FIELD_W,
                                 minimum=0, maximum=5000, on_change=self.on_margin_changed)
        self.f_bottom.put("h")
        self._bottom_preset_row = WrapButtonRow(bottom_line, stretch=False, wrap=False, gap=SP_XS)
        self._bottom_preset_row.put("h", fill="x", expand=True)
        for value in MARGIN_PRESETS_MM:
            self._bottom_preset_row.add_button(
                self.preset_label(value), lambda v=value: self.set_bottom(v), width=38)
        self._bottom_preset_row.add_button("Sıfırla", lambda: self.set_bottom(0.0), width=52)

        top_line = ctk.CTkFrame(pay, fg_color="transparent")
        top_line.place(1, 0, expand_x=True)
        ctk.CTkLabel(top_line, text="Üst boşluk", width=95, anchor="w",
                     font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
                     text_color=COLOR_TEXT_PRIMARY).put("h")
        self.f_top = FieldRow(top_line, "", "0", width=FIELD_W,
                              minimum=0, maximum=5000, on_change=self.on_margin_changed)
        self.f_top.put("h")
        self._top_preset_row = WrapButtonRow(top_line, stretch=False, wrap=False, gap=SP_XS)
        self._top_preset_row.put("h", fill="x", expand=True)
        for value in MARGIN_PRESETS_MM:
            self._top_preset_row.add_button(
                self.preset_label(value), lambda v=value: self.set_top(v), width=38)
        self._top_preset_row.add_button("Sıfırla", lambda: self.set_top(0.0), width=52)
        self._margin_preset_rows = (self._bottom_preset_row, self._top_preset_row)

        self.chk_pad4 = ctk.CTkCheckBox(
            pay,
            text="Kitapçık için sayfa sayısını 4'ün katına tamamla",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_PRIMARY, hover_color=COLOR_ACCENT,
            fg_color=COLOR_SOLID, command=self.ctx.on_field_changed,
        )
        self.chk_pad4.setToolTip("Kitapçık baskısı için toplam sayfa sayısını 4'ün katına tamamlar (sona boş sayfa ekler).")
        self.chk_pad4.place(2, 0, align="w")
        self.ctx.bind_wraplength(self.chk_pad4, pay, 40)

    # =====================================================================
    # Bölüm: Sayfa boyutu ve sığdırma
    # =====================================================================
    def _build_size_section(self, container, row: int) -> None:
        size = self.section(container, row, "Sayfa boyutu ve sığdırma")
        self._section_widgets["size"] = size
        form = self.form_grid(size, 0)
        # Satır sırası: Ebat modu · Hazır kağıt · Hedef ebat · Taşarsa ne olsun · Güvenli kenar.
        # Ebat moduna ve seçime uymayan satırlar pasif değil GİZLİ (``update_safe_edge_state``).

        cell = self.form_stack_row(form, 0, "Ebat modu")
        self.seg_size_mode = ctk.CTkSegmentedButton(
            cell, values=list(SIZE_MODE_LABELS.keys()), height=BTN_H,
            border_width=0, fg_color=COLOR_SUBCARD, bg_color=COLOR_SUBCARD,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            selected_color=COLOR_SELECTED, selected_hover_color=COLOR_SELECTED_HOVER,
            unselected_color=COLOR_CARD, unselected_hover_color=COLOR_SUBCARD,
            text_color=COLOR_TEXT_PRIMARY, command=lambda _v: self.on_changed(),
        )
        self.seg_size_mode.place(0, 0, align="w")
        self.lbl_size_note = ctk.CTkLabel(
            cell, text=SIZE_MODE_NOTES["fixed"],
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=NOTE_WRAP_W,
        )
        self.lbl_size_note.place(1, 0, expand_x=True)
        self.ctx.bind_wraplength(self.lbl_size_note, cell, 30)

        cell = self.form_stack_row(form, 1, "Hazır kağıt")
        self._row_paper = cell
        # Kağıt menüsü + yön + "Hedefe uygula" dar alanda alt satıra sarar; eskiden tek
        # satırda sıkışınca menü ezilip yön seçicisi üstüne biniyordu (v2.6.19, saha).
        self.paper_line = WrapButtonRow(cell, wrap=True, gap=SP_S)
        self.paper_line.place(0, 0, expand_x=True)
        self.paper_menu = ctk.CTkOptionMenu(
            self.paper_line, values=list(PAPER_SIZES.keys()), width=150, height=BTN_H,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            fg_color=COLOR_CARD, text_color=COLOR_TEXT_PRIMARY,
            button_color=COLOR_SUBCARD, button_hover_color=COLOR_BTN_SUBTLE_HOVER,
            dropdown_fg_color=COLOR_CARD, dropdown_hover_color=COLOR_SELECTED,
            dropdown_text_color=COLOR_TEXT_PRIMARY,
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
        )
        self.paper_menu.set(list(PAPER_SIZES.keys())[0])
        self.paper_line.add_widget(self.paper_menu)
        self.orientation_menu = ctk.CTkSegmentedButton(
            self.paper_line, values=["Dikey", "Yatay"], width=110, height=BTN_H,
            border_width=0, fg_color=COLOR_SUBCARD, bg_color=COLOR_SUBCARD,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            selected_color=COLOR_SELECTED, selected_hover_color=COLOR_SELECTED_HOVER,
            unselected_color=COLOR_CARD, unselected_hover_color=COLOR_SUBCARD,
            text_color=COLOR_TEXT_PRIMARY,
        )
        self.orientation_menu.set("Dikey")
        self.paper_line.add_widget(self.orientation_menu)
        # "Uygula" hazır kağıdı hedef ebada yazar; bu yüzden genişlik/yükseklik değil,
        # seçtiği kağıt ve yönün yanında durur (v2.6.15).
        self.btn_apply_size = ctk.CTkButton(
            self.paper_line, text="Hedefe uygula", width=110, height=BTN_H - 2,  # kenarlıksız dolgu, menü/segmentin görünür boyuna eşit
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            fg_color=COLOR_SOLID, text_color=COLOR_ON_ACCENT,
            hover_color=COLOR_SOLID_HOVER, command=self.apply_paper_size,
        )
        self.btn_apply_size.setToolTip(
            "Seçili kağıt ve yönü hedef ebat alanlarına yazar (alt/üst boşluk hariç)")
        self.paper_line.add_widget(self.btn_apply_size)

        cell = self.form_stack_row(form, 2, "Hedef ebat (cilt payı dahil)")
        self._row_target = cell
        # Genişlik / Yükseklik dar alanda alt satıra sarar (P2-33):
        # eskiden tek satırda sıkışıyor, birim etiketi giriş kutusunun üstüne biniyordu.
        target_line = WrapButtonRow(cell, wrap=True, gap=SP_S)
        target_line.place(0, 0, expand_x=True)
        self.f_width = FieldRow(target_line, "Genişlik", "210", width=FIELD_W,
                                minimum=1, maximum=5000, on_change=self.on_changed)
        target_line.add_widget(self.f_width)
        self.f_height = FieldRow(target_line, "Yükseklik", "297", width=FIELD_W,
                                 minimum=1, maximum=5000, on_change=self.on_changed)
        target_line.add_widget(self.f_height)
        self.target_line = target_line
        self.lbl_target_note = ctk.CTkLabel(
            cell, text="Cilt payı dahil; alt/üst boşluk sonuç yüksekliğine eklenir.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=NOTE_WRAP_W,
        )
        # Not (P2-34): hücreyi doldurur ve hücre genişliğine göre sarılır; ``align="w"``
        # ile yerleşince etiket kendi sizeHint genişliğinde kalıp yüksekliği tek satıra kilitleniyordu.
        self.lbl_target_note.place(1, 0, expand_x=True)
        self.ctx.bind_wraplength(self.lbl_target_note, cell, 30)

        cell = self.form_stack_row(form, 3, "Taşarsa ne olsun")
        self._row_overflow = cell
        self.menu_overflow = ctk.CTkOptionMenu(
            cell, values=list(CHOICE_LABELS.values()), width=300, height=BTN_H,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            fg_color=COLOR_CARD, text_color=COLOR_TEXT_PRIMARY,
            button_color=COLOR_SUBCARD, button_hover_color=COLOR_BTN_SUBTLE_HOVER,
            dropdown_fg_color=COLOR_CARD, dropdown_hover_color=COLOR_SELECTED,
            dropdown_text_color=COLOR_TEXT_PRIMARY,
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            command=lambda _v: self.on_overflow_changed(),
        )
        self.menu_overflow.set(CHOICE_LABELS[plm.CHOICE_EXTEND])
        self.menu_overflow.place(0, 0, expand_x=True)

        # Seçimin sonucu tek cümle (P2-36): sayfa ebadı, ölçek ve kırpma tahmini motorun
        # kendi yerleşiminden hesaplanır (``plm.result_sentence``).
        self.lbl_overflow_note = ctk.CTkLabel(
            cell, text=plm.OVERFLOW_CHOICES[plm.CHOICE_EXTEND][1],
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=NOTE_WRAP_W,
        )
        self.lbl_overflow_note.place(1, 0, expand_x=True)
        self.ctx.bind_wraplength(self.lbl_overflow_note, cell, 30)

        self.lbl_overflow_legacy = ctk.CTkLabel(
            cell, text="",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY, weight="bold"),
            text_color=COLOR_WARN, anchor="w", justify="left", wraplength=NOTE_WRAP_W,
        )
        self.lbl_overflow_legacy.place(2, 0, expand_x=True)
        self.lbl_overflow_legacy.grid_remove()

        cell = self.form_stack_row(form, 4, "Güvenli kenar")
        self._row_safe_edge = cell
        self.f_safe_edge = FieldRow(cell, "", "0", width=FIELD_W,
                                    minimum=0, maximum=100, on_change=self.on_changed)
        self.f_safe_edge.place(0, 0, align="w")
        self.lbl_safe_edge_note = ctk.CTkLabel(
            cell, text=SAFE_EDGE_NOTE,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=NOTE_WRAP_W,
        )
        self.lbl_safe_edge_note.place(1, 0, expand_x=True)

        # Sayfaları eşitle: Acrobat'taki "Yazdır > Adobe PDF > Sığdır" karşılığı, yazdırmadan.
        cell = self.form_stack_row(form, 5, "Sayfaları eşitle")
        self._row_fit = cell
        self.menu_fit = ctk.CTkOptionMenu(
            cell, values=list(FIT_LABELS.keys()), width=300, height=BTN_H,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            fg_color=COLOR_CARD, text_color=COLOR_TEXT_PRIMARY,
            button_color=COLOR_SUBCARD, button_hover_color=COLOR_BTN_SUBTLE_HOVER,
            dropdown_fg_color=COLOR_CARD, dropdown_hover_color=COLOR_SELECTED,
            dropdown_text_color=COLOR_TEXT_PRIMARY,
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            command=lambda _v: self.ctx.on_field_changed(),
        )
        self.menu_fit.set(FIT_CODES["off"])
        self.menu_fit.place(0, 0, expand_x=True)
        self.chk_fit_orient = ctk.CTkCheckBox(
            cell, text="Yatay sayfalar yatay kalsın",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_PRIMARY, hover_color=COLOR_ACCENT,
            fg_color=COLOR_SOLID, command=self._on_fit_orient_changed,
        )
        self.chk_fit_orient.select()
        self.chk_fit_orient.place(1, 0, align="w")
        self.chk_fit_rotate = ctk.CTkCheckBox(
            cell, text="Yatay sayfaları dikeye döndür",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_PRIMARY, hover_color=COLOR_ACCENT,
            fg_color=COLOR_SOLID, command=self.ctx.on_field_changed,
        )
        self.chk_fit_rotate.setToolTip(
            "Yalnız \"Yatay sayfalar yatay kalsın\" kapalıyken geçerlidir: yatay sayfa 90° "
            "döndürülüp dikey ebadı doldurur. Kapalıysa yatay sayfa döndürülmeden küçülerek sığar.")
        self.chk_fit_rotate.deselect()
        self.chk_fit_rotate.setEnabled(False)
        self.chk_fit_rotate.place(2, 0, align="w")
        self.lbl_fit_note = ctk.CTkLabel(
            cell, text="Farklı ebatlı sayfaları oranı bozmadan ve kırpmadan seçilen ebada sığdırır "
                       "(ortalar); cilt payı ve boşluk bundan sonra uygulanır.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=NOTE_WRAP_W,
        )
        self.lbl_fit_note.place(3, 0, expand_x=True)
        self.ctx.bind_wraplength(self.lbl_fit_note, cell, 30)
        self._fit_custom_row = ctk.CTkFrame(cell, fg_color="transparent")
        self._fit_custom_row.place(4, 0, align="w")
        self.f_fit_width = FieldRow(self._fit_custom_row, "Genişlik", "210", minimum=1,
                                    maximum=2000, on_change=self.ctx.on_field_changed)
        self.f_fit_width.put("h", margins=(0, 0, SP_S, 0))
        self.f_fit_height = FieldRow(self._fit_custom_row, "Yükseklik", "297", minimum=1,
                                     maximum=2000, on_change=self.ctx.on_field_changed)
        self.f_fit_height.put("h")
        self.f_fit_margin = FieldRow(cell, "Çevreden boşluk", "0", minimum=0,
                                     maximum=500, on_change=self.ctx.on_field_changed)
        self.f_fit_margin.place(5, 0, align="w")
        self.menu_fit.configure(command=lambda _v: (self.update_fit_state(), self.ctx.on_field_changed()))
        self.update_fit_state()

    def _on_fit_orient_changed(self) -> None:
        self.update_fit_state()
        self.ctx.on_field_changed()

    def update_fit_state(self) -> None:
        """"Dikeye döndür" yalnız yatay sayfalar yatay kalmayacaksa seçilebilir."""
        keep = self.chk_fit_orient.get() == 1
        if hasattr(self, "_fit_custom_row"):
            self._fit_custom_row.setVisible(FIT_LABELS.get(self.menu_fit.get()) == "custom")
            self.f_fit_margin.setVisible(FIT_LABELS.get(self.menu_fit.get()) != "off")
        self.chk_fit_rotate.setEnabled(not keep)
        if keep:
            self.chk_fit_rotate.deselect()

    # =====================================================================
    # Bölüm: Özel sayfalar
    # =====================================================================
    def _build_special_section(self, container, row: int) -> None:
        special = self.section(container, row, "Özel sayfalar")
        self._section_widgets["special"] = special
        self._special_hint = ctk.CTkLabel(
            special,
            text="Belirli sayfalarda payı kapatın; örn. ara kapakta yalnız cilt payı kalsın.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=NOTE_WRAP_W,
        )
        self._special_hint.place(0, 0, expand_x=True)
        self.ctx.bind_wraplength(self._special_hint, special, 30)

        self._rule_host = ctk.CTkFrame(special, fg_color="transparent")
        self._rule_host.set_padding(0, 0, 0, 0, spacing=SP_S)
        self._rule_host.place(2, 0, expand_x=True)
        self._rule_host.grid_columnconfigure(0, weight=1)

        buttons = WrapButtonRow(special, wrap=False, gap=SP_S)
        buttons.place(1, 0, expand_x=True)
        buttons.add_button("Kural ekle", self.add_rule, width=BTN_W_PRIMARY)
        buttons.add_button("Ara kapak kuralı ekle", self.add_cover_rule, width=170)

        self.lbl_rule_warning = ctk.CTkLabel(
            special, text="",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY, weight="bold"),
            text_color=COLOR_WARN, anchor="w", justify="left", wraplength=NOTE_WRAP_W,
        )
        self.lbl_rule_warning.place(3, 0, expand_x=True)
        self.lbl_rule_warning.grid_remove()
        self._update_rule_summary()

    # =====================================================================
    # Taşma denetimi (tek seçim)
    # =====================================================================
    def overflow_choice(self) -> str:
        return LABEL_TO_CHOICE.get(self.menu_overflow.get(), plm.CHOICE_EXTEND)

    def overflow_selection(self) -> Tuple[str, Optional[Tuple[str, str]]]:
        """``(seçim, yüklenen özgün çift)``; çift yalnızca kullanıcı dokunmadıysa döner."""
        return self.overflow_choice(), self._loaded_pair

    def set_overflow_choice(self, choice: str) -> None:
        """Dışarıdan (kırpma riski diyaloğu) seçim yapar; eski çifti bırakır."""
        self._loaded_pair = None
        self.menu_overflow.set(CHOICE_LABELS.get(choice, CHOICE_LABELS[plm.CHOICE_EXTEND]))
        self.on_overflow_changed()

    def on_overflow_changed(self) -> None:
        self._loaded_pair = None
        self.lbl_overflow_legacy.grid_remove()
        self.on_changed()

    def set_unified_state(self, state: plm.OverflowState, rules: List[plm.SpecialRule],
                          loaded_pair: Optional[Tuple[str, str]] = None) -> None:
        """Kayıtlı ayardan birleşik sekme durumunu kurar."""
        self._loaded_pair = None if state.exact else loaded_pair
        self.menu_overflow.set(CHOICE_LABELS[state.choice])
        if state.exact:
            self.lbl_overflow_legacy.grid_remove()
        else:
            self.lbl_overflow_legacy.configure(
                text="Kayıtlı ayar eski bir birleşim; seçim değiştirilene kadar korunur.")
            self.lbl_overflow_legacy.place_restore()
        self.set_rules(rules)
        self.update_safe_edge_state()

    def _margin_pay_active(self) -> bool:
        """Alt/üst boşluk modülü açık ve en az biri sıfırdan büyük mü?"""
        if not self.ctx.module_enabled("margin"):
            return False
        for row in (self.f_bottom, self.f_top):
            try:
                if row.get_mm() > 0:
                    return True
            except FieldError:
                continue
        return False

    def sync_size_source(self) -> None:
        """Ebat kaynağı seçicisini yalnız karışık ebatlı belgede gösterir."""
        row = getattr(self, "_size_source_row", None)
        if row is None:
            return
        policy = getattr(getattr(self.ctx, "store", None), "page_size_policy", "dominant")
        self.size_source_menu.set(SIZE_SOURCE_CODES.get(policy, SIZE_SOURCE_CODES["dominant"]))
        row.setVisible(bool(getattr(self.ctx, "mixed_sizes", False)))

    def _on_size_source_changed(self, label: str) -> None:
        self.ctx.set_page_size_policy(SIZE_SOURCE_LABELS.get(label, "dominant"))

    def update_safe_edge_state(self) -> None:
        """Ebat moduna ve seçime uymayan satırları gizler, kalanın açıklamasını yazar (P2-36).

        Kural ``plm.relevance`` içindedir. Gizlenen alanlar ayrıca pasif bırakılır; böylece
        ayar yazılırken değerleri okunmaya devam eder ama kullanıcıya gösterilmez.
        """
        if not hasattr(self, "_row_safe_edge"):
            return  # bölüm henüz kurulmadı
        mode = SIZE_MODE_LABELS.get(self.seg_size_mode.get(), plm.SIZE_FIXED)
        rel = plm.relevance(mode, self.overflow_choice(), self._margin_pay_active())
        self.f_width.set_enabled(rel.target)
        self.f_height.set_enabled(rel.target)
        self.f_safe_edge.set_enabled(rel.safe_edge)
        self.set_row_visible(self._row_paper, rel.target)
        self.set_row_visible(self._row_target, rel.target)
        self.set_row_visible(self._row_overflow, rel.overflow)
        self.set_row_visible(self._row_safe_edge, rel.safe_edge)
        self.lbl_size_note.configure(text=SIZE_MODE_NOTES.get(mode, ""))
        self.lbl_safe_edge_note.configure(text=SAFE_EDGE_NOTE)
        self.refresh_result_sentence(mode)

    def refresh_result_sentence(self, mode: Optional[str] = None) -> None:
        """"Taşarsa ne olsun" altındaki tek cümlelik sonuç özetini yeniler."""
        choice = self.overflow_choice()
        mode = mode or SIZE_MODE_LABELS.get(self.seg_size_mode.get(), plm.SIZE_FIXED)
        try:
            text = plm.result_sentence(
                mode, choice,
                src_w_mm=float(getattr(self.ctx, "orig_width_mm", 210.0) or 210.0),
                src_h_mm=float(getattr(self.ctx, "orig_height_mm", 297.0) or 297.0),
                gutter_enabled=self.ctx.module_enabled("gutter"),
                target_w_mm=self.f_width.get_mm(), target_h_mm=self.f_height.get_mm(),
                odd_x_mm=self.f_odd_x.get_mm(), even_x_mm=self.f_even_x.get_mm(),
                odd_y_mm=self.f_odd_y.get_mm(), even_y_mm=self.f_even_y.get_mm(),
                safe_edge_mm=self.f_safe_edge.get_mm(),
                margin_enabled=self.ctx.module_enabled("margin"),
                top_mm=self.f_top.get_mm(), bottom_mm=self.f_bottom.get_mm(),
                engine_pair=plm.resolve_engine_pair(choice, self._loaded_pair))
        except (FieldError, ValueError, ZeroDivisionError):
            text = plm.OVERFLOW_CHOICES[choice][1]  # geçersiz değer: genel açıklama
        self.lbl_overflow_note.configure(text=text)
        self.lbl_target_note.configure(text=self._target_note_text(mode, choice))

    def _target_note_text(self, mode: str, choice: str) -> str:
        """Yükseklik alanının altındaki kısa not (v2.6.16: sayfa boyu cümlesi kaldırıldı).

        Oluşacak sayfa boyu zaten "Taşarsa ne olsun" altındaki sonuç cümlesinde yazar
        (``result_sentence``); burada tekrarlanması kafa karıştırıyordu.
        """
        return "Cilt payı dahil; alt/üst boşluk sonuç yüksekliğine eklenir."

    # =====================================================================
    # Cilt payı davranışları
    # =====================================================================
    def on_changed(self) -> None:
        """Ebat/taşma/ofset/mod değişince: cilt modülü kapalıysa açar, değilse yeniler."""
        self.update_safe_edge_state()
        self.update_preset_highlight()
        if not self.ctx.module_enabled("gutter"):
            self.ctx.enable_module("gutter")
        else:
            self.ctx.on_field_changed()

    def update_preset_highlight(self) -> None:
        """Geçerli tek sayfa payı bir hızlı seçimle eşleşiyorsa o düğmeyi vurgular."""
        if not hasattr(self, "_gutter_preset_row"):
            return
        buttons = getattr(self._gutter_preset_row, "_buttons", [])
        try:
            current = self.f_odd_x.get_mm()
            enabled = self.ctx.module_enabled("gutter")
        except Exception:
            current, enabled = None, False
        for value, button in zip(self._preset_values, buttons[:3]):
            active = enabled and current is not None and abs(current - value) < 0.05
            button.configure(
                fg_color=COLOR_SELECTED if active else COLOR_CARD,
                border_color=COLOR_ACCENT if active else COLOR_BORDER,
            )

    def apply_preset(self, gutter: float) -> None:
        """Hızlı cilt payı düğmesi: kaynak genişliği + pay, tek sayfalara ofset."""
        self.f_width.set_mm(self.ctx.orig_width_mm + gutter)
        self.f_height.set_mm(self.ctx.orig_height_mm)
        self.f_odd_x.set_mm(gutter)
        self.f_odd_y.set_mm(0.0)
        self.f_even_x.set_mm(0.0)
        self.f_even_y.set_mm(0.0)
        self.ctx.enable_module("gutter")
        self.update_preset_highlight()

    def reset_values(self) -> None:
        """Hızlı seçimdeki "Sıfırla": değerleri sıfırlar; modül anahtarı olduğu gibi kalır."""
        self.f_width.set_mm(self.ctx.orig_width_mm)
        self.f_height.set_mm(self.ctx.orig_height_mm)
        for row in (self.f_odd_x, self.f_odd_y, self.f_even_x, self.f_even_y):
            row.set_mm(0.0)
        self.update_preset_highlight()
        self.ctx.on_field_changed()

    def reset_to_original(self) -> None:
        """Sıfırla / kapat: modülü kapatır, ebadı kaynağa döndürür, ofsetleri sıfırlar."""
        self.f_width.set_mm(self.ctx.orig_width_mm)
        self.f_height.set_mm(self.ctx.orig_height_mm)
        for row in (self.f_odd_x, self.f_odd_y, self.f_even_x, self.f_even_y):
            row.set_mm(0.0)
        self.ctx.disable_module("gutter")
        self.update_preset_highlight()

    def sync_paper_menu(self, width_mm: float, height_mm: float) -> None:
        """Hedef ebat alanlarıyla "Hazır kağıt" menüsünü tutarlı gösterir."""
        for name, (paper_w, paper_h) in PAPER_SIZES.items():
            if abs(paper_w - width_mm) < 0.2 and abs(paper_h - height_mm) < 0.2:
                self.paper_menu.set(name)
                self.orientation_menu.set("Dikey")
                return
            if abs(paper_h - width_mm) < 0.2 and abs(paper_w - height_mm) < 0.2:
                self.paper_menu.set(name)
                self.orientation_menu.set("Yatay")
                return
        self.paper_menu.set(self.CUSTOM_PAPER)

    def apply_paper_size(self) -> None:
        if self.paper_menu.get() not in PAPER_SIZES:
            self.ctx.set_status("Önce listeden hazır bir kağıt boyutu seçin.", COLOR_TEXT_PRIMARY)
            return
        width, height = PAPER_SIZES[self.paper_menu.get()]
        if self.orientation_menu.get() == "Yatay":
            width, height = height, width
        self.seg_size_mode.set(SIZE_MODE_CODES["fixed"])
        self.update_safe_edge_state()
        self.f_width.set_mm(width)
        self.f_height.set_mm(height)
        self.ctx.enable_module("gutter")
        self.ctx.set_status(f"Kağıt boyutu {width:g} × {height:g} mm olarak ayarlandı.",
                            COLOR_TEXT_PRIMARY)

    # =====================================================================
    # Boşluk davranışları
    # =====================================================================
    def on_margin_changed(self) -> None:
        """Alt/üst pay değişince: pay varsa modülü açar, yoksa yeniler."""
        self.update_safe_edge_state()
        if not self.ctx.module_enabled("margin"):
            has_pay = False
            for row in (self.f_bottom, self.f_top):
                try:
                    has_pay = has_pay or row.get_mm() > 0
                except FieldError:
                    continue
            if has_pay:
                self.ctx.enable_module("margin")
                return
        self.ctx.on_field_changed()

    def set_bottom(self, mm_value: float) -> None:
        self.f_bottom.set_mm(mm_value)
        self.on_margin_changed()

    def set_top(self, mm_value: float) -> None:
        self.f_top.set_mm(mm_value)
        self.on_margin_changed()

    def preset_label(self, mm_value: float) -> str:
        return f"+{format_measure(mm_value, self.ctx.unit)}"

    def update_preset_labels(self) -> None:
        for row in getattr(self, "_margin_preset_rows", ()):
            for button, value in zip(row._buttons, MARGIN_PRESETS_MM):
                button.configure(text=self.preset_label(value))

    # =====================================================================
    # Özel sayfa kuralları
    # =====================================================================
    def add_rule(self) -> _RuleRow:
        return self._append_rule("", plm.MODE_NONE)

    def add_cover_rule(self) -> _RuleRow:
        """Hızlı düğme: yalnız cilt payı (ara kapak) kuralı ekler."""
        return self._append_rule("", plm.MODE_GUTTER_ONLY)

    def _append_rule(self, pages: str, mode: str) -> _RuleRow:
        row = self._make_rule_row(pages, mode)
        self._relayout_rules()
        self.on_rules_changed()
        try:
            row.entry._entry.focus_set()
        except Exception:
            pass
        return row

    def _make_rule_row(self, pages: str, mode: str) -> _RuleRow:
        """Satırı kurar ve listeye ekler; yerleşim :meth:`_relayout_rules` ile yapılır."""
        row = _RuleRow(self._rule_host, self.on_rules_changed, pages, mode)
        # ``is`` ile eşleştirilir: düğme komutu hangi satıra ait olduğunu kapanıştan alır.
        row.remove_button.configure(command=lambda r=row: self.remove_rule(r))
        self._rule_rows.append(row)
        return row

    def _relayout_rules(self) -> None:
        """Kalan satırları 0..n-1 sırasına yerleştirir ve satır aralığını yeniden yazar.

        Her çağrıda aralık (``SP_S``) açıkça verilir; silinen satırdan artakalan boş ızgara
        satırları ve eski yerleşim ölçüsü satırları birbirine yapıştırmasın diye ızgara
        geçersiz kılınır.
        """
        host = self._rule_host
        host.set_padding(0, 0, 0, 0, spacing=SP_S)
        for index, row in enumerate(self._rule_rows):
            row.frame.place(index, 0, expand_x=True)
        layout = host._ensure_layout("grid")
        layout.invalidate()
        layout.activate()
        host.updateGeometry()

    def remove_rule(self, row: _RuleRow) -> None:
        """Satırı kaldırır. Son kalan satır da dahil her satır kaldırılabilir."""
        index = next((i for i, r in enumerate(self._rule_rows) if r is row), None)
        if index is None:
            return
        del self._rule_rows[index]
        row.frame.hide()  # tıklamayı işleyen düğmeyi hemen gizle; yıkım olay döngüsüne kalır
        row.destroy()
        self._relayout_rules()
        self.on_rules_changed()

    def set_rules(self, rules: List[plm.SpecialRule]) -> None:
        for row in self._rule_rows:
            row.destroy()
        self._rule_rows = []
        for rule in rules:
            self._make_rule_row(rule.pages, rule.mode)
        self._relayout_rules()
        self._update_rule_summary()

    def rules(self) -> List[plm.SpecialRule]:
        """Boş satırlar atlanır; aralık doğruluğu :meth:`check_rules` ile denetlenir."""
        return [plm.SpecialRule(row.pages(), row.mode())
                for row in self._rule_rows if row.pages()]

    def check_rules(self) -> List[Tuple[_RuleRow, str]]:
        """Her satırı denetler, hatayı satırın altında gösterir; (satır, mesaj) döner."""
        problems: List[Tuple[_RuleRow, str]] = []
        for row in self._rule_rows:
            text = row.pages()
            if not text:
                row.set_error("")
                continue
            bad = invalid_range_tokens(text)
            if bad:
                row.set_error("Anlaşılamayan değer: " + ", ".join(bad))
                problems.append((row, "Özel sayfalar: anlaşılamayan değer → " + ", ".join(bad[:3])))
            else:
                row.set_error("")
        return problems

    def on_rules_changed(self) -> None:
        self.check_rules()
        self._update_rule_summary()
        self.ctx.on_field_changed()

    def _update_rule_summary(self) -> None:
        if not hasattr(self, "lbl_rule_warning"):
            return
        try:
            overlap = plm.overlapping_pages(self.rules())
        except plm.RuleError:
            overlap = []
        if not overlap:
            self.lbl_rule_warning.grid_remove()
            return
        shown = plm.compact_ranges(overlap)
        self.lbl_rule_warning.configure(
            text=f"Sayfa {shown}: birden çok kuralda geçiyor; sonuç “hiçbir pay uygulanmasın”.")
        self.lbl_rule_warning.place_restore()

    # =====================================================================
    # Modül anahtarları / rozetler
    # =====================================================================
    def on_module_toggle(self, key: str) -> None:
        active = (self.switch_gutter if key == "gutter" else self.switch_margin).get() == 1
        if key == "gutter":
            self.show_active(active)
        else:
            self.show_margin_active(active)
        self.update_safe_edge_state()
        self.ctx.on_field_changed()

    def show_active(self, active: bool) -> None:
        """Cilt payı rozetini modül anahtarına göre yazar."""
        if not hasattr(self, "lbl_gutter_status"):
            return  # sekme henüz kurulmadı; kurulumda rozet yazılır
        if hasattr(self, "_gutter_preset_row"):
            self.update_preset_highlight()
        self.set_badge(self.lbl_gutter_status, active)

    def show_margin_active(self, active: bool) -> None:
        """Alt/üst boşluk rozetini modül anahtarına göre yazar."""
        self.set_badge(self.lbl_margin_status, active)
