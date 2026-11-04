"""``BaseTab`` sözleşmesi: her sekmenin pencere kabuğuyla konuştuğu üç kanca.

Kabuk (``app.py``) sekmenin çerçevesini (``frame``) oluşturup yerleştirir; sekme
yalnızca içeriğini kurar. Kabuğun sekmeden beklediği:

``build``        İçeriği kurar. Yalnızca bir kez, ``ensure_built`` üzerinden çağrılır.
``on_show``      Sekme öne geldiğinde çağrılır (varsayılan: kaydırmayı başa alır).
``apply_theme``  Tema değiştiğinde çağrılır. CTk renk çiftlerini kendisi çözdüğü
                 için çoğu sekmede boş kalır; elle renk veren sekme burada günceller.

``ensure_built`` tembel kurulumu (2.9) sağlar: kabuk yalnızca açılıştaki sekmeyi kurar,
diğerlerini göstermeden hemen önce kurar. Kurulum bitince bağlam ``tab_built`` sağlıyorsa
çağrılır; kabuk orada eski takma adları bağlar, birimi ayarlar ve bekleyen ayarı yazar.
"""

from __future__ import annotations

from typing import Any

from ui import qt_compat as ctk
from ui.theme import *  # noqa: F401,F403


class BaseTab:
    """Tüm sekmelerin ortak sözleşmesi."""

    def __init__(self, name: str, ctx: Any, frame: Any):
        self.name = name
        self.ctx = ctx
        self.frame = frame
        self._built = False

    @property
    def built(self) -> bool:
        return self._built

    def ensure_built(self) -> None:
        """``build`` yöntemini en fazla bir kez çalıştırır."""
        if self._built:
            return
        self.build()
        # Bayrak ``build`` başarıyla bittikten sonra kurulur; yarım kalmış kurulum
        # bir sonraki çağrıda yeniden denenir.
        self._built = True
        hook = getattr(self.ctx, "tab_built", None)
        if hook is not None:
            hook(self)

    def build(self) -> None:
        raise NotImplementedError(f"{type(self).__name__}.build yazılmamış")

    def on_show(self) -> None:
        """Varsayılan: sekmedeki kaydırılabilir alanları başa alır."""
        self.scroll_to_top()

    def apply_theme(self) -> None:
        """Varsayılan: yapılacak bir şey yok (CTk renk çiftlerini kendisi çözer)."""

    def scroll_to_top(self) -> None:
        frame = self.frame
        if frame is None:
            return
        for child in frame.winfo_children():
            canvas = getattr(child, "_parent_canvas", None)
            if canvas is None:
                continue
            try:
                canvas.yview_moveto(0.0)
            except Exception:
                pass

    # =====================================================================
    # Ortak yerleşim yardımcıları
    # =====================================================================
    def section(self, container, row: int, title: str, column: int = 0):
        """Vurgu çubuklu düz bölüm: renkli şerit + başlık, çerçevesiz gövde.

        Gövde, başlık metniyle hizalanır (sol 11 px); dönen çerçeveye içeriği koy.
        """
        sec = ctk.CTkFrame(container, fg_color="transparent")
        sec.grid(row=row, column=column, sticky="new")
        sec.grid_columnconfigure(0, weight=1)
        header = ctk.CTkFrame(sec, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew")
        ctk.CTkFrame(header, fg_color=COLOR_ACCENT, width=3, height=16,
                     corner_radius=2).grid(row=0, column=0, sticky="w", padx=(0, 8))
        ctk.CTkLabel(
            header, text=title,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, anchor="w",
        ).grid(row=0, column=1, sticky="w")
        body = ctk.CTkFrame(sec, fg_color="transparent")
        body.grid(row=1, column=0, sticky="ew", padx=(11, 0), pady=(6, 0))
        return body
