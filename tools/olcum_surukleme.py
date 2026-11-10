"""P3-40: birleştirme listesinde sürükleme maliyeti (ekran dışı Qt; 25 / 100 / 300 dosya).

Eski yöntem (her fare adımında satırları yeniden yerleştirme) ile yeni yöntemin (yalnız bırakma
çizgisini taşıma, bırakınca tek taşıma) fare başına süresini karşılaştırır. Windows'ta aynı
betik gerçek ekranda çalıştırılabilir: ``python tools/olcum_surukleme.py``.
"""
import os
import sys
import tempfile
import time
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication  # noqa: E402

from tests.fake_context import FakeContext  # noqa: E402
from tests.pdf_factory import create_sample_a4_pdf  # noqa: E402
from ui import qt_compat as ctk  # noqa: E402
from ui.tabs.merge import MergeTab  # noqa: E402


def build(count, folder):
    root = ctk.CTk()
    root.withdraw()
    ctx = FakeContext()
    ctx.store = SimpleNamespace(add_recent_file=lambda _p: None, data={}, save=lambda: None, merge_preview_sequence=False, merge_handle_only=False)
    frame = ctk.CTkFrame(root)
    frame.put("v", fill="both", expand=True)
    tab = MergeTab("Birleştirme", ctx, frame)
    tab.ensure_built()
    sample = os.path.join(folder, "ornek.pdf")
    create_sample_a4_pdf(sample, pages=1)
    for index in range(count):  # aynı dosya yolu tekrar eklenemez: kopyala
        path = os.path.join(folder, f"d{index:04d}.pdf")
        if not os.path.exists(path):
            with open(sample, "rb") as src, open(path, "wb") as dst:
                dst.write(src.read())
        tab.append_file(path)
    tab.refresh_list()
    root.show()
    root.resize(900, 700)
    frame.show()
    for _ in range(5):
        QApplication.processEvents()
    return root, tab


def fire(widget, name, y):
    ev = SimpleNamespace(widget=widget, x_root=0, y_root=y, ctrl=False, shift=False)
    for cb in widget._bindings[name]:
        cb(ev)


def ms(fn, repeat):
    start = time.perf_counter()
    for _ in range(repeat):
        fn()
    return (time.perf_counter() - start) * 1000 / repeat


def main():
    folder = tempfile.mkdtemp()
    print(f"{'dosya':>6} | {'eski: adım (ms)':>16} | {'yeni: fare adımı (ms)':>22} | {'bırakma (ms)':>13}")
    for count in (25, 100, 300):
        root, tab = build(count, folder)
        # Eski yöntem: her fare adımında blok bir adım taşınır + tüm satırlar yeniden yerleştirilir.
        tab.select_item(count // 2)
        old = ms(lambda: (tab._move_block(1), tab.reorder_rows(), tab._move_block(-1), tab.reorder_rows()), 10) / 2
        # Yeni yöntem: listenin üstünden altına fare hareketleri (çizgi taşınır, satırlar yerinde).
        first = tab.rows[0]
        top = first.winfo_rooty()
        last = tab.rows[-1]
        span = last.winfo_rooty() + last.winfo_height() - top
        fire(first, "<Button-1>", top + 5)
        ys = [top + 20 + (span * i) // 200 for i in range(200)]
        start = time.perf_counter()
        for y in ys:
            fire(first, "<B1-Motion>", y)
        new = (time.perf_counter() - start) * 1000 / len(ys)
        # Bırakma: tek taşıma (ortaya).
        slot = count // 2
        drop = ms(lambda: (tab.drop_selection_at(slot), tab.drop_selection_at(0)), 5) / 2
        fire(first, "<ButtonRelease-1>", ys[-1])
        print(f"{count:>6} | {old:>16.2f} | {new:>22.3f} | {drop:>13.2f}")
        root.destroy()


if __name__ == "__main__":
    main()
