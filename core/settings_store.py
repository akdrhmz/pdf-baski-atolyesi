"""
PDF Baskı & Cilt Stüdyosu - Kalıcı ayarlar, profil deposu ve günlük kaydı.

Tüm kullanıcı verisi Windows'un standart uygulama klasörlerinde tutulur:
- Ayarlar/profiller: %APPDATA%\\PDFBaskiCiltStudyosu\\settings.json
- Günlük:            %LOCALAPPDATA%\\PDFBaskiCiltStudyosu\\studio.log

Yazma işlemleri atomiktir (geçici dosya + yer değiştirme); bozuk bir JSON
dosyası uygulamayı kilitlemez, yedeklenip varsayılanlarla devam edilir.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.gutter_engine import PdfProcessConfig, config_to_dict, config_from_dict

APP_FOLDER = "PDFBaskiCiltStudyosu"
SETTINGS_VERSION = 1
VALID_UNITS = ("mm", "cm", "pt")

def _default_app_dirs() -> tuple[Path, Path]:
    """İşletim sistemine uygun ayar ve günlük kök dizinlerini döndürür."""
    if sys.platform.startswith("win"):
        appdata = Path(os.environ.get("APPDATA") or Path.home())
        local_appdata = Path(os.environ.get("LOCALAPPDATA") or appdata)
        return appdata, local_appdata
    if sys.platform == "darwin":
        support = Path.home() / "Library" / "Application Support"
        logs = Path.home() / "Library" / "Logs"
        return support, logs
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    state_home = Path(os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state"))
    return config_home, state_home


APPDATA, LOCALAPPDATA = _default_app_dirs()
SETTINGS_PATH = APPDATA / APP_FOLDER / "settings.json"
LOG_PATH = LOCALAPPDATA / APP_FOLDER / "studio.log"

THEMES = ("Açık", "Koyu", "Sistem")

# Hazır öneri profilleri. Değerler mm cinsindendir ve kullanıcı düzenleyebilir.
PRESETS: Dict[str, Dict[str, Any]] = {
    "Tez (üniversite)": {
        "page_boxes": {
            "enabled": True, "size_mode": "auto",
            "target_width_mm": 225.0, "target_height_mm": 297.0,
            "odd_x_mm": 20.0, "odd_y_mm": 0.0, "even_x_mm": 0.0, "even_y_mm": 0.0,
        },
        "margins": {
            "enabled": True, "extra_bottom_mm": 20.0, "extra_top_mm": 0.0,
            "bottom_mode": "expand",
        },
        "page_numbers": {
            "enabled": True, "position": "outer", "format_style": "dash",
            "start_num": 1, "start_page": 2, "font_size": 10.0,
            "font_color": [0.0, 0.0, 0.0], "bottom_margin_mm": 12.0,
            "side_margin_mm": 15.0, "skip_pages_str": "1",
            "skip_pages_set": [], "continuous_numbering": True,
        },
        "quality_mode": "print",
        "flatten_annotations": True,
    },
    "Spiral cilt": {
        "page_boxes": {
            "enabled": True, "size_mode": "auto",
            "target_width_mm": 220.0, "target_height_mm": 297.0,
            "odd_x_mm": 10.0, "odd_y_mm": 0.0, "even_x_mm": 0.0, "even_y_mm": 0.0,
        },
        "margins": {
            "enabled": True, "extra_bottom_mm": 0.0, "extra_top_mm": 8.0,
            "bottom_mode": "expand",
        },
        "page_numbers": {
            "enabled": True, "position": "outer", "format_style": "number",
            "start_num": 1, "start_page": 1, "font_size": 10.0,
            "font_color": [0.0, 0.0, 0.0], "bottom_margin_mm": 12.0,
            "side_margin_mm": 15.0, "skip_pages_str": "",
            "skip_pages_set": [], "continuous_numbering": True,
        },
        "quality_mode": "print",
        "flatten_annotations": True,
    },
    "Sıcak tutkal cilt": {
        "page_boxes": {
            "enabled": True, "size_mode": "auto",
            "target_width_mm": 230.0, "target_height_mm": 297.0,
            "odd_x_mm": 20.0, "odd_y_mm": 0.0, "even_x_mm": 0.0, "even_y_mm": 0.0,
        },
        "margins": {
            "enabled": True, "extra_bottom_mm": 15.0, "extra_top_mm": 0.0,
            "bottom_mode": "expand",
        },
        "page_numbers": {
            "enabled": True, "position": "center", "format_style": "number",
            "start_num": 1, "start_page": 1, "font_size": 10.0,
            "font_color": [0.0, 0.0, 0.0], "bottom_margin_mm": 12.0,
            "side_margin_mm": 15.0, "skip_pages_str": "",
            "skip_pages_set": [], "continuous_numbering": True,
        },
        "quality_mode": "print",
        "flatten_annotations": True,
    },
    "Kitapçık": {
        "page_boxes": {
            "enabled": True, "size_mode": "auto",
            "target_width_mm": 220.0, "target_height_mm": 297.0,
            "odd_x_mm": 10.0, "odd_y_mm": 0.0, "even_x_mm": 0.0, "even_y_mm": 0.0,
        },
        "margins": {
            "enabled": True, "extra_bottom_mm": 10.0, "extra_top_mm": 0.0,
            "bottom_mode": "expand",
        },
        "page_numbers": {
            "enabled": True, "position": "outer", "format_style": "number",
            "start_num": 1, "start_page": 1, "font_size": 9.0,
            "font_color": [0.0, 0.0, 0.0], "bottom_margin_mm": 10.0,
            "side_margin_mm": 12.0, "skip_pages_str": "",
            "skip_pages_set": [], "continuous_numbering": True,
        },
        "quality_mode": "print",
        "flatten_annotations": True,
    },
}


def presets_as_configs() -> Dict[str, PdfProcessConfig]:
    """Hazır profilleri doğrulanabilir ``PdfProcessConfig`` nesnelerine çevirir."""
    return {name: config_from_dict(data) for name, data in PRESETS.items()}


class SettingsStore:
    """JSON tabanlı dayanıklı ayar ve profil deposu."""

    def __init__(self, path: Optional[os.PathLike] = None):
        self.path = Path(path) if path else SETTINGS_PATH
        self.data: Dict[str, Any] = self._load()
        self._logger = logging.getLogger("studio")

    # -- düşük seviye -------------------------------------------------------
    def _defaults(self) -> Dict[str, Any]:
        return {
            "settings_version": SETTINGS_VERSION,
            "unit": "mm",
            "theme": "Sistem",
            "language": "tr",
            "auto_open_output": False,
            "merge_preview_sequence": False,
            "merge_handle_only": False,
            "page_size_policy": "dominant",
            "merge_fit": {},
            "preview_width": 480,
            "preview_on_top": True,
            "last_state": {},
            "profiles": {},
            "recent_files": [],
        }

    def _load(self) -> Dict[str, Any]:
        defaults = self._defaults()
        if not self.path.exists():
            return defaults
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            if not isinstance(loaded, dict):
                raise ValueError("settings.json bir nesne değil")
        except Exception as exc:  # bozuk JSON uygulamayı kilitlemesin
            backup = self.path.with_suffix(f".bozuk-{os.getpid()}.json")
            try:
                shutil.copy2(self.path, backup)
                logging.getLogger("studio").warning(
                    "Ayarlar okunamadı (%s); yedek: %s", exc, backup
                )
            except OSError:
                pass
            return defaults

        merged = defaults
        merged.update({k: v for k, v in loaded.items() if k in defaults})
        if not isinstance(merged.get("profiles"), dict):
            merged["profiles"] = {}
        if not isinstance(merged.get("last_state"), dict):
            merged["last_state"] = {}
        if not isinstance(merged.get("recent_files"), list):
            merged["recent_files"] = []
        if merged.get("unit") not in VALID_UNITS:
            merged["unit"] = "mm"
        if merged.get("theme") not in THEMES:
            merged["theme"] = "Sistem"
        if merged.get("language") not in ("tr", "en"):
            merged["language"] = "tr"
        if not isinstance(merged.get("auto_open_output"), bool):
            merged["auto_open_output"] = False
        for key in ("merge_preview_sequence", "merge_handle_only"):
            if not isinstance(merged.get(key), bool):
                merged[key] = False
        if not isinstance(merged.get("merge_fit"), dict):
            merged["merge_fit"] = {}
        return merged

    def reset(self) -> None:
        """Tüm ayarları fabrika değerlerine döndürür ve diske yazar."""
        self.data = self._defaults()
        self.save()

    def save(self) -> None:
        """Ayarları atomik olarak diske yazar; hata günlüğe düşer, akışı bozmaz."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix=".~", suffix=".json.tmp", dir=str(self.path.parent))
            os.close(fd)
            try:
                with open(tmp, "w", encoding="utf-8") as handle:
                    json.dump(self.data, handle, ensure_ascii=False, indent=2)
                os.replace(tmp, self.path)
            except Exception:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                raise
        except Exception as exc:
            logging.getLogger("studio").warning("Ayarlar kaydedilemedi: %s", exc)

    # -- basit alanlar ------------------------------------------------------
    @property
    def merge_preview_sequence(self) -> bool:
        return self.data.get("merge_preview_sequence", False) is True

    @merge_preview_sequence.setter
    def merge_preview_sequence(self, value: bool) -> None:
        self.data["merge_preview_sequence"] = bool(value)

    @property
    def merge_handle_only(self) -> bool:
        return self.data.get("merge_handle_only", False) is True

    @merge_handle_only.setter
    def merge_handle_only(self, value: bool) -> None:
        self.data["merge_handle_only"] = bool(value)

    @property
    def page_size_policy(self) -> str:
        """Karışık ebatlı PDF'te hedef için kullanılacak sayfa boyutu seçimi."""
        value = self.data.get("page_size_policy", "dominant")
        return value if value in ("first", "dominant", "largest") else "dominant"

    @page_size_policy.setter
    def page_size_policy(self, value: str) -> None:
        self.data["page_size_policy"] = value if value in ("first", "dominant", "largest") else "dominant"

    @property
    def preview_width(self) -> int:
        """Önizleme kolonunun kayıtlı genişliği (280–900 px arası)."""
        try:
            return max(280, min(900, int(self.data.get("preview_width", 480))))
        except (TypeError, ValueError):
            return 480

    @preview_width.setter
    def preview_width(self, value: int) -> None:
        self.data["preview_width"] = max(280, min(900, int(value)))

    @property
    def preview_on_top(self) -> bool:
        """Ayrı önizleme penceresi diğer pencerelerin üstünde kalsın mı (varsayılan: evet)."""
        return bool(self.data.get("preview_on_top", True))

    @preview_on_top.setter
    def preview_on_top(self, value: bool) -> None:
        self.data["preview_on_top"] = bool(value)

    @property
    def unit(self) -> str:
        return self.data.get("unit", "mm")

    @unit.setter
    def unit(self, value: str) -> None:
        if value in VALID_UNITS:
            self.data["unit"] = value

    @property
    def theme(self) -> str:
        return self.data.get("theme", "Sistem")

    @theme.setter
    def theme(self, value: str) -> None:
        if value in THEMES:
            self.data["theme"] = value

    @property
    def last_state(self) -> Dict[str, Any]:
        return dict(self.data.get("last_state") or {})

    @last_state.setter
    def last_state(self, state: Dict[str, Any]) -> None:
        if isinstance(state, dict):
            self.data["last_state"] = state

    @property
    def recent_files(self) -> List[str]:
        return list(self.data.get("recent_files") or [])

    def add_recent_file(self, path: str) -> None:
        if not path:
            return
        items = [p for p in self.recent_files if os.path.normcase(p) != os.path.normcase(path)]
        self.data["recent_files"] = ([path] + items)[:10]

    # -- profiller ----------------------------------------------------------
    def profile_names(self) -> List[str]:
        return sorted(self.data.get("profiles", {}).keys(), key=str.casefold)

    def get_profile(self, name: str) -> Optional[Dict[str, Any]]:
        value = self.data.get("profiles", {}).get(name)
        return dict(value) if isinstance(value, dict) else None

    def save_profile(self, name: str, config: PdfProcessConfig) -> None:
        name = (name or "").strip()
        if not name:
            raise ValueError("Profil adı boş olamaz.")
        self.data.setdefault("profiles", {})[name] = config_to_dict(config)
        self.save()

    def delete_profile(self, name: str) -> bool:
        profiles = self.data.get("profiles", {})
        if name in profiles:
            del profiles[name]
            self.save()
            return True
        return False


_logging_ready = False


def setup_logging(log_path: Optional[os.PathLike] = None) -> logging.Logger:
    """
    Uygulama günlüğünü kurar: 1 MB'ta dönen, 3 yedek tutan dosya + konsol.
    Aynı süreçte iki kez çağrılırsa yinelenen handler eklemez.
    """
    global _logging_ready
    logger = logging.getLogger("studio")
    logger.setLevel(logging.INFO)
    if _logging_ready:
        return logger

    target = Path(log_path) if log_path else LOG_PATH
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            target, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    except OSError:
        pass

    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    logger.addHandler(stream)
    logger.propagate = False
    _logging_ready = True
    return logger
