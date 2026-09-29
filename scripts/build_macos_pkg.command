#!/bin/zsh
set -e
export COPYFILE_DISABLE=1 COPY_EXTENDED_ATTRIBUTES_DISABLE=1
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="$(python3 -c 'import sys,tomllib; print(tomllib.load(open(sys.argv[1],"rb"))["project"]["version"])' "$ROOT/pyproject.toml")"
APP_NAME="CRAFT"; EXECUTABLE="craft"; BUNDLE_ID="com.scitools.craft"; PKG_ID="com.scitools.craft.pkg"
PKG_NAME="CRAFT_macOS_${VERSION}.pkg"; DIST="$ROOT/dist"; WORK="$DIST/macos_pkg_build"; PAYLOAD="$WORK/payload"; SCRIPTS="$WORK/scripts"
APP="$PAYLOAD/Applications/$APP_NAME.app"; CONTENTS="$APP/Contents"; APP_ROOT="$CONTENTS/Resources/app"; PKG_PATH="$DIST/$PKG_NAME"
ICON_RELATIVE="assets/craft.ico"; ICON_SOURCE="$ROOT/$ICON_RELATIVE"
if [ "$1" = "--print-config" ]; then
  print -r -- "{\"app_name\":\"$APP_NAME\",\"bundle_id\":\"$BUNDLE_ID\",\"pkg_name\":\"$PKG_NAME\",\"install_path\":\"/Applications/$APP_NAME.app\",\"relocatable\":false,\"icon\":\"icon.icns\",\"icon_source\":\"$ICON_RELATIVE\",\"signing\":\"adhoc\",\"launcher\":\"native-mach-o\"}"; exit 0
fi
command -v pkgbuild >/dev/null || { print -u2 -- "pkgbuild is required."; exit 1; }
command -v productbuild >/dev/null || { print -u2 -- "productbuild is required."; exit 1; }
command -v clang >/dev/null || { print -u2 -- "clang is required."; exit 1; }
if [ -d "$WORK" ]; then chmod -R u+w "$WORK" >/dev/null 2>&1 || true; fi
rm -rf "$WORK"; mkdir -p "$CONTENTS/MacOS" "$APP_ROOT" "$SCRIPTS" "$DIST"
rsync -a --exclude '.git/' --exclude '.DS_Store' --exclude '._*' --exclude '__pycache__/' --exclude '*.pyc' --exclude '*.exe' --exclude '.venv/' --exclude '.pytest_cache/' --exclude '.ruff_cache/' --exclude 'build/' --exclude 'dist/' --exclude 'tests/' --exclude '.superpowers/' --exclude '*.egg-info/' "$ROOT/" "$APP_ROOT/"
chmod +x "$APP_ROOT"/toolkit/*.command
if [ -f "$ICON_SOURCE" ]; then
  ICON_PYTHON=""
  for candidate in "$ROOT/.venv/bin/python" /Library/Frameworks/Python.framework/Versions/3.11/bin/python3 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import PIL' >/dev/null 2>&1; then ICON_PYTHON="$candidate"; break; fi
  done
  [ -n "$ICON_PYTHON" ] || { print -u2 -- "Pillow is required to build icon.icns."; exit 1; }
  "$ICON_PYTHON" - "$ICON_SOURCE" "$CONTENTS/Resources/icon.icns" <<'PY'
from PIL import Image
from pathlib import Path
import sys
Image.open(Path(sys.argv[1])).convert("RGBA").save(
    Path(sys.argv[2]), format="ICNS",
    sizes=[(16,16),(32,32),(64,64),(128,128),(256,256),(512,512),(1024,1024)],
)
PY
fi
cat > "$CONTENTS/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleDisplayName</key><string>$APP_NAME</string><key>CFBundleExecutable</key><string>$EXECUTABLE</string>
<key>CFBundleIdentifier</key><string>$BUNDLE_ID</string><key>CFBundleName</key><string>$APP_NAME</string>
<key>CFBundleIconFile</key><string>icon.icns</string>
<key>CFBundlePackageType</key><string>APPL</string><key>CFBundleShortVersionString</key><string>$VERSION</string>
<key>CFBundleVersion</key><string>$VERSION</string><key>LSMinimumSystemVersion</key><string>11.0</string><key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST
clang -arch arm64 -mmacosx-version-min=11.0 -Os \
  "$ROOT/toolkit/macos_launcher.c" -o "$CONTENTS/MacOS/$EXECUTABLE"
chmod +x "$CONTENTS/MacOS/$EXECUTABLE"
cat > "$SCRIPTS/preinstall" <<'PREINSTALL'
#!/bin/zsh
rm -rf "/Applications/CRAFT.app"
exit 0
PREINSTALL
cat > "$SCRIPTS/postinstall" <<'POSTINSTALL'
#!/bin/zsh
APP="/Applications/CRAFT.app"
xattr -dr com.apple.quarantine "$APP" >/dev/null 2>&1 || true
LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
[ ! -x "$LSREGISTER" ] || "$LSREGISTER" -f "$APP" >/dev/null 2>&1 || true
exit 0
POSTINSTALL
chmod +x "$SCRIPTS/preinstall" "$SCRIPTS/postinstall"; xattr -cr "$PAYLOAD" >/dev/null 2>&1 || true
codesign --force --deep --sign - --identifier "$BUNDLE_ID" "$APP"
COMPONENT="$WORK/CRAFT.component.pkg"
COMPONENT_PLIST="$WORK/component.plist"
pkgbuild --analyze --root "$PAYLOAD" "$COMPONENT_PLIST"
/usr/libexec/PlistBuddy -c 'Set :0:BundleIsRelocatable false' "$COMPONENT_PLIST"
pkgbuild --root "$PAYLOAD" --install-location / --identifier "$PKG_ID" --version "$VERSION" --ownership recommended --scripts "$SCRIPTS" --component-plist "$COMPONENT_PLIST" "$COMPONENT"
productbuild --package "$COMPONENT" "$PKG_PATH"
print -r -- "$PKG_PATH"
