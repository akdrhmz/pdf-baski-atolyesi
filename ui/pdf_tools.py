"""Ana çalışma alanını kalabalıklaştırmayan PDF araçları penceresi."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import QColorDialog, QLabel, QListWidget, QListWidgetItem, QAbstractItemView

from ui import qt_compat as ctk
from ui.preview_canvas import PreviewCanvas
from ui.qt_compat import filedialog, messagebox
from ui.widgets import FieldRow, FieldError
from ui.theme import *
from gutter_engine import open_pdf, unique_output_path, PDF_LOCK
from pdf_tools import (
    export_pages, split_pages, stamp_pdf, impose_pdf, apply_security_and_metadata,
    render_tool_preview, StampOptions, PrintOptions, SecurityMetaOptions,
)

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


class PageGrid(QListWidget, ctk.QtWidgetMixin):
    def __init__(self, master):
        super().__init__(master._content_host())
        self._init_mixin(master)
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setIconSize(QSize(96, 120))
        self.setGridSize(QSize(125, 155))
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setMovement(QListWidget.Movement.Snap)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setMinimumHeight(230)


class PdfToolsWindow:
    def __init__(self, app):
        self.app, self.path = app, ""
        self._generation = 0
        self._preview_gen = 0
        self._preview_page = 0
        self._page_count = 0
        self._busy = False
        self._pending = set()
        self._cancel = threading.Event()
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pdf-tools")
        self.window = ctk.CTkToplevel(app)
        self.window.title("PDF araçları")
        self.window.geometry("980x780")
        self.window.minsize(640, 520)
        self.window.transient(app)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.grab_set()
        self.window.set_drop_callback(self._on_drop_files)

        outer = ctk.CTkFrame(self.window, fg_color=COLOR_CARD)
        self.outer = outer
        outer.put("v", fill="both", expand=True, margins=(12, 12, 12, 12))
        outer.grid_columnconfigure(0, weight=3)
        outer.grid_columnconfigure(1, weight=2)
        outer.grid_rowconfigure(1, weight=1)

        toolbar = ctk.CTkFrame(outer, fg_color="transparent")
        toolbar.place(0, 0, columnspan=2, expand_x=True)
        ctk.CTkButton(toolbar, text="PDF seç…", width=110, command=self.choose).put("h")
        self.file_label = ctk.CTkLabel(toolbar, text="Belge seçin (veya sürükleyip bırakın)", anchor="w")
        self.file_label.put("h", fill="x", expand=True)

        self.scroll = ctk.CTkScrollableFrame(outer)
        self.scroll.place(1, 0, expand_x=True, expand_y=True, valign="fill")
        self.scroll.grid_columnconfigure(0, weight=1)
        self.scroll.grid_rowconfigure(6, weight=1)
        self.scroll.set_padding(8, 8, 8, 8, spacing=10)
        self.operation = ctk.CTkOptionMenu(
            self.scroll,
            values=["Sayfaları düzenle ve böl", "Filigran ve Bates", "Baskı montajı", "Güvenlik ve Meta Veri"],
            width=280, command=lambda _v: self.update_operation())
        self.operation.place(0, 0, align="w")

        self.grid = PageGrid(self.scroll)
        self.grid.place(1, 0, expand_x=True)
        self.grid.verticalScrollBar().valueChanged.connect(lambda _v: self._timer.start())
        self.grid.bind("<Configure>", lambda _e: self._timer.start(), add="+")
        self._timer = QTimer(self.window)
        self._timer.setSingleShot(True)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self.thumbnails)
        self.grid.model().rowsMoved.connect(lambda *_args: self._timer.start())

        self._preview_timer = QTimer(self.window)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(220)
        self._preview_timer.timeout.connect(self._render_live_preview)

        # -- 1. Sayfaları düzenle ve böl -------------------------------------
        self.page_options = self.group(2, "Sayfalar")
        buttons = ctk.CTkFrame(self.page_options, fg_color="transparent")
        buttons.place(0, 0, align="w")
        for text, command in (("Tümünü seç", self.grid.selectAll), ("Seçileni kaldır", self.remove),
                              ("Döndür ⟳", self.rotate)):
            ctk.CTkButton(buttons, text=text, width=120, command=command).put("h")
        self.group_size = FieldRow(self.page_options, "Parça başına sayfa (0: tek dosya)", "0",
                                   integer=True, convert=False, suffix="sayfa", minimum=0, maximum=100000)
        self.group_size.place(1, 0, align="w")
        ctk.CTkLabel(
            self.page_options,
            text="Sürükleyerek sıralayın. Ctrl/Shift ile çoklu seçin. Seçim varsa yalnız seçilenler, yoksa tüm liste dışa aktarılır.",
            wraplength=520, anchor="w", justify="left",
        ).place(2, 0, expand_x=True)

        # -- 2. Filigran ve Bates --------------------------------------------
        self.stamp_options = self.group(3, "Filigran ve Bates")
        self.watermark = self.entry(self.stamp_options, 0, "Filigran metni")
        self.watermark.bind("<KeyRelease>", lambda _e: self._schedule_tool_preview())
        self.opacity = self.field(self.stamp_options, 1, "Saydamlık (%)", "18", 0, 100,
                                  on_change=self._schedule_tool_preview)
        self.angle = self.field(self.stamp_options, 2, "Açı (derece)", "45", -180, 180,
                                on_change=self._schedule_tool_preview)
        self.stamp_size = self.field(self.stamp_options, 3, "Filigran puntosu", "40", 4, 200,
                                     on_change=self._schedule_tool_preview)
        color_row = ctk.CTkFrame(self.stamp_options, fg_color="transparent")
        color_row.place(4, 0, expand_x=True)
        color_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(color_row, text="Filigran rengi", width=140, anchor="w").place(0, 0, align="w")
        self._stamp_color = (0.4, 0.4, 0.4)
        self.btn_stamp_color = ctk.CTkButton(
            color_row, text="Renk seç", width=100, height=26,
            fg_color="#666666", text_color="#FFFFFF", command=self._pick_stamp_color,
        )
        self.btn_stamp_color.place(0, 1, align="w")
        self.stamp_pages = self.entry(self.stamp_options, 5, "Sayfa aralığı (boş: tümü)")
        self.stamp_pages.bind("<KeyRelease>", lambda _e: self._schedule_tool_preview())

        self.bates = ctk.CTkCheckBox(self.stamp_options, text="Bates numarası ekle",
                                     command=self._schedule_tool_preview)
        self.bates.place(6, 0, align="w")
        self.prefix = self.entry(self.stamp_options, 7, "Bates ön eki")
        self.prefix.bind("<KeyRelease>", lambda _e: self._schedule_tool_preview())
        self.suffix = self.entry(self.stamp_options, 8, "Bates son eki")
        self.suffix.bind("<KeyRelease>", lambda _e: self._schedule_tool_preview())
        self.bates_start = self.field(self.stamp_options, 9, "İlk Bates numarası", "1", 0, 100000000,
                                      on_change=self._schedule_tool_preview)
        self.bates_digits = self.field(self.stamp_options, 10, "Bates basamak sayısı", "6", 1, 20,
                                       on_change=self._schedule_tool_preview)
        bpos_row = ctk.CTkFrame(self.stamp_options, fg_color="transparent")
        bpos_row.place(11, 0, expand_x=True)
        bpos_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(bpos_row, text="Bates konumu", width=140, anchor="w").place(0, 0, align="w")
        self.bates_pos = ctk.CTkOptionMenu(
            bpos_row, values=list(_BATES_POSITIONS.keys()), width=160,
            command=lambda _v: self._schedule_tool_preview(),
        )
        self.bates_pos.set("Sol alt")
        self.bates_pos.place(0, 1, align="w")

        # -- 3. Baskı montajı ------------------------------------------------
        self.print_options = self.group(4, "Baskı montajı")
        mode_row = ctk.CTkFrame(self.print_options, fg_color="transparent")
        mode_row.place(0, 0, align="w")
        self.print_mode = ctk.CTkOptionMenu(
            mode_row,
            values=["2 sayfa / yaprak", "4 sayfa / yaprak", "Kitapçık", "Yalnız kesim ve taşma payı"],
            width=210, command=lambda _v: self._schedule_tool_preview(),
        )
        self.print_mode.put("h", margins=(0, 0, SP_S, 0))
        self.paper_preset = ctk.CTkOptionMenu(
            mode_row, values=list(_PAPER_PRESETS.keys()), width=180,
            command=self._apply_paper_preset,
        )
        self.paper_preset.set("A4 Yatay (297×210)")
        self.paper_preset.put("h")

        self.paper_width = self.field(self.print_options, 1, "Yaprak genişliği (mm)", "297", 10, 2000,
                                      on_change=self._schedule_tool_preview)
        self.paper_height = self.field(self.print_options, 2, "Yaprak yüksekliği (mm)", "210", 10, 2000,
                                       on_change=self._schedule_tool_preview)
        self.print_margin = self.field(self.print_options, 3, "Dış kenar payı (mm)", "5", 0, 500,
                                       on_change=self._schedule_tool_preview)
        self.print_gap = self.field(self.print_options, 4, "Sayfalar arası boşluk (mm)", "2", 0, 100,
                                    on_change=self._schedule_tool_preview)
        self.bleed = self.field(self.print_options, 5, "Taşma payı (mm)", "0", 0, 100,
                                on_change=self._schedule_tool_preview)
        self.creep = self.field(self.print_options, 6, "Yaprak başına kayma telafisi (mm)", "0", 0, 10,
                                on_change=self._schedule_tool_preview)

        sig_row = ctk.CTkFrame(self.print_options, fg_color="transparent")
        sig_row.place(7, 0, expand_x=True)
        sig_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(sig_row, text="Kitapçık forma boyutu", width=160, anchor="w").place(0, 0, align="w")
        self.signature_menu = ctk.CTkOptionMenu(
            sig_row, values=list(_SIGNATURE_OPTIONS.keys()), width=200,
            command=lambda _v: self._schedule_tool_preview(),
        )
        self.signature_menu.set("Tek forma (tüm belge)")
        self.signature_menu.place(0, 1, align="w")

        self.crop_marks = ctk.CTkCheckBox(self.print_options, text="Kesim işaretleri ekle",
                                          command=self._schedule_tool_preview)
        self.crop_marks.place(8, 0, align="w")
        self.divider_line = ctk.CTkCheckBox(self.print_options, text="Sayfalar arası kesim/katlama çizgisi",
                                            command=self._schedule_tool_preview)
        self.divider_line.place(9, 0, align="w")
        self.rtl_order = ctk.CTkCheckBox(self.print_options, text="Sağdan-sola (RTL) dizilim",
                                         command=self._schedule_tool_preview)
        self.rtl_order.place(10, 0, align="w")
        ctk.CTkLabel(
            self.print_options,
            text="Kitapçıkta ön/arka yüzler art arda üretilir; kısa kenardan çift taraflı yazdırın.",
            wraplength=520, anchor="w", justify="left",
        ).place(11, 0, expand_x=True)

        # -- 4. Güvenlik, Meta Veri ve Sıkıştırma ----------------------------
        self.security_options = self.group(5, "Güvenlik ve Meta Veri")
        self.meta_title = self.entry(self.security_options, 0, "Başlık (boş: koru)")
        self.meta_author = self.entry(self.security_options, 1, "Yazar (boş: koru)")
        self.meta_subject = self.entry(self.security_options, 2, "Konu (boş: koru)")
        self.meta_keywords = self.entry(self.security_options, 3, "Anahtar kelimeler")
        self.clear_meta = ctk.CTkCheckBox(self.security_options, text="Mevcut tüm meta verileri temizle")
        self.clear_meta.place(4, 0, align="w")
        self.user_pw = self.entry(self.security_options, 5, "Açılış parolası (opsiyonel)")
        self.owner_pw = self.entry(self.security_options, 6, "İzin parolası (opsiyonel)")
        perm_row = ctk.CTkFrame(self.security_options, fg_color="transparent")
        perm_row.place(7, 0, align="w")
        self.allow_print = ctk.CTkCheckBox(perm_row, text="Yazdırmaya izin ver")
        self.allow_print.select()
        self.allow_print.put("h", margins=(0, 0, SP_M, 0))
        self.allow_copy = ctk.CTkCheckBox(perm_row, text="Metin kopyalamaya izin ver")
        self.allow_copy.select()
        self.allow_copy.put("h")
        self.compress_images = ctk.CTkCheckBox(self.security_options, text="Görselleri yeniden örnekle (dosya küçült)")
        self.compress_images.place(8, 0, align="w")
        self.image_dpi = self.field(self.security_options, 9, "Hedef görsel DPI", "150", 36, 600)

        # -- Sağ Canlı Önizleme Paneli ---------------------------------------
        self.preview_card = ctk.CTkFrame(outer, fg_color=COLOR_SUBCARD)
        self.preview_card.place(1, 1, expand_x=True, expand_y=True, valign="fill")
        self.preview_card.grid_columnconfigure(0, weight=1)
        self.preview_card.grid_rowconfigure(1, weight=1)
        self.preview_card.set_padding(10, 10, 10, 10, spacing=8)

        pnav = ctk.CTkFrame(self.preview_card, fg_color="transparent")
        pnav.place(0, 0, expand_x=True)
        ctk.CTkLabel(pnav, text="Canlı önizleme", font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold")).put("h", fill="x", expand=True)
        ctk.CTkButton(
            pnav, text="Sığdır", width=56, height=24,
            fg_color=COLOR_BTN_SUBTLE, text_color=COLOR_TEXT_PRIMARY,
            border_width=1, border_color=COLOR_BORDER, hover_color=COLOR_BTN_SUBTLE_HOVER,
            command=self._reset_preview_zoom,
        ).put("h", margins=(0, 0, 6, 0))
        ctk.CTkButton(
            pnav, text="<", width=32, height=24,
            fg_color=COLOR_BTN_SUBTLE, text_color=COLOR_TEXT_PRIMARY,
            border_width=1, border_color=COLOR_BORDER, hover_color=COLOR_BTN_SUBTLE_HOVER,
            command=lambda: self._step_preview(-1),
        ).put("h", margins=(0, 0, 4, 0))
        self.preview_page_lbl = ctk.CTkLabel(pnav, text="1", width=42, anchor="center")
        self.preview_page_lbl.put("h", margins=(0, 0, 4, 0))
        ctk.CTkButton(
            pnav, text=">", width=32, height=24,
            fg_color=COLOR_BTN_SUBTLE, text_color=COLOR_TEXT_PRIMARY,
            border_width=1, border_color=COLOR_BORDER, hover_color=COLOR_BTN_SUBTLE_HOVER,
            command=lambda: self._step_preview(1),
        ).put("h")

        self.preview_image_lbl = PreviewCanvas(self.preview_card, bg=COLOR_CARD)
        self.preview_image_lbl.set_placeholder("single")
        self.preview_image_lbl.setToolTip("Ctrl+tekerlek ile yakınlaştırın, sürükleyerek kaydırın.")
        self.preview_image_lbl.place(1, 0, expand_x=True, expand_y=True, valign="fill")

        actions = ctk.CTkFrame(outer, fg_color="transparent")
        actions.place(2, 0, columnspan=2, expand_x=True)
        actions.grid_columnconfigure(0, weight=1)
        self.status = ctk.CTkLabel(actions, text="Kaynak PDF değiştirilmez.", anchor="w", wraplength=520)
        self.status.place(0, 0, expand_x=True)
        self.run_button = ctk.CTkButton(actions, text="Oluştur ve kaydet…", width=170, command=self.run)
        self.run_button.place(0, 1, align="e")
        self.cancel_button = ctk.CTkButton(actions, text="Kapat", width=90, command=self.close)
        self.cancel_button.place(0, 2, align="e")
        self.update_operation()
        if app.input_pdf_path:
            self.load(app.input_pdf_path)

    def group(self, row, title):
        group = ctk.CTkFrame(self.scroll, fg_color=COLOR_SUBCARD)
        group.place(row, 0, expand_x=True)
        group.grid_columnconfigure(0, weight=1)
        group.set_padding(10, 10, 10, 10, spacing=8)
        return group

    def entry(self, parent, row, label):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.place(row, 0, expand_x=True)
        frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(frame, text=label, width=165, anchor="w").place(0, 0, align="w")
        entry = ctk.CTkEntry(frame, height=28)
        entry.place(0, 1, expand_x=True)
        return entry

    def field(self, parent, row, label, value, minimum, maximum, on_change=None):
        field = FieldRow(parent, label, value, minimum=minimum, maximum=maximum,
                         allow_negative=minimum < 0, convert=False, suffix="", label_width=240,
                         on_change=on_change)
        field.place(row, 0, align="w")
        return field

    def _on_drop_files(self, paths) -> None:
        if self._busy:
            return
        pdfs = [p for p in paths if str(p).lower().endswith(".pdf")]
        if pdfs:
            self.load(pdfs[0])

    def _apply_paper_preset(self, label: str) -> None:
        size = _PAPER_PRESETS.get(label)
        if size is not None:
            self.paper_width.set_value(str(size[0]))
            self.paper_height.set_value(str(size[1]))
            self._schedule_tool_preview()

    def _pick_stamp_color(self) -> None:
        initial = QColor.fromRgbF(*self._stamp_color)
        chosen = QColorDialog.getColor(initial, self.window, "Filigran rengi")
        if chosen.isValid():
            self._stamp_color = (chosen.redF(), chosen.greenF(), chosen.blueF())
            lum = 0.299 * chosen.redF() + 0.587 * chosen.greenF() + 0.114 * chosen.blueF()
            self.btn_stamp_color.configure(
                fg_color=chosen.name(),
                text_color="#111111" if lum > 0.55 else "#FFFFFF",
            )
            self._schedule_tool_preview()

    def _reset_preview_zoom(self) -> None:
        if hasattr(self.preview_image_lbl, "set_zoom"):
            self.preview_image_lbl.set_zoom(1.0)

    def _step_preview(self, delta: int) -> None:
        self._preview_page = max(0, self._preview_page + delta)
        self.preview_page_lbl.configure(text=str(self._preview_page + 1))
        self._schedule_tool_preview()

    def _schedule_tool_preview(self) -> None:
        if not self.path or self._busy:
            return
        op = self.operation.get()
        if op in ("Filigran ve Bates", "Baskı montajı"):
            self._preview_timer.start()

    def _render_live_preview(self) -> None:
        if not self.path or self._busy or getattr(self.window, "_destroyed", False):
            return
        op = self.operation.get()
        if op not in ("Filigran ve Bates", "Baskı montajı"):
            return
        try:
            if op == "Filigran ve Bates":
                kind = "stamp"
                opts = self._build_stamp_options()
            else:
                kind = "impose"
                opts = self._build_print_options()
        except Exception as exc:
            self.preview_image_lbl.setText(str(exc))
            return
        self._preview_gen += 1
        gen = self._preview_gen
        page_idx = self._preview_page
        path = self.path

        def work():
            return render_tool_preview(path, kind, opts, page_index=page_idx, zoom=2.0)

        def done(future):
            try:
                data = future.result()
                err = None
            except Exception as exc:
                data, err = None, str(exc)

            def apply():
                if getattr(self.window, "_destroyed", False) or gen != self._preview_gen:
                    return
                if err or not data:
                    self.preview_image_lbl.set_source(None)
                    self.preview_image_lbl.configure(text=err or "Önizleme üretilemedi.")
                    return
                pix = QPixmap()
                if pix.loadFromData(data):
                    self.preview_image_lbl.set_source(pix)
            self.app._ui(apply)

        self._pool.submit(work).add_done_callback(done)

    def update_operation(self):
        value = self.operation.get()
        is_pages = value == "Sayfaları düzenle ve böl"
        show_preview = value in ("Filigran ve Bates", "Baskı montajı")
        self.grid.setVisible(is_pages)
        self.page_options.setVisible(is_pages)
        self.stamp_options.setVisible(value == "Filigran ve Bates")
        self.print_options.setVisible(value == "Baskı montajı")
        self.security_options.setVisible(value == "Güvenlik ve Meta Veri")
        self.preview_card.setVisible(show_preview)
        if show_preview:
            self.outer.grid_columnconfigure(1, weight=2)
            self.scroll.place(1, 0, columnspan=1, expand_x=True, expand_y=True, valign="fill")
            self.preview_card.place(1, 1, expand_x=True, expand_y=True, valign="fill")
        else:
            self.outer.grid_columnconfigure(1, weight=0)
            self.scroll.place(1, 0, columnspan=2, expand_x=True, expand_y=True, valign="fill")
        self.scroll.grid_rowconfigure(1, weight=1 if is_pages else 0)
        self.scroll.grid_rowconfigure(6, weight=0 if is_pages else 1)
        self.grid.place(1, 0, expand_x=True, expand_y=is_pages, valign="fill" if is_pages else "center")
        if show_preview:
            self._schedule_tool_preview()

    def choose(self):
        if self._busy:
            return
        path = filedialog.askopenfilename(title="PDF seç", filetypes=[("PDF", "*.pdf")])
        if path:
            self.load(path)

    def load(self, path):
        try:
            with PDF_LOCK, open_pdf(path) as doc:
                count = len(doc)
        except Exception as exc:
            messagebox.showerror("PDF açılamadı", str(exc))
            return
        self._generation += 1
        self._preview_page = 0
        self._page_count = count
        self.preview_page_lbl.configure(text="1")
        self.path = path
        self.grid.clear()
        self.file_label.configure(text=Path(path).name)
        for index in range(count):
            item = QListWidgetItem(f"{index + 1}. sayfa")
            item.setData(Qt.ItemDataRole.UserRole, (index, 0))
            self.grid.addItem(item)
        self._timer.start()
        self._schedule_tool_preview()

    def remove(self):
        if self._busy:
            return
        for item in self.grid.selectedItems():
            self.grid.takeItem(self.grid.row(item))
        self._timer.start()

    def rotate(self):
        if self._busy:
            return
        for item in self.grid.selectedItems():
            page, rotation = item.data(Qt.ItemDataRole.UserRole)
            rotation = (rotation + 90) % 360
            item.setData(Qt.ItemDataRole.UserRole, (page, rotation))
            item.setText(f"{page + 1}. sayfa · {rotation}°")
            item.setIcon(QIcon())
        self._timer.start()

    def thumbnails(self):
        if self._busy or not self.path or getattr(self.window, "_destroyed", False):
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
                    zoom = min(96 / current.rect.width, 120 / current.rect.height)
                    return current.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False).tobytes("png")

            def completed(future, key=key):
                try:
                    data = future.result()
                except Exception:
                    data = None

                def apply():
                    self._pending.discard(key)
                    if getattr(self.window, "_destroyed", False) or key[0] != self._generation:
                        return
                    for row in range(self.grid.count()):
                        item = self.grid.item(row)
                        if tuple(item.data(Qt.ItemDataRole.UserRole)) == key[1:]:
                            pixmap = QPixmap()
                            if data:
                                pixmap.loadFromData(data)
                            else:
                                pixmap = QPixmap(96, 120)
                                pixmap.fill(Qt.GlobalColor.lightGray)
                            item.setIcon(QIcon(pixmap))
                    self._timer.start()
                self.app._ui(apply)
            self._pool.submit(work).add_done_callback(completed)

    def _build_stamp_options(self) -> StampOptions:
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

    def _build_print_options(self) -> PrintOptions:
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

    def run(self):
        if self._busy or not self.path:
            return
        operation = self.operation.get()
        try:
            if operation == "Sayfaları düzenle ve böl":
                selected = set(self.grid.row(item) for item in self.grid.selectedItems())
                pages = [tuple(self.grid.item(i).data(Qt.ItemDataRole.UserRole)) for i in range(self.grid.count())
                         if not selected or i in selected]
                if not pages:
                    raise FieldError("En az bir sayfa bırakın.")
                size = int(self.group_size.get_value())
                if size:
                    target = filedialog.askdirectory(title="Parçaların kaydedileceği klasör")
                    action = lambda: split_pages(self.path, target, pages, size, self._cancel.is_set)
                else:
                    target = self.output_path("sayfalar")
                    action = lambda: export_pages(self.path, target, pages, self._cancel.is_set)
            elif operation == "Filigran ve Bates":
                options = self._build_stamp_options()
                if not options.watermark and not options.bates_enabled:
                    raise FieldError("Filigran metni yazın veya Bates numarasını açın.")
                target = self.output_path("damga")
                action = lambda: stamp_pdf(self.path, target, options, self._cancel.is_set)
            elif operation == "Baskı montajı":
                options = self._build_print_options()
                target = self.output_path("baski")
                action = lambda: impose_pdf(self.path, target, options, self._cancel.is_set)
            else:
                options = SecurityMetaOptions(
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
                )
                target = self.output_path("guvenli")
                action = lambda: apply_security_and_metadata(self.path, target, options, self._cancel.is_set)
        except (FieldError, ValueError) as exc:
            messagebox.showerror("Ayarları düzeltin", str(exc))
            return
        if not target:
            return
        self._busy = True
        self._cancel.clear()
        self.run_button.configure(state="disabled")
        self.grid.setEnabled(False)
        self.cancel_button.configure(text="İptal")
        self.status.configure(text="PDF hazırlanıyor…")

        def completed(future):
            try:
                result, error = future.result(), None
            except Exception as exc:
                result, error = None, str(exc)

            def apply():
                if getattr(self.window, "_destroyed", False):
                    return
                self._busy = False
                self.run_button.configure(state="normal")
                self.grid.setEnabled(True)
                self.cancel_button.configure(text="Kapat")
                self.status.configure(text=error or f"Kaydedildi: {len(result)} parça" if isinstance(result, list)
                                      else error or f"Kaydedildi: {Path(str(result)).name}")
                self._timer.start()
                if error:
                    messagebox.showerror("PDF araçları", error)
            self.app._ui(apply)
        self._pool.submit(action).add_done_callback(completed)

    def output_path(self, suffix):
        value = filedialog.asksaveasfilename(title="PDF'i kaydet", defaultextension=".pdf",
                    initialfile=f"{Path(self.path).stem}_{suffix}.pdf", filetypes=[("PDF", "*.pdf")])
        return unique_output_path(value) if value else ""

    def close(self):
        if self._busy:
            self._cancel.set()
            self.status.configure(text="İptal ediliyor…")
            return False
        self._timer.stop()
        self._preview_timer.stop()
        self._generation += 1
        self._preview_gen += 1
        self._pool.shutdown(wait=False, cancel_futures=True)
        self.window.destroy()
        return True
