"""Pencere kabuğunun kurulumu (widget ağacı); davranış ``app.py`` ve sekmelerdedir.

Yerleşim: başlık çubuğu + gövde + eylem çubuğu. Gövde üç sütundur:
solda ``Belge`` kartı ve adım menüsü (her adımın kendi Açık/Kapalı anahtarı
vardır), ortada seçili adımın içerik kartı, sağda canlı önizleme.
"""

from __future__ import annotations

import os
from typing import Any, Dict

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QSplitter, QSplitterHandle, QVBoxLayout, QWidget

from ui import qt_compat as ctk
from PIL import Image

from core.gutter_engine import UNITS
from core.version import APP_NAME, VERSION
from ui.context import AppContext
from ui.paths import ASSETS_DIR
from ui.tabs.merge import MergeTab
from ui.tabs.number import NumberTab
from ui.tabs.page_layout import PageLayoutTab
from ui.tabs.tools import ToolsTab
from ui.theme import *  # noqa: F401,F403
from ui.window import TAB_NAMES, TabNav


class _PreviewHandle(QSplitterHandle):
    """Ayraç tutamacı: tema renginde ince çubuk; çift tıklamada varsayılan ↔ en geniş."""

    BAR_W = 4
    BAR_MARGIN = 16

    def __init__(self, orientation, parent: "PreviewSplitter"):
        super().__init__(orientation, parent)
        self._splitter = parent
        self.setCursor(Qt.CursorShape.SplitHCursor)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(ctk.resolve_color(COLOR_BORDER)))
        x = (self.width() - self.BAR_W) / 2.0
        top = float(self.BAR_MARGIN)
        height = max(0.0, self.height() - 2.0 * self.BAR_MARGIN)
        painter.drawRoundedRect(QRectF(x, top, self.BAR_W, height), 2, 2)
        painter.end()

    def mouseDoubleClickEvent(self, event) -> None:
        self._splitter.toggle_wide()

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        self._splitter.save_width()


class PreviewSplitter(QSplitter):
    """İçerik ile önizleme kolonu arasındaki gerçek ``QSplitter``.

    Sola çekilirse önizleme genişler, sağa çekilirse daralır. Çocukların asgari/azami
    boyutları (içerik ``CENTER_MIN``, önizleme ``MIN_WIDTH``..``MAX_WIDTH``) Qt tarafından
    uygulanır; kullanıcının istediği genişlik ``host._preview_width``'te saklanır ve pencere
    yeniden büyüyünce geri getirilir. Çift tıklama varsayılan ↔ olabildiğince geniş arasında geçer.
    """

    MIN_WIDTH = PREVIEW_MIN_W
    MAX_WIDTH = PREVIEW_MAX_W
    DEFAULT_WIDTH = PREVIEW_DEFAULT_W
    HANDLE_W = 14

    def __init__(self, host):
        super().__init__(Qt.Orientation.Horizontal)
        self._host = host
        self.setChildrenCollapsible(False)
        self.setOpaqueResize(True)
        self.setHandleWidth(self.HANDLE_W)
        self.splitterMoved.connect(self._on_moved)

    def createHandle(self) -> QSplitterHandle:
        return _PreviewHandle(self.orientation(), self)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        # Pencere/ayraç boyu değişince (ve açılışta) kullanıcının istediği genişlik geri gelir.
        self._host._apply_preview_column()

    def preview_index(self) -> int:
        return self.indexOf(self._host.preview_panel.card)

    def _on_moved(self, _pos: int, _index: int) -> None:
        index = self.preview_index()
        if index >= 0:
            self._host._preview_width = int(self.sizes()[index])

    def toggle_wide(self) -> None:
        host = self._host
        limit = min(self.MAX_WIDTH, host._preview_max_width())
        near_max = host._preview_width >= limit - 8
        host._set_preview_width(self.DEFAULT_WIDTH if near_max else limit)
        self.save_width()

    def save_width(self) -> None:
        try:  # panel genişliği bir sonraki açılışta korunur
            self._host.store.preview_width = self._host._preview_width
            self._host.store.save()
        except Exception:
            pass


