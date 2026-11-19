"""Tanılama paketi: günlük + anonim ayar + sürüm/ortam bilgisi → tek ``.zip``.

Qt'siz çalışır (test edilebilir). Kişisel veri sızmasın diye:
- ayarlardan son dosya listesi ve yol içeren değerler çıkarılır,
- günlükte kullanıcı klasörü ve kullanıcı adı maskelenir.
"""

from __future__ import annotations

import json
import os
import platform
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

from core.version import APP_NAME, VERSION

PATH_MASK = "<yol>"
_WIN_PATH = re.compile(r"^[A-Za-z]:[\\/]")
_UNC_PATH = re.compile(r"^\\\\")
# Ayar anahtarları: değeri tümüyle çıkarılır.
_DROP_KEYS = {"recent_files"}


def _looks_like_path(value: str) -> bool:
    return bool(_WIN_PATH.match(value) or _UNC_PATH.match(value) or value.startswith("/"))


def anonymize_settings(data: Any) -> Any:
    """Ayar ağacının kopyasını döndürür; yol benzeri metinleri maskeler."""
    if isinstance(data, dict):
        return {key: anonymize_settings(val) for key, val in data.items()
                if key not in _DROP_KEYS}
    if isinstance(data, list):
        return [anonymize_settings(item) for item in data]
    if isinstance(data, str) and _looks_like_path(data):
        return PATH_MASK
    return data


def scrub_text(text: str, home: Optional[str] = None, user: Optional[str] = None) -> str:
    """Günlük metninde kullanıcı klasörünü ve kullanıcı adını maskeler."""
    home = home if home is not None else str(Path.home())
    user = user if user is not None else (os.environ.get("USERNAME") or os.environ.get("USER") or "")
    for variant in {home, home.replace("\\", "/"), home.replace("/", "\\")}:
        if variant and len(variant) > 3:
            text = re.sub(re.escape(variant), "~", text, flags=re.IGNORECASE)
    if user and len(user) >= 3:
        text = re.sub(rf"(?<![A-Za-z0-9_]){re.escape(user)}(?![A-Za-z0-9_])", "<kullanici>",
                      text, flags=re.IGNORECASE)
    return text


def _lib_version(name: str) -> str:
    try:
        module = __import__(name)
        return str(getattr(module, "__version__", None) or getattr(module, "VersionBind", "?"))
    except Exception:
        return "yok"


def collect_info(screen: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Sürüm, işletim sistemi, kütüphane sürümleri ve (varsa) ekran/DPI bilgisi."""
    return {
        "uygulama": APP_NAME,
        "surum": VERSION,
        "olusturma": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "python": sys.version.split()[0],
        "isletim_sistemi": platform.platform(),
        "PySide6": _lib_version("PySide6"),
        "PyMuPDF": _lib_version("pymupdf") if _lib_version("pymupdf") != "yok" else _lib_version("fitz"),
        "Pillow": _lib_version("PIL"),
        "ekran": screen or {},
    }


def default_filename() -> str:
    return f"PDFBaskiCiltStudyosu_tanilama_{datetime.now():%Y%m%d_%H%M%S}.zip"


def _log_files(log_path: Path) -> Iterable[Path]:
    # studio.log (+ dönen yedekler studio.log.1 … .3)
    for suffix in ("", ".1", ".2", ".3"):
        candidate = Path(str(log_path) + suffix)
        if candidate.is_file():
            yield candidate


def build_diagnostics_zip(dest: os.PathLike, settings: Dict[str, Any], log_path: os.PathLike,
                          screen: Optional[Dict[str, Any]] = None) -> Path:
    """Paketi ``dest`` yoluna yazar (önce ``.part``, sonra atomik taşıma)."""
    dest = Path(dest)
    part = dest.with_name(dest.name + ".part")
    try:
        with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr("bilgi.json", json.dumps(collect_info(screen), ensure_ascii=False, indent=2))
            bundle.writestr("ayarlar_anonim.json",
                            json.dumps(anonymize_settings(settings), ensure_ascii=False, indent=2))
            for log_file in _log_files(Path(log_path)):
                try:
                    raw = log_file.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                bundle.writestr(f"gunluk/{log_file.name}", scrub_text(raw))
            bundle.writestr("OKU.txt", (
                "Bu paket yalnızca sorun giderme içindir.\n"
                "Dosya adları/yolları ve son kullanılan dosya listesi çıkarılmıştır;\n"
                "günlükte kullanıcı klasörü ve kullanıcı adı maskelenmiştir.\n"
                "PDF içeriği pakete dahil edilmez. Göndermeden önce gözden geçirebilirsiniz.\n"))
        os.replace(part, dest)
    except Exception:
        try:
            part.unlink()
        except OSError:
            pass
        raise
    return dest
