"""Folder/file batch dialog with profile selection and per-file results."""

from __future__ import annotations

import os
from pathlib import Path
import threading

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QListWidget, QListWidgetItem

from core.gutter_engine import config_from_dict, validate_config
from core.settings_store import PRESETS
from ui import qt_compat as ctk
from ui.qt_compat import filedialog, messagebox
from ui.theme import *  # noqa: F401,F403
from ui.i18n import tr


class BatchDialog:
    def __init__(self, app):
        self.app = app
        self.files: list[str] = []
        self._cancel = threading.Event()
        self._busy = False
        self._closed = False
        self._worker = None
        self.window = ctk.CTkToplevel(app)
        self.window.title("Toplu PDF işlemi")
        self.window.geometry("760x650")
        self.window.minsize(620, 500)
        self.window.transient(app)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.set_drop_callback(self._on_drop_files)

        outer = ctk.CTkFrame(self.window, fg_color=COLOR_CARD)
        outer.put("v", fill="both", expand=True, margins=(16, 12, 16, 12))
        outer.grid_columnconfigure(0, weight=1)
        outer.grid_rowconfigure(3, weight=1)
        ctk.CTkLabel(outer, text="Klasör veya dosya listesini aynı profille sırayla işler.",
                     font=ctk.CTkFont(family=FONT_FAMILY, size=FS_BODY),
                     text_color=COLOR_TEXT_SECONDARY, anchor="w").place(0, 0, expand_x=True)

        profile_row = ctk.CTkFrame(outer, fg_color="transparent")
        profile_row.place(1, 0, expand_x=True)
        ctk.CTkLabel(profile_row, text="Ayar profili", width=120, anchor="w").put("h")
        names = ["Ekrandaki ayarlar", *PRESETS.keys(), *app.store.profile_names()]
        self.profile = ctk.CTkOptionMenu(profile_row, values=list(dict.fromkeys(names)), width=250)
        self.profile.set("Ekrandaki ayarlar")
        self.profile.put("h")

        add_row = ctk.CTkFrame(outer, fg_color="transparent")
        add_row.place(2, 0, expand_x=True)
        self.add_files_button = ctk.CTkButton(add_row, text="PDF dosyaları ekle…", width=160,
                                              command=self.add_files)
        self.add_files_button.put("h", margins=(0, 0, SP_S, 0))
        self.recursive = ctk.CTkCheckBox(add_row, text="Alt klasörleri tara")
        self.recursive.put("h", margins=(0, 0, SP_S, 0))
        self.add_folder_button = ctk.CTkButton(add_row, text="Klasör ekle…", width=130,
                                               command=self.add_folder)
        self.add_folder_button.put("h")
        self.file_list = QListWidget()
        self.file_list.setAlternatingRowColors(True)
        palette = self.file_list.palette()
        palette.setColor(QPalette.ColorRole.Base, QColor(ctk.resolve_color(COLOR_CARD)))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(ctk.resolve_color(COLOR_SUBCARD)))
        palette.setColor(QPalette.ColorRole.Text, QColor(ctk.resolve_color(COLOR_TEXT_PRIMARY)))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(ctk.resolve_color(COLOR_SELECTED)))
        self.file_list.setPalette(palette)
        self.file_list.setMinimumHeight(180)
        outer._ensure_layout("grid").addWidget(self.file_list, 3, 0)

        output_row = ctk.CTkFrame(outer, fg_color="transparent")
        output_row.place(4, 0, expand_x=True)
        ctk.CTkLabel(output_row, text="Çıktı klasörü", width=120, anchor="w").put("h")
        self.output = ctk.CTkEntry(output_row, placeholder_text="PDF'lerin kaydedileceği klasör…")
        self.output.put("h", fill="x", expand=True, margins=(0, 0, SP_S, 0))
        self.output_button = ctk.CTkButton(output_row, text="Gözat…", width=82,
                                           command=self.choose_output)
        self.output_button.put("h")

        self.skip_clipping = ctk.CTkCheckBox(outer, text="Kırpma riski bulunan dosyaları atla")
        self.skip_clipping.select()
        self.skip_clipping.setToolTip("Riskli dosyaların çıktısı oluşturulmaz; listede nedeni gösterilir.")
        self.skip_clipping.place(5, 0, align="w")
        self.status = ctk.CTkLabel(outer, text="Dosya ekleyin. Kaynaklar korunur ve her çıktı doğrulanır.",
                                   anchor="w", wraplength=680,
                                   text_color=COLOR_TEXT_SECONDARY)
        self.status.place(6, 0, expand_x=True)
        self.progress = ctk.CTkProgressBar(outer, height=5, progress_color=COLOR_ACCENT)
        self.progress.set(0)
        self.progress.place(7, 0, expand_x=True)
        actions = ctk.CTkFrame(outer, fg_color="transparent")
        actions.place(8, 0, expand_x=True)
        actions.grid_columnconfigure(0, weight=1)
        self.clear_button = ctk.CTkButton(actions, text="Listeyi temizle", width=120,
                                          command=self.clear)
        self.clear_button.place(0, 0, align="w")
        self.close_button = ctk.CTkButton(actions, text="Kapat", width=90, command=self.close)
        self.close_button.place(0, 1, align="e")
        self.run_button = ctk.CTkButton(actions, text="Toplu işlemi başlat", width=180,
                                        fg_color=COLOR_SOLID, text_color=COLOR_ON_ACCENT,
                                        command=self.run)
        self.run_button.place(0, 2, align="e")
        self._refresh_list()
        self.window.grab_set()

    def _on_drop_files(self, paths):
        if self._busy:
            return
        collected = []
        for value in paths:
            p = Path(value)
            if p.is_dir():
                candidates = p.rglob("*") if self.recursive.get() else p.iterdir()
                collected.extend(str(c) for c in sorted(candidates) if c.is_file() and c.suffix.lower() == ".pdf")
            elif p.is_file() and p.suffix.lower() == ".pdf":
                collected.append(str(p))
        if collected:
            self._add_paths(collected)

    def add_files(self):
        if self._busy:
            return
        paths = filedialog.askopenfilenames(title="İşlenecek PDF dosyalarını seçin",
                                            filetypes=[("PDF belgeleri", "*.pdf")])
        self._add_paths(paths)

    def add_folder(self):
        if self._busy:
            return
        folder = filedialog.askdirectory(title="PDF klasörünü seçin")
        if not folder:
            return
        root = Path(folder)
        candidates = root.rglob("*") if self.recursive.get() else root.iterdir()
        paths = sorted(str(path) for path in candidates if path.is_file() and path.suffix.lower() == ".pdf")
        if not paths:
            self.status.configure(text="Bu klasörde PDF bulunamadı.", text_color=COLOR_WARN)
            return
        self._add_paths(paths)

    def _add_paths(self, paths):
        known = {os.path.normcase(os.path.realpath(path)) for path in self.files}
        added = 0
        for value in paths:
            path = os.path.abspath(os.fspath(value))
            if os.path.isfile(path) and path.lower().endswith(".pdf"):
                key = os.path.normcase(os.path.realpath(path))
                if key not in known:
                    self.files.append(path)
                    known.add(key)
                    added += 1
        self._refresh_list()
        self.status.configure(text=f"{len(self.files)} PDF sırada; {added} yeni dosya eklendi.",
                              text_color=COLOR_TEXT_SECONDARY)

    def _refresh_list(self):
        self.file_list.clear()
        if not self.files:
            placeholder = QListWidgetItem("PDF listesi boş. Dosya veya klasör ekleyin.")
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self.file_list.addItem(placeholder)
        for path in self.files:
            item = QListWidgetItem(f"{tr('Bekliyor')}  ·  {Path(path).name} — {Path(path).parent}")
            item.setToolTip(path)
            item.setData(256, path)
            self.file_list.addItem(item)
        self._sync_actions()

    def _sync_actions(self):
        self.run_button.configure(state="normal" if self.files and not self._busy else "disabled")
        self.clear_button.configure(state="normal" if self.files and not self._busy else "disabled")

    def clear(self):
        if self._busy:
            return
        self.files.clear()
        self._refresh_list()
        self.progress.set(0)
        self.status.configure(text="Dosya ekleyin. Kaynaklar korunur ve her çıktı doğrulanır.",
                              text_color=COLOR_TEXT_SECONDARY)
        self._sync_actions()

    def choose_output(self):
        if self._busy:
            return
        folder = filedialog.askdirectory(title="Çıktı klasörünü seçin")
        if folder:
            self.output.delete(0, "end")
            self.output.insert(0, folder)

    def _selected_config(self):
        name = self.profile.get()
        if name == "Ekrandaki ayarlar":
            return self.app._build_config(notify=False)
        raw = PRESETS.get(name) or self.app.store.get_profile(name)
        if raw is None:
            raise ValueError(f"'{name}' profili bulunamadı.")
        return config_from_dict(raw)

    def run(self):
        if self._busy:
            return
        output = self.output.get().strip()
        if not output:
            messagebox.showwarning("Toplu işlem", "Önce çıktı klasörünü seçin.")
            return
        if not self.files:
            return
        try:
            config = self._selected_config()
            if config is None:
                return
            validation = validate_config(config)
            if not validation.ok:
                raise ValueError("\n".join(validation.errors))
            active = (config.page_boxes.enabled or config.margins.enabled or config.page_numbers.enabled
                      or config.fit_mode != "off" or config.quality_mode != "print")
            if not active:
                raise ValueError("Seçilen profilde etkin işlem yok. Ayar profili seçin veya ayarları etkinleştirin.")
        except Exception as exc:
            messagebox.showerror("Toplu işlem ayarları", str(exc))
            return
        try:
            os.makedirs(output, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("Çıktı klasörü", str(exc))
            return
        files = list(self.files)

        from ui.batch_jobs import run_batch
        self._busy = True
        self._cancel.clear()
        self._set_controls_enabled(False)
        self.progress.set(0)
        self.status.configure(text=f"0 / {len(files)} dosya işlendi…", text_color=COLOR_ACCENT)

        def on_progress(current, total, item):
            def apply():
                if self._closed:
                    return
                row = current - 1
                if 0 <= row < self.file_list.count():
                    title = tr(item.state)
                    self.file_list.item(row).setText(f"{title}  ·  {Path(item.source).name}"
                                                     + (f" — {item.detail}" if item.detail else ""))
                self.progress.set(current / total if total else 0)
                self.status.configure(text=f"{current} / {total} dosya işlendi…",
                                      text_color=COLOR_ACCENT)
            self.app._ui(apply)

        def worker():
            try:
                results = run_batch(files, output, config, skip_clipping=bool(self.skip_clipping.get()),
                                    should_cancel=self._cancel.is_set, progress=on_progress)
            except Exception as exc:
                from ui.batch_jobs import BatchItemResult
                results = [BatchItemResult(path, state="Hata", detail=str(exc)) for path in files]
            def finish():
                if self._closed:
                    return
                self._busy = False
                self._set_controls_enabled(True)
                ok = sum(result.state in ("Tamamlandı", "Uyarı") for result in results)
                skipped = sum(result.state == "Atlandı" for result in results)
                errors = sum(result.state == "Hata" for result in results)
                cancelled = self._cancel.is_set()
                self.progress.set(1 if results and not cancelled else 0)
                summary = f"Bitti: {ok} başarılı, {skipped} risk nedeniyle atlandı, {errors} hatalı."
                if cancelled:
                    summary = "İptal edildi. Tamamlanmış dosyalar korundu. " + summary
                self.status.configure(text=summary,
                                      text_color=COLOR_WARN if errors or skipped or cancelled else COLOR_OK)
                for index, result in enumerate(results):
                    if index >= self.file_list.count():
                        break
                    label = tr(result.state)
                    self.file_list.item(index).setText(f"{label}  ·  {Path(result.source).name}"
                                                       + (f" — {result.detail}" if result.detail else ""))
                    if result.output:
                        self.file_list.item(index).setToolTip(result.output)
            self.app._ui(finish)

        self._worker = threading.Thread(target=worker, name="studio-batch", daemon=True)
        self._worker.start()

    def _set_controls_enabled(self, enabled: bool):
        for widget in (self.profile, self.add_files_button, self.add_folder_button, self.recursive,
                       self.output, self.output_button, self.skip_clipping, self.clear_button):
            widget.configure(state="normal" if enabled else "disabled")
        self.file_list.setEnabled(enabled)
        self.run_button.configure(state="normal" if enabled and self.files else "disabled")
        self.close_button.configure(text="İptal ediliyor…" if not enabled else "Kapat")

    def close(self):
        if self._busy:
            self._cancel.set()
            self.status.configure(text="İptal ediliyor; mevcut dosya güvenli biçimde tamamlanacak…",
                                  text_color=COLOR_WARN)
            return False
        self._closed = True
        self.window.destroy()
        return True
