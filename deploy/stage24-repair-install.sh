#!/usr/bin/env bash
set -Eeuo pipefail

REPO_DIR="${CRYPTOSNIPER_REPO_DIR:-/root/github/CryptoSniper}"
APP_DIR="${CRYPTOSNIPER_APP_DIR:-/opt/cryptosniper/app}"
BACKUP_ROOT="${CRYPTOSNIPER_BACKUP_ROOT:-/opt/cryptosniper/backups}"
RUN_USER="${CRYPTOSNIPER_USER:-cryptosniper}"
BRANCH="stage24-exchange-repair"
ENABLE_LIVE=0
BITUNIX_SMOKE=0
BITUNIX_ACCOUNT_ID=""
MAX_USDT="1.00"
HOLD_SECONDS="2"
TELEGRAM=0
TELEGRAM_PHONE=""
TELEGRAM_USER=""

say(){ printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn(){ printf '\n\033[1;33mWARN: %s\033[0m\n' "$*"; }
die(){ echo "ERROR: $*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --enable-live) ENABLE_LIVE=1; shift ;;
    --bitunix-smoke) BITUNIX_SMOKE=1; shift ;;
    --bitunix-account-id) BITUNIX_ACCOUNT_ID="${2:-}"; shift 2 ;;
    --max-usdt) MAX_USDT="${2:-}"; shift 2 ;;
    --hold-seconds) HOLD_SECONDS="${2:-}"; shift 2 ;;
    --telegram) TELEGRAM=1; shift ;;
    --telegram-phone) TELEGRAM=1; TELEGRAM_PHONE="${2:-}"; shift 2 ;;
    --telegram-user) TELEGRAM_USER="${2:-}"; shift 2 ;;
    *) die "Unknown argument: $1" ;;
  esac
done

[[ $EUID -eq 0 ]] || die "Run as root."
[[ -d "$REPO_DIR/.git" ]] || die "Git clone not found: $REPO_DIR"
[[ -r "$APP_DIR/.env" ]] || die "Production env not found: $APP_DIR/.env"
[[ -x "$APP_DIR/.venv/bin/python" ]] || die "Production virtualenv not found."
command -v git >/dev/null || die "git missing"
command -v rsync >/dev/null || die "rsync missing"
command -v npm >/dev/null || die "npm missing"

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$BACKUP_ROOT/app-pre-stage24-$STAMP"

say "Update Git branch $BRANCH"
git -C "$REPO_DIR" fetch origin "$BRANCH"
git -C "$REPO_DIR" checkout "$BRANCH"
git -C "$REPO_DIR" pull --ff-only origin "$BRANCH"

say "Backup production source and env"
mkdir -p "$BACKUP_DIR"
rsync -a   --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' --exclude='staticfiles'   "$APP_DIR/" "$BACKUP_DIR/"
echo "$BACKUP_DIR" > /root/cryptosniper-stage24-last-backup.txt

say "Build React bundle"
cd "$REPO_DIR/frontend-react"
npm ci --no-audit --no-fund
npm run build
test -s "$REPO_DIR/backend/static/react/app.js" || die "React app.js was not built."
test -s "$REPO_DIR/backend/static/react/app.css" || die "React app.css was not built."

say "Python syntax check"
find "$REPO_DIR/backend" -type f -name '*.py' -print0   | xargs -0 "$APP_DIR/.venv/bin/python" -m py_compile

say "Deploy Stage24 source"
rsync -a   --exclude='.env' --exclude='*.env' --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc'   "$REPO_DIR/backend/" "$APP_DIR/backend/"
mkdir -p "$APP_DIR/docs"
rsync -a "$REPO_DIR/docs/" "$APP_DIR/docs/"
chown -R "$RUN_USER:$RUN_USER" "$APP_DIR/backend" "$APP_DIR/docs" 2>/dev/null || true

say "Load production environment"
set -a
# shellcheck disable=SC1090
source "$APP_DIR/.env"
set +a
export DJANGO_SETTINGS_MODULE=config.settings.server

say "Django check / migrations / static"
cd "$APP_DIR/backend"
"$APP_DIR/.venv/bin/python" manage.py check
"$APP_DIR/.venv/bin/python" manage.py migrate --plan
"$APP_DIR/.venv/bin/python" manage.py migrate --noinput
"$APP_DIR/.venv/bin/python" manage.py collectstatic --noinput

say "Restart application services"
SERVICES=(
  cryptosniper-web.service cryptosniper-beat.service cryptosniper-orders.service
  cryptosniper-reports.service cryptosniper-signals.service cryptosniper-market-data.service
  cryptosniper-trailing.service cryptosniper-alerts.service cryptosniper-maintenance.service
  cryptosniper-telegram.service
)
for service in "${SERVICES[@]}"; do
  if systemctl list-unit-files "$service" >/dev/null 2>&1; then
    systemctl restart "$service"
  fi
done
sleep 3

say "NTP / time status"
timedatectl show -p NTPSynchronized -p TimeUSec --value 2>/dev/null || true

say "Repair and re-test ALL saved exchange accounts using encrypted credentials"
set +e
"$APP_DIR/.venv/bin/python" manage.py repair_exchanges_stage24 --apply --include-disabled   | tee /root/cryptosniper-stage24-exchanges.txt
REPAIR_RC=${PIPESTATUS[0]}
set -e
if [[ $REPAIR_RC -ne 0 ]]; then
  warn "Exchange repair command returned $REPAIR_RC; report preserved."
fi

