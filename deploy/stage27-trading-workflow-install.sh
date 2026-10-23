#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${CRYPTOSNIPER_APP_DIR:-/opt/cryptosniper/app}"
REPO_DIR="${CRYPTOSNIPER_REPO_DIR:-/root/github/CryptoSniper}"
BACKUP_ROOT="${CRYPTOSNIPER_BACKUP_ROOT:-/opt/cryptosniper/backups}"
RUN_USER="${CRYPTOSNIPER_USER:-cryptosniper}"
BRANCH="stage27-trading-workflow-hardening"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$BACKUP_ROOT/app-pre-stage27-$STAMP"

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

say "Preserve any local repository changes"
cd "$REPO_DIR"
if [[ -n "$(git status --porcelain)" ]]; then
  git stash push -u -m "pre-stage27-installer-$STAMP"
  echo "Local changes were stashed safely:"
  git stash list | head -3
fi

say "Update Stage27 branch"
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"
git log -1 --oneline

say "Backup current production"
mkdir -p "$BACKUP_DIR"
rsync -a \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='staticfiles' \
  "$APP_DIR/" "$BACKUP_DIR/"
echo "$BACKUP_DIR" > /root/cryptosniper-stage27-last-backup.txt

say "Build React"
cd "$REPO_DIR/frontend-react"
npm ci --no-audit --no-fund
npm run build
test -s "$REPO_DIR/backend/static/react/app.js" || die "React app.js ساخته نشد."
test -s "$REPO_DIR/backend/static/react/app.css" || die "React app.css ساخته نشد."

say "Python syntax check"
find "$REPO_DIR/backend" -type f -name '*.py' -print0 \
  | xargs -0 "$APP_DIR/.venv/bin/python" -m py_compile

say "Deploy Stage27 source"
rsync -a \
  --exclude='.env' \
  --exclude='*.env' \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  "$REPO_DIR/backend/" "$APP_DIR/backend/"
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

say "Django and schema checks"
"$APP_DIR/.venv/bin/python" manage.py check
"$APP_DIR/.venv/bin/python" manage.py makemigrations --check --dry-run
"$APP_DIR/.venv/bin/python" manage.py migrate --plan

say "Apply migrations"
"$APP_DIR/.venv/bin/python" manage.py migrate --noinput

say "Collect static"
"$APP_DIR/.venv/bin/python" manage.py collectstatic --noinput

say "Stage27 route/model verification"
"$APP_DIR/.venv/bin/python" manage.py shell -c '
from django.conf import settings
from django.urls import reverse
from apps.accounts.models import TradingPreferences
from apps.operations.models import (
    ExternalTradeManagement,
    ManagedLiveExit,
    ManagedLiveTarget,
    ManagedLiveTrade,
)
from apps.tradeplans.models import TradePlan

checks = [
    ("react", reverse("react-app")),
    ("bootstrap", reverse("api-ui-bootstrap")),
    ("live_orders", reverse("api-live-orders")),
    ("bulk_signal", reverse("api-inbox-bulk-action")),
    ("external_management", reverse("api-external-management", args=[1])),
    ("operations", reverse("api-operations-health")),
]
print("ROUTES=", checks)
print("TRAILING_CHOICES=", list(TradingPreferences.TrailingTrigger.choices))
print("TradePlan percentage_trigger=", TradePlan._meta.get_field("percentage_trigger").name)
print("ExternalTradeManagement fields=", [f.name for f in ExternalTradeManagement._meta.fields])
print("ManagedLiveTrade fields=", [f.name for f in ManagedLiveTrade._meta.fields])
print("LIVE_TRADING_ENABLED=", settings.LIVE_TRADING_ENABLED)
assert {x[0] for x in TradingPreferences.TrailingTrigger.choices} == {"tp1","tp2","tp3"}
assert TradePlan._meta.get_field("percentage_trigger")
assert ExternalTradeManagement._meta.get_field("trailing_sl_enabled")
assert ManagedLiveTrade._meta.get_field("entry_order")
assert ManagedLiveTarget._meta.get_field("exit_order")
assert ManagedLiveExit._meta.get_field("order")
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
  cryptosniper-telegram.service
)
for service in "${SERVICES[@]}"; do
  if systemctl list-unit-files "$service" >/dev/null 2>&1; then
    systemctl restart "$service"
  fi
done
sleep 4

say "Local health"
curl -fsS http://127.0.0.1:18881/health/live/ \
  | tee /root/cryptosniper-stage27-health-local.json
echo
curl -fsS http://127.0.0.1:18881/health/ready/ \
  | tee /root/cryptosniper-stage27-ready-local.json
echo

say "Public health"
set +e
curl -fsS https://srun.ir/cryptosniper/health/live/ \
  | tee /root/cryptosniper-stage27-health.json
PUBLIC_RC=${PIPESTATUS[0]}
echo
set -e
if [[ $PUBLIC_RC -ne 0 ]]; then
  echo "WARN: public DNS/HTTP failed; local health above is authoritative for this install."
fi

say "Service status"
for service in "${SERVICES[@]}"; do
  if systemctl list-unit-files "$service" >/dev/null 2>&1; then
    printf '%-42s ' "$service"
    systemctl is-active "$service" || true
  fi
done

say "Recent application errors"
{
  for service in cryptosniper-web.service cryptosniper-orders.service cryptosniper-trailing.service cryptosniper-maintenance.service; do
    echo "===== $service ====="
    journalctl -u "$service" --since "10 minutes ago" --no-pager \
      | grep -Ei 'traceback|exception|error| 500 ' | tail -80 || true
  done
} | tee /root/cryptosniper-stage27-errors.txt

cat <<EOF

============================================================
CryptoSniper Stage27 trading workflow installed.

Works included:
  W1  New Trade / Market Picker / blank Entry / integer capital
  W2  Trailing + Trailing SL semantics and settings
  W3  Signal Inbox approval transfer + bulk delete
  W4  External trade details + explicit managed trailing
  W5  Exchange add/delete UI hardening
  W6  Operations hides deleted connections
  W7  Stronger deterministic signal analysis
  W8  Live-order reconciliation + managed TP/SL/Trailing lifecycle

Backup:
  $BACKUP_DIR

Reports:
  /root/cryptosniper-stage27-health-local.json
  /root/cryptosniper-stage27-ready-local.json
  /root/cryptosniper-stage27-errors.txt

Public:
  https://srun.ir/cryptosniper/

Rollback:
  bash $REPO_DIR/deploy/rollback.sh "$BACKUP_DIR"

Safety:
  LIVE_TRADING_ENABLED was NOT changed.
  This installer submitted NO real order.
============================================================
EOF
