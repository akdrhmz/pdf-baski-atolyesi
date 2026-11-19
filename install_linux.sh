#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

echo "=== PDF Baskı Atölyesi — Linux Kurulumu ==="

# 1. Uygun Python sürümünü bul (3.12 -> 3.11 -> 3.10 -> python3)
PYTHON_BIN=""
for candidate in python3.12 python3.11 python3.13 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
        PYTHON_BIN="$candidate"
        break
    fi
done

if [[ -z "$PYTHON_BIN" ]]; then
    echo "HATA: Python 3.10+ bulunamadı." >&2
    exit 1
fi

# 2. Sanal ortam ve bağımlılıklar
if [[ ! -x ".venv/bin/python" ]]; then
    echo "[1/3] Sanal ortam (.venv) oluşturuluyor ($PYTHON_BIN)..."
    "$PYTHON_BIN" -m venv .venv
fi

echo "[2/3] Bağımlılıklar kontrol ediliyor..."
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt

chmod +x "$APP_DIR/baslat.sh"

# 3. Kullanıcı uygulama menüsü (.desktop) ve ikon kurulumu (root gerektirmez)
ICON_DIR="$HOME/.local/share/icons/hicolor/512x512/apps"
APP_MENU_DIR="$HOME/.local/share/applications"
mkdir -p "$ICON_DIR" "$APP_MENU_DIR"

cp "$APP_DIR/assets/icon.png" "$ICON_DIR/pdf-baski-atolyesi.png"

cat > "$APP_MENU_DIR/pdf-baski-atolyesi.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=PDF Baskı Atölyesi
Comment=Vektörel PDF baskı, cilt payı, numaralandırma ve montaj atölyesi
Exec=$APP_DIR/baslat.sh %f
Icon=$ICON_DIR/pdf-baski-atolyesi.png
Terminal=false
Categories=Office;Publishing;Utility;
MimeType=application/pdf;
StartupWMClass=pdf-baski-atolyesi
EOF

chmod +x "$APP_MENU_DIR/pdf-baski-atolyesi.desktop"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APP_MENU_DIR" >/dev/null 2>&1 || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true
command -v kbuildsycoca6 >/dev/null 2>&1 && kbuildsycoca6 >/dev/null 2>&1 || true

echo "[3/3] Kurulum tamamlandı!"
echo "Uygulama menüsünden 'PDF Baskı Atölyesi' olarak başlatabilir"
echo "veya PDF dosyalarına sağ tıklayıp 'Birlikte Aç' ile seçebilirsiniz."