if [[ -z "$BITUNIX_ACCOUNT_ID" ]]; then
  BITUNIX_ACCOUNT_ID="$("$APP_DIR/.venv/bin/python" manage.py shell -c     "from apps.exchanges.models import UserExchangeAccount; x=UserExchangeAccount.objects.filter(environment='live',exchange__adapter_code='bitunix',status='connected').order_by('pk').first(); print(x.pk if x else '')"     | tail -n1 | tr -d '[:space:]')"
fi

if [[ $ENABLE_LIVE -eq 1 ]]; then
  say "Validate Bitunix safety gates before enabling live writes"
  [[ -n "$BITUNIX_ACCOUNT_ID" ]] || die "No connected Bitunix account found; LIVE trading stays unchanged."
  READY="$("$APP_DIR/.venv/bin/python" manage.py shell -c     "from apps.exchanges.models import UserExchangeAccount; from apps.operations.models import AccountControl,RecoveryIssue; a=UserExchangeAccount.objects.get(pk=$BITUNIX_ACCOUNT_ID); c,_=AccountControl.objects.get_or_create(account=a); print('YES' if a.status=='connected' and a.trading_enabled and a.permissions.get('can_trade_spot') is True and a.permissions.get('can_withdraw') is False and not c.paused and not RecoveryIssue.objects.filter(account=a,resolved=False).exists() else 'NO')"     | tail -n1 | tr -d '[:space:]')"
  [[ "$READY" == "YES" ]] || die "Bitunix safety preflight is not ready; LIVE trading was NOT enabled."

  say "Enable LIVE_TRADING_ENABLED=true"
  cp -a "$APP_DIR/.env" "$BACKUP_DIR/.env.before-live-toggle"
  if grep -q '^LIVE_TRADING_ENABLED=' "$APP_DIR/.env"; then
    sed -i 's/^LIVE_TRADING_ENABLED=.*/LIVE_TRADING_ENABLED=true/' "$APP_DIR/.env"
  else
    printf '\nLIVE_TRADING_ENABLED=true\n' >> "$APP_DIR/.env"
  fi
  systemctl restart cryptosniper-web.service cryptosniper-orders.service
  sleep 2
  set -a
  source "$APP_DIR/.env"
  set +a
  export DJANGO_SETTINGS_MODULE=config.settings.server
  "$APP_DIR/.venv/bin/python" manage.py shell -c     'from django.conf import settings; print("LIVE_TRADING_ENABLED =",settings.LIVE_TRADING_ENABLED)'
fi

if [[ $BITUNIX_SMOKE -eq 1 ]]; then
  say "Guarded real-money Bitunix round-trip smoke"
  [[ $ENABLE_LIVE -eq 1 ]] || die "--bitunix-smoke requires --enable-live in this installer."
  [[ -n "$BITUNIX_ACCOUNT_ID" ]] || die "No connected Bitunix account found."
  set +e
  "$APP_DIR/.venv/bin/python" manage.py bitunix_roundtrip_smoke     --account-id "$BITUNIX_ACCOUNT_ID"     --max-usdt "$MAX_USDT"     --hold-seconds "$HOLD_SECONDS"     --confirm REAL_MONEY     | tee /root/cryptosniper-stage24-bitunix-smoke.txt
  SMOKE_RC=${PIPESTATUS[0]}
  set -e
  if [[ $SMOKE_RC -ne 0 ]]; then
    warn "Real smoke did not complete. It may have refused the exchange minimum/safety ceiling. Read /root/cryptosniper-stage24-bitunix-smoke.txt and DO NOT retry blindly."
  fi
fi

if [[ $TELEGRAM -eq 1 ]]; then
  say "Telegram / Telethon authorization"
  if [[ -z "$TELEGRAM_PHONE" ]]; then
    read -r -p "Telegram phone (international format): " TELEGRAM_PHONE
  fi
  if [[ -z "$TELEGRAM_USER" ]]; then
    if [[ -n "$BITUNIX_ACCOUNT_ID" ]]; then
      TELEGRAM_USER="$("$APP_DIR/.venv/bin/python" manage.py shell -c         "from apps.exchanges.models import UserExchangeAccount; print(UserExchangeAccount.objects.get(pk=$BITUNIX_ACCOUNT_ID).owner.username)"         | tail -n1 | tr -d '[:space:]')"
    fi
  fi
  [[ -n "$TELEGRAM_USER" ]] || die "Telegram CryptoSniper username could not be inferred; pass --telegram-user."
  "$APP_DIR/.venv/bin/python" manage.py telegram_connect_smoke     --username "$TELEGRAM_USER" --phone "$TELEGRAM_PHONE"     | tee /root/cryptosniper-stage24-telegram.txt
  systemctl restart cryptosniper-telegram.service
fi

say "Final Stage24 diagnostic"
"$APP_DIR/.venv/bin/python" manage.py diagnose_stage23   | tee /root/cryptosniper-stage24-final-diagnostic.txt || true

say "Public health"
curl -fsS https://srun.ir/cryptosniper/health/live/; echo
curl -fsS https://srun.ir/cryptosniper/health/ready/; echo

cat <<EOF

============================================================
CryptoSniper Stage24 exchange repair installed.
Backup:
  $BACKUP_DIR

Reports:
  /root/cryptosniper-stage24-exchanges.txt
  /root/cryptosniper-stage24-final-diagnostic.txt
  /root/cryptosniper-stage24-bitunix-smoke.txt   (if requested)
  /root/cryptosniper-stage24-telegram.txt        (if requested)

Rollback source:
  bash $REPO_DIR/deploy/rollback.sh "$BACKUP_DIR"
============================================================
EOF
