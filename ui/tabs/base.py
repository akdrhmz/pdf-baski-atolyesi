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
        self._building = False

    @property
    def built(self) -> bool:
        return self._built

    def ensure_built(self) -> None:
        """``build`` yöntemini en fazla bir kez çalıştırır."""
        if self._built:
            return
        self._building = True
        try:
            self.build()
        finally:
            self._building = False
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
    # Ortak yerleşim yardımcıları (v2.2.3 tasarım bileşenleri)
    # =====================================================================
    # Not: qt_compat padx/pady'yi aralık olarak uygulamaz; tüm aralıklar kapsayıcıların
    # ``set_padding(spacing=...)`` değeriyle verilir (theme.SP_*).
    def make_scroll(self):
        """Sekme içeriği için tek kaydırma alanı: tek dolgu, azami genişlik, bölümler arası SP_L."""
        scroll = ctk.CTkScrollableFrame(self.frame, fg_color="transparent")
        scroll.put("v", fill="both", expand=True, margins=(8, 6, 8, 6))
        scroll.set_padding(SP_XS, SP_S, SP_XS, SP_S, spacing=SP_S)
        # scroll._inner genişletilebilir; orta alan çerçevesini boşluksuz doldurur.
        scroll.grid_columnconfigure(0, weight=1)
        # Fazla dikey alanı en alttaki boş satır yutsun; içerik üstte kalır.
        scroll.grid_rowconfigure(20, weight=1)
        return scroll

    def section(self, container, row: int, title: str, column: int = 0, expand: bool = False):
        """Bölüm kartı: başlık satırı (sağda anahtar/rozet yeri) + gövde.

        Dönen gövde çerçevesinde ``header`` özniteliği başlık satırıdır (``badge`` için).
        ``expand`` verilirse kart dikeyde de büyür (liste gibi esnek içerik için).
        """
        sec = ctk.CTkFrame(container, fg_color=COLOR_CARD, corner_radius=10,
                           border_width=1, border_color=COLOR_BORDER)
        sec.set_padding(SP_S, SP_M, SP_S, SP_M, spacing=SP_XS)
        sec.place(row, column, valign="fill" if expand else "n")
        sec.grid_columnconfigure(0, weight=1)
        if expand:
            sec.grid_rowconfigure(1, weight=1)
        header = ctk.CTkFrame(sec, fg_color="transparent")  # pack_h düzeni (set_padding yok)
        header.place(0, 0)
        bar = ctk.CTkFrame(header, fg_color=COLOR_ACCENT, width=3, height=16,
                           corner_radius=2)
        # Qt uyum katmanında pack edilen Preferred öge kalan alanı paylaşır;
        # sabit politika ile çubuk 3 px kalır.
        bar.lock_width(3)
        bar.put("h")
        ctk.CTkLabel(
            header, text=title,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, anchor="w", justify="left",
        ).put("h")
        header._ensure_layout("pack_h").addStretch(1)  # sonradan eklenen rozet sağa yaslanır
        body = ctk.CTkFrame(sec, fg_color="transparent")
        body.set_padding(0, 2, 0, 0, spacing=SP_S)
        body.place(1, 0, valign="fill" if expand else "c")
        body.grid_columnconfigure(0, weight=1)
        body.header = header
        return body

    def form_stack_row(self, grid, row: int, label: str):
        """Form satırı: etiket + alt alta içerik hücresi (not/açıklama satırı için)."""
        title = ctk.CTkLabel(
            grid, text=label,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, anchor="w", width=FORM_LABEL_W,
        )
        # Etiket üstte durur ama ilk satırın (düğme/alan, ``BTN_H``) dikey ortasına oturur;
        # eskiden alanların ~10 px üstünde kalıp üstteki satıra yapışık görünüyordu.
        title.setContentsMargins(0, STACK_LABEL_TOP, 0, 0)
        title.place(row, 0, align="w", valign="n")
        cell = ctk.CTkFrame(grid, fg_color="transparent")
        cell.set_padding(0, 0, 0, 0, spacing=SP_XS)
        cell.place(row, 1)
        cell.grid_columnconfigure(0, weight=1)
        cell.row_label = title
        return cell

    def badge(self, body, text: str = "Devre dışı"):
        """Bölüm başlığının sağında Etkin/Devre dışı rozeti (modül anahtarıyla eşlenir)."""
        label = ctk.CTkLabel(
            body.header, text=text,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_TINY, weight="bold"),
            text_color=COLOR_TEXT_SECONDARY, fg_color=COLOR_SUBCARD,
            corner_radius=8, anchor="center",
        )
        label.setContentsMargins(10, 2, 10, 2)
        label.put("h")
        return label

    def set_badge(self, label, active: bool) -> None:
        """Rozetin metnini ve rengini modül durumuna göre ayarlar."""
        if active:
            label.configure(text="Etkin", text_color=COLOR_OK, fg_color=COLOR_OK_BG)
        else:
            label.configure(text="Devre dışı", text_color=COLOR_TEXT_SECONDARY,
                            fg_color=COLOR_SUBCARD)

    def sub_label(self, parent, row: int, text: str, columnspan: int = 1):
        """Bölüm içindeki alt grup başlığı: başlıktan daha hafif, ikincil renk."""
        label = ctk.CTkLabel(
            parent, text=text,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_SECONDARY, anchor="w", justify="left",
        )
        label.place(row, 0, columnspan=columnspan, align="w")
        return label

    def form_grid(self, parent, row: int):
        """İki sütunlu form: sol etiket sütunu (sabit genişlik), sağ içerik sütunu."""
        grid = ctk.CTkFrame(parent, fg_color="transparent")
        grid.set_padding(0, 0, 0, 0, spacing=SP_S)
        # Satırlar arası dikey boşluk yatay boşluktan büyük: alt alta satırlar (özellikle
        # not satırlı olanlar) birbirine yapışmasın (v2.6.16, saha ekran görüntüsü).
        grid._ensure_layout("grid").setVerticalSpacing(SP_M)
        grid.place(row, 0)
        grid.grid_columnconfigure(1, weight=1)
        return grid

    def form_row(self, grid, row: int, label: str, stretch: bool = False):
        """Form satırı: hizalı etiket + içerik hücresi (içine ``pack(side="left")`` ile ekleyin)."""
        title = ctk.CTkLabel(
            grid, text=label,
            font=ctk.CTkFont(family=FONT_FAMILY, size=FS_SMALL, weight="bold"),
            text_color=COLOR_TEXT_PRIMARY, anchor="w", width=FORM_LABEL_W,
        )
        title.place(row, 0, align="w")
        cell = ctk.CTkFrame(grid, fg_color="transparent")  # pack_h düzeni (set_padding yok)
        cell.place(row, 1, align="" if stretch else "w")
        cell.row_label = title
        return cell

    @staticmethod
    def set_row_visible(cell, visible: bool) -> None:
        """``form_row`` / ``form_stack_row`` satırını (etiket + hücre) birlikte gösterir/gizler.

        Gizlenen satır yer kaplamaz; ilgisiz denetimler pasif bırakılmak yerine kaldırılır (P2-36).
        """
        for widget in (getattr(cell, "row_label", None), cell):
            if widget is None:
                continue
            if visible:
                widget.place_restore()
            else:
                widget.grid_remove()
