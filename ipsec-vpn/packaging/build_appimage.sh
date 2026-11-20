#!/bin/bash
# Build IPSec-VPN-Design-By-Rashid-<ver>-x86_64.AppImage.  Needs: uv, curl, the project sources.
# Usage: packaging/build_appimage.sh [workdir]     (default: ./build)
set -euo pipefail
SRC="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(realpath -m "${1:-$SRC/build}")"
VER="$(sed -n 's/__version__ = "\(.*\)"/\1/p' "$SRC/ipsec_vpn/__init__.py")"
APPDIR="$WORK/AppDir"
export UV_PYTHON_INSTALL_DIR="$WORK/pyroot"
mkdir -p "$WORK"; cd "$WORK"

echo "==> portable Python"
uv python install 3.12 >/dev/null
PYSRC="$(echo "$UV_PYTHON_INSTALL_DIR"/cpython-3.12.*-linux-x86_64-gnu | awk '{print $1}')"
rm -rf "$APPDIR"; mkdir -p "$APPDIR/usr/app"
cp -aL "$PYSRC" "$APPDIR/usr/python"
PY="$APPDIR/usr/python/bin/python3"

echo "==> PyQt5"
uv pip install -q --python "$PY" --target "$APPDIR/usr/lib/site" PyQt5

echo "==> prune"
P="$APPDIR/usr/python/lib/python3.12"
rm -rf "$P"/test "$P"/idlelib "$P"/tkinter "$P"/turtledemo "$P"/ensurepip "$P"/lib2to3 "$P"/site-packages \
       "$P"/config-3.12-x86_64-linux-gnu "$APPDIR"/usr/python/share "$APPDIR"/usr/python/include \
       "$APPDIR"/usr/python/bin/{idle3*,2to3*,pip*,python3-config,python3.12-config,pydoc*}
rm -f "$P"/lib-dynload/_tkinter*.so "$P"/lib-dynload/_test*.so
find "$APPDIR/usr/python" -name '__pycache__' -type d -prune -exec rm -rf {} +
Q="$APPDIR/usr/lib/site/PyQt5"
rm -rf "$Q/Qt5/qml" "$Q/Qt5/translations" "$Q/Qt5/qsci" "$Q/bindings" "$Q/uic" "$APPDIR/usr/lib/site/bin"
cd "$Q/Qt5/lib"
for f in libQt5*.so.5; do
  case "$f" in libQt5Core*|libQt5DBus*|libQt5Gui*|libQt5Network*|libQt5Widgets*|libQt5XcbQpa*|libQt5Svg*|libQt5WaylandClient*|libQt5XkbCommonSupport*) ;; *) rm -f "$f";; esac
done
cd "$Q/Qt5/plugins"
for d in */; do
  case "${d%/}" in platforms|platforminputcontexts|platformthemes|imageformats|iconengines|xcbglintegrations|wayland-*|generic) ;; *) rm -rf "$d";; esac
done
cd "$Q/Qt5/plugins/platforms"
for f in *.so; do case "$f" in libqxcb*|libqoffscreen*|libqminimal.so|libqwayland-generic*|libqwayland-egl*) ;; *) rm -f "$f";; esac; done
cd "$Q"
for f in *.abi3.so; do
  case "$f" in QtCore*|QtDBus*|QtGui*|QtNetwork*|QtWidgets*|QtSvg*|Qt.abi3.so) ;; *) rm -f "$f";; esac
done
rm -f pylupdate.abi3.so pyrcc.abi3.so _QOpenGLFunctions_*.so

echo "==> app files"
cp -r "$SRC/ipsec_vpn" "$APPDIR/usr/app/"
rm -rf "$APPDIR/usr/app/ipsec_vpn/__pycache__"
cat > "$APPDIR/AppRun" <<'RUN'
#!/bin/sh
HERE="$(dirname "$(readlink -f "$0")")"
export PYTHONPATH="$HERE/usr/app:$HERE/usr/lib/site"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONNOUSERSITE=1
export QT_PLUGIN_PATH="$HERE/usr/lib/site/PyQt5/Qt5/plugins"
exec "$HERE/usr/python/bin/python3" -s -m ipsec_vpn.app "$@"
RUN
chmod +x "$APPDIR/AppRun"
cat > "$APPDIR/ipsec-vpn.desktop" <<'DESK'
[Desktop Entry]
Type=Application
Name=IPSec VPN - Design By Rashid
Comment=IPsec VPN client for FortiGate (FortiClient configs)
Exec=ipsec-vpn
Icon=ipsec-vpn
Categories=Network;Security;
Terminal=false
StartupWMClass=ipsec-vpn
DESK
QT_QPA_PLATFORM=offscreen PYTHONPATH="$APPDIR/usr/app:$APPDIR/usr/lib/site" "$PY" -s -c "
from PyQt5 import QtWidgets
from ipsec_vpn import qt_app
a = QtWidgets.QApplication([])
qt_app.make_pixmap('on', 256).save('$APPDIR/ipsec-vpn.png')"
ln -sf ipsec-vpn.png "$APPDIR/.DirIcon"

echo "==> appimage"
[ -x "$WORK/appimagetool" ] || { curl -sL -o "$WORK/appimagetool" https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage; chmod +x "$WORK/appimagetool"; }
OUT="$WORK/IPSec-VPN-Design-By-Rashid-$VER-x86_64.AppImage"
rm -f "$OUT"
ARCH=x86_64 "$WORK/appimagetool" --appimage-extract-and-run "$APPDIR" "$OUT" 2>&1 | tail -5
chmod +x "$OUT"; ls -la "$OUT"
