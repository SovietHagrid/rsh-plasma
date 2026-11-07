#!/usr/bin/env bash
# Construit l'AppImage.   Usage : packaging/build.sh <archive-du-thème.tar.gz> [sortie]
# Nécessite : curl, tar, readelf (binutils), accès à github.com et pypi.org.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
ARCHIVE="$(readlink -f "${1:?archive du thème (.tar.gz) requise}")"
OUT="${2:-$HERE/dist}"
WORK="${WORK:-$HERE/.build}"
CACHE="${CACHE:-$HERE/.cache}"
PYAPP_URL="https://github.com/niess/python-appimage/releases/download/python3.12/python3.12.15-cp312-cp312-manylinux2014_x86_64.AppImage"
TOOL_URL="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"

# version du thème d'après le nom de l'archive : rsh_plasma_a1_9_tar.gz -> a1.9
REL="$(basename "$ARCHIVE" | sed -E 's/.*_(a[0-9]+)_([0-9]+).*/\1.\2/')"
case "$REL" in a*.*) ;; *) REL="inconnue" ;; esac
echo "▸ thème : $REL"

mkdir -p "$CACHE" "$OUT"; rm -rf "$WORK"; mkdir -p "$WORK"
[ -f "$CACHE/python.AppImage" ] || curl -fsSL -o "$CACHE/python.AppImage" "$PYAPP_URL"
[ -f "$CACHE/appimagetool" ]    || curl -fsSL -o "$CACHE/appimagetool" "$TOOL_URL"
chmod +x "$CACHE/python.AppImage" "$CACHE/appimagetool"

echo "▸ runtime Python"
( cd "$WORK" && "$CACHE/python.AppImage" --appimage-extract >/dev/null && mv squashfs-root AppDir )
APPDIR="$WORK/AppDir"
PY="$APPDIR/opt/python3.12/bin/python3.12"
rm -f "$APPDIR"/python3.12.15.desktop "$APPDIR"/python.png

echo "▸ PySide6"
"$PY" -m pip install --no-cache-dir --disable-pip-version-check -q PySide6-Essentials
SP="$("$PY" -c 'import site;print(site.getsitepackages()[0])')"

echo "▸ icône"
mkdir -p "$WORK/theme"; tar -xzf "$ARCHIVE" -C "$WORK/theme" 2>/dev/null
STAR="$WORK/theme/share/plasma/look-and-feel/com.republiquehagridienne.zephyr/contents/splash/images/star.svg"
QT_QPA_PLATFORM=offscreen "$PY" - "$STAR" "$APPDIR/rsh-installer.png" <<'PYEOF'
import sys
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
app = QGuiApplication([])
img = QImage(256, 256, QImage.Format_ARGB32); img.fill(0)
p = QPainter(img); QSvgRenderer(sys.argv[1]).render(p); p.end(); img.save(sys.argv[2])
PYEOF
ln -sf rsh-installer.png "$APPDIR/.DirIcon"

echo "▸ élagage de PySide6"
python3 "$HERE/packaging/prune.py" "$SP"
echo "▸ libxcb-cursor (requise par Qt 6 sur X11, absente de certains systèmes)"
DEB_URL="http://archive.ubuntu.com/ubuntu/pool/universe/x/xcb-util-cursor/libxcb-cursor0_0.1.1-4ubuntu1_amd64.deb"
DEB_SHA="c9b5d1ad4af57397b1bd77e0a92750e34419def134c0282a0836ae9efc07cf64"
[ -f "$CACHE/libxcb-cursor0.deb" ] || curl -fsSL -o "$CACHE/libxcb-cursor0.deb" "$DEB_URL"
echo "$DEB_SHA  $CACHE/libxcb-cursor0.deb" | sha256sum -c - >/dev/null
( cd "$WORK" && rm -rf deb && mkdir deb && cd deb && ar x "$CACHE/libxcb-cursor0.deb" && tar -xf data.tar.xz )
cp "$WORK/deb/usr/lib/x86_64-linux-gnu/libxcb-cursor.so.0.0.0" "$SP/PySide6/Qt/lib/libxcb-cursor.so.0"
# Python : retire ce qui ne sert pas (tests, Tk, outils)
LIBPY="$APPDIR/opt/python3.12/lib/python3.12"
rm -rf "$LIBPY"/test "$LIBPY"/idlelib "$LIBPY"/tkinter "$LIBPY"/turtledemo "$LIBPY"/lib2to3 "$LIBPY"/ensurepip \
       "$LIBPY"/lib-dynload/_tkinter* "$APPDIR"/usr/share/tcltk "$APPDIR"/opt/python3.12/share \
       "$APPDIR"/opt/python3.12/include 2>/dev/null || true
find "$APPDIR" -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
rm -f "$APPDIR"/opt/python3.12/bin/pip* "$APPDIR"/opt/python3.12/bin/idle* "$APPDIR"/opt/python3.12/bin/2to3* "$APPDIR"/opt/python3.12/bin/pydoc*

echo "▸ application et thème"
RSH="$APPDIR/opt/rsh"; mkdir -p "$RSH/payload"
cp -r "$HERE/app/rsh_installer" "$HERE/app/launcher.py" "$RSH/"
sed -i "s/^THEME_RELEASE = .*/THEME_RELEASE = \"$REL\"/" "$RSH/rsh_installer/version.py"
cp -r "$WORK/theme/share" "$WORK/theme/apercu" "$WORK/theme/LICENSE.md" "$RSH/payload/"
chmod -R u+rwX,go+rX,go-w "$RSH"
"$PY" -E -s -m compileall -q "$RSH" >/dev/null
rm -f "$APPDIR/AppRun"   # lien symbolique du runtime d'origine : ne pas écrire à travers
cp "$HERE/packaging/AppRun" "$HERE/packaging/rsh-installer.desktop" "$APPDIR/"

chmod -R u+rwX,go+rX,go-w "$APPDIR"   # AppImage lisible par tous les utilisateurs

echo "▸ AppImage"
NAME="Installeur-Republique-Hagridienne-$REL-x86_64.AppImage"
ARCH=x86_64 "$CACHE/appimagetool" --appimage-extract-and-run "$APPDIR" "$OUT/$NAME" > "$WORK/appimagetool.log" 2>&1 \
  || { cat "$WORK/appimagetool.log"; exit 1; }
grep -i 'warning' "$WORK/appimagetool.log" || true
chmod +x "$OUT/$NAME"
ls -la "$OUT/$NAME"
