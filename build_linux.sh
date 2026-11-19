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
PKG_NAME="pdf-baski-atolyesi"
BUNDLE_NAME="PDFBaskiAtolyesi-v${APP_VER}-linux-x86_64"

echo "=== PDF Baskı Atölyesi v${APP_VER} — Linux Paketleme ==="
rm -rf build/ "dist/${PKG_NAME}" "dist/${BUNDLE_NAME}"

# 1. Yalnızca çalışma dosyalarıyla bağımsız ikili derle (tests/, docs/, .venv hariç)
.venv/bin/pyinstaller \
    --noconfirm \
    --windowed \
    --onedir \
    --name "$PKG_NAME" \
    --icon "assets/icon.png" \
    --add-data "assets:assets" \
    --add-data "locales:locales" \
    --exclude-module PySide6.QtWebEngineCore \
    --exclude-module PySide6.QtWebEngineWidgets \
    --exclude-module PySide6.Qt3DCore \
    --exclude-module PySide6.Qt3DRender \
    --exclude-module PySide6.QtQuick \
    --exclude-module PySide6.QtQml \
    --exclude-module PySide6.QtMultimedia \
    --exclude-module PySide6.QtCharts \
    --exclude-module tkinter \
    --hidden-import "core.gutter_engine" \
    --hidden-import "core.pdf_tools" \
    --hidden-import "core.page_layout_model" \
    --hidden-import "core.settings_store" \
    --hidden-import "core.diagnostics" \
    --hidden-import "core.version" \
    app.py

# 2. Venvsiz kurulabilir taşınabilir arşiv (.tar.gz + install.sh)
BUNDLE_DIR="dist/${BUNDLE_NAME}"
mkdir -p "$BUNDLE_DIR/app"
cp -a "dist/${PKG_NAME}/." "$BUNDLE_DIR/app/"
cp "assets/icon.png" "$BUNDLE_DIR/icon.png"

cat > "$BUNDLE_DIR/install.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="$HOME/.local/opt/pdf-baski-atolyesi"
ICON_DIR="$HOME/.local/share/icons/hicolor/512x512/apps"
APP_DIR="$HOME/.local/share/applications"

