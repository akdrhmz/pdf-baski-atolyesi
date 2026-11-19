"""Birleştirme sekmesi: dosya listesi, sıralama, döndürme, sayfa aralığı, sürükleyerek sıralama.

Sekme listeyi (``files``), seçimi (``selected_idx``) ve satır widget'larını (``rows``)
kendisi taşır. Kabuk işleri (durum çubuğu, önizleme, özet, son dosyalar) ``ctx``
üzerinden yapılır. Arka plandaki birleştirme işi (iş parçacığı, kırpma onayı, geçici
dosya) ``ui/merge_job.py`` içindedir; oraya sekmeden yalnızca ``worker_items`` ve
``expected_pages`` ile veri verilir.

Pencere yüzeyi (``app.merge_files``, ``app.merge_rows`` vb.) ``app.py``'deki açık özelliklerdir;
widget'lara sekme üzerinden erişilir (``app._merge_tab().chk_merge_bookmarks``). Eski
``EXPOSED`` / ``__getattr__`` köprüsü v2.6.20'de kaldırıldı.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional
from PySide6.QtCore import QTimer
from PySide6.QtGui import QPixmap
from concurrent.futures import ThreadPoolExecutor
from collections import OrderedDict
import threading

from ui import qt_compat as ctk
from ui.qt_compat import filedialog, messagebox

from core.gutter_engine import (get_pdf_info, invalid_range_tokens, parse_page_ranges,
                           PdfProcessConfig, config_from_dict, config_to_dict, validate_config)
from ui.tabs.base import BaseTab
from ui.tabs.merge_drag import MergeDragMixin
from ui.theme import *  # noqa: F401,F403
from ui.widgets import WrapButtonRow, FieldRow, FieldError
from ui.perf import record_ui


class MergeTab(MergeDragMixin, BaseTab):
    """PDF birleştirme listesi (sürükleme davranışı ``merge_drag.py``'de)."""

    def __init__(self, name: str, ctx: Any, frame: Any):
        super().__init__(name, ctx, frame)
        # Liste durumu kurulumdan önce de geçerlidir (sürükle-bırak, test, tembel kurulum).
        self.files: List[Dict[str, Any]] = []
        self._primary: Optional[int] = None   # ana seçim (önizleme bunu gösterir)
        self._extra: set = set()              # ek seçili dosyaların ``id(item)`` değerleri
        self._anchor: Optional[int] = None    # Shift+tık aralığının başlangıcı
        self.rows: List[ctk.CTkFrame] = []
        self._init_drag_state()
        self._thumb_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="merge-thumbnail")
        self._thumb_cache = OrderedDict()
        self._thumb_pending = set()
        self._visible_timer = None

    # -- Seçim modeli -----------------------------------------------------------
    @property
    def selected_idx(self) -> Optional[int]:
        """Ana seçili satır (tek seçimde tek seçili satır). Atama ek seçimi temizler."""
        return self._primary

    @selected_idx.setter
    def selected_idx(self, value: Optional[int]) -> None:
        self._primary = value
        self._extra = set()
        self._anchor = value

    def selection(self) -> List[int]:
        """Seçili tüm satırların sıralı, geçerli indeksleri."""
        chosen = {i for i, item in enumerate(self.files) if id(item) in self._extra}
        if self._primary is not None and 0 <= self._primary < len(self.files):
            chosen.add(self._primary)
        return sorted(chosen)

    def _set_selection(self, indices: List[int], primary: Optional[int]) -> None:
        indices = [i for i in indices if 0 <= i < len(self.files)]
        if primary is None or primary not in indices:
            primary = indices[-1] if indices else None
        self._primary = primary
        self._extra = {id(self.files[i]) for i in indices if i != primary}

    def select_all(self) -> None:
        """Ctrl+A: listedeki tüm dosyaları seçer (ana seçim korunur, yoksa ilk satır)."""
        if not self.files:
            return
        primary = self._primary if self._primary is not None and self._primary < len(self.files) else 0
        self._set_selection(list(range(len(self.files))), primary)
        self._anchor = primary
        self.refresh_selection()
        self.ctx.schedule_preview()

    def build(self) -> None:
        self._building = True
        container = ctk.CTkFrame(self.frame, fg_color="transparent")
        container.put("v", fill="both", expand=True, margins=(8, 6, 8, 6))
        container.set_padding(SP_S, SP_S, SP_S, SP_S, spacing=SP_M)
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(0, weight=1)

        files = self.section(container, 0, "Birleştirilecek dosyalar", expand=True)
        files.grid_rowconfigure(3, weight=1)
        self.merge_summary_badge = ctk.CTkLabel(
            files.header, text="Toplam: 0 dosya | 0 sayfa",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_SECONDARY, anchor="e",
        )
        self.merge_summary_badge.put("h")

        toolbar = ctk.CTkFrame(files, fg_color="transparent")
        toolbar.place(0, 0, align="w")
        
        btn_add = ctk.CTkButton(
            toolbar, text="+ Dosya ekle...", width=120, height=BTN_H,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            fg_color=COLOR_SOLID, text_color=COLOR_ON_ACCENT,
            hover_color=COLOR_SOLID_HOVER, corner_radius=6,
            command=self.add_files,
        )
        btn_add.put("h", margins=(0, 0, SP_S, 0))
        
        btn_clear = ctk.CTkButton(
            toolbar, text="Tümünü temizle", width=95, height=BTN_H,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            fg_color=COLOR_BTN_SUBTLE, text_color=COLOR_TEXT_PRIMARY,
            hover_color=COLOR_BTN_SUBTLE_HOVER, corner_radius=6,
            command=self.clear,
        )
        btn_clear.put("h")
        toolbar._ensure_layout("pack_h").addStretch(1)

        ops = WrapButtonRow(files, stretch=False, wrap=True, gap=SP_S)
        ops.place(1, 0, expand_x=True)
        ops.add_button("Döndür ⟲", self.rotate_selected_left, width=80)
        ops.add_button("Döndür ⟳", self.rotate_selected_right, width=80)
        ops.add_button("Yukarı taşı", self.move_up, width=85)
        ops.add_button("Aşağı taşı", self.move_down, width=85)
        ops.add_button("Seçilenleri kaldır", self.remove_selected, width=115)
        self._merge_ops_row = ops

        hint = ctk.CTkLabel(
            files, text="Satıra tıklayıp seçin; Ctrl+tık ekler/çıkarır, Shift+tık aralık seçer, "
                        "Ctrl+A tümünü seçer. Seçili satırları sürükleyerek sıralayın: bırakılacak yer "
                        "mavi çizgiyle gösterilir, listenin kenarına getirince liste kayar. "
                        "Kısayollar: Del (kaldır), Alt+↑/↓ (sırala).",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=560,
        )
        hint.place(2, 0)
        self.ctx.bind_wraplength(hint, files, 24)

        self.merge_list_frame = ctk.CTkScrollableFrame(
            files, fg_color=COLOR_SUBCARD, border_width=1,
            border_color=COLOR_BORDER, corner_radius=6,
        )
        self.merge_list_frame.place(3, 0, valign="fill")
        # Liste çerçevesinin üst/alt boşluğu (eskiden grid() sezgisinden örtük geliyordu).
        self.merge_list_frame._ensure_layout("grid").setContentsMargins(0, 10, 0, 10)
        self.merge_list_frame.grid_columnconfigure(0, weight=1)
        self._visible_timer = QTimer(self.merge_list_frame)
        self._visible_timer.setSingleShot(True)
        self._visible_timer.setInterval(25)
        self._visible_timer.timeout.connect(self._refresh_visible_rows)
        self.merge_list_frame.verticalScrollBar().valueChanged.connect(lambda _v: self._visible_timer.start())
        self.merge_list_frame.bind("<Configure>", lambda _e: self._visible_timer.start(), add="+")

        bot = self.section(container, 1, "Birleştirme seçenekleri")

        self.chk_merge_apply_pipeline = ctk.CTkCheckBox(
            bot, text="Birleştirdikten sonra diğer sekmelerdeki aktif ayarları uygula",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_SECONDARY, hover_color=COLOR_ACCENT_HOVER,
            fg_color=COLOR_ACCENT,
            command=self._merge_options_changed,
        )
        self.chk_merge_apply_pipeline.deselect()
        self.chk_merge_apply_pipeline.place(0, 0, align="w")

        self.chk_merge_bookmarks = ctk.CTkCheckBox(
            bot, text="Her dosya için dosya adından yer imi ekle",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_SECONDARY, hover_color=COLOR_ACCENT_HOVER,
            fg_color=COLOR_ACCENT,
        )
        self.chk_merge_bookmarks.select()
        self.chk_merge_bookmarks.place(1, 0, align="w")

        self.chk_merge_fit = ctk.CTkCheckBox(
            bot, text="Farklı ebatlı sayfaları eşitle",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_SECONDARY, hover_color=COLOR_ACCENT_HOVER,
            fg_color=COLOR_ACCENT, command=self._merge_options_changed,
        )
        self.chk_merge_fit.setToolTip(
            "Acrobat'ta Yazdır > Adobe PDF > Sığdır ile yapılan işin karşılığı: içerik oranı "
            "bozulmadan ve kırpılmadan ortalanarak tek ebada getirilir.")
        self.chk_merge_fit.deselect()
        self.chk_merge_fit.place(2, 0, align="w")

        self.fit_options = ctk.CTkFrame(bot, fg_color="transparent")
        self.fit_options.place(3, 0, expand_x=True)
        self.fit_options.grid_columnconfigure(0, weight=1)
        initial = self.merge_fit_config()
        self.merge_fit_menu = ctk.CTkOptionMenu(
            self.fit_options, values=[label for label, code in FIT_LABELS.items() if code != "off"],
            width=240, command=lambda _v: self._merge_options_changed())
        self.merge_fit_menu.set(FIT_CODES[initial.fit_mode])
        self.merge_fit_menu.place(0, 0, align="w")
        self.merge_fit_keep = ctk.CTkCheckBox(self.fit_options, text="Yatay sayfalar yatay kalsın",
                                            command=self._merge_options_changed)
        self.merge_fit_keep.select() if initial.fit_keep_orientation else self.merge_fit_keep.deselect()
        self.merge_fit_keep.place(1, 0, align="w")
        self.merge_fit_rotate = ctk.CTkCheckBox(self.fit_options, text="Yatay sayfaları dikeye döndür",
                                              command=self._merge_options_changed)
        self.merge_fit_rotate.select() if initial.fit_rotate_landscape else self.merge_fit_rotate.deselect()
        self.merge_fit_rotate.place(2, 0, align="w")
        self.merge_fit_custom = ctk.CTkFrame(self.fit_options, fg_color="transparent")
        self.merge_fit_custom.place(3, 0, align="w")
        self.f_merge_fit_width = FieldRow(self.merge_fit_custom, "Genişlik", str(initial.fit_width_mm),
                                         minimum=1, maximum=2000, on_change=self._merge_options_changed)
        self.f_merge_fit_width.put("h", margins=(0, 0, SP_S, 0))
        self.f_merge_fit_height = FieldRow(self.merge_fit_custom, "Yükseklik", str(initial.fit_height_mm),
                                          minimum=1, maximum=2000, on_change=self._merge_options_changed)
        self.f_merge_fit_height.put("h")
        self.f_merge_fit_margin = FieldRow(self.fit_options, "Çevreden boşluk", str(initial.fit_margin_mm),
                                          minimum=0, maximum=500, on_change=self._merge_options_changed)
        self.f_merge_fit_margin.place(4, 0, align="w")
        for field in (self.f_merge_fit_width, self.f_merge_fit_height, self.f_merge_fit_margin):
            field.change_unit("mm", self.ctx.unit)
        self._merge_options_changed()

        preferences = ctk.CTkButton(
            bot, text="Liste ve önizleme tercihleri…", width=205, height=28,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            fg_color=COLOR_BTN_SUBTLE, text_color=COLOR_TEXT_PRIMARY,
            hover_color=COLOR_BTN_SUBTLE_HOVER, command=self.ctx.open_settings,
        )
        preferences.place(4, 0, align="w")

        self.refresh_list()
        self._building = False

    FIELD_ROWS = ("f_merge_fit_width", "f_merge_fit_height", "f_merge_fit_margin")

    def merge_fit_config(self):
        config = config_from_dict(self.ctx.store.data.get("merge_fit", {}))
        if config.fit_mode == "off":
            config.fit_mode = "largest"
        return config

    def restore_fit_preferences(self):
        if not hasattr(self, "merge_fit_menu"):
            return
        config = self.merge_fit_config()
        self.merge_fit_menu.set(FIT_CODES[config.fit_mode])
        self.merge_fit_keep.select() if config.fit_keep_orientation else self.merge_fit_keep.deselect()
        self.merge_fit_rotate.select() if config.fit_rotate_landscape else self.merge_fit_rotate.deselect()
        self.f_merge_fit_width.set_mm(config.fit_width_mm)
        self.f_merge_fit_height.set_mm(config.fit_height_mm)
        self.f_merge_fit_margin.set_mm(config.fit_margin_mm)
        self._merge_options_changed()

    def _merge_options_changed(self):
        if not hasattr(self, "fit_options"):
            return
        active = self.chk_merge_fit.get() == 1 and self.chk_merge_apply_pipeline.get() != 1
        self.fit_options.setVisible(active)
        self.chk_merge_fit.setEnabled(self.chk_merge_apply_pipeline.get() != 1)
        keep = self.merge_fit_keep.get() == 1
        self.merge_fit_rotate.setEnabled(not keep)
        if keep:
            self.merge_fit_rotate.deselect()
        mode = FIT_LABELS[self.merge_fit_menu.get()]
        self.merge_fit_custom.setVisible(mode == "custom")
        self._fit_error = ""
        try:
            config = PdfProcessConfig(
                fit_mode=mode, fit_keep_orientation=keep,
                fit_rotate_landscape=self.merge_fit_rotate.get() == 1,
                fit_width_mm=self.f_merge_fit_width.get_mm() if mode == "custom" else self.f_merge_fit_width._canonical_mm,
                fit_height_mm=self.f_merge_fit_height.get_mm() if mode == "custom" else self.f_merge_fit_height._canonical_mm,
                fit_margin_mm=self.f_merge_fit_margin.get_mm())
            validation = validate_config(config)
            if not validation.ok:
                raise FieldError("; ".join(validation.errors))
        except FieldError as exc:
            self._fit_error = exc.message
            return
        self.ctx.store.data["merge_fit"] = config_to_dict(config)
        self.ctx.store.save()
        self.ctx.update_summary()
        self.ctx.schedule_preview()

    _IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")
    _TEMP_IMAGE_PDFS: list[str] = []

    @classmethod
    def _cleanup_image_pdfs(cls) -> None:
        for p in cls._TEMP_IMAGE_PDFS:
            try:
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass

    @classmethod
    def _image_to_temp_pdf(cls, image_path: str) -> str:
        import atexit
        import tempfile
        import pymupdf
        if not cls._TEMP_IMAGE_PDFS:
            atexit.register(cls._cleanup_image_pdfs)
        with pymupdf.open(image_path) as img:
            pdf_bytes = img.convert_to_pdf()
        fd, tmp = tempfile.mkstemp(prefix=".~img-", suffix=".pdf")
        os.close(fd)
        with open(tmp, "wb") as handle:
            handle.write(pdf_bytes)
        cls._TEMP_IMAGE_PDFS.append(tmp)
        return tmp

    def append_file(self, path: str) -> None:
        if not path or not os.path.exists(path):
            return
        display_name = os.path.basename(path)
        actual_path = path
        if path.lower().endswith(self._IMAGE_EXTS):
            try:
                actual_path = self._image_to_temp_pdf(path)
            except Exception as exc:
                messagebox.showwarning("Görsel dönüştürülemedi", f"{display_name}\n\n{exc}")
                return
        if any(os.path.normcase(item["path"]) == os.path.normcase(actual_path) for item in self.files):
            return
        try:
            info = get_pdf_info(actual_path, quick=True)
        except Exception as exc:
            messagebox.showwarning("Dosya eklenemedi", f"{display_name}\n\n{exc}")
            return
        self.files.append({
            "path": actual_path,
            "name": display_name,
            "pages": info["page_count"],
            "size_mb": info["file_size_mb"],
            "rotation": 0,
            "page_range": "",
        })
        self.ctx.store.add_recent_file(path)

    def add_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Birleştirilecek PDF veya görsel dosyalarını seçin",
            filetypes=[("PDF ve görseller", "*.pdf *.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff"),
                       ("PDF belgeleri", "*.pdf")],
        )
        before = len(self.files)
        for path in paths or ():
            self.append_file(path)
        self.rows_added(before)

    @record_ui("birles_liste_ekle")
    def rows_added(self, before: int) -> None:
        """``before`` kadar dosya varken eklenenler için yalnız yeni satırları kurar.

        Satırlar dosyalarla eşleşmiyorsa ya da liste boştan başlıyorsa tam yenileme yapılır.
        """
        added = len(self.files) - before
        if added <= 0:
            return
        if before == 0 or len(self.rows) != before or not self.built:
            self.refresh_list()
            return
        for index in range(before, len(self.files)):
            self.rows.append(self._build_row(index, self.files[index]))
        self.update_summary()
        self.ctx.schedule_preview()

    def rotate_selected(self, delta: int) -> None:
        if not self.files:
            return
        chosen = self.selection()
        if not chosen:
            self.ctx.set_status("Döndürmek için listeden bir dosya seçin.", COLOR_WARN)
            return
        for index in chosen:
            item = self.files[index]
            item["rotation"] = (int(item.get("rotation", 0)) + delta) % 360
        self._refresh_badges()

    def _refresh_badges(self) -> None:
        """Döndürme rozetlerini yeniler; satırlar yeniden kurulmaz (çok dosyada hızlı)."""
        if not self._rows_match_files():
            self.refresh_list()
            return
        for row, item in zip(self.rows, self.files):
            badge = getattr(row, "_badge_label", None)
            if badge is not None:
                badge.configure(text=self._rotation_text(item))
        self._refresh_visible_rows()
        self.ctx.schedule_preview()

    def rotate_all(self, delta: int) -> None:
        if not self.files:
            return
        for item in self.files:
            item["rotation"] = (int(item.get("rotation", 0)) + delta) % 360
        self._refresh_badges()

    def rotate_selected_left(self) -> None:
        self.rotate_selected(-90)

    def rotate_selected_right(self) -> None:
        self.rotate_selected(90)

    def _move_block(self, direction: int) -> bool:
        """Seçili satırları (blok) bir adım taşır; kenara dayanmışsa hiçbir şey yapmaz.

        Seçili olmayan komşu, bloğun öbür yanına geçer; seçilenlerin kendi sırası korunur.
        Dosya ve satır listeleri birlikte taşınır (sürükleme sırasında satırlar yok edilmez).
        """
        chosen = self.selection()
        if not chosen:
            return False
        if (direction < 0 and chosen[0] == 0) or (direction > 0 and chosen[-1] >= len(self.files) - 1):
            return False
        primary_item = self.files[self._primary] if self._primary is not None else None
        order = chosen if direction < 0 else list(reversed(chosen))
        for index in order:
            other = index + direction
            self.files[index], self.files[other] = self.files[other], self.files[index]
            if len(self.rows) == len(self.files):
                self.rows[index], self.rows[other] = self.rows[other], self.rows[index]
        new_selection = [i + direction for i in chosen]
        primary = next((i for i, item in enumerate(self.files) if item is primary_item), None)
        self._set_selection(new_selection, primary)
        return True

    def _after_move(self) -> None:
        if self._rows_match_files():
            self.reorder_rows()
            self.ctx.schedule_preview()
        else:
            self.refresh_list()

    def move_up(self) -> None:
        if self._move_block(-1):
            self._after_move()

    def move_down(self) -> None:
        if self._move_block(1):
            self._after_move()

    def remove_selected(self) -> None:
        chosen = self.selection()
        if not chosen:
            return
        doomed = set(chosen)
        matched = self._rows_match_files()
        self.files[:] = [item for i, item in enumerate(self.files) if i not in doomed]
        self.selected_idx = None
        if matched and self.files:
            # Hedefli silme: yalnız silinen satırlar yok edilir, kalanlar yeniden numaralanır.
            keep = []
            for i, row in enumerate(self.rows):
                if i in doomed:
                    row.destroy()
                else:
                    keep.append(row)
            self.rows[:] = keep
            self.update_summary()
            self.reorder_rows()
            self.ctx.schedule_preview()
        else:
            self.refresh_list()
        if len(chosen) > 1:
            self.ctx.set_status(f"{len(chosen)} dosya listeden kaldırıldı.", COLOR_TEXT_SECONDARY)

    @record_ui("birles_liste_temizle")
    def clear(self) -> None:
        self.files.clear()
        self.selected_idx = None
        self.refresh_list()

    def select_item(self, index: Optional[int], ctrl: bool = False, shift: bool = False) -> None:
        """Satır seçer. ``ctrl``: seçime ekle/çıkar · ``shift``: son seçilenden aralık."""
        if index is None or not (0 <= index < len(self.files)):
            self.selected_idx = None if index is None else index
        elif shift and self._anchor is not None and 0 <= self._anchor < len(self.files):
            low, high = sorted((self._anchor, index))
            anchor = self._anchor
            self._set_selection(list(range(low, high + 1)), index)
            self._anchor = anchor
        elif ctrl:
            chosen = self.selection()
            if index in chosen:
                chosen.remove(index)
                self._set_selection(chosen, None)
            else:
                chosen.append(index)
                self._set_selection(chosen, index)
            self._anchor = index
        else:
            self.selected_idx = index
        self.refresh_selection()
        self.ctx.schedule_preview()

    @record_ui("birles_secim")
    def refresh_selection(self) -> None:
        chosen = set(self.selection())
        if self.files and hasattr(self, "merge_summary_badge") and (self.built or getattr(self, "_building", False)):
            self.update_summary()
        for idx, row in enumerate(self.rows):
            if not getattr(row, "_loaded", True):
                continue
            selected = idx in chosen
            if getattr(row, "_selected", None) == selected:
                continue
            row._selected = selected
            row.configure(fg_color=COLOR_SOLID if selected else COLOR_CARD,
                          border_color=COLOR_SOLID if selected else COLOR_BORDER)
            # Seçimde satır metinleri beyaz olur; rozet kendi rengini korur.
            try:
                row._title_label.configure(
                    text_color=COLOR_ON_ACCENT if selected else COLOR_TEXT_PRIMARY)
            except Exception:
                pass
            try:
                row._number_label.configure(
                    text_color=COLOR_ON_ACCENT if selected else COLOR_TEXT_SECONDARY)
            except Exception:
                pass

            for label_name in ("_range_label", "_handle_label"):
                label = getattr(row, label_name, None)
                if label is not None:
                    label.configure(
                        text_color=COLOR_ON_ACCENT if selected else COLOR_TEXT_SECONDARY)

    @staticmethod
    def _rotation_text(item: Dict[str, Any]) -> str:
        rotation = int(item.get("rotation", 0))
        text = {0: "0° düz", 90: "90° sağa", 180: "180° ters", 270: "90° sola"}.get(
            rotation, f"{rotation}°")
        return f" {text} "

    def _rows_match_files(self) -> bool:
        return bool(self.files) and len(self.rows) == len(self.files)

    @record_ui("birles_liste_kur")
    def refresh_list(self) -> None:
        if not self.built and not getattr(self, "_building", False):
            return  # kurulmamış sekmede widget yok; build sonunda yenilenir
        self._end_drag()  # satırlar yok edilirken yarım kalmış sürükleme olmasın
        self._summary_text = None
        if getattr(self, "_empty_hint", None) is not None:
            self._empty_hint.destroy()
            self._empty_hint = None
        for row in self.rows:
            row.destroy()
        self.rows.clear()

        if not self.files:
            self.merge_summary_badge.configure(text="Toplam: 0 dosya | 0 sayfa",
                                               text_color=COLOR_TEXT_SECONDARY)
            self._empty_hint = ctk.CTkLabel(
                self.merge_list_frame,
                text="Liste boş. Dosya ekleyin veya PDF'leri bu sekmeye sürükleyin.",
                font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
                text_color=COLOR_TEXT_SECONDARY,
            )
            self._empty_hint.place(0, 0, align="c")
            return

        self.update_summary()

        for index, item in enumerate(self.files):
            self.rows.append(self._build_row(index, item))

        self.refresh_selection()
        self.ctx.schedule_preview()

    def _build_row(self, index: int, item: Dict[str, Any]) -> ctk.CTkFrame:
        """Tek liste satırını kurar (tam yenileme ve hedefli ekleme ortak kullanır)."""
        row = ctk.CTkFrame(self.merge_list_frame, fg_color=COLOR_CARD,
                           corner_radius=5, border_width=1, border_color=COLOR_BORDER)
        row.place(index, 0)
        row.setFixedHeight(82)
        row._loaded = False
        row._item = item
        if len(self.files) < 100:
            self._populate_row(row, index, item)
        if self._visible_timer is not None:
            self._visible_timer.start()
        return row

    def _populate_row(self, row, index, item):
        if row._loaded:
            return
        row._loaded = True
        row._selected = None
        row.grid_columnconfigure(3, weight=1)
        row._ensure_layout("grid").setContentsMargins(4, 5, 8, 5)  # açık satır iç boşluğu

        handle = ctk.CTkLabel(
            row, text="⠿", width=18,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_SECONDARY, cursor="fleur",
        )
        handle.place(0, 1, align="c")

        number = ctk.CTkLabel(
            row, text=f"{index + 1:>2}", width=26,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_SECONDARY,
        )
        number.place(0, 2, align="c")

        title = ctk.CTkLabel(
            row, text=f"{item['name']}  •  {item['pages']} sayfa  •  {item['size_mb']} MB",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
        )
        title.place(0, 3)

        range_label = ctk.CTkLabel(
            row, text="Sayfa:", width=40,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, anchor="e",
        )
        range_label.place(0, 4, align="c")

        range_entry = ctk.CTkEntry(
            row, width=88, height=28, placeholder_text="Tümü",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            fg_color=COLOR_SUBCARD, border_color=COLOR_BORDER,
            text_color=COLOR_TEXT_PRIMARY,
        )
        range_entry.insert(0, item.get("page_range", ""))
        range_entry.place(0, 5, align="c")
        range_entry.bind(
            "<KeyRelease>",
            lambda event, current=item, entry=range_entry: self.on_range_changed(current, entry),
        )

        badge = ctk.CTkLabel(
            row, text=self._rotation_text(item),
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY, weight="bold"),
            fg_color=COLOR_WARN_BG, text_color=COLOR_WARN, corner_radius=4,
        )
        badge.place(0, 6, align="c")

        row._range_label = range_label  # type: ignore[attr-defined]
        row._handle_label = handle  # type: ignore[attr-defined]
        row._number_label = number  # type: ignore[attr-defined]
        row._title_label = title  # type: ignore[attr-defined]
        row._badge_label = badge  # type: ignore[attr-defined]
        row._thumbnail = ctk.CTkLabel(row, text="…", width=56, height=72)
        row._thumbnail.place(0, 0, align="c")
        self.bind_row_drag(row, index)
        return row

    @record_ui("birles_gorunen_satirlar")
    def _refresh_visible_rows(self):
        if not hasattr(self, "merge_list_frame") or not self.rows:
            return
        viewport = self.merge_list_frame.viewport()
        from PySide6.QtCore import QPoint
        visible = viewport.rect().adjusted(0, -90, 0, 90)
        focus = ctk.ensure_qapp().focusWidget()
        for index, row in enumerate(self.rows):
            top = row.mapTo(viewport, QPoint(0, 0)).y()
            on_screen = top < visible.bottom() and top + row.height() > visible.top()
            if on_screen:
                self._populate_row(row, index, self.files[index])
                self._request_thumbnail(row, self.files[index])
            elif (len(self.files) >= 100 and row._loaded and not self._dragged
                  and not (focus is not None and (focus is row or row.isAncestorOf(focus)))):
                for child in row.winfo_children():
                    child.destroy()
                for attr in ("_range_label", "_handle_label", "_number_label", "_title_label", "_badge_label", "_thumbnail"):
                    setattr(row, attr, None)
                row._loaded = False
                row._thumb_key = None
        self.refresh_selection()

    def _request_thumbnail(self, row, item):
        if not getattr(row, "_loaded", False) or getattr(row, "_thumbnail", None) is None:
            return
        try:
            stamp = os.stat(item["path"])
        except OSError:
            return
        key = (item["path"], stamp.st_mtime_ns, stamp.st_size, int(item.get("rotation", 0)), item.get("page_range", ""))
        if getattr(row, "_thumb_key", None) == key:
            return
        row._thumb_key = key
        if key in self._thumb_cache:
            pixmap = QPixmap()
            pixmap.loadFromData(self._thumb_cache[key])
            row._thumbnail.configure(image=pixmap, text="")
            self._thumb_cache.move_to_end(key)
            return
        if key in self._thumb_pending:
            row._thumb_key = None
            return
        if len(self._thumb_pending) >= 16:
            row._thumb_key = None
            return
        self._thumb_pending.add(key)

        def render():
            from ui.preview import PDF_RENDER_LOCK
            from core.gutter_engine import open_pdf
            import pymupdf
            with PDF_RENDER_LOCK, open_pdf(key[0]) as doc:
                picked = sorted(p for p in parse_page_ranges(key[4]) if 1 <= p <= len(doc))
                page = doc[picked[0] - 1 if picked else 0]
                page.set_rotation((page.rotation + key[3]) % 360)
                rect = page.rect
                zoom = min(56 / rect.width, 72 / rect.height)
                return page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False).tobytes("png")

        def complete(future):
            try:
                data = future.result()
            except Exception:
                data = None

            def apply():
                self._thumb_pending.discard(key)
                if data:
                    self._thumb_cache[key] = data
                    while len(self._thumb_cache) > 64:
                        self._thumb_cache.popitem(last=False)
                if (row in self.rows and getattr(row, "_loaded", False)
                        and getattr(row, "_thumb_key", None) == key):
                    if data:
                        pixmap = QPixmap()
                        pixmap.loadFromData(data)
                        row._thumbnail.configure(image=pixmap, text="")
                    else:
                        row._thumbnail.configure(text="PDF")
                if self._visible_timer is not None:
                    self._visible_timer.start()

            self.ctx.run_on_ui(apply)

        self._thumb_pool.submit(render).add_done_callback(complete)

    def sequence_enabled(self) -> bool:
        return self.built and self.ctx.store.merge_preview_sequence

    def existing_items(self) -> List[Dict[str, Any]]:
        """Birleşik dizi gezintisi için diskte var olan dosyalar (liste sırasıyla)."""
        return [item for item in self.files if os.path.exists(str(item.get("path", "") or ""))]

    def item_count(self, item: Dict[str, Any]) -> int:
        total = int(item.get("pages", 0))
        text = str(item.get("page_range", "") or "").strip()
        if not text:
            return total
        selected = {page for page in parse_page_ranges(text) if 1 <= page <= total}
        return len(selected) if selected else total

    def on_range_changed(self, item: Dict[str, Any], entry: ctk.CTkEntry) -> None:
        item["page_range"] = entry.get().strip()
        invalid = bool(invalid_range_tokens(item["page_range"]))
        try:
            entry.configure(border_color=COLOR_ERROR if invalid else COLOR_BORDER)
        except Exception:
            pass
        self.update_summary()
        # Yazarken yarım aralık ("1-", "3,") önizlemeyi tüm belgeye döndürüp geri getirirdi
        # (yanıp sönme): yalnız geçerli aralıkta yenilenir, geçersizken son önizleme kalır.
        if not invalid:
            self._refresh_visible_rows()
            self.ctx.schedule_preview()

    def update_summary(self) -> None:
        """Üst rozet: toplamlar (+ birden çok satır seçiliyse seçili sayısı)."""
        key = tuple((id(item), item.get("page_range", ""), item["pages"], item["size_mb"]) for item in self.files)
        if getattr(self, "_summary_key", None) != key:
            self._summary_key = key
            self._summary_totals = (sum(self.item_count(item) for item in self.files),
                                    sum(item["size_mb"] for item in self.files))
        total_pages, total_size = self._summary_totals
        text = f"Toplam: {len(self.files)} dosya | {total_pages} sayfa | ~{total_size:.1f} MB"
        chosen = len(self.selection())
        if chosen > 1:
            text += f" | {chosen} seçili"
        if getattr(self, "_summary_text", None) != text:
            self._summary_text = text
            self.merge_summary_badge.configure(text=text, text_color=COLOR_TEXT_PRIMARY)

    def move_item(self, old_index: int, new_index: int) -> None:
        """Liste ve satır nesnelerini birlikte taşır; görsel sıra veriyle eşleşir."""
        if old_index == new_index or not (0 <= old_index < len(self.files)):
            return
        new_index = max(0, min(new_index, len(self.files) - 1))
        item = self.files.pop(old_index)
        self.files.insert(new_index, item)
        if 0 <= old_index < len(self.rows):
            row = self.rows.pop(old_index)
            self.rows.insert(new_index, row)
        self.drag_idx = new_index
        self.selected_idx = new_index
        self.reorder_rows()

    def reorder_rows(self) -> None:
        """Satırları yeniden oluşturmadan taşır: titremesiz sürükleme."""
        for idx, row in enumerate(self.rows):
            row.place(idx, 0)
            number = getattr(row, "_number_label", None)
            if number is not None:
                number.configure(text=f"{idx + 1:>2}")
        self.refresh_selection()
        if self._visible_timer is not None:
            self._visible_timer.start()

    # -- Arka plan işine verilen veri ------------------------------------------
    def invalid_range_lines(self) -> List[str]:
        """Sayfa aralığı anlaşılamayan dosyalar için "ad: belirteçler" satırları."""
        return [f"{os.path.basename(item['path'])}: {', '.join(invalid_range_tokens(item.get('page_range', ''))[:3])}"
                for item in self.files if invalid_range_tokens(item.get("page_range", ""))]

    def worker_items(self) -> List[Dict[str, Any]]:
        return [{
            "path": item["path"],
            "rotation": int(item.get("rotation", 0)),
            "pages": str(item.get("page_range", "") or ""),
        } for item in self.files]

    def expected_pages(self) -> int:
        return sum(self.item_count(item) for item in self.files
                   if os.path.exists(item.get("path", "")))
