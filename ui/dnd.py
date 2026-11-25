"""Sürükle-bırak ile dosya açma."""

from __future__ import annotations

import os

from ui.qt_compat import messagebox

from ui.theme import *  # noqa: F401,F403


class DropMixin:
    """Sürükle-bırak ile dosya açma."""

    def _init_drag_and_drop(self) -> None:
        try:
            self.set_drop_callback(self._on_drop_files)
        except Exception:
            self.log.exception("Sürükle-bırak kancası kurulamadı")

    def _on_drop_files(self, files) -> None:
        """windnd bu geri çağrıyı pencere yordamı içinden çalıştırır.

        Burada Tk'ye hiç dokunulmaz: pencere yordamı içinden Tcl çağırmak
        (``after`` dahil) yeniden girişe ve uygulamanın sessizce kapanmasına yol
        açabiliyor. İş, ana döngüde çalıştırılmak üzere kuyruğa bırakılır.
        """
        try:
            paths = list(files)
        except Exception:
            self.log.exception("Sürükle-bırak verisi okunamadı")
            return
        try:
            self._ui_queue.put(lambda: self._handle_dropped_files(paths))
        except Exception:
            self.log.exception("Sürükle-bırak kuyruğa alınamadı")

    @staticmethod
    def _decode_dropped(item) -> str:
        """Bırakılan yolu metne çevirir; ANSI (mbcs) ve UTF-8 baytlarını destekler."""
        if isinstance(item, str):
            return item
        if isinstance(item, bytes):
            for encoding in ("utf-8", "mbcs"):
                try:
                    return item.decode(encoding)
                except (UnicodeDecodeError, LookupError):
                    continue
            return item.decode("latin-1", "replace")
        return str(item)

    def _handle_dropped_files(self, files) -> None:
        """Bırakılan dosyaları sekmeye göre açar veya birleştirme listesine ekler."""
        try:
            paths = [self._decode_dropped(item).strip().strip('"') for item in files]
            paths = [p for p in paths if p]
            in_merge = "Birleştirme" in self.tabview.get()
            img_exts = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")
            if in_merge:
                pdfs = [p for p in paths
                        if (p.lower().endswith(".pdf") or p.lower().endswith(img_exts)) and os.path.isfile(p)]
            else:
                pdfs = [p for p in paths
                        if p.lower().endswith(".pdf") and os.path.isfile(p)]
            if not pdfs:
                messagebox.showinfo(
                    "Sürükle-bırak",
                    "Bırakılan öğeler arasında PDF dosyası yok.\n"
                    "Klasör yerine doğrudan PDF dosyalarını bırakın.",
                )
                return

            if in_merge:
                before = len(self.merge_files)
                for path in pdfs:
                    self._append_merge_file(path)
                self._tabs["Birleştirme"].rows_added(before)
                added = len(self.merge_files) - before
                skipped = len(pdfs) - added
                text = f"{added} PDF birleştirme listesine eklendi."
                if skipped:
                    text += f" {skipped} dosya listede zaten vardı veya açılamadı."
                self._set_status(text, COLOR_TEXT_PRIMARY)
                return

            self._load_file(pdfs[0])
            if len(pdfs) > 1:
                self._set_status(
                    f"{len(pdfs)} PDF bırakıldı; ilki açıldı. Hepsini birleştirmek için "
                    "Birleştirme sekmesine bırakın.",
                    COLOR_TEXT_PRIMARY,
                )
            elif len(paths) > 1:
                self._set_status("PDF dışı öğeler yok sayıldı.", COLOR_TEXT_SECONDARY)
        except Exception:
            self.log.exception("Sürükle-bırak işlenemedi")
            messagebox.showerror("Sürükle-bırak",
                                 "Bırakılan dosyalar işlenemedi. Ayrıntılar günlükte.")
