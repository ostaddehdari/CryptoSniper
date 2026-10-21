#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${CRYPTOSNIPER_APP_DIR:-/opt/cryptosniper/app}"
REPO_DIR="${CRYPTOSNIPER_REPO_DIR:-/root/github/CryptoSniper}"

[[ -r "$APP_DIR/.env" ]] || { echo "Missing $APP_DIR/.env" >&2; exit 2; }
[[ -x "$APP_DIR/.venv/bin/python" ]] || { echo "Missing production Python venv" >&2; exit 2; }
[[ -f "$REPO_DIR/backend/manage.py" ]] || { echo "Missing repo backend: $REPO_DIR" >&2; exit 2; }

set -a
# shellcheck disable=SC1090
source "$APP_DIR/.env"
set +a
export DJANGO_SETTINGS_MODULE=config.settings.server

cd "$REPO_DIR/backend"
exec "$APP_DIR/.venv/bin/python" manage.py diagnose_stage23 "$@"