class _PreviewWindow(QWidget):
    """Önizleme panelinin ayrı (isteğe bağlı üstte kalan) penceresi."""

    def __init__(self, host):
        # Üst pencere (sahip) VERİLMEZ: Windows'ta sahipli pencere, 'Üstte tut'
        # kapalıyken bile sahibinin önünde kalır. Bağımsız pencere olunca kapalı
        # durumda ana pencerenin arkasına düşebilir.
        super().__init__(None, Qt.WindowType.Window)
        self._host = host
        self.silent = False  # ana pencere kapatırken geri yerleştirmeyi tetikleme

    def closeEvent(self, event) -> None:
        if not self.silent:
            self._host._set_preview_display("docked")
        event.accept()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._host._set_preview_display("docked")
            return
        super().keyPressEvent(event)


class ShellBuildMixin:
    """Pencerenin kurulumu: üst çubuk, sol menü, çalışma alanı, eylem çubuğu."""

    #: Ortadaki içerik alanının asgari genişliği; önizleme paneli bunun altına itemez.
    CENTER_MIN = CENTER_MIN_W
    CENTER_MAX = CENTER_MAX_W
    SIDEBAR_W = SIDEBAR_W

    def _build_ui(self) -> None:
        with self.freeze_redraw():
            self.grid_columnconfigure(0, weight=1)
            self.grid_rowconfigure(1, weight=1)
            self._build_header()
            self._build_workspace()

    def _build_header(self) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        # Pencere kenar boşlukları (eskiden ``padx=16, pady=(12, 6)`` değerinden türüyordu).
        bar.place(0, 0, expand_x=True, margins=(14, 10, 14, 6))

        left = ctk.CTkFrame(bar, fg_color="transparent")
        left.put("h", fill="x", expand=True)
        # Simge/başlık grubunun sağ boşluğu (eskiden ilk çocuğun ``padx``'inden türüyordu).
        left._ensure_layout("pack_h").setContentsMargins(0, 0, 10, 0)

        icon_path = os.path.join(ASSETS_DIR, "icon.png")
        if os.path.exists(icon_path):
            try:
                image = Image.open(icon_path)
                self._header_icon = ctk.CTkImage(light_image=image, dark_image=image, size=(30, 30))
                ctk.CTkLabel(left, text="", image=self._header_icon).put("h")
            except Exception:
                pass

        ctk.CTkLabel(
            left, text=APP_NAME,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SUBTITLE, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        ).put("h")
        ctk.CTkLabel(
            left, text=f"v{VERSION}",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_SECONDARY,
        ).put("h")
        # Qt'de pack(side="left") öğeleri sola yığmaz; sondaki esnek boşluk simge,
        # başlık ve sürümü birbirine yapışık tutar (2.2.3).
        left._ensure_layout("pack_h").addStretch(1)

        right = ctk.CTkFrame(bar, fg_color="transparent")
        right.put("h")
        self.btn_top_batch = ctk.CTkButton(right, text="Toplu işlem…", width=104, height=30,
                                           command=self._show_batch_dialog)
        self.btn_top_batch.put("h", margins=(0, 0, SP_S, 0))

        self.theme_segmented = ctk.CTkSegmentedButton(
            right, values=["Açık", "Koyu", "Sistem"], width=186, height=30,
            border_width=0, fg_color=COLOR_CARD, bg_color=COLOR_BG,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            command=self._on_theme_changed,
            selected_color=COLOR_SELECTED, selected_hover_color=COLOR_SELECTED_HOVER,
            unselected_color=COLOR_CARD, unselected_hover_color=COLOR_SUBCARD,
            text_color=COLOR_TEXT_PRIMARY, corner_radius=6,
        )
        self.theme_segmented.put("h")

    def _build_workspace(self) -> None:
        workspace = ctk.CTkFrame(self, fg_color="transparent")
        workspace.place(1, 0, valign="fill", expand_x=True, expand_y=True)
        self._workspace = workspace
        self._preview_width = self.store.preview_width  # kayıtlı genişlik (sürüklenebilir; varsayılan 480)
        workspace.grid_columnconfigure(0, weight=0, minsize=SIDEBAR_W)
        workspace.grid_columnconfigure(1, weight=1)
        workspace.grid_rowconfigure(0, weight=1)
        self._preview_display = "docked"  # "docked" | "window" | "fullscreen"
        self._preview_win = None

        self._build_sidebar(workspace)
        self._build_action_bar(workspace)
        content = ctk.CTkFrame(workspace, fg_color=COLOR_CARD, corner_radius=10,
                               border_width=1, border_color=COLOR_BORDER)
        content.place(0, 1, valign="fill", expand_x=True, expand_y=True)
        self._content_frame = content
        content.set_padding(4, 4, 4, 4, spacing=0)
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(0, weight=1)

        self.tab_layout = ctk.CTkFrame(content, fg_color=COLOR_CARD)
        self.tab_number = ctk.CTkFrame(content, fg_color=COLOR_CARD)
        self.tab_merge = ctk.CTkFrame(content, fg_color=COLOR_CARD)
        self.tab_tools = ctk.CTkFrame(content, fg_color=COLOR_CARD)
        self._tab_frames = [self.tab_layout, self.tab_number, self.tab_merge, self.tab_tools]
        self._tab_frames_map = {
            "Sayfa Düzeni": self.tab_layout,
            "Sayfa Numaraları": self.tab_number,
            "Birleştirme": self.tab_merge,
            "Baskı ve Araçlar": self.tab_tools,
        }
        for frame in self._tab_frames:
            frame.place(0, 0, valign="fill", expand_x=True, expand_y=True)
            frame.grid_remove()

        # Sekmeler BaseTab sözleşmesiyle yönetilir (her biri kendi modülünde).
        ctx = AppContext(self)
        self._tabs: Dict[str, Any] = {
            "Sayfa Düzeni": PageLayoutTab("Sayfa Düzeni", ctx, self.tab_layout),
            "Sayfa Numaraları": NumberTab("Sayfa Numaraları", ctx, self.tab_number),
            "Birleştirme": MergeTab("Birleştirme", ctx, self.tab_merge),
            "Baskı ve Araçlar": ToolsTab("Baskı ve Araçlar", ctx, self.tab_tools),
        }
        # Tembel kurulum (2.9): açılışta yalnızca görünen sekme kurulur; diğerleri ilk
        # gösterildiğinde (select_tab) ya da eski adla ilk erişimde kurulur.
        self._tabs[self.current_tab].ensure_built()

        self.preview_panel.build(workspace)
        # (0: menü, 1-3: içerik | ayraç | önizleme) tek bir QSplitter; altında eylem çubuğu.
        self._split_host = ctk.CTkFrame(workspace, fg_color="transparent")
        self._split_host.set_padding(0, 0, 0, 0, spacing=0)
        self._split_host.place(0, 1, columnspan=3, valign="fill", expand_x=True, expand_y=True)
        self._preview_splitter = PreviewSplitter(self)
        self._split_host._ensure_layout("grid").addWidget(self._preview_splitter, 0, 0)
        self._place_in_splitter(content, 0)
        self._place_in_splitter(self.preview_panel.card, 1)
        content.setMinimumWidth(self.CENTER_MIN)
        content.setMaximumWidth(16777215)
        self._preview_splitter.setStretchFactor(0, 1)
        self._preview_splitter.setStretchFactor(1, 0)
        self._preview_splitter.setCollapsible(0, False)
        self._preview_splitter.setCollapsible(1, False)
        self._apply_preview_limits()
        self.preview_panel.display_handler = self._set_preview_display
        self.preview_panel.pin_handler = self._toggle_preview_on_top
        self.preview_panel.set_display_state("docked", self.store.preview_on_top)
        # Pencere daralınca önizleme, ortadaki alanı ezmeden kendi payını küçültür.
        workspace.bind("<Configure>", lambda _e: self._apply_preview_column(), add="+")

        self.tabview = TabNav(self)
        self.select_tab(self.current_tab)

    # =====================================================================
    # Sol menü: Belge kartı + adım menüsü (Açık/Kapalı anahtarlı)
    # =====================================================================
    def _build_sidebar(self, parent) -> None:
        sidebar = ctk.CTkFrame(parent, fg_color="transparent")
        # İki satıra yayılır: altındaki düğmeler sağdaki eylem çubuğuyla aynı hizada biter.
        sidebar.place(0, 0, rowspan=2, valign="fill", expand_x=True, expand_y=True)
        sidebar.grid_columnconfigure(0, weight=1)
        sidebar.grid_rowconfigure(0, weight=1)
        self._sidebar = sidebar
        # Sabit genişlik: orta alan ve önizleme payı hesabı yan menüye bağlı kalmasın.
        sidebar.setFixedWidth(self.SIDEBAR_W)

        # Üst blok (Belge + Adımlar), alt blok (Hakkında/Ayarlar) yapışık düzen.
        top = ctk.CTkFrame(sidebar, fg_color="transparent")
        top.place(0, 0, valign="n", expand_x=True)
        top.grid_columnconfigure(0, weight=1)

        self._build_sidebar_document_card(top)
        self._build_sidebar_step_card(top)
        self.top_sidebar = top
        self._build_sidebar_footer(sidebar)

    def _build_sidebar_document_card(self, parent) -> None:
        card = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=10,
                            border_width=1, border_color=COLOR_BORDER)
        card.place(0, 0, expand_x=True)
        card.set_padding(10, 10, 10, 10, spacing=6)
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card, text="Belge",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_SECONDARY, anchor="w",
        ).place(0, 0, align="w")

        ctk.CTkButton(
            card, text="PDF Seç...", height=36,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_BODY, weight="bold"),
            fg_color=COLOR_SOLID, text_color=COLOR_ON_ACCENT,
            hover_color=COLOR_SOLID_HOVER, corner_radius=6,
            command=self._choose_file,
        ).place(1, 0, expand_x=True)

        self.info_badge = ctk.CTkLabel(
            card, text="Henüz belge seçilmedi.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=200,
        )
        self.info_badge.place(2, 0, expand_x=True)
        self._bind_wraplength(self.info_badge, card, 24)

    def _build_sidebar_step_card(self, parent) -> None:
        card = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=10,
                            border_width=1, border_color=COLOR_BORDER)
        card.place(1, 0, valign="fill", expand_x=True, expand_y=True)
        card.set_padding(10, 10, 10, 10, spacing=SP_S)
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card, text="Adımlar",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_SECONDARY, anchor="w",
        ).place(0, 0, align="w")

        # Sayfa Düzeni, tıklanınca aşağı açılan bir akordeondur: Cilt payı ve Alt/üst
        # boşluk anahtarları (varsayılan açık) burada durur, sayfa içinde anahtar yoktur.
        # Sayfa Numaraları anahtarı da yalnızca burada bulunur.
        self._tab_buttons: Dict[str, ctk.CTkButton] = {}
        self._layout_expanded = True
        grid_row = 1
        for index, name in enumerate(TAB_NAMES):
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.place(grid_row, 0, expand_x=True)
            grid_row += 1
            row.grid_columnconfigure(0, weight=1)

            button = ctk.CTkButton(
                row, text=f"{index + 1}. {name}", height=36,
                font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
                fg_color=COLOR_CARD, text_color=COLOR_TEXT_PRIMARY,
                border_width=1, border_color=COLOR_BORDER,
                hover_color=COLOR_SUBCARD, corner_radius=8, anchor="w",
                command=lambda n=name: self._on_tab_button(n),
            )
            button.place(0, 0, expand_x=True)
            self._tab_buttons[name] = button

            if name == "Sayfa Numaraları":
                switch = ctk.QtSwitch(
                    row, checked=False, width=42, height=22,
                    command=lambda: self._toggle_pnum_fields(),
                )
                switch.place(0, 1, align="e")
                self.switch_pnum = switch
            else:
                # Açık/Kapalı anahtarı yok; hizayı korumak için iç boşluk.
                ctk.CTkLabel(row, text="", width=42).place(0, 1, align="c")

            if name == "Sayfa Düzeni":
                self._layout_sub = self._build_layout_submenu(card, grid_row)
                grid_row += 1

        # Sıra sabittir; Birleştirme ise ayrı bir dönüşümdür (sıranın parçası değil).
        self.lbl_steps_hint = ctk.CTkLabel(
            card, text="Sıra sabit: düzen → numara.\nBirleştirme ayrı bir dönüşümdür.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left",
            wraplength=SIDEBAR_W - 44,
        )
        self.lbl_steps_hint.place(grid_row, 0, expand_x=True)

    def _build_layout_submenu(self, parent, row: int):
        """Sayfa Düzeni'nin altında açılan alt başlıklar ve motor anahtarları."""
        sub = ctk.CTkFrame(parent, fg_color="transparent")
        sub.set_padding(14, 0, 0, 2, spacing=2)
        sub.place(row, 0, expand_x=True)
        sub.grid_columnconfigure(0, weight=1)

        entries = (
            ("Cilt payı", "gutter", "switch_gutter", "_toggle_gutter_fields"),
            ("Alt/üst boşluk", "margin", "switch_margin", "_toggle_margin_fields"),
            ("Ebat ve sığdırma", "size", None, None),
            ("Özel sayfalar", "special", None, None),
        )
        for index, (label, key, switch_attr, toggle) in enumerate(entries):
            item = ctk.CTkFrame(sub, fg_color="transparent")
            item.place(index, 0, expand_x=True)
            item.grid_columnconfigure(0, weight=1)
            ctk.CTkButton(
                item, text=label, height=28,
                font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
                fg_color="transparent", text_color=COLOR_TEXT_PRIMARY,
                hover_color=COLOR_SUBCARD, corner_radius=6, anchor="w",
                command=lambda k=key: self._goto_layout_section(k),
            ).place(0, 0, expand_x=True)
            if switch_attr is None:
                continue
            switch = ctk.QtSwitch(
                item, checked=True, width=42, height=22,
                command=lambda t=toggle: getattr(self, t)(),
            )
            switch.place(0, 1, align="e")
            setattr(self, switch_attr, switch)
        return sub

    def _on_tab_button(self, name: str) -> None:
        """Seçili Sayfa Düzeni'ne tekrar basmak akordeonu kapatır/açar."""
        if name == "Sayfa Düzeni" and self.current_tab == name:
            self._layout_expanded = not self._layout_expanded
            self._sync_layout_submenu()
            return
        self.select_tab(name)

    def _close_preview_window(self) -> None:
        """Uygulama kapanırken ayrı önizleme penceresini sessizce kapatır."""
        win = getattr(self, "_preview_win", None)
        if win is not None:
            try:
                win.silent = True
                win.close()
            except Exception:
                pass

    def _sync_layout_submenu(self, expand=None) -> None:
        if expand is not None:
            self._layout_expanded = expand
        sub = getattr(self, "_layout_sub", None)
        if sub is None:
            return
        if self._layout_expanded and self.current_tab == "Sayfa Düzeni":
            sub.place_restore()
        else:
            sub.grid_remove()

    def _goto_layout_section(self, key: str) -> None:
        """Alt başlığa tıklanınca Sayfa Düzeni'ni açar ve ilgili bölüme kaydırır."""
        self.select_tab("Sayfa Düzeni")
        tab = self._tabs["Sayfa Düzeni"]
        self.after(40, lambda: tab.scroll_to_section(key))

    def _build_sidebar_footer(self, sidebar) -> None:
        """Kılavuz & Hakkında ile Ayarlar: yan panelin en altında, eylem çubuğuyla hizalı."""
        footer = ctk.CTkFrame(sidebar, fg_color="transparent")
        footer.set_padding(0, 0, 0, 0, spacing=SP_XS)
        footer.place(1, 0, valign="s", expand_x=True)
        footer.grid_columnconfigure(0, weight=1)
        for row, (label, handler) in enumerate((("Kılavuz & Hakkında", self._show_about_dialog),
                                                ("Ayarlar", self._show_settings_dialog))):
            ctk.CTkButton(
                footer, text=label, height=32,
                font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
                fg_color=COLOR_CARD, text_color=COLOR_TEXT_PRIMARY,
                border_width=1, border_color=COLOR_BORDER,
                hover_color=COLOR_BTN_SUBTLE_HOVER, corner_radius=8,
                command=handler,
            ).place(row, 0, expand_x=True)

    def _build_action_bar(self, parent=None) -> None:
        if parent is None:
            parent = self
        card = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=10,
                            border_width=1, border_color=COLOR_BORDER)
        # Bölme alanı ile eylem kartı arası üst boşluk 6 px (eskiden ``pady=(6, 0)``).
        card.place(1, 1, columnspan=3, expand_x=True, margins=(0, 6, 0, 0))
        self._action_card = card
        card.grid_columnconfigure(0, weight=1)

        # Satır 1: hap etiketler + durum metni · Satır 2: seçenekler + düğmeler.
        # (v2.3.0: "Birleşik işlem hattı" başlığı kaldırıldı; ince ilerleme çizgisi ayraçtır.)
        row0 = ctk.CTkFrame(card, fg_color="transparent")
        row0.place(0, 0, expand_x=True, margins=(12, 6, 12, 1))  # eskiden padx=12, pady=(6, 1)
        row0.grid_columnconfigure(1, weight=1)
        self.pipeline_frame = ctk.CTkFrame(row0, fg_color="transparent")
        self.pipeline_frame.place(0, 0, align="w")
        self.pill_gutter = self._make_pill("Cilt: kapalı")
        self.pill_margin = self._make_pill("Boşluk: kapalı")
        self.pill_pnum = self._make_pill("Sayfa no: kapalı")
        # Başlık artık görünmez; ``pipeline`` modülü metnini güncellemeyi sürdürür.
        self.action_title_label = ctk.CTkLabel(row0, text="İşlem durumu")
        self.action_title_label.hide()

        self.status_label = ctk.CTkLabel(
            row0, text="Hazır. En az bir adım açın.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=560,
        )
        self.status_label.place(0, 1, expand_x=True, margins=(12, 0, 0, 0))  # eskiden padx=(12, 0)
        self._bind_wraplength(self.status_label, row0, 340)

        self.progress_bar = ctk.CTkProgressBar(card, height=4, progress_color=COLOR_ACCENT)
        self.progress_bar.set(0)
        self.progress_bar.place(1, 0, expand_x=True)

        bottom_row = ctk.CTkFrame(card, fg_color="transparent")
        bottom_row.place(2, 0, expand_x=True)
        bottom_row.grid_columnconfigure(0, weight=1)

        # PDF çıktı tercihleri Ayarlar'da düzenlenir; iş akışı widget'a bağlı değildir.
        self._output_quality = "print"
        self._flatten_annotations = True

        buttons = ctk.CTkFrame(bottom_row, fg_color="transparent")
        buttons.place(0, 1, align="e")
        buttons.grid_columnconfigure(0, weight=1)

        self.btn_new_job = ctk.CTkButton(
            buttons, text="Yeni iş", width=78, height=34,
            fg_color=COLOR_BTN_SUBTLE, text_color=COLOR_TEXT_PRIMARY,
            hover_color=COLOR_BTN_SUBTLE_HOVER, command=self._new_job,
        )
        self.btn_new_job.setToolTip(
            "Belgeyi ve birleştirme listesini temizler; ayarlar korunur. "
            "Programı kapatıp açmadan yeni bir iş başlatır.")
        self.btn_new_job.place(0, 0, align="e")
        self.btn_new_job.hide()
        self.btn_open_folder = ctk.CTkButton(
            buttons, text="Klasörde göster", width=116, height=34, state="disabled",
            fg_color=COLOR_BTN_SUBTLE, text_color=COLOR_TEXT_PRIMARY,
            hover_color=COLOR_BTN_SUBTLE_HOVER, command=self._open_output_folder,
        )
        self.btn_open_folder.place(0, 1, align="e")
        self.btn_open_folder.hide()
        self.btn_open_pdf = ctk.CTkButton(
            buttons, text="PDF'i aç", width=92, height=34, state="disabled",
            fg_color=COLOR_BTN_SUBTLE, text_color=COLOR_TEXT_PRIMARY,
            hover_color=COLOR_BTN_SUBTLE_HOVER, command=self._open_output_pdf,
        )
        self.btn_open_pdf.place(0, 2, align="e")
        self.btn_open_pdf.hide()
        self.btn_open_tools = ctk.CTkButton(
            buttons, text="Araçlarda aç", width=102, height=34, state="disabled",
            fg_color=COLOR_BTN_SUBTLE, text_color=COLOR_TEXT_PRIMARY,
            hover_color=COLOR_BTN_SUBTLE_HOVER, command=self._open_output_in_tools,
        )
        self.btn_open_tools.place(0, 3, align="e")
        self.btn_open_tools.hide()
        self.btn_cancel = ctk.CTkButton(
            buttons, text="İptal", width=74, height=34, state="disabled",
            fg_color=COLOR_SUBCARD, text_color=COLOR_TEXT_SECONDARY,
            hover_color=COLOR_ERROR_BG, command=self._cancel_work,
        )
        self.btn_cancel.place(0, 4, align="e")
        self.btn_cancel.hide()
        self.btn_preflight = ctk.CTkButton(
            buttons, text="Ön kontrol", width=90, height=34,
            fg_color=COLOR_BTN_SUBTLE, text_color=COLOR_TEXT_PRIMARY,
            hover_color=COLOR_BTN_SUBTLE_HOVER, command=self._show_preflight_summary,
        )
        self.btn_preflight.setToolTip("Kaynağı, etkin ayarları ve çıktı seçeneklerini gözden geçirin.")
        self.btn_preflight.place(0, 5, align="e")
        self.btn_preflight.hide()
        self.btn_main_action = ctk.CTkButton(
            buttons, text="PDF'i işle ve kaydet", width=ACTION_BTN_W, height=36,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_BODY, weight="bold"),
            fg_color=COLOR_SOLID, hover_color=COLOR_SOLID_HOVER,
            text_color=COLOR_ON_ACCENT,
            command=self._start_processing,
        )
        self.btn_main_action.place(0, 6, align="e")

    # =====================================================================
    # Önizleme paneli: genişlik sınırı ve gösterim kipleri
    # =====================================================================
    def _place_in_splitter(self, widget, index: int) -> None:
        """Izgaradaki bir kartı ayıraca taşır (ızgaradan çıkarıp ``QSplitter``'a ekler)."""
        lay = self._workspace._ensure_layout("grid")
        try:
            lay.removeWidget(widget)
        except Exception:
            pass
        self._preview_splitter.insertWidget(index, widget)
        widget.show()

    def _apply_preview_limits(self) -> None:
        """Önizleme kartının asgari/azami genişliği (yalnızca yerleşik kipte)."""
        card = self.preview_panel.card
        card.setMinimumWidth(self._preview_minimum_width())
        card.setMaximumWidth(PreviewSplitter.MAX_WIDTH)

    def _preview_minimum_width(self) -> int:
        return int(getattr(self, "_preview_min_width", PreviewSplitter.MIN_WIDTH))

    def _preview_max_width(self) -> int:
        """Ortadaki içerik alanına en az ``CENTER_MIN`` bırakan güvenli azami önizleme genişliği."""
        total = int(self._preview_splitter.width())
        if total <= 0:
            return PreviewSplitter.DEFAULT_WIDTH
        limit = total - self._preview_splitter.handleWidth() - self.CENTER_MIN
        minimum = self._preview_minimum_width()
        return max(minimum, min(PreviewSplitter.MAX_WIDTH, limit))

    def _effective_preview_width(self) -> int:
        return max(self._preview_minimum_width(), min(self._preview_width, self._preview_max_width()))

    def _apply_preview_column(self) -> None:
        """Kullanıcının istediği önizleme genişliğini ayıraca uygular (pencere boyu değişince de)."""
        if getattr(self, "_preview_display", "docked") != "docked":
            return
        splitter = self._preview_splitter
        total = int(splitter.width())
        if total <= 0 or splitter.preview_index() < 0:
            return
        width = self._effective_preview_width()
        center = max(0, total - splitter.handleWidth() - width)
        try:
            splitter.setSizes([center, width])
        except Exception:
            self.log.exception("Önizleme sütunu ayarlanamadı")

    def _set_preview_width(self, width: int) -> None:
        """Önizleme kolonunun genişliğini ayarlar (ayraç çift tıklaması, kayıtlı ayar, testler)."""
        limit = min(PreviewSplitter.MAX_WIDTH, self._preview_max_width())
        self._preview_width = max(self._preview_minimum_width(), min(limit, int(width)))
        try:
            self._apply_preview_column()
            try:
                self._schedule_preview()
            except Exception:
                pass
        except Exception:
            self.log.exception("Önizleme genişliği güncellenemedi")

    def _set_workspace_columns(self, left: int, center: int, right: int) -> None:
        lay = self._workspace._ensure_layout("grid")
        lay.setColumnMinimumWidth(0, left)
        lay.setColumnMinimumWidth(1, center)

    def _set_preview_display(self, mode: str) -> None:
        """Önizlemeyi yerleşik / ayrı pencere / tam alan kipleri arasında taşır."""
        current = getattr(self, "_preview_display", "docked")
        if mode == current:
            return
        card = self.preview_panel.card
        with self.freeze_redraw():
            if current == "window":
                self._leave_preview_window()
            elif current == "fullscreen":
                self._leave_preview_fullscreen()
            if mode == "window":
                self._enter_preview_window()
            elif mode == "fullscreen":
                self._enter_preview_fullscreen()
            self._preview_display = mode
            if mode == "docked":
                self._dock_preview_card(card)
        self.preview_panel.set_display_state(mode, self.store.preview_on_top)
        self.preview_panel.invalidate_fit()
        try:
            self._schedule_preview()
        except Exception:
            pass

    def _dock_preview_card(self, card) -> None:
        if self._preview_splitter.preview_index() < 0:
            self._preview_splitter.insertWidget(1, card)
        card.show()
        self._apply_preview_limits()
        self._set_workspace_columns(self.SIDEBAR_W, 0, 0)
        self._apply_preview_column()

    def _enter_preview_window(self) -> None:
        card = self.preview_panel.card
        card.setMaximumWidth(16777215)
        card.setMinimumWidth(self._preview_minimum_width())
        card.setParent(None)  # ayıraçtan çıkar; içerik alanı tam genişliği alır
        win = _PreviewWindow(self)
        win.setWindowTitle(f"Canlı önizleme - {APP_NAME}")
        lay = QVBoxLayout(win)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.addWidget(card)
        card.show()
        geo = self.frameGeometry()
        width = max(self._preview_minimum_width() + 40, self._preview_width + 40)
        height = max(420 if self._compact_screen else 560, self.height() - 120)
        win.resize(width, height)
        win.move(max(0, geo.right() - width - 20), geo.top() + 60)
        self._preview_win = win
        self._apply_on_top_flag(win, show=True)

    def _leave_preview_window(self) -> None:
        win = self._preview_win
        self._preview_win = None
        if win is None:
            return
        win.silent = True
        self.preview_panel.card.setParent(None)
        win.close()
        win.deleteLater()

    def _apply_on_top_flag(self, win, show: bool = False) -> None:
        """Ayrı pencereye 'her zaman üstte' bayrağını uygular (Qt bayrak değişince pencereyi gizler)."""
        on_top = bool(self.store.preview_on_top)
        was_visible = win.isVisible()
        geometry = win.geometry()
        win.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, on_top)
        if show or was_visible:
            win.show()
            if was_visible:
                win.setGeometry(geometry)
            win.raise_()
            win.activateWindow()

    def _toggle_preview_on_top(self) -> None:
        """Ayrı önizleme penceresinde 'Üstte tut' tercihini değiştirir ve kaydeder."""
        self.store.preview_on_top = not self.store.preview_on_top
        try:
            self.store.save()
        except Exception:
            pass
        if self._preview_win is not None:
            self._apply_on_top_flag(self._preview_win)
        self.preview_panel.set_display_state(self._preview_display, self.store.preview_on_top)

    def _enter_preview_fullscreen(self) -> None:
        card = self.preview_panel.card
        card.setMaximumWidth(16777215)
        card.setMinimumWidth(self._preview_minimum_width())
        for part in (self._sidebar, self._content_frame, self._action_card):
            part.grid_remove()
        self._set_workspace_columns(0, 0, 0)
        # Ayıraç (yalnızca önizleme kartı görünür) tüm çalışma alanına yayılır.
        self._split_host.place(0, 0, rowspan=2, columnspan=4, valign="fill",
                               expand_x=True, expand_y=True)

    def _leave_preview_fullscreen(self) -> None:
        self._split_host.place(0, 1, rowspan=1, columnspan=3, valign="fill",
                               expand_x=True, expand_y=True)
        self._sidebar.place_restore()
        self._content_frame.setVisible(True)
        self._action_card.place_restore()

    def _make_pill(self, text: str) -> ctk.CTkLabel:
        pill = ctk.CTkLabel(
            self.pipeline_frame, text=f" {text} ",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY, weight="bold"),
            fg_color=COLOR_SUBCARD, text_color=COLOR_TEXT_SECONDARY, corner_radius=4,
        )
        pill.put("h")
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
