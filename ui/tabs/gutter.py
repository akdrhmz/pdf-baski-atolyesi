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
        scroll.pack(fill="both", expand=True, padx=10, pady=6)
        scroll.set_padding(2, 4, 2, 6, spacing=6)
        container = scroll
        container.grid_columnconfigure(0, weight=1)
        # Dikey nefes: kart bloğu üst/altta, iç boşluklar sıfır.
        container.grid_rowconfigure(1, weight=1)
        container.grid_rowconfigure(3, minsize=6)
        container.grid_rowconfigure(5, minsize=6)
        container.grid_rowconfigure(7, weight=1)

        # -- Modül Durumu ( küçük tek satır; anahtar sol menüde) ----------------
        top = ctk.CTkFrame(container, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew")
        top.set_padding(0, 0, 0, 0, spacing=6)
        top.grid_columnconfigure(1, weight=1)

        self.lbl_gutter_status = ctk.CTkLabel(
            top, text="Devre dışı: soldaki anahtarla açın",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=540,
        )
        self.lbl_gutter_status.grid(row=0, column=1, sticky="ew")
        self.ctx.bind_wraplength(self.lbl_gutter_status, top, 24)

        # -- Hızlı Seçim (Tek Tıkla Cilt Payı veya Hazır Şablon) -----------------
        quick_card = ctk.CTkFrame(container, fg_color=COLOR_SUBCARD, corner_radius=8,
                                  border_width=1, border_color=COLOR_BORDER)
        quick_card.grid(row=2, column=0, sticky="ew")
        quick_card.set_padding(12, 8, 12, 10, spacing=4)
        quick_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            quick_card, text="Hızlı seçim",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
        ).grid(row=0, column=0, sticky="w")

        self._gutter_preset_row = WrapButtonRow(quick_card)
        self._gutter_preset_row.grid(row=1, column=0, sticky="ew")
        self._gutter_preset_row.add_button("İnce (10 mm)", lambda: self.apply_preset(10.0))
        self._gutter_preset_row.add_button("Standart (15 mm)", lambda: self.apply_preset(15.0), bold=True)
        self._gutter_preset_row.add_button("Geniş (20 mm)", lambda: self.apply_preset(20.0))
        self._gutter_preset_row.add_button("Sıfırla", self.reset_to_original)

        profile_row = ctk.CTkFrame(quick_card, fg_color="transparent")
        profile_row.grid(row=2, column=0, sticky="ew")
        profile_row.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            profile_row, text="Hazır baskı şablonları:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
        ).grid(row=0, column=0, sticky="w")
        self._preset_row = WrapButtonRow(profile_row)
        self._preset_row.grid(row=1, column=0, sticky="ew")
        for preset_name in PRESETS:
            short = preset_name.split(" (")[0]
            self._preset_row.add_button(
                short, lambda name=preset_name: self.ctx.apply_named_preset(name), width=96,
            )

        # -- Cilt Boşluğu Miktarı ve Muaf Kapak Sayfaları ------------------------
        offset_card = ctk.CTkFrame(container, fg_color=COLOR_SUBCARD, corner_radius=8,
                                   border_width=1, border_color=COLOR_BORDER)
        offset_card.grid(row=4, column=0, sticky="ew")
        offset_card.set_padding(12, 8, 12, 10, spacing=4)
        offset_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            offset_card, text="Cilt payı miktarı",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
        ).grid(row=0, column=0, sticky="w")

        def _offset_group(row: int, title: str):
            grp = ctk.CTkFrame(offset_card, fg_color="transparent")
            grp.grid(row=row, column=0, sticky="ew")
            ctk.CTkLabel(
                grp, text=title,
                font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
                text_color=COLOR_TEXT_PRIMARY, anchor="w",
            ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 2))
            return grp

        odd = _offset_group(1, "Tek sayfalar (sağ sayfa • sol kenar):")
        self.f_odd_x = FieldRow(odd, "Yatay pay", "0", width=62,
                                minimum=-5000, maximum=5000, allow_negative=True, on_change=self.on_changed)
        self.f_odd_x.grid(row=1, column=0, sticky="w", padx=(0, 12))
        self.f_odd_y = FieldRow(odd, "Dikey pay", "0", width=56,
                                minimum=-5000, maximum=5000, allow_negative=True, on_change=self.on_changed)
        self.f_odd_y.grid(row=1, column=1, sticky="w")

        even = _offset_group(2, "Çift sayfalar (sol sayfa • sağ kenar):")
        self.f_even_x = FieldRow(even, "Yatay pay", "0", width=62,
                                 minimum=-5000, maximum=5000, allow_negative=True, on_change=self.on_changed)
        self.f_even_x.grid(row=1, column=0, sticky="w", padx=(0, 12))
        self.f_even_y = FieldRow(even, "Dikey pay", "0", width=56,
                                 minimum=-5000, maximum=5000, allow_negative=True, on_change=self.on_changed)
        self.f_even_y.grid(row=1, column=1, sticky="w")

        exclude_row = ctk.CTkFrame(offset_card, fg_color="transparent")
        exclude_row.grid(row=3, column=0, sticky="ew")
        exclude_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            exclude_row, text="Muaf sayfalar:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.entry_exclude_pages = ctk.CTkEntry(
            exclude_row, placeholder_text="Örn: 1, 5, 9-10 (boş bırakırsanız tüm sayfalara uygulanır)",
            height=26, font=ctk.CTkFont(family=FONT_FAMILY, size=FS_BODY),
            fg_color=COLOR_CARD, border_color=COLOR_BORDER, text_color=COLOR_TEXT_PRIMARY,
        )
        self.entry_exclude_pages.grid(row=0, column=1, sticky="ew")
        self.entry_exclude_pages.bind("<KeyRelease>", lambda e: self.ctx.on_field_changed())

        # -- Sayfa Boyutu ve Sığdırma (Gelişmiş Ebat Ayarları) -------------------
        mode_card = ctk.CTkFrame(container, fg_color=COLOR_SUBCARD, corner_radius=8,
                                 border_width=1, border_color=COLOR_BORDER)
        mode_card.grid(row=6, column=0, sticky="ew")
        mode_card.set_padding(12, 8, 12, 10, spacing=4)
        mode_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            mode_card, text="Sayfa boyutu ve sığdırma",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
        ).grid(row=0, column=0, sticky="w")

        self.seg_size_mode = ctk.CTkSegmentedButton(
            mode_card, values=list(SIZE_MODE_LABELS.keys()), height=26,
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
            paper_row, values=list(PAPER_SIZES.keys()), width=148, height=26,
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
            paper_row, values=["Dikey", "Yatay"], width=116, height=26,
            border_width=0, fg_color=COLOR_SUBCARD, bg_color=COLOR_SUBCARD,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            selected_color=COLOR_SELECTED, selected_hover_color=COLOR_SELECTED_HOVER,
            unselected_color=COLOR_CARD, unselected_hover_color=COLOR_SUBCARD,
            text_color=COLOR_TEXT_PRIMARY,
        )
        self.orientation_menu.set("Dikey")
        self.orientation_menu.grid(row=0, column=2, sticky="w", padx=(0, 4))
        ctk.CTkButton(
            paper_row, text="Ölçüyü Uygula", width=98, height=26,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            fg_color=COLOR_SOLID, text_color=COLOR_ON_ACCENT,
            hover_color=COLOR_SOLID_HOVER,
            command=self.apply_paper_size,
        ).grid(row=0, column=3, sticky="w", padx=(0, 12))
        paper_row.grid_columnconfigure(4, weight=1)

        ctk.CTkLabel(
            paper_row, text="Taşma:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
        ).grid(row=1, column=0, sticky="w", padx=(0, 4), pady=(4, 0))
        self.seg_overflow = ctk.CTkSegmentedButton(
            paper_row, values=list(OVERFLOW_LABELS.keys()), height=26,
            border_width=0, fg_color=COLOR_SUBCARD, bg_color=COLOR_SUBCARD,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            selected_color=COLOR_SELECTED, selected_hover_color=COLOR_SELECTED_HOVER,
            unselected_color=COLOR_CARD, unselected_hover_color=COLOR_SUBCARD,
            text_color=COLOR_TEXT_PRIMARY, command=lambda _v: self.on_changed(),
        )
        self.seg_overflow.set(list(OVERFLOW_LABELS.keys())[0])
        self.seg_overflow.grid(row=1, column=1, columnspan=2, sticky="w", pady=(4, 0))
        paper_row.grid_columnconfigure(6, weight=1)

        sizes = ctk.CTkFrame(mode_card, fg_color="transparent")
        sizes.grid(row=3, column=0, sticky="ew")
        sizes.grid_columnconfigure(0, weight=1)
        sizes.grid_columnconfigure(1, weight=1)
        sizes.grid_columnconfigure(1, weight=1)

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
        self.f_safe_edge.grid(row=1, column=0, sticky="w", pady=(2, 0))
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
        """Modül anahtarının durumunu içeriğin üstündeki küçük etikete yazar."""
        if active:
            self.lbl_gutter_status.configure(
                text="Etkin: cilt payı uygulanacak", text_color=COLOR_OK)
        else:
            self.lbl_gutter_status.configure(
                text="Devre dışı: soldaki anahtarla açın",
                text_color=COLOR_TEXT_SECONDARY)
