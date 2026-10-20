#!/bin/zsh
set -e
APP_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCI_ROOT="$HOME/Library/Application Support/Sci"
SCI_ENV="$SCI_ROOT/env"
MARKER="$SCI_ROOT/apps/craft/installed-version.txt"
if [ "$1" = "--print-config" ]; then
  print -r -- '{"environment":"~/Library/Application Support/Sci/env","module":"craft.app"}'; exit 0
fi
VERSION_PYTHON="$SCI_ENV/bin/python"
if [ ! -x "$VERSION_PYTHON" ]; then
  for candidate in /opt/homebrew/bin/python3 /usr/local/bin/python3 /Library/Frameworks/Python.framework/Versions/3.12/bin/python3 /Library/Frameworks/Python.framework/Versions/3.11/bin/python3 python3; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; raise SystemExit(0 if (3,11) <= sys.version_info[:2] < (3,13) else 1)' >/dev/null 2>&1; then VERSION_PYTHON="$candidate"; break; fi
  done
fi
VERSION="$("$VERSION_PYTHON" -c 'import sys,tomllib; print(tomllib.load(open(sys.argv[1],"rb"))["project"]["version"])' "$APP_ROOT/pyproject.toml" 2>/dev/null || true)"
CRISTMA_VERSION="$("$VERSION_PYTHON" -c 'import sys,tomllib; dependencies=tomllib.load(open(sys.argv[1],"rb"))["project"]["dependencies"]; print(next(item.split("==",1)[1] for item in dependencies if item.lower().startswith("cristma==")))' "$APP_ROOT/pyproject.toml" 2>/dev/null || true)"
INSTALLED="$(cat "$MARKER" 2>/dev/null || true)"
export MPLCONFIGDIR="$SCI_ROOT/apps/craft/matplotlib"
mkdir -p "$MPLCONFIGDIR"
ENV_READY=0
if [ -x "$SCI_ENV/bin/python" ]; then
  PYTHONPATH="$APP_ROOT" "$SCI_ENV/bin/python" -c 'import sys, cristma, craft, PySide6, pyvista, pyvistaqt, vtk, docx; raise SystemExit(0 if cristma.__version__ == sys.argv[1] else 1)' "$CRISTMA_VERSION" >/dev/null 2>&1 && ENV_READY=1
fi
if [ "$ENV_READY" -ne 1 ]; then
  "$APP_ROOT/toolkit/setup_craft_env.command"
elif [ "$VERSION" != "$INSTALLED" ]; then
  mkdir -p "${MARKER:h}"
  print -r -- "$VERSION" > "$MARKER"
fi
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$APP_ROOT${PYTHONPATH+:$PYTHONPATH}"
exec "$SCI_ENV/bin/python" -m craft.app "$@"
