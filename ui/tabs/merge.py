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

from ui import qt_compat as ctk
from ui.qt_compat import filedialog, messagebox

from gutter_engine import get_pdf_info, invalid_range_tokens, parse_page_ranges
from ui.tabs.base import BaseTab
from ui.tabs.merge_drag import MergeDragMixin
from ui.theme import *  # noqa: F401,F403
from ui.widgets import WrapButtonRow


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

        ops = WrapButtonRow(files, stretch=False, wrap=False, gap=SP_S)
        ops.place(1, 0, align="w")
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

        bot = self.section(container, 1, "Birleştirme seçenekleri")

        self.chk_merge_apply_pipeline = ctk.CTkCheckBox(
            bot, text="Birleştirdikten sonra diğer sekmelerdeki aktif ayarları uygula",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_SECONDARY, hover_color=COLOR_ACCENT_HOVER,
            fg_color=COLOR_ACCENT,
            command=lambda: (self.ctx.update_summary(), self.ctx.schedule_preview()),
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
            bot, text="Farklı ebatlı sayfaları eşitle (Sayfa Düzeni'ndeki ebada; kapalıysa en büyük sayfaya sığdır)",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_SECONDARY, hover_color=COLOR_ACCENT_HOVER,
            fg_color=COLOR_ACCENT, command=self.ctx.schedule_preview,
        )
        self.chk_merge_fit.setToolTip(
            "Acrobat'ta Yazdır > Adobe PDF > Sığdır ile yapılan işin karşılığı: içerik oranı "
            "bozulmadan ve kırpılmadan ortalanarak tek ebada getirilir.")
        self.chk_merge_fit.deselect()
        self.chk_merge_fit.place(2, 0, align="w")

        self.chk_merge_sequence = ctk.CTkCheckBox(
            bot, text="Önizlemede tüm birleşik diziyi gez (dosya sınırı işaretli)",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_SECONDARY, hover_color=COLOR_ACCENT_HOVER,
            fg_color=COLOR_ACCENT, command=self.ctx.schedule_preview,
        )
        self.chk_merge_sequence.setToolTip(
            "Önizleme yalnız seçili dosyayı değil, birleşik belgenin tüm sayfalarını art arda "
            "gösterir. İlk kullanımda birleşik bir geçici kopya hazırlanır; sonra sayfa "
            "çevirmek hızlıdır.")
        self.chk_merge_sequence.deselect()
        self.chk_merge_sequence.place(3, 0, align="w")

        self.chk_merge_handle_only = ctk.CTkCheckBox(
            bot, text="Satırları yalnız ⠿ tutamacından sürükle (yanlışlıkla taşımayı önler)",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_SECONDARY, hover_color=COLOR_ACCENT_HOVER,
            fg_color=COLOR_ACCENT,
        )
        self.chk_merge_handle_only.setToolTip(
            "Açıkken satırı sürüklemek için soldaki ⠿ simgesinden tutmak gerekir; satırın "
            "başka yerine tıklamak yalnızca seçer. Bu oturum için geçerlidir.")
        self.chk_merge_handle_only.deselect()
        self.chk_merge_handle_only.place(4, 0, align="w")

        self.refresh_list()
        self._building = False

    def append_file(self, path: str) -> None:
        if not path or not os.path.exists(path):
            return
        if any(os.path.normcase(item["path"]) == os.path.normcase(path) for item in self.files):
            return
        try:
            info = get_pdf_info(path, quick=True)
        except Exception as exc:
            messagebox.showwarning("Dosya eklenemedi", f"{os.path.basename(path)}\n\n{exc}")
            return
        self.files.append({
            "path": path,
            "name": os.path.basename(path),
            "pages": info["page_count"],
            "size_mb": info["file_size_mb"],
            "rotation": 0,
            "page_range": "",
        })
        self.ctx.store.add_recent_file(path)

    def add_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Birleştirilecek PDF dosyalarını seçin",
            filetypes=[("PDF belgeleri", "*.pdf")],
        )
        before = len(self.files)
        for path in paths or ():
            self.append_file(path)
        self.rows_added(before)

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

    def refresh_selection(self) -> None:
        chosen = set(self.selection())
        if self.files and hasattr(self, "merge_summary_badge") and (self.built or getattr(self, "_building", False)):
            self.update_summary()
        for idx, row in enumerate(self.rows):
            selected = idx in chosen
            row.configure(fg_color=COLOR_SOLID if selected else COLOR_CARD,
                          border_color=COLOR_SOLID if selected else COLOR_BORDER)
            # Yalnızca sıra numarası ve dosya adı seçim rengine uyar; döndürme
            # rozeti kendi kontrastını korur (seçiliyken okunmaz hâle gelmesin).
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

    @staticmethod
    def _rotation_text(item: Dict[str, Any]) -> str:
        rotation = int(item.get("rotation", 0))
        text = {0: "0° düz", 90: "90° sağa", 180: "180° ters", 270: "90° sola"}.get(
            rotation, f"{rotation}°")
        return f" {text} "

    def _rows_match_files(self) -> bool:
        return bool(self.files) and len(self.rows) == len(self.files)

    def refresh_list(self) -> None:
        if not self.built and not getattr(self, "_building", False):
            return  # kurulmamış sekmede widget yok; build sonunda yenilenir
        self._end_drag()  # satırlar yok edilirken yarım kalmış sürükleme olmasın
        for row in self.rows:
            row.destroy()
        self.rows.clear()

        if not self.files:
            self.merge_summary_badge.configure(text="Toplam: 0 dosya | 0 sayfa",
                                               text_color=COLOR_TEXT_SECONDARY)
            ctk.CTkLabel(
                self.merge_list_frame,
                text="Liste boş. Dosya ekleyin veya PDF'leri bu sekmeye sürükleyin.",
                font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
                text_color=COLOR_TEXT_SECONDARY,
            ).place(0, 0, align="c")
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
        row.grid_columnconfigure(2, weight=1)
        row._ensure_layout("grid").setContentsMargins(4, 5, 8, 5)  # açık satır iç boşluğu

        handle = ctk.CTkLabel(
            row, text="⠿", width=18,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_SECONDARY, cursor="fleur",
        )
        handle.place(0, 0, align="c")

        number = ctk.CTkLabel(
            row, text=f"{index + 1:>2}", width=26,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_SECONDARY,
        )
        number.place(0, 1, align="c")

        title = ctk.CTkLabel(
            row, text=f"{item['name']}  •  {item['pages']} sayfa  •  {item['size_mb']} MB",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
        )
        title.place(0, 2)

        ctk.CTkLabel(
            row, text="Sayfa:", width=40,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, anchor="e",
        ).place(0, 3, align="c")

        range_entry = ctk.CTkEntry(
            row, width=88, height=28, placeholder_text="Tümü",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            fg_color=COLOR_SUBCARD, border_color=COLOR_BORDER,
            text_color=COLOR_TEXT_PRIMARY,
        )
        range_entry.insert(0, item.get("page_range", ""))
        range_entry.place(0, 4, align="c")
        range_entry.bind(
            "<KeyRelease>",
            lambda event, current=item, entry=range_entry: self.on_range_changed(current, entry),
        )

        badge = ctk.CTkLabel(
            row, text=self._rotation_text(item),
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY, weight="bold"),
            fg_color=COLOR_WARN_BG, text_color=COLOR_WARN, corner_radius=4,
        )
        badge.place(0, 5, align="c")

        row._handle_label = handle  # type: ignore[attr-defined]
        row._number_label = number  # type: ignore[attr-defined]
        row._title_label = title  # type: ignore[attr-defined]
        row._badge_label = badge  # type: ignore[attr-defined]
        self.bind_row_drag(row, index)
        return row

    def sequence_enabled(self) -> bool:
        return self.built and self.chk_merge_sequence.get() == 1

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
            self.ctx.schedule_preview()

    def update_summary(self) -> None:
        """Üst rozet: toplamlar (+ birden çok satır seçiliyse seçili sayısı)."""
        total_pages = sum(self.item_count(item) for item in self.files)
        total_size = sum(item["size_mb"] for item in self.files)
        text = f"Toplam: {len(self.files)} dosya | {total_pages} sayfa | ~{total_size:.1f} MB"
        chosen = len(self.selection())
        if chosen > 1:
            text += f" | {chosen} seçili"
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
