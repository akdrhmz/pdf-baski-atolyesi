"""Per-file batch processing shared by the desktop dialog and regression tests."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

from core.gutter_engine import (ProcessCancelled, PdfProcessConfig, process_pdf,
                           same_path, scan_clipping, unique_output_path, verify_output)


@dataclass(frozen=True)
class BatchItemResult:
    source: str
    output: str = ""
    state: str = ""
    detail: str = ""


def run_batch(
    files: Iterable[str], output_dir: str, config: PdfProcessConfig, *,
    skip_clipping: bool = True, should_cancel: Optional[Callable[[], bool]] = None,
    progress: Optional[Callable[[int, int, BatchItemResult], None]] = None,
) -> list[BatchItemResult]:
    """Process and verify each PDF separately, preserving successful earlier items."""
    sources = list(dict.fromkeys(os.path.abspath(os.fspath(path)) for path in files))
    target_dir = os.path.abspath(output_dir)
    os.makedirs(target_dir, exist_ok=True)
    results: list[BatchItemResult] = []
    for index, source in enumerate(sources, 1):
        if should_cancel and should_cancel():
            results.append(BatchItemResult(source, state="İptal edildi"))
            break
        target = unique_output_path(os.path.join(target_dir, f"{Path(source).stem}_islenmis.pdf"))
        try:
            if same_path(source, target):
                raise ValueError("Çıktı kaynak dosyayla aynı olamaz.")
            clipping = scan_clipping(source, config, should_cancel=should_cancel)
            if clipping.has_issues and skip_clipping:
                result = BatchItemResult(source, state="Atlandı",
                                         detail=clipping.summary(limit=1).replace("\n", " "))
            else:
                process_pdf(source, target, config, should_cancel=should_cancel)
                verified = verify_output(source, target, config, should_cancel=should_cancel)
                if clipping.has_issues or not verified.ok:
                    detail = " ".join(verified.lines()[:3])
                    if clipping.has_issues:
                        detail = "Kırpma riski kullanıcı seçimiyle kabul edildi. " + detail
                    result = BatchItemResult(source, target, "Uyarı",
                                             detail or "Doğrulama uyarısı var.")
                else:
                    result = BatchItemResult(source, target, "Tamamlandı")
        except ProcessCancelled:
            result = BatchItemResult(source, state="İptal edildi")
            results.append(result)
            if progress:
                progress(index, len(sources), result)
            break
        except Exception as exc:
            result = BatchItemResult(source, state="Hata", detail=str(exc))
        results.append(result)
        if progress:
            progress(index, len(sources), result)
        if should_cancel and should_cancel():
            break
    return results
