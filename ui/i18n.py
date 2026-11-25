"""Görünen metinler çevrilir; ayar kodları ve kullanıcı girdileri değişmez."""
import json
from pathlib import Path
import re
from string import Formatter

_language = "tr"
_catalog = {}
_templates = []


def set_language(language):
    global _language, _catalog, _templates
    _language = language if language in ("tr", "en") else "tr"
    root = Path(__file__).resolve().parent.parent / "locales"
    try:
        _catalog = json.loads((root / f"{_language}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        _catalog = {}
    _templates = []
    templates = _catalog.get("_templates", {})
    for source, target in sorted(templates.items(), key=lambda pair: len(pair[0]), reverse=True):
        parts = []
        for literal, field, _spec, _conversion in Formatter().parse(source):
            parts.append(re.escape(literal))
            if field is not None:
                parts.append(f"(?P<{field}>.+?)")
        _templates.append((re.compile("".join(parts), re.DOTALL), target))


def tr(text):
    text = str(text)
    if _language == "tr":
        return text
    if text in _catalog and isinstance(_catalog[text], str):
        return _catalog[text]
    if "\n" in text:
        return "\n".join(tr(line) for line in text.split("\n"))
    stripped = text.strip()
    if stripped and stripped != text:
        start = len(text) - len(text.lstrip())
        end = len(text.rstrip())
        return text[:start] + tr(stripped) + text[end:]
    bullet = re.fullmatch(r"([•✔✘]\s*)(.+)", text)
    if bullet:
        return bullet[1] + tr(bullet[2])
    for pattern, target in _templates:
        match = pattern.fullmatch(text)
        if match:
            values = match.groupdict()
            for field in ("message", "details"):
                if field in values:
                    values[field] = ", ".join(tr(part) for part in values[field].split(", "))
            return target.format_map(values)
    # Yalnız bilinen arayüz kalıpları; dosya adları ve kullanıcı metinlerine
    # kelime kelime çeviri uygulanmaz.
    for pattern, replacement in (
        (r"^(\d+)\. (Sayfa Düzeni|Sayfa Numaraları|Birleştirme|Baskı ve Araçlar)$",
         lambda m: f"{m[1]}. {tr(m[2])}"),
        (r"^(\d+)\. sayfa$", lambda m: f"Page {m[1]}"),
        (r"^(\d+)\. sayfa · (\d+)°$", lambda m: f"Page {m[1]} · {m[2]}°"),
        (r"^(\d+)\. sayfa \(damga/Bates\)$", lambda m: f"Page {m[1]} (stamp/Bates)"),
        (r"^(\d+)\. Yaprak · (Ön|Arka) \[(.+)\]$",
         lambda m: f"Sheet {m[1]} · {'Front' if m[2] == 'Ön' else 'Back'} [{m[3]}]"),
        (r"^Yaprak (\d+) \[(.+)\]$", lambda m: f"Sheet {m[1]} [{m[2]}]"),
        (r"^(Ayarlar|Hakkında|Yazdır) - (.+)$", lambda m: f"{tr(m[1])} - {m[2]}"),
        (r"^Toplam: (\d+) dosya \| (\d+) sayfa(.*)$",
         lambda m: f"Total: {m[1]} files | {m[2]} pages{m[3]}"),
    ):
        if re.match(pattern, text):
            return re.sub(pattern, replacement, text)
    return text


def refresh_widgets(root):
    from PySide6.QtWidgets import QWidget
    for widget in [root] + root.findChildren(QWidget):
        props = getattr(widget, "_props", {})
        if "text" in props and hasattr(widget, "setText"):
            widget.setText(tr(props["text"]))
        if hasattr(widget, "refresh_language"):
            widget.refresh_language()
        widget.updateGeometry()
        widget.update()
