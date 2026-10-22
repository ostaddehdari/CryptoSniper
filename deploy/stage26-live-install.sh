#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${CRYPTOSNIPER_APP_DIR:-/opt/cryptosniper/app}"
REPO_DIR="${CRYPTOSNIPER_REPO_DIR:-/root/github/CryptoSniper}"
BACKUP_ROOT="${CRYPTOSNIPER_BACKUP_ROOT:-/opt/cryptosniper/backups}"
RUN_USER="${CRYPTOSNIPER_USER:-cryptosniper}"
BRANCH="stage26-live-market-exchange-validation"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$BACKUP_ROOT/app-pre-stage26-$STAMP"

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

say "Update Stage26 branch"
git -C "$REPO_DIR" fetch origin "$BRANCH"
git -C "$REPO_DIR" checkout "$BRANCH"
git -C "$REPO_DIR" pull --ff-only origin "$BRANCH"

say "Backup current production"
mkdir -p "$BACKUP_DIR"
rsync -a   --exclude='.venv'   --exclude='__pycache__'   --exclude='*.pyc'   --exclude='staticfiles'   "$APP_DIR/" "$BACKUP_DIR/"
echo "$BACKUP_DIR" > /root/cryptosniper-stage26-last-backup.txt

say "Build React"
cd "$REPO_DIR/frontend-react"
npm ci --no-audit --no-fund
npm run build
test -s "$REPO_DIR/backend/static/react/app.js" || die "React app.js ساخته نشد."
test -s "$REPO_DIR/backend/static/react/app.css" || die "React app.css ساخته نشد."

say "Python syntax check"
find "$REPO_DIR/backend" -type f -name '*.py' -print0   | xargs -0 "$APP_DIR/.venv/bin/python" -m py_compile

say "Deploy Stage26 source"
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

say "Django check / migrations / static"
"$APP_DIR/.venv/bin/python" manage.py check
"$APP_DIR/.venv/bin/python" manage.py migrate --plan
"$APP_DIR/.venv/bin/python" manage.py migrate --noinput
"$APP_DIR/.venv/bin/python" manage.py collectstatic --noinput

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
  cryptosniper-telegram.service
)
for service in "${SERVICES[@]}"; do
  if systemctl list-unit-files "$service" >/dev/null 2>&1; then
    systemctl restart "$service"
  fi
done
sleep 4

say "Retry and diagnose ALL saved exchange connections"
set +e
"$APP_DIR/.venv/bin/python" manage.py repair_exchanges_stage24   --apply   --include-disabled   | tee /root/cryptosniper-stage26-exchanges.txt
REPAIR_RC=${PIPESTATUS[0]}
set -e
if [[ $REPAIR_RC -ne 0 ]]; then
  echo "WARN: exchange repair returned $REPAIR_RC; report was preserved."
fi

say "Direct live public price test"
"$APP_DIR/.venv/bin/python" manage.py shell -c '
from apps.exchanges.adapters import get_adapter
for code,symbol in (("bitunix","BTC/USDT"),("nobitex","USDT/IRT")):
    try:
        t=get_adapter(code,credentials={},environment="paper").fetch_ticker(symbol)
        print(code, symbol, "price=", t.price, "observed_at=", t.observed_at.isoformat())
    except Exception as e:
        print(code, symbol, "ERROR", type(e).__name__)
' | tee /root/cryptosniper-stage26-live-prices.txt

say "Final health"
curl -fsS https://srun.ir/cryptosniper/health/live/   | tee /root/cryptosniper-stage26-health.json
echo
curl -fsS https://srun.ir/cryptosniper/health/ready/   | tee /root/cryptosniper-stage26-ready.json
echo

say "Service status"
for service in "${SERVICES[@]}"; do
  if systemctl list-unit-files "$service" >/dev/null 2>&1; then
    printf '%-42s ' "$service"
    systemctl is-active "$service" || true
  fi
done

say "Recent web / market-data errors"
{
  echo "===== WEB ====="
  journalctl -u cryptosniper-web.service --since "10 minutes ago" --no-pager     | grep -Ei 'traceback|exception|error| 500 ' | tail -100 || true
  echo "===== MARKET DATA ====="
  journalctl -u cryptosniper-market-data.service --since "10 minutes ago" --no-pager     | grep -Ei 'traceback|exception|error|failed' | tail -100 || true
} | tee /root/cryptosniper-stage26-errors.txt

cat <<EOF

============================================================
CryptoSniper Stage26 installed.

Backup:
  $BACKUP_DIR

Reports:
  /root/cryptosniper-stage26-exchanges.txt
  /root/cryptosniper-stage26-live-prices.txt
  /root/cryptosniper-stage26-errors.txt

Public:
  https://srun.ir/cryptosniper/

Rollback:
  bash $REPO_DIR/deploy/rollback.sh "$BACKUP_DIR"

NOTE:
  This installer does NOT place a real order.
  LIVE_TRADING_ENABLED is preserved exactly as it was.
============================================================
EOF
