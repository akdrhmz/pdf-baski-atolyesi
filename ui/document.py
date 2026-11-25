"""Ana belgenin seçilmesi ve yüklenmesi."""

from __future__ import annotations

import os
import shutil
import tempfile
from typing import Optional

from PySide6.QtWidgets import QInputDialog, QLineEdit

from ui.i18n import tr
from ui.qt_compat import filedialog, messagebox

from core.gutter_engine import PdfPasswordError, get_pdf_info, open_pdf
from core.version import APP_NAME
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

    def _ask_pdf_password(self, path: str) -> Optional[str]:
        """Şifreli PDF için kullanıcıdan parola ister (ekran dışı testlerde bloklamaz)."""
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen" and not getattr(self, "_allow_password_prompt", False):
            return None
        pw, ok = QInputDialog.getText(
            self,
            tr("Parola korumalı PDF"),
            tr(f"'{os.path.basename(path)}' parola korumalı. Açmak için parolayı girin:"),
            QLineEdit.EchoMode.Password,
        )
        return pw if (ok and pw) else None

    def _unlock_pdf_to_temp(self, path: str, password: str) -> str:
        """Şifreli PDF'i doğrulayıp oturum süresince geçici şifresiz kopyaya açar."""
        import pymupdf
        with open_pdf(path, password=password) as doc:
            tmpdir = tempfile.mkdtemp(prefix="studio-unlocked-")
            dirs = getattr(self, "_unlocked_dirs", None)
            if dirs is None:
                dirs = self._unlocked_dirs = []
            dirs.append(tmpdir)
            unlocked_path = os.path.join(tmpdir, os.path.basename(path))
            doc.save(unlocked_path, encryption=pymupdf.PDF_ENCRYPT_NONE)
            return unlocked_path

    def _cleanup_unlocked_temps(self) -> None:
        """Oturumda açılmış geçici şifresiz PDF klasörlerini temizler."""
        dirs = getattr(self, "_unlocked_dirs", None) or []
        while dirs:
            shutil.rmtree(dirs.pop(), ignore_errors=True)

    def _load_file(self, path: str) -> None:
        path = (path or "").strip().strip('"')
        if not path or not os.path.exists(path):
            self.info_badge.configure(text=f"Dosya bulunamadı: {path or '(boş)'}",
                                      text_color=COLOR_ERROR)
            return
        origin_path = os.path.abspath(path)
        working_path = origin_path
        try:
            info = get_pdf_info(working_path, size_policy=self.store.page_size_policy)
        except PdfPasswordError as exc:
            pw = self._ask_pdf_password(origin_path)
            if not pw:
                self.log.warning("PDF okunamadı (parolalı): %s (%s)", origin_path, exc)
                self.info_badge.configure(text=f"PDF okunamadı: {exc}", text_color=COLOR_ERROR)
                self._set_status(f"PDF okunamadı: {exc}", COLOR_ERROR)
                return
            try:
                working_path = self._unlock_pdf_to_temp(origin_path, pw)
                info = get_pdf_info(working_path, size_policy=self.store.page_size_policy)
            except Exception as unlock_exc:
                messagebox.showerror(tr("Parola hatalı"), str(unlock_exc))
                self.info_badge.configure(text=f"PDF okunamadı: {unlock_exc}", text_color=COLOR_ERROR)
                self._set_status(f"PDF okunamadı: {unlock_exc}", COLOR_ERROR)
                return
        except Exception as exc:
            self.log.warning("PDF okunamadı: %s (%s)", origin_path, exc)
            self.info_badge.configure(text=f"PDF okunamadı: {exc}", text_color=COLOR_ERROR)
            self._set_status(f"PDF okunamadı: {exc}", COLOR_ERROR)
            return

        self._source_origin_path = origin_path
        self._source_origin_dir = os.path.dirname(origin_path)
        self.input_pdf_path = working_path
        self.output_pdf_path = ""
        self.btn_open_pdf.hide()
        self.btn_open_tools.hide()
        self.btn_open_folder.hide()
        self.orig_width_mm = info["width_mm"]
        self.orig_height_mm = info["height_mm"]
        self.orig_page_count = info["page_count"]
        self.orig_mixed_sizes = info.get("mixed_sizes", False)
        self.store.add_recent_file(origin_path)

        mixed = " • karışık ebatlı" if info.get("mixed_sizes") else ""
        self.info_badge.configure(
            text=(f"{os.path.basename(origin_path)}  •  {info['width_mm']:.1f} × {info['height_mm']:.1f} mm  •  "
                  f"{info['page_count']} sayfa{mixed}  •  {info['file_size_mb']} MB"),
            text_color=COLOR_TEXT_PRIMARY,
        )
        lt = self._layout_tab()
        self._apply_document_size(lt)
        self.title(f"{os.path.basename(origin_path)} — {APP_NAME}")
        self._set_status(f"'{os.path.basename(origin_path)}' yüklendi.", COLOR_TEXT_PRIMARY)
        tools_tab = getattr(self, "_tabs", {}).get("Baskı ve Araçlar")
        if tools_tab is not None and getattr(tools_tab, "built", False):
            tools_tab.load(working_path)
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
