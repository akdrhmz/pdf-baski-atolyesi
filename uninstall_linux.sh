#!/usr/bin/env bash
set -euo pipefail

rm -f "$HOME/.local/share/applications/pdf-baski-atolyesi.desktop"
rm -f "$HOME/.local/share/icons/hicolor/512x512/apps/pdf-baski-atolyesi.png"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true
fi

echo "PDF Baskı Atölyesi masaüstü kısayolu ve ikonu kaldırıldı."
