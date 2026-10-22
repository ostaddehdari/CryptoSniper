#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${CRYPTOSNIPER_APP_DIR:-/opt/cryptosniper/app}"
REPO_DIR="${CRYPTOSNIPER_REPO_DIR:-/root/github/CryptoSniper}"
BACKUP_ROOT="${CRYPTOSNIPER_BACKUP_ROOT:-/opt/cryptosniper/backups}"
RUN_USER="${CRYPTOSNIPER_USER:-cryptosniper}"
BRANCH="stage25-dashboard-trading-ux"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$BACKUP_ROOT/app-pre-stage25-$STAMP"

say(){ printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
die(){ echo "ERROR: $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "این نصب باید با root اجرا شود."
[[ -d "$REPO_DIR/.git" ]] || die "Clone گیت پیدا نشد: $REPO_DIR"
[[ -d "$APP_DIR/backend" ]] || die "Production app پیدا نشد: $APP_DIR"
[[ -x "$APP_DIR/.venv/bin/python" ]] || die "Production venv پیدا نشد."
[[ -r "$APP_DIR/.env" ]] || die "Production .env پیدا نشد."
command -v git >/dev/null || die "git نصب نیست."
command -v npm >/dev/null || die "npm نصب نیست."
command -v rsync >/dev/null || die "rsync نصب نیست."

say "Update Stage25 branch"
git -C "$REPO_DIR" fetch origin "$BRANCH"
git -C "$REPO_DIR" checkout "$BRANCH"
git -C "$REPO_DIR" pull --ff-only origin "$BRANCH"

say "Backup current production"
mkdir -p "$BACKUP_DIR"
rsync -a   --exclude='.venv'   --exclude='__pycache__'   --exclude='*.pyc'   --exclude='staticfiles'   "$APP_DIR/" "$BACKUP_DIR/"
echo "$BACKUP_DIR" > /root/cryptosniper-stage25-last-backup.txt

say "Build React"
cd "$REPO_DIR/frontend-react"
npm ci --no-audit --no-fund
npm run build
test -s "$REPO_DIR/backend/static/react/app.js" || die "React app.js ساخته نشد."
test -s "$REPO_DIR/backend/static/react/app.css" || die "React app.css ساخته نشد."

say "Python syntax check"
find "$REPO_DIR/backend" -type f -name '*.py' -print0   | xargs -0 "$APP_DIR/.venv/bin/python" -m py_compile

say "Deploy source"
rsync -a   --exclude='.env'   --exclude='*.env'   --exclude='.venv'   --exclude='__pycache__'   --exclude='*.pyc'   "$REPO_DIR/backend/" "$APP_DIR/backend/"
mkdir -p "$APP_DIR/docs"
rsync -a "$REPO_DIR/docs/" "$APP_DIR/docs/" 2>/dev/null || true
chown -R "$RUN_USER:$RUN_USER" "$APP_DIR/backend" "$APP_DIR/docs" 2>/dev/null || true

say "Load production environment"
set -a
# shellcheck disable=SC1090
source "$APP_DIR/.env"
set +a
export DJANGO_SETTINGS_MODULE=config.settings.server

cd "$APP_DIR/backend"

say "Django check"
"$APP_DIR/.venv/bin/python" manage.py check

say "Migration plan"
"$APP_DIR/.venv/bin/python" manage.py migrate --plan

say "Apply migrations"
"$APP_DIR/.venv/bin/python" manage.py migrate --noinput

say "Collect static"
"$APP_DIR/.venv/bin/python" manage.py collectstatic --noinput

say "Stage25 route/model verification"
"$APP_DIR/.venv/bin/python" manage.py shell -c '
from django.urls import reverse
from apps.marketdata.models import FavoriteAsset
checks = [
    ("react", reverse("react-app")),
    ("bootstrap", reverse("api-ui-bootstrap")),
    ("favorites", reverse("api-ui-favorites")),
    ("fix_loss", reverse("api-fix-loss")),
    ("live_orders", reverse("api-live-orders")),
]
print("ROUTES=", checks)
print("FavoriteAsset fields=", [f.name for f in FavoriteAsset._meta.fields])
assert "exchange" in [f.name for f in FavoriteAsset._meta.fields]
'

say "Restart CryptoSniper services"
SERVICES=(
  cryptosniper-web.service
  cryptosniper-beat.service
  cryptosniper-orders.service
  cryptosniper-reports.service
  cryptosniper-signals.service
  cryptosniper-market-data.service
  cryptosniper-trailing.service
  cryptosniper-alerts.service
  cryptosniper-maintenance.service
)
for service in "${SERVICES[@]}"; do
  if systemctl list-unit-files "$service" >/dev/null 2>&1; then
    systemctl restart "$service"
  fi
done
sleep 4

say "Service status"
for service in "${SERVICES[@]}"; do
  if systemctl list-unit-files "$service" >/dev/null 2>&1; then
    printf '%-42s ' "$service"
    systemctl is-active "$service" || true
  fi
done

say "Public health"
curl -fsS https://srun.ir/cryptosniper/health/live/ | tee /root/cryptosniper-stage25-health.json
echo
curl -fsS https://srun.ir/cryptosniper/health/ready/ | tee /root/cryptosniper-stage25-ready.json
echo

say "Recent web errors"
journalctl -u cryptosniper-web.service --since "5 minutes ago" --no-pager   | grep -Ei 'traceback|exception|error| 500 '   | tail -80 || true

cat <<EOF

============================================================
CryptoSniper Stage25 dashboard/trading UX installed.

Backup:
  $BACKUP_DIR

Public:
  https://srun.ir/cryptosniper/

Rollback:
  bash $REPO_DIR/deploy/rollback.sh "$BACKUP_DIR"

This installer does NOT change LIVE_TRADING_ENABLED and does NOT submit any order.
============================================================
EOF
