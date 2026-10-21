#!/usr/bin/env bash
set -Eeuo pipefail
APP_DIR="${CRYPTOSNIPER_APP_DIR:-/opt/cryptosniper/app}"
BACKUP_DIR="${1:-}"
[[ $EUID -eq 0 ]] || { echo "Run as root"; exit 1; }
[[ -n "$BACKUP_DIR" && -d "$BACKUP_DIR/backend" ]] || { echo "Usage: rollback.sh /opt/cryptosniper/backups/app-pre-stage23-..."; exit 1; }
rsync -a --delete --exclude='.env' --exclude='*.env' --exclude='.venv' "$BACKUP_DIR/backend/" "$APP_DIR/backend/"
if [[ -d "$BACKUP_DIR/docs" ]]; then mkdir -p "$APP_DIR/docs"; rsync -a "$BACKUP_DIR/docs/" "$APP_DIR/docs/"; fi
cd "$APP_DIR/backend"
"$APP_DIR/.venv/bin/python" manage.py check
"$APP_DIR/.venv/bin/python" manage.py migrate --noinput
"$APP_DIR/.venv/bin/python" manage.py collectstatic --noinput
for s in cryptosniper-web cryptosniper-beat cryptosniper-orders cryptosniper-reports cryptosniper-signals cryptosniper-market-data cryptosniper-trailing cryptosniper-alerts cryptosniper-maintenance cryptosniper-telegram; do systemctl restart "$s.service" 2>/dev/null || true; done
echo "Rollback completed from: $BACKUP_DIR"
