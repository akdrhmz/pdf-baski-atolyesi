"""Canlı önizleme paneli: pencere öğeleri, durum, üretim iş parçacığı ve sayfa gezinmesi.

``PreviewPanel`` önizlemeyle ilgili her şeyin sahibidir (``history`` dahil); kabukla
yalnızca dar bir ``PreviewHost`` yüzeyi üzerinden konuşur: önizlenecek dosya, geçerli
ayar, arayüz iş parçacığına dönüş ve birkaç hizmet. Böylece panel gerçek pencere
olmadan sahte bir ev sahibiyle denenebilir (``tests/test_preview_panel.py``).

Kabuk ``preview_mode``, ``_preview_gen`` gibi eski adları geçiş süresince
``forward`` ile panele yönlendirir (2.9/2.8'de kalkar).
"""

from __future__ import annotations

import io
import os
import threading
from typing import Any, Callable, List, Optional, Protocol

from PIL import Image

from ui import qt_compat as ctk

from gutter_engine import config_to_dict, render_preview
from ui.theme import *  # noqa: F401,F403

# Titremeyi önlemek için son birkaç PhotoImage tutulur; 6-8 yeterlidir, fazlası büyük
# sayfalarda gereksiz bellek harcar.
PREVIEW_HISTORY_LIMIT = 8


class PreviewHost(Protocol):
    """Panelin pencereden beklediği her şey; ``AppPreviewHost`` ve test sahtesi sağlar."""

    log: Any

    @property
    def orig_page_count(self) -> int: ...
    def source_path(self) -> str: ...
    def build_config(self) -> Any: ...
    def run_on_ui(self, callback: Callable[[], None]) -> None: ...
    def after(self, ms: int, callback: Callable[[], None]) -> Any: ...
    def after_cancel(self, after_id: Any) -> None: ...
    def bind_wraplength(self, label: Any, container: Any, padding: int) -> None: ...
    def appearance_color(self, color: Any) -> str: ...
    def scan_for_clipping(self) -> None: ...


class AppPreviewHost:
    """Gerçek pencereye bağlı ``PreviewHost``; her okuma pencereden canlı yapılır."""

    def __init__(self, app: Any):
        self._app = app

    @property
    def log(self) -> Any:
        return self._app.log

    @property
    def orig_page_count(self) -> int:
        return self._app.orig_page_count

    def source_path(self) -> str:
        return self._app._preview_source_path()

    def build_config(self) -> Any:
        return self._app._build_config(notify=False)

    def run_on_ui(self, callback: Callable[[], None]) -> None:
        self._app._ui(callback)

    def after(self, ms: int, callback: Callable[[], None]) -> Any:
        return self._app.after(ms, callback)

    def after_cancel(self, after_id: Any) -> None:
        self._app.after_cancel(after_id)

    def bind_wraplength(self, label: Any, container: Any, padding: int) -> None:
        self._app._bind_wraplength(label, container, padding)

    def appearance_color(self, color: Any) -> str:
        return self._app._apply_appearance_mode(color)

    def scan_for_clipping(self) -> None:
        self._app._scan_for_clipping()


