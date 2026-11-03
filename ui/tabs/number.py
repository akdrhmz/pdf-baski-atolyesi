"""Sayfa Numaraları sekmesi: kurulum, konum/biçim davranışları ve durum etiketi.

Sekme kendi widget'larını ve davranışını taşır; modül anahtarı ("Sayfa numarası"
onay kutusu), özet ve önizleme gibi kabuk işleri ``ctx`` üzerinden yapılır.
Ayar okuma/yazma (``config_binding``) ve testler eski adlarla (``app.f_start_page``
gibi) çalışmaya devam eder: kabuk ``EXPOSED`` içindeki widget'ları geçiş süresince
pencereye takma ad olarak bağlar (2.9'da alanlar ``StringVar`` olunca kalkar).
"""

from __future__ import annotations

from ui import qt_compat as ctk

from ui.tabs.base import BaseTab
from ui.theme import *  # noqa: F401,F403
from ui.widgets import FieldRow


class NumberTab(BaseTab):
    """Sayfa numaralandırma ayarları."""

    #: Pencereye takma ad olarak bağlanan widget adları (geçiş köprüsü).
    EXPOSED = (
        "lbl_pnum_status", "seg_pos", "menu_format", "f_font_size", "f_start_page",
        "f_start_num", "f_num_bottom", "f_num_side", "lbl_side_hint",
        "entry_number_template", "entry_skip_pages", "chk_continuous",
    )

    def build(self) -> None:
        scroll = ctk.CTkScrollableFrame(self.frame, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=10, pady=6)
        scroll.set_padding(2, 4, 2, 6, spacing=8)
        container = scroll
        container.grid_columnconfigure(0, weight=1)
        # Kart bloğu dikeyde dengeli: üst ve alt eşit nefes alır.
        container.grid_rowconfigure(1, weight=1)
        container.grid_rowconfigure(5, weight=1)

        # -- Modül Durumu (küçük tek satır; anahtar sol menüde) --------------
        top = ctk.CTkFrame(container, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew")
        top.set_padding(0, 0, 0, 0, spacing=6)
        top.grid_columnconfigure(1, weight=1)

        self.lbl_pnum_status = ctk.CTkLabel(
            top, text="Devre dışı: soldaki anahtarla açın",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=540,
        )
        self.lbl_pnum_status.grid(row=0, column=1, sticky="ew")
        self.ctx.bind_wraplength(self.lbl_pnum_status, top, 24)

        # -- Numara Konumu, Biçimi ve Yazı Boyutu ------------------------------
        pos_card = ctk.CTkFrame(container, fg_color=COLOR_SUBCARD, corner_radius=8,
                                border_width=1, border_color=COLOR_BORDER)
        pos_card.grid(row=2, column=0, sticky="ew")
        pos_card.set_padding(12, 10, 12, 12, spacing=6)
        pos_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            pos_card, text="Numara konumu ve biçimi",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
        ).grid(row=0, column=0, sticky="w")

        self.seg_pos = ctk.CTkSegmentedButton(
            pos_card, values=list(POSITION_LABELS.keys()), height=32,
            border_width=0, fg_color=COLOR_SUBCARD, bg_color=COLOR_SUBCARD,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            selected_color=COLOR_SELECTED, selected_hover_color=COLOR_SELECTED_HOVER,
            unselected_color=COLOR_CARD, unselected_hover_color=COLOR_SUBCARD,
            text_color=COLOR_TEXT_PRIMARY, command=lambda _v: self.on_position_changed(),
        )
        self.seg_pos.grid(row=1, column=0, sticky="ew")

        fmt_row = ctk.CTkFrame(pos_card, fg_color="transparent")
        fmt_row.grid(row=2, column=0, sticky="ew")
        fmt_row.set_padding(0, 0, 0, 0, spacing=6)

        ctk.CTkLabel(
            fmt_row, text="Görünüm biçimi:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.menu_format = ctk.CTkOptionMenu(
            fmt_row, values=list(FORMAT_LABELS.keys()), width=148, height=30,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            fg_color=COLOR_CARD, text_color=COLOR_TEXT_PRIMARY,
            button_color=COLOR_SUBCARD, button_hover_color=COLOR_BTN_SUBTLE_HOVER,
            dropdown_fg_color=COLOR_CARD, dropdown_hover_color=COLOR_SELECTED,
            dropdown_text_color=COLOR_TEXT_PRIMARY,
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            command=lambda _v: self.on_changed(),
        )
        self.menu_format.set("1, 2, 3")
        self.menu_format.grid(row=0, column=1, sticky="w", padx=(0, 24))
        fmt_row.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(
            fmt_row, text="Yazı boyutu (Punto):",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
        ).grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(4, 0))
        self.f_font_size = FieldRow(fmt_row, "", "10", unit="pt", convert=False, width=64,
                                    minimum=1, maximum=72, on_change=self.on_changed)
        self.f_font_size.grid(row=1, column=1, sticky="w", pady=(4, 0))

        # -- Başlangıç Sayfası ve Kenar Mesafeleri -----------------------------
        dist_card = ctk.CTkFrame(container, fg_color=COLOR_SUBCARD, corner_radius=8,
                                 border_width=1, border_color=COLOR_BORDER)
        dist_card.grid(row=3, column=0, sticky="ew")
        dist_card.set_padding(12, 10, 12, 12, spacing=6)
        dist_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            dist_card, text="Başlangıç ve mesafeler",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
        ).grid(row=0, column=0, sticky="w")

        grid = ctk.CTkFrame(dist_card, fg_color="transparent")
        grid.grid(row=1, column=0, sticky="ew")
        grid.grid_columnconfigure(0, weight=1)
        grid.grid_columnconfigure(1, weight=1)

        self.f_start_page = FieldRow(grid, "Başlangıç sayfası", "1", convert=False, width=68,
                                     minimum=1, maximum=100000, integer=True,
                                     suffix="", label_width=130, on_change=self.on_changed)
        self.f_start_page.grid(row=0, column=0, sticky="w", pady=1)
        self.f_start_num = FieldRow(grid, "İlk numara", "1", convert=False, width=68,
                                    minimum=0, maximum=100000, integer=True,
                                    suffix="", label_width=130, on_change=self.on_changed)
        self.f_start_num.grid(row=0, column=1, sticky="w", pady=1)

        self.f_num_bottom = FieldRow(grid, "Alt kenardan uzaklık", "12", width=68, minimum=0, maximum=5000,
                                     label_width=130, on_change=self.on_changed)
        self.f_num_bottom.grid(row=1, column=0, sticky="w", pady=1)
        self.f_num_side = FieldRow(grid, "Yan boşluk", "15", width=68, minimum=0, maximum=5000,
                                   label_width=130, on_change=self.on_changed)
        self.f_num_side.grid(row=1, column=1, sticky="w", pady=1)

        self.lbl_side_hint = ctk.CTkLabel(
            grid, text="", font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, anchor="w",
        )
        self.lbl_side_hint.grid(row=2, column=1, sticky="w")

        # -- Numarasız Sayfalar ve Özel Şablon ---------------------------------
        extra_card = ctk.CTkFrame(container, fg_color=COLOR_SUBCARD, corner_radius=8,
                                  border_width=1, border_color=COLOR_BORDER)
        extra_card.grid(row=4, column=0, sticky="ew")
        extra_card.set_padding(12, 10, 12, 12, spacing=6)
        extra_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            extra_card, text="Numarasız sayfalar ve özel şablon",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
        ).grid(row=0, column=0, sticky="w")

        skip_row = ctk.CTkFrame(extra_card, fg_color="transparent")
        skip_row.grid(row=1, column=0, sticky="ew")
        ctk.CTkLabel(
            skip_row, text="Numarasız sayfalar:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, width=130, anchor="w",
        ).pack(side="left", padx=(0, 8))
        self.entry_skip_pages = ctk.CTkEntry(
            skip_row, placeholder_text="Örn: 1, 2, 15, 24-26 (kapak veya bölüm başlıkları)", height=30,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_BODY),
            fg_color=COLOR_CARD, border_color=COLOR_BORDER, text_color=COLOR_TEXT_PRIMARY,
        )
        self.entry_skip_pages.pack(side="left", fill="x", expand=True)
        self.entry_skip_pages.bind("<KeyRelease>", lambda e: self.on_changed())

        self.chk_continuous = ctk.CTkCheckBox(
            extra_card,
            text="Numarasız kapak sayfalarında sayacı dondur (ör. 90 → kapak → 91 olarak devam etsin)",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_PRIMARY, hover_color=COLOR_ACCENT,
            fg_color=COLOR_SOLID, command=self.on_changed,
        )
        self.chk_continuous.select()
        self.chk_continuous.grid(row=2, column=0, sticky="w")

        template_row = ctk.CTkFrame(extra_card, fg_color="transparent")
        template_row.grid(row=3, column=0, sticky="ew")
        ctk.CTkLabel(
            template_row, text="Özel şablon:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, width=130, anchor="w",
        ).pack(side="left", padx=(0, 8))
        self.entry_number_template = ctk.CTkEntry(
            template_row, placeholder_text="Örn: {n} / {N}  •  {roman}  •  Sayfa {n}",
            height=30, font=ctk.CTkFont(family=FONT_FAMILY, size=FS_BODY),
            fg_color=COLOR_CARD, border_color=COLOR_BORDER, text_color=COLOR_TEXT_PRIMARY,
        )
        self.entry_number_template.pack(side="left", fill="x", expand=True)
        self.entry_number_template.bind("<KeyRelease>", lambda e: self.on_changed())

        tmpl_help = ctk.CTkLabel(
            extra_card,
            text="Boş bırakılırsa seçili numara biçimi kullanılır. Değişkenler: {n} numara, {N} toplam sayfa, "
                 "{roman}/{ROMAN} Romen rakamı.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=580,
        )
        tmpl_help.grid(row=4, column=0, sticky="ew")
        self.ctx.bind_wraplength(tmpl_help, extra_card, 24)

        # Açılış durumu: etiket modül anahtarına göre kurulur, özet ve önizleme güncellenir.
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
        """Modül anahtarının durumunu içeriğin üstündeki küçük etikete yazar."""
        if active:
            self.lbl_pnum_status.configure(
                text="Etkin: sayfa numaraları belgeye eklenecek", text_color=COLOR_OK)
        else:
            self.lbl_pnum_status.configure(
                text="Devre dışı: soldaki anahtarla açın",
                text_color=COLOR_TEXT_SECONDARY)
