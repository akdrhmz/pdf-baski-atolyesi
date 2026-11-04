"""Pencere kabuğunun kurulumu (widget ağacı); davranış ``app.py`` ve sekmelerdedir.

Yerleşim: başlık çubuğu + gövde + eylem çubuğu. Gövde üç sütundur:
solda ``Belge`` kartı ve adım menüsü (her adımın kendi Açık/Kapalı anahtarı
vardır), ortada seçili adımın içerik kartı, sağda canlı önizleme.
"""

from __future__ import annotations

import os
from typing import Any, Dict

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor

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


class PreviewSplitter(ctk.CTkFrame):
    """İçerik ile önizleme kolonu arasındaki sürüklenebilir ayraç.

    Sola çekilirse önizleme genişler, sağa çekilirse daralır (CLAMP aralığı 280-800).
    """

    MIN_WIDTH = 280
    MAX_WIDTH = 900

    def __init__(self, master, host, preview_panel):
        super().__init__(master, fg_color=COLOR_BORDER, corner_radius=2)
        self.setFixedWidth(7)
        self.setCursor(Qt.CursorShape.SplitHCursor)
        self._host = host
        self._panel = preview_panel
        self._press_x = -1
        self._start_w = 0

    def _set_width(self, width: int) -> None:
        new_w = max(self.MIN_WIDTH, min(self.MAX_WIDTH, int(width)))
        self._host._set_preview_width(new_w)

    def mousePressEvent(self, event) -> None:
        self._press_x = QCursor.pos().x()
        self._start_w = self._host._preview_width
        self.grabMouse()

    def mouseMoveEvent(self, event) -> None:
        if self._press_x >= 0:
            # Sola sürükleme (+delta) önizlemeyi genişletir.
            self._set_width(self._start_w + self._press_x - QCursor.pos().x())

    def mouseReleaseEvent(self, event) -> None:
        self._press_x = -1
        self.releaseMouse()


