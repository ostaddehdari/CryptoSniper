#!/usr/bin/env bash
set -Eeuo pipefail
APP_DIR="${CRYPTOSNIPER_APP_DIR:-/opt/cryptosniper/app}"
PKG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_ROOT="${CRYPTOSNIPER_BACKUP_ROOT:-/opt/cryptosniper/backups}"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$BACKUP_ROOT/app-pre-stage23-$STAMP"
RUN_USER="${CRYPTOSNIPER_USER:-cryptosniper}"
say(){ printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
die(){ echo "ERROR: $*" >&2; exit 1; }
[[ $EUID -eq 0 ]] || die "این نصب باید با root اجرا شود."
[[ -d "$APP_DIR/backend" ]] || die "مسیر فعلی CryptoSniper پیدا نشد: $APP_DIR/backend"
[[ -x "$APP_DIR/.venv/bin/python" ]] || die "virtualenv فعلی پیدا نشد: $APP_DIR/.venv"
command -v node >/dev/null || die "Node.js نصب نیست."
command -v npm >/dev/null || die "npm نصب نیست."
command -v rsync >/dev/null || die "rsync نصب نیست."
say "Preflight"
"$APP_DIR/.venv/bin/python" --version
node -v
npm -v
systemctl is-active --quiet cryptosniper-web.service || die "cryptosniper-web.service فعال نیست."
say "Backup current application source"
mkdir -p "$BACKUP_DIR"
rsync -a --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' --exclude='staticfiles' "$APP_DIR/" "$BACKUP_DIR/"
echo "$BACKUP_DIR" > /root/cryptosniper-stage23-last-backup.txt
say "Build React production bundle"
cd "$PKG_DIR/frontend-react"
npm install --no-audit --no-fund
npm run build
test -s "$PKG_DIR/backend/static/react/app.js" || die "React app.js ساخته نشد."
test -s "$PKG_DIR/backend/static/react/app.css" || die "React app.css ساخته نشد."
say "Python syntax check"
find "$PKG_DIR/backend" -type f -name '*.py' -print0 | xargs -0 "$APP_DIR/.venv/bin/python" -m py_compile
say "Copy Stage23 source over current app"
rsync -a --exclude='.env' --exclude='*.env' --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' "$PKG_DIR/backend/" "$APP_DIR/backend/"
mkdir -p "$APP_DIR/docs"
rsync -a "$PKG_DIR/docs/" "$APP_DIR/docs/"
chown -R "$RUN_USER:$RUN_USER" "$APP_DIR/backend" "$APP_DIR/docs" 2>/dev/null || true
say "Django checks"
cd "$APP_DIR/backend"
sudo -u "$RUN_USER" "$APP_DIR/.venv/bin/python" manage.py check
say "Migration plan"
sudo -u "$RUN_USER" "$APP_DIR/.venv/bin/python" manage.py migrate --plan
say "Apply migrations"
sudo -u "$RUN_USER" "$APP_DIR/.venv/bin/python" manage.py migrate --noinput
say "Collect static"
sudo -u "$RUN_USER" "$APP_DIR/.venv/bin/python" manage.py collectstatic --noinput
say "Restart CryptoSniper services"
SERVICES=(cryptosniper-web.service cryptosniper-beat.service cryptosniper-orders.service cryptosniper-reports.service cryptosniper-signals.service cryptosniper-market-data.service cryptosniper-trailing.service cryptosniper-alerts.service cryptosniper-maintenance.service cryptosniper-telegram.service)
for s in "${SERVICES[@]}"; do
  if systemctl list-unit-files "$s" >/dev/null 2>&1; then systemctl restart "$s"; fi
done
sleep 3
say "Service status"
systemctl --no-pager --full status cryptosniper-web.service | sed -n '1,25p'
say "Local health"
curl -fsS http://127.0.0.1:18881/health/live/ | tee /tmp/cryptosniper-stage23-health.json
echo
curl -fsS http://127.0.0.1:18881/health/ready/ | tee /tmp/cryptosniper-stage23-ready.json || true
echo
say "HTTP shell check"
code="$(curl -sS -o /tmp/cs-stage23-root.html -w '%{http_code}' http://127.0.0.1:18881/ || true)"
echo "root HTTP=$code"
appcode="$(curl -sS -o /tmp/cs-stage23-app.html -w '%{http_code}' http://127.0.0.1:18881/app/ || true)"
echo "app HTTP=$appcode (302 به login برای session ناشناس طبیعی است)"
cat <<EOT

============================================================
CryptoSniper Stage23 installed.
Backup: $BACKUP_DIR
Public URL: https://srun.ir/cryptosniper/
React URL:  https://srun.ir/cryptosniper/app/
Rollback:   bash $PKG_DIR/deploy/rollback.sh "$BACKUP_DIR"
============================================================
EOT
