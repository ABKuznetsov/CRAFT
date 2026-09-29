#!/bin/zsh
set -e
APP_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCI_ROOT="$HOME/Library/Application Support/Sci"
SCI_ENV="$SCI_ROOT/env"
LOG_FILE="$SCI_ROOT/logs/craft_setup.log"
MARKER="$SCI_ROOT/apps/craft/installed-version.txt"
if [ "$1" = "--print-config" ]; then
  print -r -- '{"environment":"~/Library/Application Support/Sci/env","python":"3.11 or 3.12","install_mode":"dependencies-only","repair_architecture":true}'; exit 0
fi
mkdir -p "${LOG_FILE:h}" "${MARKER:h}"
find_python() {
  for candidate in /opt/homebrew/bin/python3 /usr/local/bin/python3 /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 /Library/Frameworks/Python.framework/Versions/3.11/bin/python3 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(0 if (3,11) <= sys.version_info[:2] < (3,13) else 1)' >/dev/null 2>&1; then print -r -- "$candidate"; return 0; fi
  done
  return 1
}
PYTHON="$(find_python || true)"
[ -n "$PYTHON" ] || { print -u2 -- "CRAFT requires Python 3.11 or 3.12."; exit 1; }
[ -x "$SCI_ENV/bin/python" ] || "$PYTHON" -m venv "$SCI_ENV"
"$SCI_ENV/bin/python" -c 'import sys; raise SystemExit(0 if (3,11) <= sys.version_info[:2] < (3,13) else 1)' >/dev/null 2>&1 || { print -u2 -- "Shared Sci environment has incompatible Python."; exit 1; }
{
  print -r -- "[$(date)] Installing CRAFT"
  "$SCI_ENV/bin/python" -m pip install --disable-pip-version-check --prefer-binary --upgrade pip setuptools wheel
  DEPENDENCIES=("${(@f)$("$SCI_ENV/bin/python" -c 'import sys,tomllib; print("\n".join(tomllib.load(open(sys.argv[1],"rb"))["project"]["dependencies"]))' "$APP_ROOT/pyproject.toml")}")
  "$SCI_ENV/bin/python" -m pip install --disable-pip-version-check --prefer-binary --no-cache-dir --upgrade "${DEPENDENCIES[@]}"
  PYTHONPATH="$APP_ROOT" "$SCI_ENV/bin/python" -c 'import craft, PySide6, pyvista, vtk'
} >> "$LOG_FILE" 2>&1
VERSION="$($SCI_ENV/bin/python -c 'import sys,tomllib; print(tomllib.load(open(sys.argv[1],"rb"))["project"]["version"])' "$APP_ROOT/pyproject.toml")"
print -r -- "$VERSION" > "$MARKER"
print -r -- "CRAFT environment is ready."
