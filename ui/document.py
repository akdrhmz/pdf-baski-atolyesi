"""Ana belgenin seçilmesi ve yüklenmesi."""

from __future__ import annotations

import os

from ui.qt_compat import filedialog

from gutter_engine import get_pdf_info
from version import APP_NAME
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

    def _load_file(self, path: str) -> None:
        path = (path or "").strip().strip('"')
        if not path or not os.path.exists(path):
            self.info_badge.configure(text=f"Dosya bulunamadı: {path or '(boş)'}",
                                      text_color=COLOR_ERROR)
            return
        try:
            info = get_pdf_info(path, size_policy=self.store.page_size_policy)
        except Exception as exc:
            self.log.warning("PDF okunamadı: %s (%s)", path, exc)
            self.info_badge.configure(text=f"PDF okunamadı: {exc}", text_color=COLOR_ERROR)
            self._set_status(f"PDF okunamadı: {exc}", COLOR_ERROR)
            return

        self.input_pdf_path = path
        self.output_pdf_path = ""
        self.btn_open_pdf.hide()
        self.btn_open_tools.hide()
        self.btn_open_folder.hide()
        self.orig_width_mm = info["width_mm"]
        self.orig_height_mm = info["height_mm"]
        self.orig_page_count = info["page_count"]
        self.orig_mixed_sizes = info.get("mixed_sizes", False)
        self.store.add_recent_file(path)

        mixed = " • karışık ebatlı" if info.get("mixed_sizes") else ""
        self.info_badge.configure(
            text=(f"{os.path.basename(path)}  •  {info['width_mm']:.1f} × {info['height_mm']:.1f} mm  •  "
                  f"{info['page_count']} sayfa{mixed}  •  {info['file_size_mb']} MB"),
            text_color=COLOR_TEXT_PRIMARY,
        )
        lt = self._layout_tab()
        self._apply_document_size(lt)
        self.title(f"{os.path.basename(path)} — {APP_NAME}")
        self._set_status(f"'{os.path.basename(path)}' yüklendi.", COLOR_TEXT_PRIMARY)
        self.preview_panel.reset_for_new_document()
        self._update_pipeline_summary()
        self._schedule_preview()

    def _apply_document_size(self, lt) -> None:
        """Hedef ebat alanlarını kaynak boyuta ve geçerli cilt payına göre tazeler."""
        if (self._module_switch("gutter").get() == 1
                and SIZE_MODE_LABELS.get(lt.seg_size_mode.get()) == "fixed"):
            try:
                extra_x = max(self._row_mm(lt.f_odd_x), self._row_mm(lt.f_even_x), 0.0)
                extra_y = max(self._row_mm(lt.f_odd_y), self._row_mm(lt.f_even_y), 0.0)
                lt.f_width.set_mm(self.orig_width_mm + extra_x)
                lt.f_height.set_mm(self.orig_height_mm + extra_y)
            except Exception:
                pass
        else:
            lt.f_width.set_mm(self.orig_width_mm)
            lt.f_height.set_mm(self.orig_height_mm)
        if getattr(lt, "built", False):
            lt.sync_size_source()

    def set_page_size_policy(self, policy: str) -> None:
        """Karışık ebatlı belgede hedef boyut seçimini değiştirir ve alanları tazeler."""
        if policy not in ("first", "dominant", "largest"):
            policy = "dominant"
        self.store.page_size_policy = policy
        self.store.save()
        path = self.input_pdf_path
        if not path or not os.path.exists(path):
            return
        info = get_pdf_info(path, size_policy=policy)
        self.orig_width_mm, self.orig_height_mm = info["width_mm"], info["height_mm"]
        self.orig_mixed_sizes = info.get("mixed_sizes", False)
        lt = self._layout_tab()
        if not getattr(lt, "built", False):
            return
        self._apply_document_size(lt)
        self._schedule_preview()
