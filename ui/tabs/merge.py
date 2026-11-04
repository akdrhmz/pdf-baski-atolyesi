"""Birleştirme sekmesi: dosya listesi, sıralama, döndürme, sayfa aralığı, sürükleyerek sıralama.

Sekme listeyi (``files``), seçimi (``selected_idx``) ve satır widget'larını (``rows``)
kendisi taşır. Kabuk işleri (durum çubuğu, önizleme, özet, son dosyalar) ``ctx``
üzerinden yapılır. Arka plandaki birleştirme işi (iş parçacığı, kırpma onayı, geçici
dosya) ``ui/merge_job.py`` içindedir; oraya sekmeden yalnızca ``worker_items`` ve
``expected_pages`` ile veri verilir.

Ayar okuma/yazma (``config_binding``) ve testler eski adlarla (``app.merge_files``,
``app.chk_merge_bookmarks`` gibi) çalışmaya devam eder: kabuk ``EXPOSED`` içindeki
widget'ları ve liste durumunu geçiş süresince pencereye takma ad olarak bağlar
(2.9'da alanlar ``StringVar`` olunca kalkar).
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from ui import qt_compat as ctk
from ui.qt_compat import filedialog, messagebox

from gutter_engine import get_pdf_info, invalid_range_tokens, parse_page_ranges
from ui.tabs.base import BaseTab
from ui.theme import *  # noqa: F401,F403
from ui.widgets import WrapButtonRow


class MergeTab(BaseTab):
    """PDF birleştirme listesi."""

    #: Pencereye takma ad olarak bağlanan widget adları (geçiş köprüsü).
    EXPOSED = (
        "merge_list_frame", "merge_summary_badge", "chk_merge_apply_pipeline",
        "chk_merge_bookmarks",
    )

    def __init__(self, name: str, ctx: Any, frame: Any):
        super().__init__(name, ctx, frame)
        # Liste durumu kurulumdan önce de geçerlidir (sürükle-bırak, test, tembel kurulum).
        self.files: List[Dict[str, Any]] = []
        self.selected_idx: Optional[int] = None
        self.rows: List[ctk.CTkFrame] = []
        self.drag_idx: Optional[int] = None

    def build(self) -> None:
        self._building = True
        container = ctk.CTkFrame(self.frame, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=10, pady=8)
        container.set_padding(6, 4, 6, 6, spacing=8)
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(3, weight=1)

        top_row = ctk.CTkFrame(container, fg_color="transparent")
        top_row.grid(row=0, column=0, sticky="ew", pady=(2, 4))
        top_row.grid_columnconfigure(0, weight=1)
        top_row.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(
            top_row, text="+ Dosya ekle...", width=130, height=30,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            fg_color=COLOR_SOLID, text_color=COLOR_ON_ACCENT,
            hover_color=COLOR_SOLID_HOVER, corner_radius=6,
            command=self.add_files,
        ).grid(row=0, column=0, sticky="w")
        ctk.CTkButton(
            top_row, text="Tümünü temizle", width=110, height=30,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            fg_color=COLOR_BTN_SUBTLE, text_color=COLOR_TEXT_PRIMARY,
            hover_color=COLOR_BTN_SUBTLE_HOVER, corner_radius=6,
            command=self.clear,
        ).grid(row=0, column=1, sticky="e")

        ops = WrapButtonRow(container)
        ops.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        ops.add_button("Döndür ⟲", self.rotate_selected_left)
        ops.add_button("Döndür ⟳", self.rotate_selected_right)
        ops.add_button("Yukarı taşı", self.move_up)
        ops.add_button("Aşağı taşı", self.move_down)
        ops.add_button("Seçileni kaldır", self.remove_selected)
        self._merge_ops_row = ops

        hint = ctk.CTkLabel(
            container, text="Satıra tıklayıp seçin; satırları sürükleyerek sıralayın. "
                            "Kısayollar: Del (kaldır), Alt+↑/↓ (sırala).",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=560,
        )
        hint.grid(row=2, column=0, sticky="ew", pady=(0, 4))
        self.ctx.bind_wraplength(hint, container, 24)

        self.merge_list_frame = ctk.CTkScrollableFrame(
            container, fg_color=COLOR_SUBCARD, border_width=1,
            border_color=COLOR_BORDER, corner_radius=6,
        )
        self.merge_list_frame.grid(row=3, column=0, sticky="nsew", pady=(0, 6))
        self.merge_list_frame.grid_columnconfigure(0, weight=1)

        bot = self.section(container, 4, "Birleştirme seçenekleri")
        self.merge_summary_badge = ctk.CTkLabel(
            bot, text="Toplam: 0 dosya | 0 sayfa",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_SECONDARY, anchor="w",
        )
        self.merge_summary_badge.grid(row=0, column=0, sticky="w")

        self.chk_merge_apply_pipeline = ctk.CTkCheckBox(
            bot, text="Birleştirdikten sonra diğer sekmelerdeki aktif ayarları uygula",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_SECONDARY, hover_color=COLOR_ACCENT_HOVER,
            fg_color=COLOR_ACCENT, command=self.ctx.update_summary,
        )
        self.chk_merge_apply_pipeline.deselect()
        self.chk_merge_apply_pipeline.grid(row=1, column=0, sticky="w", pady=(3, 0))

        self.chk_merge_bookmarks = ctk.CTkCheckBox(
            bot, text="Her dosya için dosya adından yer imi ekle",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_SECONDARY, hover_color=COLOR_ACCENT_HOVER,
            fg_color=COLOR_ACCENT,
        )
        self.chk_merge_bookmarks.select()
        self.chk_merge_bookmarks.grid(row=2, column=0, sticky="w", pady=(3, 0))

        self.refresh_list()
        self._building = False

    def append_file(self, path: str) -> None:
        if not path or not os.path.exists(path):
            return
        if any(os.path.normcase(item["path"]) == os.path.normcase(path) for item in self.files):
            return
        try:
            info = get_pdf_info(path)
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
        for path in paths or ():
            self.append_file(path)
        self.refresh_list()

    def rotate_selected(self, delta: int) -> None:
        if not self.files:
            return
        index = self.selected_idx
        if index is None or not (0 <= index < len(self.files)):
            self.ctx.set_status("Döndürmek için listeden bir dosya seçin.", COLOR_WARN)
            return
        item = self.files[index]
        item["rotation"] = (int(item.get("rotation", 0)) + delta) % 360
        self.refresh_list()

    def rotate_all(self, delta: int) -> None:
        if not self.files:
            return
        for item in self.files:
            item["rotation"] = (int(item.get("rotation", 0)) + delta) % 360
        self.refresh_list()

    def rotate_selected_left(self) -> None:
        self.rotate_selected(-90)

    def rotate_selected_right(self) -> None:
        self.rotate_selected(90)

    def move_up(self) -> None:
        index = self.selected_idx
        if index is not None and index > 0:
            self.files[index - 1], self.files[index] = (
                self.files[index], self.files[index - 1])
            self.selected_idx = index - 1
            self.refresh_list()

    def move_down(self) -> None:
        index = self.selected_idx
        if index is not None and index < len(self.files) - 1:
            self.files[index + 1], self.files[index] = (
                self.files[index], self.files[index + 1])
            self.selected_idx = index + 1
            self.refresh_list()

    def remove_selected(self) -> None:
        index = self.selected_idx
        if index is not None and 0 <= index < len(self.files):
            self.files.pop(index)
            self.selected_idx = None
            self.refresh_list()

    def clear(self) -> None:
        self.files.clear()
        self.selected_idx = None
        self.refresh_list()

    def select_item(self, index: int) -> None:
        self.selected_idx = index
        self.refresh_selection()
        self.ctx.schedule_preview()

    def refresh_selection(self) -> None:
        for idx, row in enumerate(self.rows):
            selected = idx == self.selected_idx
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

    def refresh_list(self) -> None:
        if not self.built and not getattr(self, "_building", False):
            return  # kurulmamış sekmede widget yok; build sonunda yenilenir
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
            ).grid(row=0, column=0, pady=18)
            return

        total_pages = sum(self.item_count(item) for item in self.files)
        total_size = sum(item["size_mb"] for item in self.files)
        self.merge_summary_badge.configure(
            text=f"Toplam: {len(self.files)} dosya | {total_pages} sayfa | ~{total_size:.1f} MB",
            text_color=COLOR_TEXT_PRIMARY,
        )

        for index, item in enumerate(self.files):
            row = ctk.CTkFrame(self.merge_list_frame, fg_color=COLOR_CARD,
                               corner_radius=5, border_width=1, border_color=COLOR_BORDER)
            row.grid(row=index, column=0, sticky="ew", padx=4, pady=2)
            row.grid_columnconfigure(2, weight=1)

            handle = ctk.CTkLabel(
                row, text="⠿", width=18,
                font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
                text_color=COLOR_TEXT_SECONDARY, cursor="fleur",
            )
            handle.grid(row=0, column=0, padx=(6, 0), pady=5)

            number = ctk.CTkLabel(
                row, text=f"{index + 1:>2}", width=26,
                font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
                text_color=COLOR_TEXT_SECONDARY,
            )
            number.grid(row=0, column=1, padx=(2, 2), pady=5)

            title = ctk.CTkLabel(
                row, text=f"{item['name']}  •  {item['pages']} sayfa  •  {item['size_mb']} MB",
                font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
                text_color=COLOR_TEXT_PRIMARY, anchor="w",
            )
            title.grid(row=0, column=2, sticky="ew", padx=4, pady=5)

            ctk.CTkLabel(
                row, text="Sayfa:", width=40,
                font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
                text_color=COLOR_TEXT_SECONDARY, anchor="e",
            ).grid(row=0, column=3, padx=(4, 2), pady=5)

            range_entry = ctk.CTkEntry(
                row, width=88, height=28, placeholder_text="Tümü",
                font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
                fg_color=COLOR_SUBCARD, border_color=COLOR_BORDER,
                text_color=COLOR_TEXT_PRIMARY,
            )
            range_entry.insert(0, item.get("page_range", ""))
            range_entry.grid(row=0, column=4, padx=4, pady=5)
            range_entry.bind(
                "<KeyRelease>",
                lambda event, current=item, entry=range_entry: self.on_range_changed(current, entry),
            )

            rotation = int(item.get("rotation", 0))
            rotation_text = {0: "0° düz", 90: "90° sağa", 180: "180° ters", 270: "90° sola"}.get(
                rotation, f"{rotation}°")
            badge = ctk.CTkLabel(
                row, text=f" {rotation_text} ",
                font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY, weight="bold"),
                fg_color=COLOR_WARN_BG, text_color=COLOR_WARN, corner_radius=4,
            )
            badge.grid(row=0, column=5, padx=(4, 8), pady=5)

            row._number_label = number  # type: ignore[attr-defined]
            row._title_label = title  # type: ignore[attr-defined]
            self.bind_row_drag(row, index)
            self.rows.append(row)

        self.refresh_selection()
        self.ctx.schedule_preview()

    def item_count(self, item: Dict[str, Any]) -> int:
        total = int(item.get("pages", 0))
        text = str(item.get("page_range", "") or "").strip()
        if not text:
            return total
        selected = {page for page in parse_page_ranges(text) if 1 <= page <= total}
        return len(selected) if selected else total

    def on_range_changed(self, item: Dict[str, Any], entry: ctk.CTkEntry) -> None:
        item["page_range"] = entry.get().strip()
        try:
            entry.configure(border_color=COLOR_ERROR if invalid_range_tokens(item["page_range"])
                            else COLOR_BORDER)
        except Exception:
            pass
        total_pages = sum(self.item_count(current) for current in self.files)
        total_size = sum(current["size_mb"] for current in self.files)
        self.merge_summary_badge.configure(
            text=f"Toplam: {len(self.files)} dosya | {total_pages} sayfa | ~{total_size:.1f} MB",
            text_color=COLOR_TEXT_PRIMARY,
        )

    def bind_row_drag(self, row: ctk.CTkFrame, index: int) -> None:
        widgets = [row] + [child for child in row.winfo_children()
                           if not isinstance(child, ctk.CTkEntry)]

        def on_press(_event, idx=index):
            self.drag_idx = idx
            self.select_item(idx)

        def on_motion(event):
            if self.drag_idx is None:
                return
            target = self.index_at(event.y_root)
            if target is not None and target != self.drag_idx:
                self.move_item(self.drag_idx, target)

        def on_release(_event):
            self.drag_idx = None

        for widget in widgets:
            widget.bind("<Button-1>", on_press, add="+")
            widget.bind("<B1-Motion>", on_motion, add="+")
            widget.bind("<ButtonRelease-1>", on_release, add="+")

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

    def index_at(self, y_root: int) -> Optional[int]:
        for idx, row in enumerate(self.rows):
            top = row.winfo_rooty()
            if top <= y_root <= top + row.winfo_height():
                return idx
        return None

    def reorder_rows(self) -> None:
        """Satırları yeniden oluşturmadan taşır: titremesiz sürükleme."""
        for idx, row in enumerate(self.rows):
            row.grid_configure(row=idx)
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
