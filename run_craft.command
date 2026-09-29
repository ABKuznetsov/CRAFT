#!/bin/zsh
set -e

APP_ROOT="$(cd "$(dirname "$0")" && pwd)"
exec "$APP_ROOT/toolkit/launch_craft.command" "$@"
