"""Baskı ve Araçlar sekmesi: sayfa düzenleme/bölme, filigran/Bates, baskı montajı, güvenlik.

Ana penceredeki canlı önizleme paneliyle (``PreviewPanel``) doğrudan çalışır.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading
from typing import Optional

from PySide6.QtCore import Qt, QSize, QThread, QTimer
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import QAbstractItemView, QColorDialog, QListWidget, QListWidgetItem

from core.gutter_engine import PDF_LOCK, open_pdf, same_path, unique_output_path
from core.pdf_tools import (
    PrintOptions,
    SecurityMetaOptions,
    StampOptions,
    apply_security_and_metadata,
    describe_impose_sheet,
    export_pages,
    impose_pdf,
    split_pages,
    stamp_pdf,
)
from ui import qt_compat as ctk
from ui.qt_compat import filedialog, messagebox
from ui.tabs.base import BaseTab
from ui.theme import *  # noqa: F401,F403
from ui.widgets import FieldError, FieldRow, WrapButtonRow

_PAPER_PRESETS = {
    "A4 Yatay (297×210)": (297, 210),
    "A3 Yatay (420×297)": (420, 297),
    "SRA3 Yatay (450×320)": (450, 320),
    "A4 Dikey (210×297)": (210, 297),
    "Özel": None,
}
_SIGNATURE_OPTIONS = {
    "Tek forma (tüm belge)": 0,
    "8 sayfa (2 yaprak)": 8,
    "16 sayfa (4 yaprak)": 16,
    "24 sayfa (6 yaprak)": 24,
    "32 sayfa (8 yaprak)": 32,
}
_BATES_POSITIONS = {
    "Sol alt": "bottom_left",
    "Alt orta": "bottom_center",
    "Sağ alt": "bottom_right",
    "Sol üst": "top_left",
    "Sağ üst": "top_right",
}


class _ToolsPageGrid(QListWidget, ctk.QtWidgetMixin):
    def __init__(self, master):
        super().__init__(master._content_host())
        self._init_mixin(master)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setIconSize(QSize(92, 116))
        self.setGridSize(QSize(120, 150))
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setMovement(QListWidget.Movement.Snap)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setMinimumHeight(240)


class ToolsTab(BaseTab):
    """Ana pencereye gömülü baskı montajı, damga, sayfa düzenleme ve güvenlik sekmesi."""

    def build(self) -> None:
        self.path: str = ""
        self._page_count: int = 0
        self._generation: int = 0
        self._pending: set = set()
        self._cancel = threading.Event()
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="tools-tab")

        scroll = self.make_scroll()
        scroll.grid_rowconfigure(1, weight=0)
        scroll.grid_rowconfigure(6, weight=1)
        self._scroll = scroll

        # -- Üst araç seçici (tek tıkla geçiş) --------------------------------
        nav_card = ctk.CTkFrame(scroll, fg_color=COLOR_CARD, corner_radius=10,
                                border_width=1, border_color=COLOR_BORDER)
        nav_card.set_padding(SP_S, SP_M, SP_S, SP_M, spacing=SP_XS)
        nav_card.place(0, 0, expand_x=True)
        nav_card.grid_columnconfigure(0, weight=1)

        self.operation = ctk.CTkSegmentedButton(
            nav_card,
            values=["Sayfaları Düzenle", "Filigran & Bates", "Baskı Montajı", "Güvenlik & Meta"],
            height=30,
            border_width=0, fg_color=COLOR_SUBCARD, bg_color=COLOR_CARD,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            selected_color=COLOR_SELECTED, selected_hover_color=COLOR_SELECTED_HOVER,
            unselected_color=COLOR_CARD, unselected_hover_color=COLOR_BTN_SUBTLE_HOVER,
            text_color=COLOR_TEXT_PRIMARY,
            command=lambda _v: self.update_operation(),
        )
        self.operation.set("Baskı Montajı")
        self.operation.place(0, 0, align="w")

        self.lbl_op_hint = ctk.CTkLabel(
            nav_card, text="",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=NOTE_WRAP_W_WIDE,
        )
        self.lbl_op_hint.place(1, 0, expand_x=True)
        self.ctx.bind_wraplength(self.lbl_op_hint, nav_card, 24)

        # -- 1. Sayfaları düzenle ve böl -------------------------------------
        self.page_section = self.section(scroll, 1, "Sayfa sırası, döndürme ve bölme")
        self.grid = _ToolsPageGrid(self.page_section)
        self.grid.place(0, 0, expand_x=True, expand_y=True, valign="fill")
        self.grid.verticalScrollBar().valueChanged.connect(lambda _v: self._thumb_timer.start())
        self.grid.bind("<Configure>", lambda _e: self._thumb_timer.start(), add="+")
        self._thumb_timer = QTimer(self.page_section)
        self._thumb_timer.setSingleShot(True)
        self._thumb_timer.setInterval(50)
        self._thumb_timer.timeout.connect(self.thumbnails)
        self.grid.model().rowsMoved.connect(lambda *_args: self._thumb_timer.start())

        btn_row = WrapButtonRow(self.page_section, wrap=True, gap=SP_S)
        btn_row.place(1, 0, expand_x=True)
        btn_row.add_button("Tümünü seç", self.grid.selectAll, width=105)
        btn_row.add_button("Seçileni kaldır", self.remove, width=120)
        btn_row.add_button("Döndür ⟳", self.rotate, width=100)

        self.group_size = FieldRow(
            self.page_section, "Parça başına sayfa (0: tek dosya)", "0",
            integer=True, convert=False, suffix="sayfa", minimum=0, maximum=100000,
        )
        self.group_size.place(2, 0, align="w")
        ctk.CTkLabel(
            self.page_section,
            text="Sürükleyerek sayfaları sıralayın. Seçim yaparsanız yalnız seçili sayfalar, yapmazsanız tüm liste kaydedilir.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, wraplength=NOTE_WRAP_W, anchor="w", justify="left",
        ).place(3, 0, expand_x=True)

        # -- 2. Filigran ve Bates --------------------------------------------
        self.stamp_section = self.section(scroll, 2, "Filigran ve belge takip numarası (Bates)")
        self.watermark = self._entry(self.stamp_section, 0, "Filigran metni", "Örn: TASLAK, GİZLİ, KOPYA")
        self.watermark.bind("<KeyRelease>", lambda _e: self._notify_preview())
        self.opacity = FieldRow(self.stamp_section, "Saydamlık (%)", "18", minimum=0, maximum=100,
                                convert=False, suffix="%", label_width=190, on_change=self._notify_preview)
        self.opacity.place(1, 0, align="w")
        self.angle = FieldRow(self.stamp_section, "Açı (derece)", "45", minimum=-180, maximum=180,
                              allow_negative=True, convert=False, suffix="°", label_width=190,
                              on_change=self._notify_preview)
        self.angle.place(2, 0, align="w")
        self.stamp_size = FieldRow(self.stamp_section, "Filigran yazı boyutu", "40", minimum=4, maximum=200,
                                   convert=False, suffix="pt", label_width=190, on_change=self._notify_preview)
        self.stamp_size.place(3, 0, align="w")

        color_row = ctk.CTkFrame(self.stamp_section, fg_color="transparent")
        color_row.place(4, 0, expand_x=True)
        color_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(color_row, text="Filigran rengi", width=190, anchor="w").place(0, 0, align="w")
        self._stamp_color = (0.4, 0.4, 0.4)
        self.btn_stamp_color = ctk.CTkButton(
            color_row, text="Renk seç", width=100, height=26,
            fg_color="#666666", text_color="#FFFFFF", command=self._pick_stamp_color,
        )
        self.btn_stamp_color.place(0, 1, align="w")

        self.stamp_pages = self._entry(self.stamp_section, 5, "Sayfa aralığı (boş: tümü)", "Örn: 2-10, 15")
        self.stamp_pages.bind("<KeyRelease>", lambda _e: self._notify_preview())

        self.bates = ctk.CTkCheckBox(self.stamp_section, text="Belge takip numarası (Bates) ekle",
                                     command=self._notify_preview)
        self.bates.place(6, 0, align="w")
        self.prefix = self._entry(self.stamp_section, 7, "Numara ön eki", "Örn: BELGE-")
        self.prefix.bind("<KeyRelease>", lambda _e: self._notify_preview())
        self.suffix = self._entry(self.stamp_section, 8, "Numara son eki", "")
        self.suffix.bind("<KeyRelease>", lambda _e: self._notify_preview())
        self.bates_start = FieldRow(self.stamp_section, "Başlangıç numarası", "1", minimum=0, maximum=100000000,
                                    integer=True, convert=False, suffix="", label_width=190,
                                    on_change=self._notify_preview)
        self.bates_start.place(9, 0, align="w")
        self.bates_digits = FieldRow(self.stamp_section, "Basamak sayısı", "6", minimum=1, maximum=20,
                                     integer=True, convert=False, suffix="", label_width=190,
                                     on_change=self._notify_preview)
        self.bates_digits.place(10, 0, align="w")
        bpos_row = ctk.CTkFrame(self.stamp_section, fg_color="transparent")
        bpos_row.place(11, 0, expand_x=True)
        bpos_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(bpos_row, text="Numara konumu", width=190, anchor="w").place(0, 0, align="w")
        self.bates_pos = ctk.CTkOptionMenu(
            bpos_row, values=list(_BATES_POSITIONS.keys()), width=160,
            command=lambda _v: self._notify_preview(),
        )
        self.bates_pos.set("Sol alt")
        self.bates_pos.place(0, 1, align="w")

        # -- 3. Baskı montajı ------------------------------------------------
        self.print_section = self.section(scroll, 3, "Baskı montajı (Kitapçık & Çoklu Sayfa)")
        mode_row = ctk.CTkFrame(self.print_section, fg_color="transparent")
        mode_row.place(0, 0, align="w")
        self.print_mode = ctk.CTkOptionMenu(
            mode_row,
            values=["2 sayfa / yaprak", "4 sayfa / yaprak", "Kitapçık", "Yalnız kesim ve taşma payı"],
            width=215, command=lambda _v: self._notify_preview(),
        )
        self.print_mode.set("Kitapçık")
        self.print_mode.put("h", margins=(0, 0, SP_S, 0))
        self.paper_preset = ctk.CTkOptionMenu(
            mode_row, values=list(_PAPER_PRESETS.keys()), width=185,
            command=self._apply_paper_preset,
        )
        self.paper_preset.set("A4 Yatay (297×210)")
        self.paper_preset.put("h")

        self.paper_width = FieldRow(self.print_section, "Yaprak genişliği (mm)", "297", minimum=10, maximum=2000,
                                    convert=False, suffix="mm", label_width=240, on_change=self._notify_preview)
        self.paper_width.place(1, 0, align="w")
        self.paper_height = FieldRow(self.print_section, "Yaprak yüksekliği (mm)", "210", minimum=10, maximum=2000,
                                     convert=False, suffix="mm", label_width=240, on_change=self._notify_preview)
        self.paper_height.place(2, 0, align="w")
        self.print_margin = FieldRow(self.print_section, "Dış kenar payı (mm)", "5", minimum=0, maximum=500,
                                     convert=False, suffix="mm", label_width=240, on_change=self._notify_preview)
        self.print_margin.place(3, 0, align="w")
        self.print_gap = FieldRow(self.print_section, "Sayfalar arası boşluk (mm)", "2", minimum=0, maximum=100,
                                  convert=False, suffix="mm", label_width=240, on_change=self._notify_preview)
        self.print_gap.place(4, 0, align="w")
        self.bleed = FieldRow(self.print_section, "Taşma payı / kenar kesim (mm)", "0", minimum=0, maximum=100,
                              convert=False, suffix="mm", label_width=240, on_change=self._notify_preview)
        self.bleed.place(5, 0, align="w")
        self.creep = FieldRow(self.print_section, "İç sayfa kayma telafisi (mm)", "0", minimum=0, maximum=10,
                              convert=False, suffix="mm", label_width=240, on_change=self._notify_preview)
        self.creep.place(6, 0, align="w")

        sig_row = ctk.CTkFrame(self.print_section, fg_color="transparent")
        sig_row.place(7, 0, expand_x=True)
        sig_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(sig_row, text="Forma kalınlığı (kitapçık)", width=240, anchor="w").place(0, 0, align="w")
        self.signature_menu = ctk.CTkOptionMenu(
            sig_row, values=list(_SIGNATURE_OPTIONS.keys()), width=200,
            command=lambda _v: self._notify_preview(),
        )
        self.signature_menu.set("Tek forma (tüm belge)")
        self.signature_menu.place(0, 1, align="w")

        self.crop_marks = ctk.CTkCheckBox(self.print_section, text="Kesim işaretleri ekle (matbaa köşe çizgileri)",
                                          command=self._notify_preview)
        self.crop_marks.place(8, 0, align="w")
        self.divider_line = ctk.CTkCheckBox(self.print_section, text="Sayfalar arası kesim / katlama çizgisi",
                                            command=self._notify_preview)
        self.divider_line.place(9, 0, align="w")
        self.rtl_order = ctk.CTkCheckBox(self.print_section, text="Sağdan-sola (RTL) kitap dizilimi",
                                         command=self._notify_preview)
        self.rtl_order.place(10, 0, align="w")
        ctk.CTkLabel(
            self.print_section,
            text="Kitapçıkta ön/arka yüzler art arda üretilir; yazıcıda 'kısa kenardan çift taraflı' seçerek yazdırın.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, wraplength=NOTE_WRAP_W, anchor="w", justify="left",
        ).place(11, 0, expand_x=True)

        # -- 4. Güvenlik, Meta Veri ve Sıkıştırma ----------------------------
        self.security_section = self.section(scroll, 4, "Parola güvenliği, meta veri ve boyut küçültme")
        self.meta_title = self._entry(self.security_section, 0, "Başlık (boş: koru)", "")
        self.meta_author = self._entry(self.security_section, 1, "Yazar (boş: koru)", "")
        self.meta_subject = self._entry(self.security_section, 2, "Konu (boş: koru)", "")
        self.meta_keywords = self._entry(self.security_section, 3, "Anahtar kelimeler", "")
        self.clear_meta = ctk.CTkCheckBox(self.security_section, text="Mevcut tüm meta verileri (yazar/başlık vb.) temizle")
        self.clear_meta.place(4, 0, align="w")
        self.source_pw = self._entry(self.security_section, 5, "Kaynak PDF parolası (şifreliyse)", "Şifresizse boş bırakın")
        self.user_pw = self._entry(self.security_section, 6, "Açılış parolası (opsiyonel)", "Boşsa parola konmaz")
        self.owner_pw = self._entry(self.security_section, 7, "İzin parolası (opsiyonel)", "Kısıtlama için parola")
        perm_row = ctk.CTkFrame(self.security_section, fg_color="transparent")
        perm_row.place(8, 0, align="w")
        self.allow_print = ctk.CTkCheckBox(perm_row, text="Yazdırmaya izin ver")
        self.allow_print.select()
        self.allow_print.put("h", margins=(0, 0, SP_M, 0))
        self.allow_copy = ctk.CTkCheckBox(perm_row, text="Metin kopyalamaya izin ver")
        self.allow_copy.select()
        self.allow_copy.put("h")
        self.compress_images = ctk.CTkCheckBox(
            self.security_section,
            text="Görselleri yeniden örnekle (taranmış büyük PDF'leri küçültür)",
        )
        self.compress_images.place(9, 0, align="w")
        self.image_dpi = FieldRow(self.security_section, "Hedef görsel çözünürlüğü (DPI)", "150",
                                  minimum=36, maximum=600, integer=True, convert=False,
                                  suffix="DPI", label_width=240)
        self.image_dpi.place(10, 0, align="w")

        self.update_operation()
        app_path = getattr(self.ctx._app, "input_pdf_path", "")
        if app_path:
            self.load(app_path)

    def _entry(self, parent, row: int, label: str, placeholder: str):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.place(row, 0, expand_x=True)
        frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(frame, text=label, width=190, anchor="w").place(0, 0, align="w")
        entry = ctk.CTkEntry(frame, height=28, placeholder_text=placeholder)
        entry.place(0, 1, expand_x=True)
        return entry

    def _apply_paper_preset(self, label: str) -> None:
        size = _PAPER_PRESETS.get(label)
        if size is not None:
            self.paper_width.set_value(str(size[0]))
            self.paper_height.set_value(str(size[1]))
            self._notify_preview()

    def _pick_stamp_color(self) -> None:
        initial = QColor.fromRgbF(*self._stamp_color)
        chosen = QColorDialog.getColor(initial, self.btn_stamp_color, "Filigran rengi")
        if chosen.isValid():
            self._stamp_color = (chosen.redF(), chosen.greenF(), chosen.blueF())
            lum = 0.299 * chosen.redF() + 0.587 * chosen.greenF() + 0.114 * chosen.blueF()
            self.btn_stamp_color.configure(
                fg_color=chosen.name(),
                text_color="#111111" if lum > 0.55 else "#FFFFFF",
            )
            self._notify_preview()

    def _notify_preview(self) -> None:
        self.ctx.update_summary()
        self.ctx.schedule_preview()

    def update_operation(self) -> None:
        value = self.operation.get()
        hints = {
            "Sayfaları Düzenle": "Sayfaları sürükleyip sıralayın, döndürün, seçip ayıklayın veya parçalara bölün.",
            "Filigran & Bates": "Sayfalara şeffaf filigran metni veya ardışık belge takip numarası (Bates) basın.",
            "Baskı Montajı": "Tek PDF'i kitapçık, 2-up/4-up baskı yaprağına dizin; sağdaki canlı önizlemeden kontrol edin.",
            "Güvenlik & Meta": "PDF'e açılış/yazdırma parolası koyun, meta veriyi düzenleyin veya görselleri sıkıştırın.",
        }
        self.lbl_op_hint.configure(text=hints.get(value, ""))
        self.page_section._section_card.setVisible(value == "Sayfaları Düzenle")
        self.stamp_section._section_card.setVisible(value == "Filigran & Bates")
        self.print_section._section_card.setVisible(value == "Baskı Montajı")
        self.security_section._section_card.setVisible(value == "Güvenlik & Meta")
        self.ctx.update_summary()
        self.ctx.schedule_preview()

    def load(self, path: str) -> None:
        if not path:
            self.path = ""
            self._page_count = 0
            self.grid.clear()
            return
        try:
            with PDF_LOCK, open_pdf(path) as doc:
                count = len(doc)
        except Exception:
            return
        self._generation += 1
        self.path = path
        self._page_count = count
        self.grid.clear()
        for index in range(count):
            item = QListWidgetItem(f"{index + 1}. sayfa")
            item.setData(Qt.ItemDataRole.UserRole, (index, 0))
            self.grid.addItem(item)
        self._thumb_timer.start()

    def remove(self) -> None:
        for item in self.grid.selectedItems():
            self.grid.takeItem(self.grid.row(item))
        self._thumb_timer.start()

    def rotate(self) -> None:
        for item in self.grid.selectedItems():
            page, rotation = item.data(Qt.ItemDataRole.UserRole)
            rotation = (rotation + 90) % 360
            item.setData(Qt.ItemDataRole.UserRole, (page, rotation))
            item.setText(f"{page + 1}. sayfa · {rotation}°")
            item.setIcon(QIcon())
        self._thumb_timer.start()

    def thumbnails(self) -> None:
        if not self.path or not self.page_section._section_card.isVisible():
            return
        for index in range(self.grid.count()):
            item = self.grid.item(index)
            if not item.icon().isNull() or not self.grid.visualItemRect(item).intersects(self.grid.viewport().rect()):
                continue
            page, rotation = item.data(Qt.ItemDataRole.UserRole)
            key = (self._generation, page, rotation)
            if key in self._pending or len(self._pending) >= 12:
                continue
            self._pending.add(key)
            path = self.path

            def work(path=path, page=page, rotation=rotation):
                import pymupdf
                from ui.preview import PDF_RENDER_LOCK
                with PDF_RENDER_LOCK, open_pdf(path) as doc:
                    current = doc[page]
                    current.set_rotation((current.rotation + rotation) % 360)
                    zoom = min(92 / current.rect.width, 116 / current.rect.height)
                    return current.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False).tobytes("png")

            def completed(future, key=key):
                try:
                    data = future.result()
                except Exception:
                    data = None

                def apply():
                    self._pending.discard(key)
                    if key[0] != self._generation:
                        return
                    for row in range(self.grid.count()):
                        item = self.grid.item(row)
                        if tuple(item.data(Qt.ItemDataRole.UserRole)) == key[1:]:
                            pixmap = QPixmap()
                            if data:
                                pixmap.loadFromData(data)
                            else:
                                pixmap = QPixmap(92, 116)
                                pixmap.fill(Qt.GlobalColor.lightGray)
                            item.setIcon(QIcon(pixmap))
                    if QThread.currentThread() is self._thumb_timer.thread():
                        self._thumb_timer.start()
                self.ctx._app._ui(apply)
            self._pool.submit(work).add_done_callback(completed)

    def shutdown(self) -> None:
        """Arka plan küçük resim/işlem havuzunu ve zamanlayıcıyı güvenle kapatır."""
        self._cancel.set()
        self._generation += 1
        try:
            self._thumb_timer.stop()
        except Exception:
            pass
        self._pool.shutdown(wait=False, cancel_futures=True)

    def to_state(self) -> dict:
        """Parolalar hariç tüm araç ayarlarını kalıcı sözlük olarak döndürür."""
        def _val(row, default):
            try:
                return row.get_value()
            except Exception:
                return default

        return {
            "operation": self.operation.get(),
            "group_size": int(_val(self.group_size, 0)),
            "watermark": self.watermark.get(),
            "opacity": float(_val(self.opacity, 18.0)),
            "angle": int(_val(self.angle, 45)),
            "stamp_size": float(_val(self.stamp_size, 40.0)),
            "stamp_color": list(self._stamp_color),
            "stamp_pages": self.stamp_pages.get(),
            "bates_enabled": bool(self.bates.get()),
            "bates_prefix": self.prefix.get(),
            "bates_suffix": self.suffix.get(),
            "bates_start": int(_val(self.bates_start, 1)),
            "bates_digits": int(_val(self.bates_digits, 6)),
            "bates_pos": self.bates_pos.get(),
            "print_mode": self.print_mode.get(),
            "paper_preset": self.paper_preset.get(),
            "paper_width": float(_val(self.paper_width, 297.0)),
            "paper_height": float(_val(self.paper_height, 210.0)),
            "print_margin": float(_val(self.print_margin, 5.0)),
            "print_gap": float(_val(self.print_gap, 2.0)),
            "bleed": float(_val(self.bleed, 0.0)),
            "creep": float(_val(self.creep, 0.0)),
            "signature": self.signature_menu.get(),
            "crop_marks": bool(self.crop_marks.get()),
            "divider_line": bool(self.divider_line.get()),
            "rtl": bool(self.rtl_order.get()),
            "clear_meta": bool(self.clear_meta.get()),
            "allow_print": bool(self.allow_print.get()),
            "allow_copy": bool(self.allow_copy.get()),
            "compress_images": bool(self.compress_images.get()),
            "image_dpi": int(_val(self.image_dpi, 150)),
        }

    def apply_state(self, data: dict) -> None:
        """Kaydedilmiş araç ayarlarını bileşenlere uygular."""
        if not isinstance(data, dict) or not data:
            return
        op = data.get("operation")
        if op in ("Sayfaları Düzenle", "Filigran & Bates", "Baskı Montajı", "Güvenlik & Meta"):
            self.operation.set(op)
        if "group_size" in data:
            self.group_size.set_value(str(int(data["group_size"])))
        for entry, key in (
            (self.watermark, "watermark"),
            (self.stamp_pages, "stamp_pages"),
            (self.prefix, "bates_prefix"),
            (self.suffix, "bates_suffix"),
        ):
            if key in data and isinstance(data[key], str):
                entry.delete(0, "end")
                entry.insert(0, data[key])
        for row, key in (
            (self.opacity, "opacity"),
            (self.angle, "angle"),
            (self.stamp_size, "stamp_size"),
            (self.bates_start, "bates_start"),
            (self.bates_digits, "bates_digits"),
            (self.paper_width, "paper_width"),
            (self.paper_height, "paper_height"),
            (self.print_margin, "print_margin"),
            (self.print_gap, "print_gap"),
            (self.bleed, "bleed"),
            (self.creep, "creep"),
            (self.image_dpi, "image_dpi"),
        ):
            if key in data:
                row.set_value(f"{data[key]:g}" if isinstance(data[key], float) else str(data[key]))
        color = data.get("stamp_color")
        if isinstance(color, (list, tuple)) and len(color) == 3:
            try:
                r, g, b = (max(0.0, min(1.0, float(c))) for c in color)
                self._stamp_color = (r, g, b)
                qc = QColor.fromRgbF(r, g, b)
                lum = 0.299 * r + 0.587 * g + 0.114 * b
                self.btn_stamp_color.configure(
                    fg_color=qc.name(),
                    text_color="#111111" if lum > 0.55 else "#FFFFFF",
                )
            except (TypeError, ValueError):
                pass
        if data.get("bates_pos") in _BATES_POSITIONS:
            self.bates_pos.set(data["bates_pos"])
        if data.get("print_mode") in ("2 sayfa / yaprak", "4 sayfa / yaprak", "Kitapçık", "Yalnız kesim ve taşma payı"):
            self.print_mode.set(data["print_mode"])
        if data.get("paper_preset") in _PAPER_PRESETS:
            self.paper_preset.set(data["paper_preset"])
        if data.get("signature") in _SIGNATURE_OPTIONS:
            self.signature_menu.set(data["signature"])
        for chk, key, default in (
            (self.bates, "bates_enabled", False),
            (self.crop_marks, "crop_marks", False),
            (self.divider_line, "divider_line", False),
            (self.rtl_order, "rtl", False),
            (self.clear_meta, "clear_meta", False),
            (self.allow_print, "allow_print", True),
            (self.allow_copy, "allow_copy", True),
            (self.compress_images, "compress_images", False),
        ):
            if key in data:
                chk.select() if bool(data[key]) else chk.deselect()
            elif default:
                chk.select()
            else:
                chk.deselect()
        self.update_operation()

    def build_stamp_options(self) -> StampOptions:
        return StampOptions(
            watermark=self.watermark.get(),
            opacity=self.opacity.get_value() / 100,
            angle=int(self.angle.get_value()),
            font_size=self.stamp_size.get_value(),
            color=self._stamp_color,
            page_range=self.stamp_pages.get().strip(),
            bates_enabled=bool(self.bates.get()),
            bates_prefix=self.prefix.get(),
            bates_suffix=self.suffix.get(),
            bates_start=int(self.bates_start.get_value()),
            bates_digits=int(self.bates_digits.get_value()),
            bates_position=_BATES_POSITIONS.get(self.bates_pos.get(), "bottom_left"),
        )

    def build_print_options(self) -> PrintOptions:
        return PrintOptions(
            mode={"2 sayfa / yaprak": "2up", "4 sayfa / yaprak": "4up", "Kitapçık": "booklet",
                  "Yalnız kesim ve taşma payı": "marks"}[self.print_mode.get()],
            width_mm=self.paper_width.get_value(),
            height_mm=self.paper_height.get_value(),
            margin_mm=self.print_margin.get_value(),
            gap_mm=self.print_gap.get_value(),
            bleed_mm=self.bleed.get_value(),
            creep_mm=self.creep.get_value(),
            crop_marks=bool(self.crop_marks.get()),
            signature_size=_SIGNATURE_OPTIONS.get(self.signature_menu.get(), 0),
            divider_line=bool(self.divider_line.get()),
            rtl=bool(self.rtl_order.get()),
        )

    def preview_spec(self) -> Optional[tuple]:
        """Ana önizleme paneli için ``(kind, options, page_count, warning)`` döndürür."""
        if not self.built or not self.path:
            return None
        op = self.operation.get()
        if op == "Filigran & Bates":
            return ("stamp", self.build_stamp_options(), max(1, self._page_count), "")
        if op == "Baskı Montajı":
            opts = self.build_print_options()
            info = describe_impose_sheet(self._page_count, opts, 0)
            warn = ""
            if opts.mode == "booklet" and info["pad_blank"] > 0:
                warn = (f"Kitapçık tamamlama: {self._page_count} sayfa → "
                        f"{self._page_count + info['pad_blank']} sayfaya tamamlamak için "
                        f"{info['pad_blank']} boş sayfa eklenecek.")
            return ("impose", opts, max(1, info["total_sides"]), warn)
        return None

    def run_active_tool(self) -> None:
        app = self.ctx._app
        if app._busy or not self.path:
            return
        op = self.operation.get()
        try:
            if op == "Sayfaları Düzenle":
                selected = set(self.grid.row(item) for item in self.grid.selectedItems())
                pages = [tuple(self.grid.item(i).data(Qt.ItemDataRole.UserRole))
                         for i in range(self.grid.count()) if not selected or i in selected]
                if not pages:
                    raise FieldError("En az bir sayfa bırakın.")
                size = int(self.group_size.get_value())
                if size:
                    target = filedialog.askdirectory(title="Parçaların kaydedileceği klasör")
                    action = lambda: split_pages(self.path, target, pages, size, app._cancel_event.is_set)
                else:
                    target = self._output_path("sayfalar")
                    action = lambda: export_pages(self.path, target, pages, app._cancel_event.is_set)
            elif op == "Filigran & Bates":
                opts = self.build_stamp_options()
                if not opts.watermark and not opts.bates_enabled:
                    raise FieldError("Filigran metni yazın veya Bates numarasını açın.")
                target = self._output_path("damga")
                action = lambda: stamp_pdf(self.path, target, opts, app._cancel_event.is_set)
            elif op == "Baskı Montajı":
                opts = self.build_print_options()
                target = self._output_path("baski")
                action = lambda: impose_pdf(self.path, target, opts, app._cancel_event.is_set)
            else:
                opts = SecurityMetaOptions(
                    title=self.meta_title.get(),
                    author=self.meta_author.get(),
                    subject=self.meta_subject.get(),
                    keywords=self.meta_keywords.get(),
                    clear_metadata=bool(self.clear_meta.get()),
                    user_password=self.user_pw.get(),
                    owner_password=self.owner_pw.get(),
                    allow_print=bool(self.allow_print.get()),
                    allow_copy=bool(self.allow_copy.get()),
                    compress_images=bool(self.compress_images.get()),
                    image_dpi=int(self.image_dpi.get_value()),
                    source_password=self.source_pw.get(),
                )
                target = self._output_path("guvenli")
                action = lambda: apply_security_and_metadata(self.path, target, opts, app._cancel_event.is_set)
        except (FieldError, ValueError) as exc:
            messagebox.showerror("Ayarları düzeltin", str(exc))
            return
        if not target:
            return

        app._begin_work(f"{op} hazırlanıyor...")

        def worker():
            try:
                result = action()
                err = None
            except Exception as exc:
                result, err = None, str(exc)

            def finish():
                if getattr(app, "_closing", False):
                    return
                if err:
                    app._end_work(f"Hata: {err}", COLOR_ERROR)
                    messagebox.showerror("Baskı ve Araçlar", err)
                    return
                if isinstance(result, str):
                    app.output_pdf_path = result
                    app.btn_open_pdf.configure(state="normal")
                    app.btn_open_tools.configure(state="normal")
                    app.btn_open_folder.configure(state="normal")
                    app._end_work(f"Kaydedildi: {Path(result).name}", COLOR_OK)
                else:
                    app._end_work(f"Kaydedildi: {len(result)} parça", COLOR_OK)
                app.store.last_state = app._collect_state()
                app.store.save()
            app._ui(finish)

        self._pool.submit(worker)

    def _output_path(self, suffix: str) -> str:
        app = self.ctx._app
        origin = getattr(app, "_source_origin_path", "") or self.path
        initial_dir = getattr(app, "_source_origin_dir", "") or str(Path(origin).parent)
        default_file = unique_output_path(str(Path(initial_dir) / f"{Path(origin).stem}_{suffix}.pdf"))
        value = filedialog.asksaveasfilename(
            title="PDF'i kaydet",
            defaultextension=".pdf",
            initialdir=initial_dir,
            initialfile=Path(default_file).name,
            filetypes=[("PDF", "*.pdf")],
        )
        if not value:
            return ""
        if same_path(self.path, value) or same_path(origin, value):
            messagebox.showerror("Hata", "Çıktı dosyası kaynakla aynı olamaz.")
            return ""
        return value