class PreviewPanel:
    """Önizleme kartı ve önizleme üretimi."""

    def __init__(self, host: PreviewHost):
        self.host = host
        # Durum pencere öğelerinden önce de geçerlidir (sekmeler kurulurken ``schedule`` çağrılır).
        self.mode = "spread"
        self.page = 0
        self.gen = 0
        self.after_id: Optional[Any] = None
        self.signature: Optional[Any] = None
        self.images: List[Any] = []
        self.history: List[Any] = []
        self.blank_images: dict = {}
        self.slots: list = []
        self.image_frame: Any = None
        self.preview_mode_menu: Any = None
        self.preview_prev_btn: Any = None
        self.preview_next_btn: Any = None
        self.preview_page_label: Any = None
        self.preview_info: Any = None
        self.preview_warning: Any = None

    # -- Kabuk işleri ---------------------------------------------------------
    def cancel_pending(self) -> None:
        """Bekleyen gecikmeli yenilemeyi iptal eder (pencere kapanırken)."""
        if self.after_id is not None:
            try:
                self.host.after_cancel(self.after_id)
            except Exception:
                pass
            self.after_id = None

    def invalidate(self) -> None:
        """Uçuştaki üretimin sonucunu geçersiz kılar (iş başlarken)."""
        self.gen += 1

    def reset_for_new_document(self) -> None:
        self.page = 0
        self.signature = None
        self.gen += 1
        self.clear("Önizleme hazırlanıyor...")
        self.update_nav()

    def apply_theme(self) -> None:
        """Görüntü etiketlerinin düz Tk arka planını tema rengine uyarlar."""
        try:
            bg = self.host.appearance_color(COLOR_CARD)
            for _slot, image_label, _caption in self.slots:
                image_label.configure(bg=bg)
        except Exception:
            pass

    # =====================================================================
    # Canlı önizleme paneli
    # =====================================================================
    def build(self, parent) -> None:
        card = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=8,
                        border_width=1, border_color=COLOR_BORDER, width=480)
        self.card = card
        card.grid(row=0, column=3, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(
            card, text="Canlı önizleme",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_BODY, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY,
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 2))
        subtitle = ctk.CTkLabel(
            card, text="İlk sayfa ve karşı sayfa; cilt şeridi, paylar ve numara konumu işaretli.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=300,
        )
        subtitle.grid(row=1, column=0, sticky="ew", padx=12)
        self.host.bind_wraplength(subtitle, card, 30)

        self.preview_mode_menu = ctk.CTkSegmentedButton(
            card, values=["Tek sayfa", "Çift sayfa"], height=26,
            border_width=0, fg_color=COLOR_SUBCARD, bg_color=COLOR_CARD,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            selected_color=COLOR_SELECTED, selected_hover_color=COLOR_SELECTED_HOVER,
            unselected_color=COLOR_SUBCARD, unselected_hover_color=COLOR_BTN_SUBTLE_HOVER,
            text_color=COLOR_TEXT_PRIMARY, corner_radius=6,
            command=self.on_mode_changed,
        )
        self.preview_mode_menu.set("Çift sayfa")
        self.preview_mode_menu.grid(row=2, column=0, sticky="ew", padx=12, pady=(5, 2))

        image_frame = ctk.CTkFrame(card, fg_color="transparent")
        image_frame.grid(row=3, column=0, sticky="nsew", padx=8, pady=(6, 3))
        self.image_frame = image_frame
        image_frame.grid_columnconfigure(0, weight=1, uniform="preview")
        image_frame.grid_columnconfigure(1, weight=1, uniform="preview")
        image_frame.grid_rowconfigure(0, weight=1)
        self.slots = []
        for column in (0, 1):
            slot = ctk.CTkFrame(image_frame, fg_color=COLOR_CARD, corner_radius=4,
                                border_width=1, border_color=COLOR_BORDER)
            slot.grid(row=0, column=column, padx=2)
            slot.grid_columnconfigure(0, weight=1)
            image_label = ctk.CTkLabel(
                slot, text="",
                bg=self.host.appearance_color(COLOR_CARD),
            )
            image_label.grid(row=0, column=0, padx=3, pady=(3, 0))
            caption = ctk.CTkLabel(
                slot, text="—", font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
                text_color=COLOR_TEXT_SECONDARY,
            )
            caption.grid(row=1, column=0, padx=3, pady=(0, 3))
            self.slots.append((slot, image_label, caption))

        try:
            from PIL import ImageDraw
            def _make_placeholder(w: int, h: int) -> Image.Image:
                im = Image.new("RGBA", (w, h), (130, 140, 155, 16))
                dr = ImageDraw.Draw(im)
                dr.rounded_rectangle((2, 2, w - 3, h - 3), radius=6, outline=(130, 140, 155, 85), width=1)
                for y in range(28, h - 32, 18):
                    line_end = w - 24 if (y // 18) % 3 != 0 else w - 56
                    dr.line((20, y, line_end, y), fill=(130, 140, 155, 42), width=2)
                return im
            blank_small = _make_placeholder(200, 283)
            blank_large = _make_placeholder(340, 481)
            self.blank_images = {
                "spread": ctk.pil_to_pixmap(blank_small),
                "single": ctk.pil_to_pixmap(blank_large),
            }
        except Exception:
            self.blank_images = {}

        nav = ctk.CTkFrame(card, fg_color="transparent")
        nav.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 2))
        nav.grid_columnconfigure(1, weight=1)
        self.preview_prev_btn = ctk.CTkButton(
            nav, text="‹ Önceki", width=84, height=26,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            fg_color=COLOR_SUBCARD, text_color=COLOR_TEXT_PRIMARY,
            border_width=1, border_color=COLOR_BORDER,
            hover_color=COLOR_BTN_SUBTLE_HOVER, command=self.previous,
        )
        self.preview_prev_btn.grid(row=0, column=0, sticky="w")
        self.preview_page_label = ctk.CTkLabel(
            nav, text="—", font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY, weight="bold"),
            text_color=COLOR_TEXT_SECONDARY,
        )
        self.preview_page_label.grid(row=0, column=1)
        self.preview_next_btn = ctk.CTkButton(
            nav, text="Sonraki ›", width=84, height=26,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            fg_color=COLOR_SUBCARD, text_color=COLOR_TEXT_PRIMARY,
            border_width=1, border_color=COLOR_BORDER,
            hover_color=COLOR_BTN_SUBTLE_HOVER, command=self.next_page,
        )
        self.preview_next_btn.grid(row=0, column=2, sticky="e")

        self.preview_info = ctk.CTkLabel(
            card, text="Belge seçildiğinde önizleme burada görünür.",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=320,
        )
        self.preview_info.grid(row=5, column=0, sticky="new", padx=12, pady=(2, 4))
        self.host.bind_wraplength(self.preview_info, card, 36)

        self.preview_warning = ctk.CTkLabel(
            card, text="", font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY, weight="bold"),
            text_color=COLOR_ERROR, anchor="w", justify="left", wraplength=320,
        )
        self.preview_warning.grid(row=6, column=0, sticky="ew", padx=12)
        self.host.bind_wraplength(self.preview_warning, card, 36)

        legend = ctk.CTkLabel(
            card, text="Mavi: cilt payı   •   Yeşil: alt/üst pay   •   Kırmızı çerçeve: kırpma riski",
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left", wraplength=320,
        )
        legend.grid(row=7, column=0, sticky="ew", padx=12, pady=(2, 6))
        self.host.bind_wraplength(legend, card, 24)

        preview_buttons = ctk.CTkFrame(card, fg_color="transparent")
        preview_buttons.grid(row=8, column=0, sticky="ew", padx=8, pady=(0, 10))
        preview_buttons.grid_columnconfigure(0, weight=1)
        self.detach_images()
        preview_buttons.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(
            preview_buttons, text="Önizlemeyi yenile", height=30,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            fg_color=COLOR_SUBCARD, text_color=COLOR_TEXT_PRIMARY,
            border_width=1, border_color=COLOR_BORDER,
            hover_color=COLOR_BTN_SUBTLE_HOVER, corner_radius=6,
            command=self.refresh_now,
        ).grid(row=0, column=0, sticky="ew", padx=(4, 3))
        ctk.CTkButton(
            preview_buttons, text="Kırpma riskini tara", height=30,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            fg_color=COLOR_SUBCARD, text_color=COLOR_TEXT_PRIMARY,
            border_width=1, border_color=COLOR_BORDER,
            hover_color=COLOR_BTN_SUBTLE_HOVER, corner_radius=6,
            command=self.host.scan_for_clipping,
        ).grid(row=0, column=1, sticky="ew", padx=(3, 4))

        self.apply_layout()
        self.update_nav()

    # =====================================================================
    # Önizleme ve tarama
    # =====================================================================
    def schedule(self) -> None:
        if self.after_id is not None:
            try:
                self.host.after_cancel(self.after_id)
            except Exception:
                pass
        self.after_id = self.host.after(300, self.refresh)

    def refresh_now(self) -> None:
        if self.after_id is not None:
            try:
                self.host.after_cancel(self.after_id)
            except Exception:
                pass
            self.after_id = None
        path = self.host.source_path()
        if not path or not os.path.exists(path):
            self.clear("Belge seçildiğinde önizleme burada görünür.")
            return
        self.signature = None
        self.preview_info.configure(text="Önizleme yenileniyor...", text_color=COLOR_TEXT_SECONDARY)
        self.refresh()

    def refresh(self) -> None:
        self.after_id = None
        path = self.host.source_path()
        if not path or not os.path.exists(path):
            self.signature = None
            self.clear("Belge seçildiğinde önizleme burada görünür.")
            return
        config = self.host.build_config()
        if config is None:
            self.preview_info.configure(text="Önizleme için ayarları düzeltin.",
                                        text_color=COLOR_WARN)
            return
        try:
            stat = os.stat(path)
            stamp = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            stamp = (0, 0)
        signature = (os.path.abspath(path), stamp,
                     self.mode, self.page, repr(config_to_dict(config)))
        if signature == self.signature and self.images:
            return
        self.signature = signature
        self.gen += 1
        generation = self.gen

        def worker():
            try:
                if self.mode == "single":
                    wanted = (self.page,)
                else:
                    wanted = (self.page, self.page + 1)
                pages = render_preview(path, config, pages=wanted, zoom=1.6)
            except Exception as exc:
                message = str(exc)
                self.host.log.warning("Önizleme üretilemedi: %s", message)
                self.host.run_on_ui(lambda message=message: self.show(generation, [], message))
                return
            self.host.run_on_ui(lambda: self.show(generation, pages, None))

        threading.Thread(target=worker, daemon=True).start()

    def _blank_slot(self, image_label, caption) -> None:
        try:
            blank = self.blank_images.get(self.mode)
            image_label.configure(image=blank if blank is not None else "", text="")
        except Exception:
            pass
        try:
            caption.configure(text="—")
        except Exception:
            pass

    def detach_images(self) -> None:
        """Etiketleri boş görüntüye alır; eski görüntüler oturum boyunca saklanır."""
        for _slot, image_label, caption in self.slots:
            self._blank_slot(image_label, caption)
        self.images.clear()

    def clear(self, message: str) -> None:
        self.detach_images()
        self.preview_info.configure(text=message, text_color=COLOR_TEXT_SECONDARY)
        self.preview_warning.configure(text="")

    def show(self, generation: int, pages, error: Optional[str]) -> None:
        if generation != self.gen:
            return
        if error:
            self.signature = None
            self.clear(f"Önizleme üretilemedi: {error}")
            return
        if not pages:
            self.clear("Önizleme için sayfa bulunamadı.")
            return

        self.detach_images()
        count = min(len(pages), 2)
        max_width = 340 if self.mode == "single" else 200
        for slot_index, (slot, image_label, caption) in enumerate(self.slots):
            if slot_index >= count:
                continue
            page = pages[slot_index]
            try:
                image = Image.open(io.BytesIO(page.png))
                image.load()
            except Exception:
                continue
            ratio = page.height_pt / page.width_pt if page.width_pt else 1.414
            display_w = max_width
            display_h = max(60, min(380, round(max_width * ratio)))
            preview_image = image.resize((display_w, display_h), Image.Resampling.LANCZOS)
            photo = ctk.pil_to_pixmap(preview_image)
            self.images.append(photo)
            self.history.append(photo)
            if len(self.history) > PREVIEW_HISTORY_LIMIT:
                del self.history[:len(self.history) - PREVIEW_HISTORY_LIMIT]
            image_label.configure(image=photo, text="")
            side = "Tek (sağ)" if page.is_odd else "Çift (sol)"
            caption.configure(text=f"{page.page_index + 1}. sayfa • {side}")

        first = pages[0]
        info = (f"{first.width_mm:.1f} × {first.height_mm:.1f} mm  •  ölçek %{first.scale * 100:.0f}")
        if first.number_text:
            info += f"  •  numara: {first.number_text}"
        self.preview_info.configure(text=info, text_color=COLOR_TEXT_PRIMARY)

        warnings = []
        for page in pages[:2]:
            if page.clipped:
                edges = ", ".join(
                    f"{name} {value:.1f} mm"
                    for name, value in zip(("sol", "sağ", "üst", "alt"), page.clip_mm)
                    if value > 0
                )
                warnings.append(f"Sayfa {page.page_index + 1}: {edges} taşıyor.")
        if warnings:
            self.preview_warning.configure(text="Kırpma riski - " + " ".join(warnings))
        else:
            self.preview_warning.configure(text="")
        self.update_nav()

    def on_mode_changed(self, value: str) -> None:
        self.mode = "single" if "Tek" in value else "spread"
        self.detach_images()
        self.apply_layout()
        self.signature = None
        self.refresh()
        self.update_nav()

    def apply_layout(self) -> None:
        """Tek sayfa modunda ikinci slotu kaldırır, ilk önizlemeyi genişletir."""
        if not self.slots:
            return
        single = self.mode == "single"
        frame = self.image_frame
        first_slot, first_label, _ = self.slots[0]
        second_slot, second_label, _ = self.slots[1]
        if single:
            frame.grid_columnconfigure(1, weight=0)
            first_slot.grid_configure(columnspan=2)
            second_slot.grid_remove()
        else:
            frame.grid_columnconfigure(1, weight=1)
            first_slot.grid_configure(columnspan=1)
            second_slot.grid()

    def step(self, delta: int) -> None:
        total = self.host.orig_page_count
        if total <= 0:
            return
        step = 1 if self.mode == "single" else 2
        candidate = self.page + delta * step
        candidate = max(0, min(candidate, total - 1))
        if candidate == self.page:
            return
        self.page = candidate
        self.signature = None
        self.refresh()
        self.update_nav()

    def previous(self) -> None:
        self.step(-1)

    def next_page(self) -> None:
        self.step(1)

    def update_nav(self) -> None:
        if self.preview_page_label is None:
            return
        total = self.host.orig_page_count
        if total <= 0:
            self.preview_page_label.configure(text="—")
            self.preview_prev_btn.configure(state="disabled")
            self.preview_next_btn.configure(state="disabled")
            return
        self.page = max(0, min(self.page, total - 1))
        if self.mode == "single":
            text = f"{self.page + 1} / {total}"
            can_prev = self.page > 0
            can_next = self.page < total - 1
        else:
            end = min(self.page + 1, total - 1)
            text = (f"{self.page + 1} / {total}" if end == self.page
                    else f"{self.page + 1}–{end + 1} / {total}")
            can_prev = self.page > 0
            can_next = self.page + 2 < total
        self.preview_page_label.configure(text=text)
        self.preview_prev_btn.configure(state="normal" if can_prev else "disabled")
        self.preview_next_btn.configure(state="normal" if can_next else "disabled")
