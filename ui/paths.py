"""Proje dizinleri (tek kaynak)."""

from __future__ import annotations

import os

# ``ui/`` bir üst dizini proje köküdür (PyInstaller'da ``sys._MEIPASS``); ``assets`` onun altındadır.
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(ROOT_DIR, "assets")
