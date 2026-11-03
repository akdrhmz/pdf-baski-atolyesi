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
