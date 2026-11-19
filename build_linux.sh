#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

if [[ ! -x ".venv/bin/python" ]]; then
    echo "Önce ./install_linux.sh ile .venv ortamını kurun." >&2
    exit 1
fi

if ! .venv/bin/python -c "import PyInstaller" >/dev/null 2>&1; then
    echo "PyInstaller kuruluyor..."
    .venv/bin/pip install --quiet "pyinstaller>=6"
fi

APP_VER="$(.venv/bin/python -c "from core import version; print(version.VERSION)")"
OUT_NAME="PDFBaskiAtolyesi-v${APP_VER}-linux-x86_64"

echo "Linux paketi derleniyor ($OUT_NAME)..."
rm -rf build/ dist/"$OUT_NAME"

.venv/bin/pyinstaller \
    --noconfirm \
    --windowed \
    --name "$OUT_NAME" \
    --icon "assets/icon.png" \
    --add-data "assets:assets" \
    --add-data "locales:locales" \
    --hidden-import "core.gutter_engine" \
    --hidden-import "core.pdf_tools" \
    --hidden-import "core.page_layout_model" \
    --hidden-import "core.settings_store" \
    --hidden-import "core.diagnostics" \
    --hidden-import "core.version" \
    app.py

echo "Arşivleniyor..."
tar -C dist -czf "dist/${OUT_NAME}.tar.gz" "$OUT_NAME"
echo "Hazır: dist/${OUT_NAME}/ ve dist/${OUT_NAME}.tar.gz"
