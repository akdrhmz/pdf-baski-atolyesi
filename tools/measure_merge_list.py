"""25/100/300 dosyada satır kurma/temizleme ölçümü; farklı kaynak klasörüyle kıyaslanabilir."""
import argparse
import json
import os
from pathlib import Path
import queue
import sys
import time
from types import SimpleNamespace

parser = argparse.ArgumentParser()
parser.add_argument("--source", default=str(Path(__file__).resolve().parent.parent))
parser.add_argument("--output", required=True)
args = parser.parse_args()
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(args.source).resolve()))
from PySide6.QtWidgets import QApplication
from ui import qt_compat as ctk
from ui.tabs.merge import MergeTab
from tests.fake_context import FakeContext
import pymupdf

output = Path(args.output).resolve()
output.parent.mkdir(parents=True, exist_ok=True)
sample = output.parent / "benchmark-input.pdf"
with pymupdf.open() as doc:
    page = doc.new_page()
    page.insert_text((30, 50), "Benchmark document")
    doc.save(sample)
results = []
for count in (25, 100, 300):
    root = ctk.CTk()
    callbacks = queue.Queue()
    ctx = FakeContext()
    ctx.run_on_ui = callbacks.put
    ctx.store = SimpleNamespace(data={}, save=lambda: None, add_recent_file=lambda _p: None,
                                merge_preview_sequence=False, merge_handle_only=False)
    frame = ctk.CTkFrame(root)
    frame.put("v", fill="both", expand=True)
    tab = MergeTab("Birleştirme", ctx, frame)
    tab.ensure_built()
    root.resize(1100, 700)
    root.show()
    QApplication.processEvents()
    tab.files[:] = [dict(path=str(sample), name=f"File {i}.pdf", pages=1, size_mb=0.01,
                         rotation=0, page_range="") for i in range(count)]
    start = time.perf_counter()
    tab.refresh_list()
    build_ms = (time.perf_counter() - start) * 1000
    # Gerçek görünür satırlar için bir Qt yerleşim turu verilir.
    deadline = time.monotonic() + 0.15
    while time.monotonic() < deadline:
        QApplication.processEvents()
        while not callbacks.empty():
            callbacks.get_nowait()()
    controls = sum(len(row.winfo_children()) for row in tab.rows)
    loaded = sum(bool(getattr(row, "_loaded", True)) for row in tab.rows)
    start = time.perf_counter()
    tab.clear()
    clear_ms = (time.perf_counter() - start) * 1000
    results.append(dict(files=count, build_ms=round(build_ms, 2), clear_ms=round(clear_ms, 2),
                        loaded_rows=loaded, child_controls=controls))
    if hasattr(tab, "_visible_timer") and tab._visible_timer is not None:
        tab._visible_timer.stop()
    if hasattr(tab, "_thumb_pool"):
        tab._thumb_pool.shutdown(wait=True, cancel_futures=True)
    root.destroy()
    QApplication.processEvents()
output.write_text(json.dumps(results, indent=2), encoding="utf-8")
print(json.dumps(results))