mkdir -p "$TARGET_DIR" "$ICON_DIR" "$APP_DIR"
rm -rf "$TARGET_DIR"/*
cp -a "$HERE/app/." "$TARGET_DIR/"
cp "$HERE/icon.png" "$ICON_DIR/pdf-baski-atolyesi.png"

cat > "$APP_DIR/pdf-baski-atolyesi.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=PDF Baskı Atölyesi
Comment=Vektörel PDF baskı, cilt payı, numaralandırma ve montaj atölyesi
Exec=$TARGET_DIR/pdf-baski-atolyesi %f
Icon=$ICON_DIR/pdf-baski-atolyesi.png
Terminal=false
Categories=Office;Publishing;Utility;
MimeType=application/pdf;
StartupWMClass=pdf-baski-atolyesi
DESK
chmod +x "$APP_DIR/pdf-baski-atolyesi.desktop"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true
command -v kbuildsycoca6 >/dev/null 2>&1 && kbuildsycoca6 >/dev/null 2>&1 || true
echo "Kuruldu: $TARGET_DIR (Python/venv gerektirmez)."
EOF

cat > "$BUNDLE_DIR/uninstall.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
rm -rf "$HOME/.local/opt/pdf-baski-atolyesi"
rm -f "$HOME/.local/share/applications/pdf-baski-atolyesi.desktop"
rm -f "$HOME/.local/share/icons/hicolor/512x512/apps/pdf-baski-atolyesi.png"
echo "Kaldırıldı."
EOF
chmod +x "$BUNDLE_DIR/install.sh" "$BUNDLE_DIR/uninstall.sh"

tar -C dist -czf "dist/${BUNDLE_NAME}.tar.gz" "$BUNDLE_NAME"
echo "Hazır (tüm Linuxlar): dist/${BUNDLE_NAME}.tar.gz"

# 3. Sistemde dpkg-deb varsa .deb kurulum paketi de üret
if command -v dpkg-deb >/dev/null 2>&1; then
    DEB_ROOT="build/deb/${PKG_NAME}_${APP_VER}_amd64"
    rm -rf "build/deb"
    mkdir -p "$DEB_ROOT/DEBIAN" "$DEB_ROOT/opt/${PKG_NAME}" \
             "$DEB_ROOT/usr/share/applications" \
             "$DEB_ROOT/usr/share/icons/hicolor/512x512/apps" \
             "$DEB_ROOT/usr/local/bin"
    cp -a "dist/${PKG_NAME}/." "$DEB_ROOT/opt/${PKG_NAME}/"
    cp "assets/icon.png" "$DEB_ROOT/usr/share/icons/hicolor/512x512/apps/${PKG_NAME}.png"
    ln -sf "/opt/${PKG_NAME}/${PKG_NAME}" "$DEB_ROOT/usr/local/bin/${PKG_NAME}"
    cat > "$DEB_ROOT/usr/share/applications/${PKG_NAME}.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=PDF Baskı Atölyesi
Comment=Vektörel PDF baskı, cilt payı, numaralandırma ve montaj atölyesi
Exec=/opt/${PKG_NAME}/${PKG_NAME} %f
Icon=/usr/share/icons/hicolor/512x512/apps/${PKG_NAME}.png
Terminal=false
Categories=Office;Publishing;Utility;
MimeType=application/pdf;
StartupWMClass=pdf-baski-atolyesi
DESK
    cat > "$DEB_ROOT/DEBIAN/control" <<CTRL
Package: ${PKG_NAME}
Version: ${APP_VER}
Section: utils
Priority: optional
Architecture: amd64
Maintainer: Abdulkadir Hamza <support@kadirhamza.com>
Description: Vektorel PDF baski, cilt payi, numaralandirma ve montaj atolyesi
CTRL
    dpkg-deb --build "$DEB_ROOT" "dist/${PKG_NAME}_${APP_VER}_amd64.deb"
    echo "Hazır (Debian/Ubuntu/Pardus): dist/${PKG_NAME}_${APP_VER}_amd64.deb"
fi

# 4. Sistemde rpmbuild varsa .rpm kurulum paketi de üret (Fedora/RHEL/openSUSE)
if command -v rpmbuild >/dev/null 2>&1; then
    RPM_TOP="$APP_DIR/build/rpm"
    rm -rf "$RPM_TOP"
    mkdir -p "$RPM_TOP"/{BUILD,RPMS,SOURCES,SPECS,SRPMS}
    cat > "$RPM_TOP/SPECS/${PKG_NAME}.spec" <<SPEC
%global debug_package %{nil}
AutoReqProv: no

Name:           ${PKG_NAME}
Version:        ${APP_VER}
Release:        1
Summary:        Vektorel PDF baski, cilt payi, numaralandirma ve montaj atolyesi
License:        MIT
URL:            https://github.com/akdrhmz/pdf-baski-cilt-studyosu

%description
PyMuPDF ve PySide6 tabanli kayipsiz PDF baski, cilt payi, numaralandirma ve kitapcik montaj uygulamasi.

%install
mkdir -p %{buildroot}/opt/${PKG_NAME}
mkdir -p %{buildroot}/usr/local/bin
mkdir -p %{buildroot}/usr/share/applications
mkdir -p %{buildroot}/usr/share/icons/hicolor/512x512/apps
cp -a "${APP_DIR}/dist/${PKG_NAME}/." "%{buildroot}/opt/${PKG_NAME}/"
cp "${APP_DIR}/assets/icon.png" "%{buildroot}/usr/share/icons/hicolor/512x512/apps/${PKG_NAME}.png"
ln -sf "/opt/${PKG_NAME}/${PKG_NAME}" "%{buildroot}/usr/local/bin/${PKG_NAME}"
cat > "%{buildroot}/usr/share/applications/${PKG_NAME}.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=PDF Baskı Atölyesi
Comment=Vektörel PDF baskı, cilt payı, numaralandırma ve montaj atölyesi
Exec=/opt/${PKG_NAME}/${PKG_NAME} %f
Icon=/usr/share/icons/hicolor/512x512/apps/${PKG_NAME}.png
Terminal=false
Categories=Office;Publishing;Utility;
MimeType=application/pdf;
StartupWMClass=pdf-baski-atolyesi
DESK

%files
/opt/${PKG_NAME}
/usr/local/bin/${PKG_NAME}
/usr/share/applications/${PKG_NAME}.desktop
/usr/share/icons/hicolor/512x512/apps/${PKG_NAME}.png
SPEC
    rpmbuild --define "_topdir ${RPM_TOP}" -bb "$RPM_TOP/SPECS/${PKG_NAME}.spec"
    find "$RPM_TOP/RPMS" -name "*.rpm" -exec cp {} "$APP_DIR/dist/" \;
    echo "Hazır (Fedora/RHEL): dist/${PKG_NAME}-${APP_VER}-1.x86_64.rpm"
fi
