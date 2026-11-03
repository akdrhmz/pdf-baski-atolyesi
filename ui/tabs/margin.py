"""Kenar Boşlukları sekmesi: alt/üst pay, pay modu, ön ayar düğmeleri, işlem dışı sayfalar.

Sekme kendi widget'larını ve davranışını taşır; modül anahtarı ("Kenar boşluğu"
onay kutusu), özet ve önizleme gibi kabuk işleri ``ctx`` üzerinden yapılır.
Ayar okuma/yazma (``config_binding``) ve testler eski adlarla (``app.f_bottom`` gibi)
çalışmaya devam eder: kabuk ``EXPOSED`` içindeki widget'ları geçiş süresince
pencereye takma ad olarak bağlar (2.9'da alanlar ``StringVar`` olunca kalkar).
"""

from __future__ import annotations

from ui import qt_compat as ctk

from gutter_engine import format_measure
from ui.tabs.base import BaseTab
from ui.theme import *  # noqa: F401,F403
from ui.widgets import FieldError, FieldRow, WrapButtonRow


class MarginTab(BaseTab):
    """Alt/üst pay ayarları."""

    #: Pencereye takma ad olarak bağlanan widget adları (geçiş köprüsü).
    EXPOSED = (
        "lbl_margin_status", "seg_bottom_mode", "lbl_mode_warning", "f_bottom", "f_top",
        "chk_pad4", "entry_exclude_margin",
    )

    def build(self) -> None:
        scroll = ctk.CTkScrollableFrame(self.frame, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=10, pady=6)
        scroll.set_padding(2, 4, 2, 6, spacing=8)
        container = scroll
        container.grid_columnconfigure(0, weight=1)
        # Dikey nefes: kart bloğu üst/altta, iç boşluklar sıfır.
        container.grid_rowconfigure(1, weight=1)
        container.grid_rowconfigure(3, minsize=6)
        container.grid_rowconfigure(5, minsize=6)
        container.grid_rowconfigure(7, weight=1)

        # -- Modül Durumu (küçük tek satır; anahtar sol menüde) --------------
        top = ctk.CTkFrame(container, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew")
        top.set_padding(0, 0, 0, 0, spacing=6)
        top.grid_columnconfigure(1, weight=1)

        self.lbl_margin_status = ctk.CTkLabel(
            top, text="Devre dışı: soldaki anahtarla açın",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=540,
        )
        self.lbl_margin_status.grid(row=0, column=1, sticky="ew")
        self.ctx.bind_wraplength(self.lbl_margin_status, top, 24)

        # -- Alt ve Üst Boşluk Miktarı ----------------------------------------
        pay_card = ctk.CTkFrame(container, fg_color=COLOR_SUBCARD, corner_radius=8,
                                border_width=1, border_color=COLOR_BORDER)
        pay_card.grid(row=2, column=0, sticky="ew")
        pay_card.set_padding(10, 6, 10, 8, spacing=4)
        pay_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            pay_card, text="Alt ve üst boşluk",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
        ).grid(row=0, column=0, sticky="w")

        bottom_row = ctk.CTkFrame(pay_card, fg_color="transparent")
        bottom_row.grid(row=1, column=0, sticky="ew")
        bottom_row.grid_columnconfigure(0, weight=1)
        self.f_bottom = FieldRow(bottom_row, "Alt boşluk", "0", width=68, label_width=76,
                                 minimum=0, maximum=5000, on_change=self.on_changed)
        self.f_bottom.grid(row=0, column=0, sticky="w")
        self._bottom_preset_row = WrapButtonRow(bottom_row)
        self._bottom_preset_row.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        for value in MARGIN_PRESETS_MM:
            self._bottom_preset_row.add_button(
                self.preset_label(value),
                lambda v=value: self.set_bottom(v), width=56)
        self._bottom_preset_row.add_button("Sıfırla", lambda: self.set_bottom(0.0), width=64)

        top_row = ctk.CTkFrame(pay_card, fg_color="transparent")
        top_row.grid(row=2, column=0, sticky="ew")
        top_row.grid_columnconfigure(0, weight=1)
        self.f_top = FieldRow(top_row, "Üst boşluk", "0", width=68, label_width=76,
                              minimum=0, maximum=5000, on_change=self.on_changed)
        self.f_top.grid(row=0, column=0, sticky="w")
        self._top_preset_row = WrapButtonRow(top_row)
        self._top_preset_row.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        for value in MARGIN_PRESETS_MM:
            self._top_preset_row.add_button(
                self.preset_label(value),
                lambda v=value: self.set_top(v), width=56)
        self._top_preset_row.add_button("Sıfırla", lambda: self.set_top(0.0), width=64)
        self._margin_preset_rows = (self._bottom_preset_row, self._top_preset_row)

        # -- Boşluk Ekleme Yöntemi ve Kitapçık Seçeneği -------------------------
        mode_card = ctk.CTkFrame(container, fg_color=COLOR_SUBCARD, corner_radius=8,
                                 border_width=1, border_color=COLOR_BORDER)
        mode_card.grid(row=4, column=0, sticky="ew")
        mode_card.set_padding(10, 6, 10, 8, spacing=4)
        mode_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            mode_card, text="Boşluk ekleme yöntemi",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
        ).grid(row=0, column=0, sticky="w")

        self.seg_bottom_mode = ctk.CTkSegmentedButton(
            mode_card, values=list(MODE_LABELS.keys()), height=26,
            border_width=0, fg_color=COLOR_SUBCARD, bg_color=COLOR_SUBCARD,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            selected_color=COLOR_SELECTED, selected_hover_color=COLOR_SELECTED_HOVER,
            unselected_color=COLOR_CARD, unselected_hover_color=COLOR_SUBCARD,
            text_color=COLOR_TEXT_PRIMARY, command=lambda _v: self.on_mode_changed(),
        )
        self.seg_bottom_mode.grid(row=1, column=0, sticky="ew")

        self.lbl_mode_warning = ctk.CTkLabel(
            mode_card, text="", font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY, weight="bold"),
            text_color=COLOR_WARN, anchor="w", justify="left", wraplength=560,
        )
        self.lbl_mode_warning.grid(row=2, column=0, sticky="ew")

        note = ctk.CTkLabel(
            mode_card,
            text="İpucu: 'Uzat' sayfa boyunu uzatır (hiçbir yazı küçülmez/kesilmez). 'Sığdır' yazıyı küçültür.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=560,
        )
        note.grid(row=3, column=0, sticky="ew")
        self.ctx.bind_wraplength(note, mode_card, 30)

        self.chk_pad4 = ctk.CTkCheckBox(
            mode_card,
            text="Kitapçık baskısı için toplam sayfa sayısını 4'ün katına tamamla (sona boş sayfa ekler)",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_PRIMARY, hover_color=COLOR_ACCENT,
            fg_color=COLOR_SOLID, command=self.ctx.on_field_changed,
        )
        self.chk_pad4.grid(row=4, column=0, sticky="w")

        # -- İşlem Dışı Sayfalar (Muafiyet) ------------------------------------
        exclude_card = ctk.CTkFrame(container, fg_color=COLOR_SUBCARD, corner_radius=8,
                                    border_width=1, border_color=COLOR_BORDER)
        exclude_card.grid(row=6, column=0, sticky="ew")
        exclude_card.set_padding(10, 6, 10, 8, spacing=4)
        exclude_card.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            exclude_card, text="Muaf sayfalar:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.entry_exclude_margin = ctk.CTkEntry(
            exclude_card, placeholder_text="Örn: 1, 5, 9-10 (bu sayfalara alt/üst boşluk eklenmez)",
            height=26, font=ctk.CTkFont(family=FONT_FAMILY, size=FS_BODY),
            fg_color=COLOR_CARD, border_color=COLOR_BORDER, text_color=COLOR_TEXT_PRIMARY,
        )
        self.entry_exclude_margin.grid(row=0, column=1, sticky="ew")
        self.entry_exclude_margin.bind("<KeyRelease>", lambda e: self.ctx.on_field_changed())

        # Açılış durumu: etiket modül anahtarına göre kurulur, özet ve önizleme güncellenir.
        self.show_active(self.ctx.module_enabled("margin"))
        self.ctx.on_field_changed()

    # =====================================================================
    # Davranışlar
    # =====================================================================
    def on_changed(self) -> None:
        """Alt/üst pay ya da pay modu değişince: pay varsa modülü açar, yoksa yeniler."""
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

    def on_mode_changed(self) -> None:
        mode = MODE_LABELS.get(self.seg_bottom_mode.get(), "expand")
        if mode == "shift":
            self.lbl_mode_warning.configure(
                text="Uyarı: Kaydır modu sayfa dışına taşan içeriği kırpar. Önizlemede kırmızı çerçeve ile gösterilir.",
                text_color=COLOR_ERROR)
        elif mode == "fit":
            self.lbl_mode_warning.configure(
                text="Sığdır modu içeriği orantılı küçültür; hiçbir içerik kırpılmaz.",
                text_color=COLOR_TEXT_SECONDARY)
        else:
            self.lbl_mode_warning.configure(
                text="Uzat modu içeriği %100 ölçekte korur; kırpma olmaz.",
                text_color=COLOR_TEXT_SECONDARY)
        self.on_changed()

    def set_bottom(self, mm_value: float) -> None:
        self.f_bottom.set_mm(mm_value)
        self.on_changed()

    def set_top(self, mm_value: float) -> None:
        self.f_top.set_mm(mm_value)
        self.on_changed()

    def preset_label(self, mm_value: float) -> str:
        return f"+{format_measure(mm_value, self.ctx.unit)}"

    def update_preset_labels(self) -> None:
        for row in getattr(self, "_margin_preset_rows", ()):
            for button, value in zip(row._buttons, MARGIN_PRESETS_MM):
                button.configure(text=self.preset_label(value))

    def show_active(self, active: bool) -> None:
        """Modül anahtarının durumunu içeriğin üstündeki küçük etikete yazar."""
        if active:
            self.lbl_margin_status.configure(
                text="Etkin: belirtilen alt/üst pay uygulanacak", text_color=COLOR_OK)
        else:
            self.lbl_margin_status.configure(
                text="Devre dışı: soldaki anahtarla açın",
                text_color=COLOR_TEXT_SECONDARY)
