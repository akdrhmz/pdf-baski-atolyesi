"""Cilt Payı sekmesi: ebat, ofsetler, hızlı cilt payı düğmeleri, kağıt boyutu, hazır profiller.

Sekme kendi widget'larını ve davranışını taşır; modül anahtarı ("Cilt payı" onay
kutusu), özet, önizleme, durum çubuğu ve hazır profillerin uygulanması (``_apply_config``)
gibi kabuk işleri ``ctx`` üzerinden yapılır. Ayar okuma/yazma (``config_binding``) ve
testler eski adlarla (``app.f_width`` gibi) çalışmaya devam eder: kabuk ``EXPOSED``
içindeki widget'ları geçiş süresince pencereye takma ad olarak bağlar (2.9'da alanlar
``StringVar`` olunca kalkar).
"""

from __future__ import annotations

from ui import qt_compat as ctk

from settings_store import PRESETS
from ui.tabs.base import BaseTab
from ui.theme import *  # noqa: F401,F403
from ui.widgets import FieldRow, WrapButtonRow


class GutterTab(BaseTab):
    """Cilt payı, hedef ebat ve ofset ayarları."""

    #: Pencereye takma ad olarak bağlanan widget adları (geçiş köprüsü).
    EXPOSED = (
        "lbl_gutter_status", "seg_size_mode", "seg_overflow", "paper_menu", "orientation_menu",
        "f_width", "f_height", "f_safe_edge", "f_odd_x", "f_odd_y", "f_even_x", "f_even_y",
        "entry_exclude_pages",
    )

    def build(self) -> None:
        scroll = ctk.CTkScrollableFrame(self.frame, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=6, pady=4)
        scroll.set_padding(6, 2, 6, 6, spacing=6)
        container = scroll
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(4, weight=1)

        # -- Başlık ve Modül Durumu (Tek Satırda Kompakt) ---------------------
        top = ctk.CTkFrame(container, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew")
        top.set_padding(2, 0, 2, 2, spacing=6)
        top.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            top, text="Cilt Payı Ayarları",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SUBTITLE, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=(0, 10))

        self.lbl_gutter_status = ctk.CTkLabel(
            top, text="Devre dışı: üstteki 'Cilt payı' onay kutusundan açın",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=540,
        )
        self.lbl_gutter_status.grid(row=0, column=1, sticky="ew")
        self.ctx.bind_wraplength(self.lbl_gutter_status, top, 24)

        # -- Adım 1: Hızlı Başlangıç (Tek Tıkla Cilt Payı ve Şablonlar) -------
        quick_card = ctk.CTkFrame(container, fg_color=COLOR_SUBCARD, corner_radius=8,
                                  border_width=1, border_color=COLOR_BORDER)
        quick_card.grid(row=1, column=0, sticky="ew")
        quick_card.set_padding(12, 8, 12, 10, spacing=5)
        quick_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            quick_card, text="1. Hızlı Seçim — Tek Tıkla Cilt Payı veya Hazır Şablon Uygula",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_ACCENT, anchor="w",
        ).grid(row=0, column=0, sticky="w")

        self._gutter_preset_row = WrapButtonRow(quick_card)
        self._gutter_preset_row.grid(row=1, column=0, sticky="ew")
        self._gutter_preset_row.add_button("10 mm duplex", lambda: self.apply_preset(10.0))
        self._gutter_preset_row.add_button("15 mm duplex (standart)", lambda: self.apply_preset(15.0), bold=True)
        self._gutter_preset_row.add_button("20 mm duplex (geniş)", lambda: self.apply_preset(20.0))
        self._gutter_preset_row.add_button("Sıfırla / kapat", self.reset_to_original)

        profile_row = ctk.CTkFrame(quick_card, fg_color="transparent")
        profile_row.grid(row=2, column=0, sticky="ew")
        ctk.CTkLabel(
            profile_row, text="Hazır baskı şablonları:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        ).pack(side="left", padx=(0, 8))
        self._preset_row = WrapButtonRow(profile_row)
        self._preset_row.pack(side="left", fill="x", expand=True)
        for preset_name in PRESETS:
            short = preset_name.split(" (")[0]
            self._preset_row.add_button(
                short, lambda name=preset_name: self.ctx.apply_named_preset(name), width=96,
            )

        # -- Adım 2: Cilt Boşluğu Miktarı ve Kapak Muafiyeti ------------------
        offset_card = ctk.CTkFrame(container, fg_color=COLOR_SUBCARD, corner_radius=8,
                                   border_width=1, border_color=COLOR_BORDER)
        offset_card.grid(row=2, column=0, sticky="ew")
        offset_card.set_padding(12, 8, 12, 10, spacing=6)
        offset_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            offset_card, text="2. Cilt Boşluğu Miktarı (Tek / Çift Sayfa) ve Muaf Kapak Sayfaları",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_ACCENT, anchor="w",
        ).grid(row=0, column=0, sticky="w")

        cols = ctk.CTkFrame(offset_card, fg_color="transparent")
        cols.grid(row=1, column=0, sticky="ew")
        cols.grid_columnconfigure(0, weight=1, uniform="col")
        cols.grid_columnconfigure(1, weight=1, uniform="col")

        odd = ctk.CTkFrame(cols, fg_color="transparent")
        odd.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ctk.CTkLabel(
            odd, text="Tek sayfalar (1, 3, 5... sağ sayfa • sol kenar):",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 2))
        self.f_odd_x = FieldRow(odd, "Yatay pay (X)", "0", width=62,
                                minimum=-5000, maximum=5000, allow_negative=True, on_change=self.on_changed)
        self.f_odd_x.grid(row=1, column=0, sticky="w", padx=(0, 12))
        self.f_odd_y = FieldRow(odd, "Dikey (Y)", "0", width=56,
                                minimum=-5000, maximum=5000, allow_negative=True, on_change=self.on_changed)
        self.f_odd_y.grid(row=1, column=1, sticky="w")

        even = ctk.CTkFrame(cols, fg_color="transparent")
        even.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        ctk.CTkLabel(
            even, text="Çift sayfalar (2, 4, 6... sol sayfa • sağ kenar):",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 2))
        self.f_even_x = FieldRow(even, "Yatay pay (X)", "0", width=62,
                                 minimum=-5000, maximum=5000, allow_negative=True, on_change=self.on_changed)
        self.f_even_x.grid(row=1, column=0, sticky="w", padx=(0, 12))
        self.f_even_y = FieldRow(even, "Dikey (Y)", "0", width=56,
                                 minimum=-5000, maximum=5000, allow_negative=True, on_change=self.on_changed)
        self.f_even_y.grid(row=1, column=1, sticky="w")

        exclude_row = ctk.CTkFrame(offset_card, fg_color="transparent")
        exclude_row.grid(row=2, column=0, sticky="ew")
        exclude_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            exclude_row, text="Kapak / Muaf sayfalar:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.entry_exclude_pages = ctk.CTkEntry(
            exclude_row, placeholder_text="Örn: 1, 5, 9-10 (boş bırakılırsa tüm sayfalara cilt payı uygulanır)",
            height=28, font=ctk.CTkFont(family=FONT_FAMILY, size=FS_BODY),
            fg_color=COLOR_CARD, border_color=COLOR_BORDER, text_color=COLOR_TEXT_PRIMARY,
        )
        self.entry_exclude_pages.grid(row=0, column=1, sticky="ew")
        self.entry_exclude_pages.bind("<KeyRelease>", lambda e: self.ctx.on_field_changed())

        # -- Adım 3: Kağıt Ölçüsü ve Sığdırma Yöntemi -------------------------
        mode_card = ctk.CTkFrame(container, fg_color=COLOR_SUBCARD, corner_radius=8,
                                 border_width=1, border_color=COLOR_BORDER)
        mode_card.grid(row=3, column=0, sticky="ew")
        mode_card.set_padding(12, 8, 12, 10, spacing=5)
        mode_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            mode_card, text="3. Kağıt Ölçüsü ve İçerik Sığdırma (Gelişmiş Ebat Ayarları)",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_ACCENT, anchor="w",
        ).grid(row=0, column=0, sticky="w")

        self.seg_size_mode = ctk.CTkSegmentedButton(
            mode_card, values=list(SIZE_MODE_LABELS.keys()), height=28,
            border_width=0, fg_color=COLOR_SUBCARD, bg_color=COLOR_SUBCARD,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            selected_color=COLOR_SELECTED, selected_hover_color=COLOR_SELECTED_HOVER,
            unselected_color=COLOR_CARD, unselected_hover_color=COLOR_SUBCARD,
            text_color=COLOR_TEXT_PRIMARY, command=lambda _v: self.on_changed(),
        )
        self.seg_size_mode.grid(row=1, column=0, sticky="ew")

        paper_row = ctk.CTkFrame(mode_card, fg_color="transparent")
        paper_row.grid(row=2, column=0, sticky="ew")
        paper_row.set_padding(0, 0, 0, 0, spacing=6)
        ctk.CTkLabel(
            paper_row, text="Hazır kağıt:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=(0, 4))
        self.paper_menu = ctk.CTkOptionMenu(
            paper_row, values=list(PAPER_SIZES.keys()), width=148, height=28,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            fg_color=COLOR_CARD, text_color=COLOR_TEXT_PRIMARY,
            button_color=COLOR_SUBCARD, button_hover_color=COLOR_BTN_SUBTLE_HOVER,
            dropdown_fg_color=COLOR_CARD, dropdown_hover_color=COLOR_SELECTED,
            dropdown_text_color=COLOR_TEXT_PRIMARY,
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
        )
        self.paper_menu.set(list(PAPER_SIZES.keys())[0])
        self.paper_menu.grid(row=0, column=1, sticky="w", padx=(0, 4))
        self.orientation_menu = ctk.CTkSegmentedButton(
            paper_row, values=["Dikey", "Yatay"], width=116, height=28,
            border_width=0, fg_color=COLOR_SUBCARD, bg_color=COLOR_SUBCARD,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            selected_color=COLOR_SELECTED, selected_hover_color=COLOR_SELECTED_HOVER,
            unselected_color=COLOR_CARD, unselected_hover_color=COLOR_SUBCARD,
            text_color=COLOR_TEXT_PRIMARY,
        )
        self.orientation_menu.set("Dikey")
        self.orientation_menu.grid(row=0, column=2, sticky="w", padx=(0, 4))
        ctk.CTkButton(
            paper_row, text="Ölçüyü Uygula", width=98, height=28,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            fg_color=COLOR_SOLID, text_color=COLOR_ON_ACCENT,
            hover_color=COLOR_SOLID_HOVER,
            command=self.apply_paper_size,
        ).grid(row=0, column=3, sticky="w", padx=(0, 12))

        ctk.CTkLabel(
            paper_row, text="Taşma:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
        ).grid(row=0, column=4, sticky="w", padx=(0, 4))
        self.seg_overflow = ctk.CTkSegmentedButton(
            paper_row, values=list(OVERFLOW_LABELS.keys()), width=176, height=28,
            border_width=0, fg_color=COLOR_SUBCARD, bg_color=COLOR_SUBCARD,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            selected_color=COLOR_SELECTED, selected_hover_color=COLOR_SELECTED_HOVER,
            unselected_color=COLOR_CARD, unselected_hover_color=COLOR_SUBCARD,
            text_color=COLOR_TEXT_PRIMARY, command=lambda _v: self.on_changed(),
        )
        self.seg_overflow.set(list(OVERFLOW_LABELS.keys())[0])
        self.seg_overflow.grid(row=0, column=5, sticky="w")
        paper_row.grid_columnconfigure(6, weight=1)

        sizes = ctk.CTkFrame(mode_card, fg_color="transparent")
        sizes.grid(row=3, column=0, sticky="ew")
        sizes.grid_columnconfigure(0, weight=1)
        sizes.grid_columnconfigure(1, weight=1)
        sizes.grid_columnconfigure(2, weight=1)

        self.f_width = FieldRow(
            sizes, "Hedef genişlik", "210", width=64, minimum=1, maximum=5000,
            on_change=self.on_changed,
        )
        self.f_width.grid(row=0, column=0, sticky="w")
        self.f_height = FieldRow(
            sizes, "Hedef yükseklik", "297", width=64, minimum=1, maximum=5000,
            on_change=self.on_changed,
        )
        self.f_height.grid(row=0, column=1, sticky="w", padx=8)
        self.f_safe_edge = FieldRow(
            sizes, "Güvenli kenar", "0", width=56, minimum=0, maximum=100,
            on_change=self.on_changed,
        )
        self.f_safe_edge.grid(row=0, column=2, sticky="w")
        self.update_safe_edge_state()

        # Açılış durumu: etiket modül anahtarına göre kurulur, özet ve önizleme güncellenir.
        self.show_active(self.ctx.module_enabled("gutter"))
        self.ctx.on_field_changed()

    # =====================================================================
    # Davranışlar
    # =====================================================================
    def on_changed(self) -> None:
        """Ebat/ofset/mod değişince: modül kapalıysa açar, değilse yeniler."""
        self.update_safe_edge_state()
        if not self.ctx.module_enabled("gutter"):
            self.ctx.enable_module("gutter")
        else:
            self.ctx.on_field_changed()

    def update_safe_edge_state(self) -> None:
        """Güvenli kenar yalnızca sabit ebat + "Sayfaya sığdır" modunda anlamlıdır."""
        shrink = (OVERFLOW_LABELS.get(self.seg_overflow.get()) == "shrink"
                  and SIZE_MODE_LABELS.get(self.seg_size_mode.get()) == "fixed")
        self.f_safe_edge.set_enabled(shrink)

    def apply_preset(self, gutter: float) -> None:
        """Hızlı cilt payı düğmesi: sabit ebat, kaynak genişliği + pay, tek sayfalara ofset."""
        self.seg_size_mode.set(SIZE_MODE_CODES["fixed"])
        self.f_width.set_mm(self.ctx.orig_width_mm + gutter)
        self.f_height.set_mm(self.ctx.orig_height_mm)
        self.f_odd_x.set_mm(gutter)
        self.f_odd_y.set_mm(0.0)
        self.f_even_x.set_mm(0.0)
        self.f_even_y.set_mm(0.0)
        self.ctx.enable_module("gutter")

    def reset_to_original(self) -> None:
        """Sıfırla / kapat: modülü kapatır, ebadı kaynağa döndürür, ofsetleri sıfırlar."""
        self.f_width.set_mm(self.ctx.orig_width_mm)
        self.f_height.set_mm(self.ctx.orig_height_mm)
        for row in (self.f_odd_x, self.f_odd_y, self.f_even_x, self.f_even_y):
            row.set_mm(0.0)
        self.ctx.disable_module("gutter")

    def apply_paper_size(self) -> None:
        width, height = PAPER_SIZES.get(self.paper_menu.get(), PAPER_SIZES["A4 (210 × 297)"])
        if self.orientation_menu.get() == "Yatay":
            width, height = height, width
        self.seg_size_mode.set(SIZE_MODE_CODES["fixed"])
        self.f_width.set_mm(width)
        self.f_height.set_mm(height)
        self.ctx.enable_module("gutter")
        self.ctx.set_status(f"Kağıt boyutu {width:g} × {height:g} mm olarak ayarlandı.",
                            COLOR_TEXT_PRIMARY)

    def show_active(self, active: bool) -> None:
        """Üst durum etiketini modül anahtarına göre günceller."""
        if active:
            self.lbl_gutter_status.configure(
                text="Etkin: tek ve çift sayfalara cilt payı uygulanacak", text_color=COLOR_OK)
        else:
            self.lbl_gutter_status.configure(
                text="Devre dışı: üstteki 'Cilt payı' onay kutusundan açın",
                text_color=COLOR_TEXT_SECONDARY)
