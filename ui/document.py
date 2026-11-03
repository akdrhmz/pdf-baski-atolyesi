"""Ana belgenin seçilmesi ve yüklenmesi."""

from __future__ import annotations

import os

from ui.qt_compat import filedialog

from gutter_engine import get_pdf_info
from ui.theme import *  # noqa: F401,F403


class DocumentMixin:
    """Ana PDF'in seçilmesi, doğrulanması ve alanlara yansıtılması."""

    def _choose_file(self) -> None:
        path = filedialog.askopenfilename(
            title="İşlenecek PDF dosyasını seçin",
            filetypes=[("PDF belgeleri", "*.pdf")],
        )
        if path:
            self._load_file(path)

    def _load_from_entry(self) -> None:
        path = self.path_entry.get().strip().strip('"')
        if path:
            self._load_file(path)

    def _load_file(self, path: str) -> None:
        path = (path or "").strip().strip('"')
        if not path or not os.path.exists(path):
            self.info_badge.configure(text=f"Dosya bulunamadı: {path or '(boş)'}",
                                      text_color=COLOR_ERROR)
            return
        try:
            info = get_pdf_info(path)
        except Exception as exc:
            self.log.warning("PDF okunamadı: %s (%s)", path, exc)
            self.info_badge.configure(text=f"PDF okunamadı: {exc}", text_color=COLOR_ERROR)
            self._set_status(f"PDF okunamadı: {exc}", COLOR_ERROR)
            return

        self.input_pdf_path = path
        self.path_entry.delete(0, "end")
        self.path_entry.insert(0, path)
        self.orig_width_mm = info["width_mm"]
        self.orig_height_mm = info["height_mm"]
        self.orig_page_count = info["page_count"]
        self.store.add_recent_file(path)

        mixed = " • karışık ebatlı" if info.get("mixed_sizes") else ""
        self.info_badge.configure(
            text=(f"{os.path.basename(path)}  •  {info['width_mm']:.1f} × {info['height_mm']:.1f} mm  •  "
                  f"{info['page_count']} sayfa{mixed}  •  {info['file_size_mb']} MB"),
            text_color=COLOR_TEXT_PRIMARY,
        )
        if self.switch_gutter.get() == 1 and SIZE_MODE_LABELS.get(self.seg_size_mode.get()) == "fixed":
            # Yeni belgeye geçerken hedef ebat, kaynak + mevcut cilt payı olarak güncellenir.
            try:
                extra_x = max(self._row_mm(self.f_odd_x), self._row_mm(self.f_even_x), 0.0)
                extra_y = max(self._row_mm(self.f_odd_y), self._row_mm(self.f_even_y), 0.0)
                self.f_width.set_mm(self.orig_width_mm + extra_x)
                self.f_height.set_mm(self.orig_height_mm + extra_y)
            except Exception:
                pass
        else:
            self.f_width.set_mm(self.orig_width_mm)
            self.f_height.set_mm(self.orig_height_mm)
        self._set_status(f"'{os.path.basename(path)}' yüklendi.", COLOR_TEXT_PRIMARY)
        self.preview_panel.reset_for_new_document()
        self._update_pipeline_summary()
        self._schedule_preview()