class ShellBuildMixin:
    """Pencerenin kurulumu: üst çubuk, sol menü, çalışma alanı, eylem çubuğu."""

    def _build_ui(self) -> None:
        with self.freeze_redraw():
            self.grid_columnconfigure(0, weight=1)
            self.grid_rowconfigure(1, weight=1)
            self._build_header()
            self._build_workspace()

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
            left, text=f"v{VERSION}",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_SECONDARY,
        ).pack(side="left")

        right = ctk.CTkFrame(bar, fg_color="transparent")
        right.pack(side="right")

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

    def _build_workspace(self) -> None:
        workspace = ctk.CTkFrame(self, fg_color="transparent")
        workspace.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 6))
        self._workspace = workspace
        self._preview_width = 480  # Önizleme kolonunun başlangıç genişliği (sürüklenebilir).
        workspace.grid_columnconfigure(0, weight=0, minsize=230)
        workspace.grid_columnconfigure(1, weight=1, minsize=360)
        workspace.grid_columnconfigure(3, weight=0, minsize=self._preview_width)
        workspace.grid_rowconfigure(0, weight=1)

        self._build_sidebar(workspace)
        self._build_action_bar(workspace)
        content = ctk.CTkFrame(workspace, fg_color=COLOR_CARD, corner_radius=10,
                               border_width=1, border_color=COLOR_BORDER)
        content.grid(row=0, column=1, sticky="nsew", padx=(0, 10))
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
        # (0: menü, 1: içerik, 2: ayraç, 3: önizleme) sürüklenebilir sütun ayracı.
        PreviewSplitter(workspace, self, self.preview_panel).grid(
            row=0, column=2, sticky="ns", pady=16)

        self.tabview = TabNav(self)
        self.select_tab(self.current_tab)

    def _expose_tab_widgets(self, tab) -> None:
        """Taşınmış sekmenin widget'larını eski adlarla pencereye bağlar (geçiş köprüsü).

        Sekme kurulunca ``_on_tab_built`` çağırır. Kurulmamış sekmenin adı istenirse
        ``ConfigBindingMixin.__getattr__`` sekmeyi o anda kurar.
        """
        for attr in getattr(tab, "EXPOSED", ()):
            setattr(self, attr, getattr(tab, attr))

    # =====================================================================
    # Sol menü: Belge kartı + adım menüsü (Açık/Kapalı anahtarlı)
    # =====================================================================
    def _build_sidebar(self, parent) -> None:
        sidebar = ctk.CTkFrame(parent, fg_color="transparent")
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_columnconfigure(0, weight=1)
        sidebar.grid_rowconfigure(2, weight=1)
        self._sidebar = sidebar

        self._build_sidebar_document_card(sidebar)
        self._build_sidebar_step_card(sidebar)
        self._build_sidebar_footer(sidebar)

    def _build_sidebar_document_card(self, sidebar) -> None:
        card = ctk.CTkFrame(sidebar, fg_color=COLOR_CARD, corner_radius=10,
                            border_width=1, border_color=COLOR_BORDER)
        card.grid(row=0, column=0, sticky="ew")
        card.set_padding(10, 10, 10, 10, spacing=6)
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card, text="Belge",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_SECONDARY, anchor="w",
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkButton(
            card, text="PDF Seç...", height=36,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_BODY, weight="bold"),
            fg_color=COLOR_SOLID, text_color=COLOR_ON_ACCENT,
            hover_color=COLOR_SOLID_HOVER, corner_radius=6,
            command=self._choose_file,
        ).grid(row=1, column=0, sticky="ew")

        self.info_badge = ctk.CTkLabel(
            card, text="Henüz belge seçilmedi.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=200,
        )
        self.info_badge.grid(row=2, column=0, sticky="ew")
        self._bind_wraplength(self.info_badge, card, 24)

        unit_row = ctk.CTkFrame(card, fg_color="transparent")
        unit_row.grid(row=3, column=0, sticky="ew")
        ctk.CTkLabel(
            unit_row, text="Ölçü birimi:",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_SECONDARY, anchor="w",
        ).pack(side="left", padx=(0, 6))
        self.unit_menu = ctk.CTkOptionMenu(
            unit_row, values=[UNITS[u][0] for u in DISPLAY_UNITS], width=66, height=28,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            fg_color=COLOR_SUBCARD, text_color=COLOR_TEXT_PRIMARY,
            button_color=COLOR_SUBCARD, button_hover_color=COLOR_BTN_SUBTLE_HOVER,
            dropdown_fg_color=COLOR_CARD, dropdown_hover_color=COLOR_SELECTED,
            dropdown_text_color=COLOR_TEXT_PRIMARY,
            dropdown_font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            command=self._on_unit_changed,
        )
        self.unit_menu.pack(side="left")

    def _build_sidebar_step_card(self, sidebar) -> None:
        card = ctk.CTkFrame(sidebar, fg_color=COLOR_CARD, corner_radius=10,
                            border_width=1, border_color=COLOR_BORDER)
        card.grid(row=1, column=0, sticky="nsew")
        card.set_padding(10, 10, 10, 10, spacing=0)
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card, text="Adımlar",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_SECONDARY, anchor="w",
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        # modül anahtarı -> (pencere anahtar metodu, sekme çerçevesi, varsayılan durum)
        module_map = {
            "Cilt Payı": ("_toggle_gutter_fields", True),
            "Kenar Boşlukları": ("_toggle_margin_fields", False),
            "Sayfa Numaraları": ("_toggle_pnum_fields", False),
            "Birleştirme": (None, True),
        }
        names_with_switch = {"Cilt Payı": "switch_gutter", "Kenar Boşlukları": "switch_margin",
                             "Sayfa Numaraları": "switch_pnum"}

        self._tab_buttons: Dict[str, ctk.CTkButton] = {}
        for index, name in enumerate(TAB_NAMES):
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.grid(row=index + 1, column=0, sticky="ew", pady=(0, 2))
            row.grid_columnconfigure(0, weight=1)

            button = ctk.CTkButton(
                row, text=f"{index + 1}. {name}", height=36,
                font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
                fg_color=COLOR_CARD, text_color=COLOR_TEXT_PRIMARY,
                border_width=1, border_color=COLOR_BORDER,
                hover_color=COLOR_SUBCARD, corner_radius=8, anchor="w",
                command=lambda n=name: self.select_tab(n),
            )
            button.grid(row=0, column=0, sticky="ew", padx=(0, 6))
            self._tab_buttons[name] = button

            toggle_name, default_on = module_map[name]
            if toggle_name is None:
                # Birleştirme seçimi anahtarlı değil; boşluk yerine iç boşluk bırak.
                blank = ctk.CTkLabel(row, text="", width=42)
                blank.grid(row=0, column=1)
                continue
            switch = ctk.QtSwitch(
                row, checked=default_on, width=42, height=22,
                command=lambda t=toggle_name: getattr(self, t)(),
            )
            switch.grid(row=0, column=1, sticky="e")
            setattr(self, names_with_switch[name], switch)

    def _build_sidebar_footer(self, sidebar) -> None:
        footer = ctk.CTkFrame(sidebar, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        footer.grid_columnconfigure(0, weight=1)

        ctk.CTkButton(
            footer, text="Kılavuz & Hakkında", height=32,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            fg_color=COLOR_CARD, text_color=COLOR_TEXT_PRIMARY,
            border_width=1, border_color=COLOR_BORDER,
            hover_color=COLOR_BTN_SUBTLE_HOVER, corner_radius=8,
            command=self._show_about_dialog,
        ).grid(row=0, column=0, sticky="ew")
        ctk.CTkButton(
            footer, text="Ayarlar", height=32,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            fg_color=COLOR_CARD, text_color=COLOR_TEXT_PRIMARY,
            border_width=1, border_color=COLOR_BORDER,
            hover_color=COLOR_BTN_SUBTLE_HOVER, corner_radius=8,
            command=self._show_settings_dialog,
        ).grid(row=1, column=0, sticky="ew", pady=(4, 0))

    def _build_action_bar(self, parent=None) -> None:
        if parent is None:
            parent = self
        card = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=10,
                            border_width=1, border_color=COLOR_BORDER)
        card.grid(row=1, column=1, columnspan=3, sticky="ew", padx=(0, 0), pady=(6, 0))
        card.grid_columnconfigure(0, weight=1)

        row0 = ctk.CTkFrame(card, fg_color="transparent")
        row0.grid(row=0, column=0, sticky="ew", padx=12, pady=(6, 1))
        row0.grid_columnconfigure(0, weight=1)
        self.pipeline_frame = ctk.CTkFrame(row0, fg_color="transparent")
        self.pipeline_frame.grid(row=0, column=0, sticky="w")
        self.pill_gutter = self._make_pill("Cilt: kapalı")
        self.pill_margin = self._make_pill("Boşluk: kapalı")
        self.pill_pnum = self._make_pill("Sayfa no: kapalı")
        self.action_title_label = ctk.CTkLabel(
            row0, text="İşlem durumu",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        )
        self.action_title_label.grid(row=0, column=1, sticky="e")

        self.progress_bar = ctk.CTkProgressBar(card, height=4, progress_color=COLOR_ACCENT)
        self.progress_bar.set(0)
        self.progress_bar.grid(row=1, column=0, sticky="ew", padx=12, pady=2)

        self.status_label = ctk.CTkLabel(
            card, text="Hazır. En az bir adım açın.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=780,
        )
        self.status_label.grid(row=2, column=0, sticky="ew", padx=12)
        self._bind_wraplength(self.status_label, card, 340)

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

    def _set_preview_width(self, width: int) -> None:
        """Önizleme kolonunun genişliğini sürüklemeyle günceller (ayraç çağırır)."""
        width = max(280, min(900, int(width)))
        self._preview_width = width
        try:
            self._workspace.grid_columnconfigure(3, weight=0, minsize=width)
            self.preview_panel.card.setMinimumWidth(width)
            needed = 230 + 360 + 7 + width + 48
            if self.width() < needed:
                self.resize(needed, self.height())
            try:
                self._schedule_preview()
            except Exception:
                pass
        except Exception:
            self.log.exception("Önizleme genişliği güncelenemedi")

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
