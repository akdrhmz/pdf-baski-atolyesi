"""Ölçüm yardımcısı: ``APP_PERF=1`` ortam değişkeniyle açılır, kapalıyken maliyeti sıfırdır.

Tema değişimi, sekme geçişi ve açılış sürelerini günlüğe yazar; ``withdraw()`` çağrılarını
sayar (tema geçişinde pencere hiç gizlenmemeli). Widget diyeti (Aşama 5) her adımdan önce
ve sonra bu çıktıyla ölçülür.
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from contextlib import nullcontext
from functools import wraps
from typing import Any, Dict, Iterator, List, Tuple

_LOG = logging.getLogger("studio.perf")


def record_ui(label):
    """Arayüz eylemlerini APP_PERF kaydına ekler; test sahteleri de uyumludur."""
    def decorate(function):
        @wraps(function)
        def measured(self, *args, **kwargs):
            recorder = getattr(getattr(self, "ctx", None), "perf", None) or getattr(self, "perf", None)
            measure = getattr(recorder, "measure", None)
            with measure(label) if measure else nullcontext():
                return function(self, *args, **kwargs)
        return measured
    return decorate


def perf_enabled() -> bool:
    return os.environ.get("APP_PERF", "").strip().lower() in ("1", "true", "yes", "on")


class PerfRecorder:
    """Etiket başına süre (ms) toplar; kapalıyken ``measure`` hiçbir şey yapmaz."""

    def __init__(self, enabled: bool | None = None):
        self.enabled = perf_enabled() if enabled is None else enabled
        self.samples: Dict[str, List[float]] = {}
        self.counters: Dict[str, int] = {}

    @contextmanager
    def measure(self, label: str) -> Iterator[None]:
        if not self.enabled:
            yield
            return
        start = time.perf_counter()
        try:
            yield
        finally:
            ms = (time.perf_counter() - start) * 1000.0
            self.samples.setdefault(label, []).append(ms)
            _LOG.info("PERF %s: %.1f ms", label, ms)

    def count(self, name: str) -> None:
        if self.enabled:
            self.counters[name] = self.counters.get(name, 0) + 1

    def summary(self) -> List[Tuple[str, int, float, float]]:
        """(etiket, örnek sayısı, ortalama ms, en yüksek ms)"""
        rows = []
        for label, values in sorted(self.samples.items()):
            rows.append((label, len(values), sum(values) / len(values), max(values)))
        return rows

    def widget_count(self, root: Any) -> int:
        """Pencere altındaki toplam widget sayısı (diyet öncesi/sonrası kıyası için)."""
        total = 0
        stack = [root]
        while stack:
            node = stack.pop()
            total += 1
            try:
                stack.extend(node.winfo_children())
            except Exception:
                pass
        return total - 1

    def log_summary(self, root: Any = None) -> None:
        if not self.enabled:
            return
        for label, n, avg, peak in self.summary():
            _LOG.info("PERF ÖZET %s: n=%d ort=%.1f ms en yüksek=%.1f ms", label, n, avg, peak)
        for name, value in sorted(self.counters.items()):
            _LOG.info("PERF SAYAÇ %s=%d", name, value)
        if root is not None:
            _LOG.info("PERF widget sayısı=%d", self.widget_count(root))
