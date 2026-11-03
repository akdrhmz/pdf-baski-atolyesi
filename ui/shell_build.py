"""Pencere kabuğunun kurulumu (widget ağacı); davranış ``app.py`` ve sekmelerdedir."""

from __future__ import annotations

import os
from typing import Any, Dict

from ui import qt_compat as ctk
from PIL import Image

from gutter_engine import UNITS
from version import APP_NAME, VERSION
from ui.context import AppContext
from ui.paths import ASSETS_DIR
from ui.tabs.gutter import GutterTab
from ui.tabs.margin import MarginTab
from ui.tabs.merge import MergeTab
from ui.tabs.number import NumberTab
from ui.theme import *  # noqa: F401,F403
from ui.window import TAB_NAMES, TabNav


class ShellBuildMixin:
    """Pencerenin kurulumu: üst çubuk, dosya çubuğu, çalışma alanı, modül şeridi, eylem çubuğu."""

    def _build_ui(self) -> None:
        with self.freeze_redraw():
            self.grid_columnconfigure(0, weight=1)
            self.grid_rowconfigure(2, weight=1)
            self._build_header()
            self._build_file_bar()
            self._build_workspace()
            self._build_action_bar()

    def _build_header(self) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", padx=16, pady=(8, 4))

        left = ctk.CTkFrame(bar, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)

        icon_path = os.path.join(ASSETS_DIR, "icon.png")
        if os.path.exists(icon_path):
            try:
                image = Image.open(icon_path)
                self._header_icon = ctk.CTkImage(light_image=image, dark_image=image, size=(30, 30))
                ctk.CTkLabel(left, text="", image=self._header_icon).pack(side="left", padx=(0, 10))
            except Exception:
                pass

        ctk.CTkLabel(
            left, text=APP_NAME,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SUBTITLE, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        ).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(
            left, text=f"v{VERSION} • Kayıpsız PDF Baskı ve Cilt Hazırlığı",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_SECONDARY,
        ).pack(side="left")

        right = ctk.CTkFrame(bar, fg_color="transparent")
        right.pack(side="right")

        ctk.CTkButton(
            right, text="Kılavuz & Hakkında", width=136, height=30,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            fg_color=COLOR_CARD, text_color=COLOR_TEXT_PRIMARY,
            border_width=1, border_color=COLOR_BORDER,
            hover_color=COLOR_BTN_SUBTLE_HOVER, corner_radius=6,
            command=self._show_about_dialog,
        ).pack(side="left", padx=(0, 8))

        self.theme_segmented = ctk.CTkSegmentedButton(
            right, values=["Açık", "Koyu", "Sistem"], width=186, height=30,
            border_width=0, fg_color=COLOR_CARD, bg_color=COLOR_BG,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            command=self._on_theme_changed,
            selected_color=COLOR_SELECTED, selected_hover_color=COLOR_SELECTED_HOVER,
            unselected_color=COLOR_CARD, unselected_hover_color=COLOR_SUBCARD,
            text_color=COLOR_TEXT_PRIMARY, corner_radius=6,
        )
        self.theme_segmented.pack(side="left")

    def _build_file_bar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color=COLOR_CARD, corner_radius=10,
                           border_width=1, border_color=COLOR_BORDER)
        bar.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 6))

        row = ctk.CTkFrame(bar, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(8, 4))

        ctk.CTkLabel(
            row, text="PDF Dosyası:", font=ctk.CTkFont(family=FONT_FAMILY, size=FS_BODY, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        ).pack(side="left", padx=(0, 8))

        self.path_entry = ctk.CTkEntry(
            row, placeholder_text="İşlenecek PDF dosyasını seçin veya pencereye sürükleyip bırakın...",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_BODY), height=34,
            border_color=COLOR_BORDER, fg_color=COLOR_SUBCARD, text_color=COLOR_TEXT_PRIMARY,
        )
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.path_entry.bind("<Return>", lambda e: self._load_from_entry())

        ctk.CTkButton(
            row, text="PDF Seç...", width=104, height=34,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_BODY, weight="bold"),
            fg_color=COLOR_SOLID, text_color=COLOR_ON_ACCENT,
            hover_color=COLOR_SOLID_HOVER,
            command=self._choose_file,
        ).pack(side="left")

        row2 = ctk.CTkFrame(bar, fg_color="transparent")
        row2.pack(fill="x", padx=12, pady=(0, 6))

        self.info_badge = ctk.CTkLabel(
            row2, text="Henüz belge seçilmedi.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=460,
        )
        self.info_badge.pack(side="left", fill="x", expand=True)

        controls = ctk.CTkFrame(row2, fg_color="transparent")
        controls.pack(side="right")

        ctk.CTkLabel(
            controls, text="Ölçü birimi:", font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_SECONDARY,
        ).pack(side="left", padx=(0, 4))
        self.unit_menu = ctk.CTkOptionMenu(
            controls, values=[UNITS[u][0] for u in DISPLAY_UNITS], width=70, height=28,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            fg_color=COLOR_SUBCARD, text_color=COLOR_TEXT_PRIMARY,
            button_color=COLOR_SUBCARD, button_hover_color=COLOR_BTN_SUBTLE_HOVER,
            dropdown_fg_color=COLOR_CARD, dropdown_hover_color=COLOR_SELECTED,
            dropdown_text_color=COLOR_TEXT_PRIMARY,
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            command=self._on_unit_changed,
        )
        self.unit_menu.pack(side="left", padx=(0, 12))

        ctk.CTkLabel(
            controls, text="Kayıtlı profil:", font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_SECONDARY,
        ).pack(side="left", padx=(0, 4))
        self.profile_menu = ctk.CTkOptionMenu(
            controls, values=["(profil seçin)"], width=164, height=28,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            fg_color=COLOR_SUBCARD, text_color=COLOR_TEXT_PRIMARY,
            button_color=COLOR_SUBCARD, button_hover_color=COLOR_BTN_SUBTLE_HOVER,
            dropdown_fg_color=COLOR_CARD, dropdown_hover_color=COLOR_SELECTED,
            dropdown_text_color=COLOR_TEXT_PRIMARY,
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
        )
        self.profile_menu.pack(side="left", padx=(0, 4))

        icon_button = {
            "width": 56, "height": 28, "font": ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            "fg_color": COLOR_SUBCARD, "text_color": COLOR_TEXT_PRIMARY,
            "border_width": 1, "border_color": COLOR_BORDER,
            "hover_color": COLOR_BTN_SUBTLE_HOVER, "corner_radius": 6,
        }
        ctk.CTkButton(controls, text="Yükle", command=self._load_profile, **icon_button).pack(side="left", padx=(0, 3))
        ctk.CTkButton(controls, text="Kaydet", command=self._save_profile, **{**icon_button, "width": 62}).pack(side="left", padx=(0, 3))
        ctk.CTkButton(controls, text="Sil", command=self._delete_profile, **{**icon_button, "width": 44}).pack(side="left")

        row2.bind("<Configure>", lambda e: self.info_badge.configure(
            wraplength=max(180, e.width - controls.winfo_reqwidth() - 24)), add="+")

    def _build_workspace(self) -> None:
        workspace = ctk.CTkFrame(self, fg_color="transparent")
        workspace.grid(row=2, column=0, sticky="nsew", padx=16, pady=(0, 6))
        self._workspace = workspace
        workspace.grid_columnconfigure(0, weight=1)
        workspace.grid_columnconfigure(1, weight=0, minsize=380)
        workspace.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(workspace, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(2, weight=1)

        self._build_module_bar(left)

        nav = ctk.CTkFrame(left, fg_color="transparent")
        nav.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        self._tab_buttons: Dict[str, ctk.CTkButton] = {}
        for index, name in enumerate(TAB_NAMES):
            nav.grid_columnconfigure(index, weight=1, uniform="tab")
            button = ctk.CTkButton(
                nav, text=f"{index + 1}. {name}", height=40,
                font=ctk.CTkFont(family=FONT_FAMILY, size=FS_BODY, weight="bold"),
                fg_color=COLOR_CARD, text_color=COLOR_TEXT_PRIMARY,
                border_width=1, border_color=COLOR_BORDER,
                hover_color=COLOR_SUBCARD, corner_radius=8,
                command=lambda n=name: self.select_tab(n),
            )
            button.grid(row=0, column=index, sticky="ew", padx=3)
            self._tab_buttons[name] = button

        content = ctk.CTkFrame(left, fg_color=COLOR_CARD, corner_radius=10,
                               border_width=1, border_color=COLOR_BORDER)
        content.grid(row=2, column=0, sticky="nsew")
        content.set_padding(4, 4, 4, 4, spacing=0)
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(0, weight=1)

        self.tab_gutter = ctk.CTkFrame(content, fg_color=COLOR_CARD)
        self.tab_margin = ctk.CTkFrame(content, fg_color=COLOR_CARD)
        self.tab_number = ctk.CTkFrame(content, fg_color=COLOR_CARD)
        self.tab_merge = ctk.CTkFrame(content, fg_color=COLOR_CARD)
        self._tab_frames = [self.tab_gutter, self.tab_margin, self.tab_number, self.tab_merge]
        self._tab_frames_map = {
            "Cilt Payı": self.tab_gutter,
            "Kenar Boşlukları": self.tab_margin,
            "Sayfa Numaraları": self.tab_number,
            "Birleştirme": self.tab_merge,
        }
        for frame in self._tab_frames:
            frame.grid(row=0, column=0, sticky="nsew")
            frame.grid_remove()

        # Sekmeler BaseTab sözleşmesiyle yönetilir (her biri kendi modülünde).
        ctx = AppContext(self)
        self._tabs: Dict[str, Any] = {
            "Cilt Payı": GutterTab("Cilt Payı", ctx, self.tab_gutter),
            "Kenar Boşlukları": MarginTab("Kenar Boşlukları", ctx, self.tab_margin),
            "Sayfa Numaraları": NumberTab("Sayfa Numaraları", ctx, self.tab_number),
            "Birleştirme": MergeTab("Birleştirme", ctx, self.tab_merge),
        }
        # Tembel kurulum (2.9): açılışta yalnızca görünen sekme kurulur; diğerleri ilk
        # gösterildiğinde (select_tab) ya da eski adla ilk erişimde kurulur.
        self._tabs[self.current_tab].ensure_built()
        self.preview_panel.build(workspace)

        self.tabview = TabNav(self)
        self.select_tab(self.current_tab)

    def _expose_tab_widgets(self, tab) -> None:
        """Taşınmış sekmenin widget'larını eski adlarla pencereye bağlar (geçiş köprüsü).

        Sekme kurulunca ``_on_tab_built`` çağırır. Kurulmamış sekmenin adı istenirse
        ``ConfigBindingMixin.__getattr__`` sekmeyi o anda kurar.
        """
        for attr in getattr(tab, "EXPOSED", ()):
            setattr(self, attr, getattr(tab, attr))

    def _build_module_bar(self, parent) -> None:
        """Üç modülün tek yerden açılıp kapatıldığı üst şerit."""
        bar = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=8,
                           border_width=1, border_color=COLOR_BORDER)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        bar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            bar, text="Uygulanacak işlemler:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
        ).grid(row=0, column=0, sticky="w", padx=(12, 8), pady=6)

        checks = ctk.CTkFrame(bar, fg_color="transparent")
        checks.grid(row=0, column=1, sticky="e", padx=(0, 6), pady=6)

        check_font = ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold")
        self.switch_gutter = ctk.CTkCheckBox(
            checks, text="Cilt payı", font=check_font,
            text_color=COLOR_TEXT_PRIMARY, hover_color=COLOR_ACCENT,
            fg_color=COLOR_SOLID, border_color=COLOR_BORDER,
            command=self._toggle_gutter_fields,
        )
        self.switch_gutter.pack(side="left", padx=(0, 14))

        self.switch_margin = ctk.CTkCheckBox(
            checks, text="Kenar boşluğu", font=check_font,
            text_color=COLOR_TEXT_PRIMARY, hover_color=COLOR_ACCENT,
            fg_color=COLOR_SOLID, border_color=COLOR_BORDER,
            command=self._toggle_margin_fields,
        )
        self.switch_margin.pack(side="left", padx=(0, 14))

        self.switch_pnum = ctk.CTkCheckBox(
            checks, text="Sayfa numarası", font=check_font,
            text_color=COLOR_TEXT_PRIMARY, hover_color=COLOR_ACCENT,
            fg_color=COLOR_SOLID, border_color=COLOR_BORDER,
            command=self._toggle_pnum_fields,
        )
        self.switch_pnum.pack(side="left")

        self.btn_all_modules = ctk.CTkButton(
            bar, text="Tümünü aç", width=106, height=26,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            fg_color=COLOR_SUBCARD, text_color=COLOR_TEXT_PRIMARY,
            border_width=1, border_color=COLOR_BORDER,
            hover_color=COLOR_BTN_SUBTLE_HOVER, corner_radius=6,
            command=self._toggle_all_modules,
        )
        self.btn_all_modules.grid(row=0, column=2, sticky="e", padx=10)

    def _build_action_bar(self) -> None:
        card = ctk.CTkFrame(self, fg_color=COLOR_CARD, corner_radius=10,
                            border_width=1, border_color=COLOR_BORDER)
        card.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 10))
        card.grid_columnconfigure(0, weight=1)

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=12, pady=(6, 1))
        head.grid_columnconfigure(0, weight=1)
        self.action_title_label = ctk.CTkLabel(
            head, text="İşlem durumu",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_BODY, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        )
        self.action_title_label.grid(row=0, column=0, sticky="w")

        self.pipeline_frame = ctk.CTkFrame(head, fg_color="transparent")
        self.pipeline_frame.grid(row=0, column=1, sticky="e")
        self.pill_gutter = self._make_pill("Cilt: kapalı")
        self.pill_margin = self._make_pill("Boşluk: kapalı")
        self.pill_pnum = self._make_pill("Sayfa no: kapalı")

        self.progress_bar = ctk.CTkProgressBar(card, height=4, progress_color=COLOR_ACCENT)
        self.progress_bar.set(0)
        self.progress_bar.grid(row=1, column=0, sticky="ew", padx=12, pady=2)

        self.status_label = ctk.CTkLabel(
            card, text="Hazır. En az bir modülü etkinleştirin.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=780,
        )
        self.status_label.grid(row=2, column=0, sticky="ew", padx=12)
        self._bind_wraplength(self.status_label, card, 40)

        bottom_row = ctk.CTkFrame(card, fg_color="transparent")
        bottom_row.grid(row=3, column=0, sticky="ew", padx=12, pady=(4, 8))
        bottom_row.grid_columnconfigure(0, weight=1)

        options = ctk.CTkFrame(bottom_row, fg_color="transparent")
        options.grid(row=0, column=0, sticky="w")
        self.chk_optimize = ctk.CTkCheckBox(
            options, text="Dosyayı optimize et (küçük boyut)",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, hover_color=COLOR_ACCENT_HOVER,
            fg_color=COLOR_ACCENT,
        )
        self.chk_optimize.pack(side="left", padx=(0, 12))
        self.chk_flatten = ctk.CTkCheckBox(
            options, text="Açıklama ve form alanlarını sayfaya göm",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, hover_color=COLOR_ACCENT_HOVER,
            fg_color=COLOR_ACCENT,
        )
        self.chk_flatten.select()
        self.chk_flatten.pack(side="left")

        buttons = ctk.CTkFrame(bottom_row, fg_color="transparent")
        buttons.grid(row=0, column=1, sticky="e")

        self.btn_open_folder = ctk.CTkButton(
            buttons, text="Klasörde göster", width=116, height=34, state="disabled",
            fg_color=COLOR_BTN_SUBTLE, text_color=COLOR_TEXT_PRIMARY,
            hover_color=COLOR_BTN_SUBTLE_HOVER, command=self._open_output_folder,
        )
        self.btn_open_folder.pack(side="left", padx=(0, 4))
        self.btn_open_pdf = ctk.CTkButton(
            buttons, text="PDF'i aç", width=92, height=34, state="disabled",
            fg_color=COLOR_BTN_SUBTLE, text_color=COLOR_TEXT_PRIMARY,
            hover_color=COLOR_BTN_SUBTLE_HOVER, command=self._open_output_pdf,
        )
        self.btn_open_pdf.pack(side="left", padx=4)
        self.btn_cancel = ctk.CTkButton(
            buttons, text="İptal", width=74, height=34, state="disabled",
            fg_color=COLOR_SUBCARD, text_color=COLOR_TEXT_SECONDARY,
            hover_color=COLOR_ERROR_BG, command=self._cancel_work,
        )
        self.btn_cancel.pack(side="left", padx=4)
        self.btn_main_action = ctk.CTkButton(
            buttons, text="PDF'i işle ve kaydet", width=230, height=36,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_BODY, weight="bold"),
            fg_color=COLOR_SOLID, hover_color=COLOR_SOLID_HOVER,
            text_color=COLOR_ON_ACCENT,
            command=self._start_processing,
        )
        self.btn_main_action.pack(side="left", padx=(6, 0))

    def _make_pill(self, text: str) -> ctk.CTkLabel:
        pill = ctk.CTkLabel(
            self.pipeline_frame, text=f" {text} ",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY, weight="bold"),
            fg_color=COLOR_SUBCARD, text_color=COLOR_TEXT_SECONDARY, corner_radius=4,
        )
        pill.pack(side="left", padx=2)
        return pill

    def _bind_wraplength(self, label, container, padding: int) -> None:
        state = {"width": None}

        def on_configure(event, pad=padding):
            width = max(120, event.width - pad)
            if state["width"] is not None and abs(state["width"] - width) < 4:
                return
            state["width"] = width
            try:
                label.configure(wraplength=width)
            except Exception:
                pass
        container.bind("<Configure>", on_configure, add="+")
