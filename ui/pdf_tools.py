"""Ana çalışma alanını kalabalıklaştırmayan PDF araçları penceresi."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading

from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QAbstractItemView

from ui import qt_compat as ctk
from ui.qt_compat import filedialog, messagebox
from ui.widgets import FieldRow, FieldError
from ui.theme import *
from gutter_engine import open_pdf, unique_output_path, PDF_LOCK
from pdf_tools import export_pages, split_pages, stamp_pdf, impose_pdf, StampOptions, PrintOptions


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
        self._busy = False
        self._pending = set()
        self._cancel = threading.Event()
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pdf-tools")
        self.window = ctk.CTkToplevel(app)
        self.window.title("PDF araçları")
        self.window.geometry("850x800")
        self.window.minsize(580, 500)
        self.window.transient(app)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.grab_set()
        outer = ctk.CTkFrame(self.window, fg_color=COLOR_CARD)
        outer.put("v", fill="both", expand=True, margins=(12, 12, 12, 12))
        outer.grid_columnconfigure(0, weight=1)
        outer.grid_rowconfigure(1, weight=1)
        toolbar = ctk.CTkFrame(outer, fg_color="transparent")
        toolbar.place(0, 0, expand_x=True)
        ctk.CTkButton(toolbar, text="PDF seç…", width=110, command=self.choose).put("h")
        self.file_label = ctk.CTkLabel(toolbar, text="Belge seçin", anchor="w")
        self.file_label.put("h", fill="x", expand=True)
        self.scroll = ctk.CTkScrollableFrame(outer)
        self.scroll.place(1, 0, expand_x=True, expand_y=True, valign="fill")
        self.scroll.grid_columnconfigure(0, weight=1)
        self.scroll.set_padding(8, 8, 8, 8, spacing=10)
        self.operation = ctk.CTkOptionMenu(
            self.scroll, values=["Sayfaları düzenle ve böl", "Filigran ve Bates", "Baskı montajı"],
            width=270, command=lambda _v: self.update_operation())
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
        self.page_options = self.group(2, "Sayfalar")
        buttons = ctk.CTkFrame(self.page_options, fg_color="transparent")
        buttons.place(0, 0, align="w")
        for text, command in (("Tümünü seç", self.grid.selectAll), ("Seçileni kaldır", self.remove),
                              ("Döndür ⟳", self.rotate)):
            ctk.CTkButton(buttons, text=text, width=120, command=command).put("h")
        self.group_size = FieldRow(self.page_options, "Parça başına sayfa (0: tek dosya)", "0",
                                   integer=True, convert=False, suffix="sayfa", minimum=0, maximum=100000)
        self.group_size.place(1, 0, align="w")
        ctk.CTkLabel(self.page_options, text="Sürükleyerek sıralayın. Ctrl/Shift ile çoklu seçin. Seçim varsa yalnız seçilenler, yoksa tüm liste dışa aktarılır.",
                      wraplength=620, anchor="w", justify="left").place(2, 0, expand_x=True)
        self.stamp_options = self.group(3, "Filigran ve Bates")
        self.watermark = self.entry(self.stamp_options, 0, "Filigran metni")
        self.opacity = self.field(self.stamp_options, 1, "Saydamlık (%)", "18", 0, 100)
        self.angle = self.field(self.stamp_options, 2, "Açı (derece)", "45", -180, 180)
        self.stamp_size = self.field(self.stamp_options, 3, "Filigran puntosu", "40", 4, 200)
        self.bates = ctk.CTkCheckBox(self.stamp_options, text="Bates numarası ekle")
        self.bates.place(4, 0, align="w")
        self.prefix = self.entry(self.stamp_options, 5, "Bates ön eki")
        self.suffix = self.entry(self.stamp_options, 6, "Bates son eki")
        self.bates_start = self.field(self.stamp_options, 7, "İlk Bates numarası", "1", 0, 100000000)
        self.bates_digits = self.field(self.stamp_options, 8, "Bates basamak sayısı", "6", 1, 20)
        self.print_options = self.group(4, "Baskı montajı")
        self.print_mode = ctk.CTkOptionMenu(self.print_options, values=["2 sayfa / yaprak", "4 sayfa / yaprak", "Kitapçık", "Yalnız kesim ve taşma payı"])
        self.print_mode.place(0, 0, align="w")
        self.paper_width = self.field(self.print_options, 1, "Yaprak genişliği (mm)", "297", 10, 2000)
        self.paper_height = self.field(self.print_options, 2, "Yaprak yüksekliği (mm)", "210", 10, 2000)
        self.print_margin = self.field(self.print_options, 3, "Dış kenar payı (mm)", "5", 0, 500)
        self.print_gap = self.field(self.print_options, 4, "Sayfalar arası boşluk (mm)", "2", 0, 100)
        self.bleed = self.field(self.print_options, 5, "Taşma payı (mm)", "0", 0, 100)
        self.creep = self.field(self.print_options, 6, "Yaprak başına kayma telafisi (mm)", "0", 0, 10)
        self.crop_marks = ctk.CTkCheckBox(self.print_options, text="Kesim işaretleri ekle")
        self.crop_marks.place(7, 0, align="w")
        ctk.CTkLabel(self.print_options, text="Kitapçıkta ön/arka yüzler art arda üretilir; kısa kenardan çift taraflı yazdırın. Eksik sayfalar boş bırakılır. Taşma payı ek alan ve BleedBox oluşturur; mevcut tasarımın dışına görsel üretmez.",
                      wraplength=620, anchor="w", justify="left").place(8, 0, expand_x=True)
        actions = ctk.CTkFrame(outer, fg_color="transparent")
        actions.place(2, 0, expand_x=True)
        actions.grid_columnconfigure(0, weight=1)
        self.status = ctk.CTkLabel(actions, text="Kaynak PDF değiştirilmez.", anchor="w", wraplength=400)
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
        ctk.CTkLabel(frame, text=label, width=140, anchor="w").place(0, 0, align="w")
        entry = ctk.CTkEntry(frame, height=28)
        entry.place(0, 1, expand_x=True)
        return entry

    def field(self, parent, row, label, value, minimum, maximum):
        field = FieldRow(parent, label, value, minimum=minimum, maximum=maximum,
                          allow_negative=minimum < 0, convert=False, suffix="", label_width=280)
        field.place(row, 0, align="w")
        return field

    def update_operation(self):
        value = self.operation.get()
        self.page_options.setVisible(value == "Sayfaları düzenle ve böl")
        self.stamp_options.setVisible(value == "Filigran ve Bates")
        self.print_options.setVisible(value == "Baskı montajı")

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
        self.path = path
        self.grid.clear()
        self.file_label.configure(text=Path(path).name)
        for index in range(count):
            item = QListWidgetItem(f"{index + 1}. sayfa")
            item.setData(Qt.ItemDataRole.UserRole, (index, 0))
            self.grid.addItem(item)
        self._timer.start()

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
                options = StampOptions(
                    watermark=self.watermark.get(), opacity=self.opacity.get_value() / 100,
                    angle=int(self.angle.get_value()), font_size=self.stamp_size.get_value(),
                    bates_enabled=bool(self.bates.get()), bates_prefix=self.prefix.get(), bates_suffix=self.suffix.get(),
                    bates_start=int(self.bates_start.get_value()), bates_digits=int(self.bates_digits.get_value()))
                if not options.watermark and not options.bates_enabled:
                    raise FieldError("Filigran metni yazın veya Bates numarasını açın.")
                target = self.output_path("damga")
                action = lambda: stamp_pdf(self.path, target, options, self._cancel.is_set)
            else:
                options = PrintOptions(
                    mode={"2 sayfa / yaprak": "2up", "4 sayfa / yaprak": "4up", "Kitapçık": "booklet",
                          "Yalnız kesim ve taşma payı": "marks"}[self.print_mode.get()],
                    width_mm=self.paper_width.get_value(), height_mm=self.paper_height.get_value(),
                    margin_mm=self.print_margin.get_value(), gap_mm=self.print_gap.get_value(),
                    bleed_mm=self.bleed.get_value(), creep_mm=self.creep.get_value(), crop_marks=bool(self.crop_marks.get()))
                target = self.output_path("baski")
                action = lambda: impose_pdf(self.path, target, options, self._cancel.is_set)
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
        self._generation += 1
        self._pool.shutdown(wait=False, cancel_futures=True)
        self.window.destroy()
        return True
