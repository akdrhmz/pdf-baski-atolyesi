#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

if [[ ! -x ".venv/bin/python" ]]; then
    echo "Önce .venv ortamı oluşturuluyor..."
    PYTHON_BIN="$(command -v python3.12 || command -v python3.11 || command -v python3 || true)"
    if [[ -z "$PYTHON_BIN" ]]; then
        echo "HATA: Python 3.10+ bulunamadı." >&2
        exit 1
    fi
    "$PYTHON_BIN" -m venv .venv
    .venv/bin/pip install --quiet --upgrade pip
    .venv/bin/pip install --quiet -r requirements.txt
fi

WANT_RPM=0
WANT_DEB=0

if [[ $# -eq 0 ]]; then
    echo "=== PDF Baskı Atölyesi — Linux Paketleme ==="
    echo "Hangi paketler üretilsin?"
    echo "  1) Yalnız taşınabilir .tar.gz (tüm Linux dağıtımları)"
    echo "  2) .rpm + .tar.gz (Fedora / RHEL / openSUSE)"
    echo "  3) .deb + .tar.gz (Debian / Ubuntu / Pardus / Mint)"
    echo "  4) Tümü (.tar.gz + .rpm + .deb)"
    read -rp "Seçiminiz [1-4, varsayılan 4]: " CHOICE
    CHOICE="${CHOICE:-4}"
    case "$CHOICE" in
        1) ;;
        2) WANT_RPM=1 ;;
        3) WANT_DEB=1 ;;
        4) WANT_RPM=1; WANT_DEB=1 ;;
        *) echo "Geçersiz seçim." >&2; exit 1 ;;
    esac
else
    for arg in "$@"; do
        case "$arg" in
            --rpm) WANT_RPM=1 ;;
            --deb) WANT_DEB=1 ;;
            --all) WANT_RPM=1; WANT_DEB=1 ;;
            --tar) ;;
            *) echo "Bilinmeyen parametre: $arg (kullanım: --tar | --rpm | --deb | --all)" >&2; exit 1 ;;
        esac
    done
fi

install_pkg() {
    local pkg_fedora="$1" pkg_debian="$2" pkg_arch="$3"
    if command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y "$pkg_fedora"
    elif command -v apt-get >/dev/null 2>&1; then
        sudo apt-get update && sudo apt-get install -y "$pkg_debian"
    elif command -v pacman >/dev/null 2>&1; then
        sudo pacman -Sy --noconfirm "$pkg_arch"
    else
        echo "Otomatik paket yöneticisi bulunamadı; lütfen '$pkg_fedora' / '$pkg_debian' elle kurun." >&2
        return 1
    fi
}

if [[ "$WANT_RPM" -eq 1 ]] && ! command -v rpmbuild >/dev/null 2>&1; then
    echo "'rpmbuild' kurulu değil; kurulum başlatılıyor (sudo şifresi istenebilir)..."
    install_pkg "rpm-build" "rpm" "rpm-tools"
fi

if [[ "$WANT_DEB" -eq 1 ]] && ! command -v dpkg-deb >/dev/null 2>&1; then
    echo "'dpkg-deb' kurulu değil; kurulum başlatılıyor (sudo şifresi istenebilir)..."
    install_pkg "dpkg" "dpkg" "dpkg"
fi

if ! .venv/bin/python -c "import PyInstaller" >/dev/null 2>&1; then
    echo "PyInstaller kuruluyor..."
    .venv/bin/pip install --quiet "pyinstaller>=6"
fi

APP_VER="$(.venv/bin/python -c "from core import version; print(version.VERSION)")"
PKG_NAME="pdf-baski-atolyesi"
BUNDLE_NAME="PDFBaskiAtolyesi-v${APP_VER}-linux-x86_64"

echo "=== PDF Baskı Atölyesi v${APP_VER} Derleniyor ==="
rm -rf build/ "dist/${PKG_NAME}" "dist/${BUNDLE_NAME}"

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

# Taşınabilir .tar.gz paketi (venvsiz install.sh içerir)
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
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true
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

if [[ "$WANT_DEB" -eq 1 ]] && command -v dpkg-deb >/dev/null 2>&1; then
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
    cat > "$DEB_ROOT/DEBIAN/postinst" <<'POST'
#!/bin/sh
set -e
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database /usr/share/applications >/dev/null 2>&1 || true
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -f -t /usr/share/icons/hicolor >/dev/null 2>&1 || true
exit 0
POST
    cp "$DEB_ROOT/DEBIAN/postinst" "$DEB_ROOT/DEBIAN/postrm"
    chmod 0755 "$DEB_ROOT/DEBIAN/postinst" "$DEB_ROOT/DEBIAN/postrm"
    dpkg-deb --build "$DEB_ROOT" "dist/${PKG_NAME}_${APP_VER}_amd64.deb"
    echo "Hazır (Debian/Ubuntu/Pardus): dist/${PKG_NAME}_${APP_VER}_amd64.deb"
fi

if [[ "$WANT_RPM" -eq 1 ]] && command -v rpmbuild >/dev/null 2>&1; then
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
URL:            https://github.com/akdrhmz/pdf-baski-atolyesi

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

%post
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database /usr/share/applications >/dev/null 2>&1 || :
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -f -t /usr/share/icons/hicolor >/dev/null 2>&1 || :

%postun
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database /usr/share/applications >/dev/null 2>&1 || :
command -v gtk-update-icon-cache >/dev/null 2>&1 && gtk-update-icon-cache -f -t /usr/share/icons/hicolor >/dev/null 2>&1 || :

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
