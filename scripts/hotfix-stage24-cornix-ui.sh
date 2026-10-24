#!/usr/bin/env bash
# Stage24 UI hotfix: permanently remove the legacy dashboard shell and restore the Cornix-like UI.
set -Eeuo pipefail
umask 022

APP_DIR=/opt/cryptosniper/app
APP_USER=cryptosniper
PIN=cc19c416387497b7a27e8dfafb26fa398fca56d4
RAW="https://raw.githubusercontent.com/ostaddehdari/CryptoSniper/$PIN"
BACKUP_ROOT=/opt/cryptosniper/ui-backups
STAMP=$(date +%Y%m%d-%H%M%S)
BACKUP="$BACKUP_ROOT/$STAMP"
TMP=$(mktemp -d /tmp/cryptosniper-ui-hotfix.XXXXXX)
APPLIED=0

FILES=(
  "backend/apps/portfolio/views.py:6ad0a69dec542575e8c8922561981e42941cc385"
  "backend/apps/core/views.py:dc2423d0af685e861ff18638105e404e734bed35"
  "backend/templates/shell.html:eb60dbb3a881a019f6f013bfccd4d2ff30542be7"
  "backend/templates/core/app_stage24.html:5221387bbff79c11878174a0b7a47051ca71038a"
  "backend/static/js/stage24-app.js:1efc9a0ccd9b37584e96582d4e390d3e2af3685d"
  "backend/static/css/stage24-app.css:2a5f881307723a507cff5a16d1a7220d0db56a54"
)

cleanup(){ rm -rf "$TMP"; }
restore(){
  if [[ $APPLIED -eq 1 && -d "$BACKUP" ]]; then
    echo "ROLLBACK: restoring previous UI files..."
    while IFS= read -r -d '' file; do
      rel=${file#"$BACKUP/"}
      mkdir -p "$APP_DIR/$(dirname "$rel")"
      cp -a "$file" "$APP_DIR/$rel"
    done < <(find "$BACKUP" -type f -print0)
    if [[ -f "$BACKUP/.dashboard-template-existed" ]]; then
      cp -a "$BACKUP/backend/templates/core/dashboard.html" "$APP_DIR/backend/templates/core/dashboard.html"
    else
      rm -f "$APP_DIR/backend/templates/core/dashboard.html"
    fi
    systemctl restart cryptosniper-web.service || true
  fi
}
trap 'status=$?; if [[ $status -ne 0 ]]; then restore; fi; cleanup; exit $status' EXIT

[[ $EUID -eq 0 ]] || { echo "ERROR: run as root"; exit 1; }
[[ -d "$APP_DIR/backend" ]] || { echo "ERROR: CryptoSniper installation not found at $APP_DIR"; exit 1; }
command -v curl >/dev/null || { echo "ERROR: curl missing"; exit 1; }
command -v python3 >/dev/null || { echo "ERROR: python3 missing"; exit 1; }

mkdir -p "$BACKUP"
echo "Pinned UI source: $PIN"

verify_blob(){
  local path=$1 expected=$2
  python3 - "$path" "$expected" <<'PY'
import hashlib, pathlib, sys
p=pathlib.Path(sys.argv[1])
expected=sys.argv[2]
data=p.read_bytes()
actual=hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()
if actual != expected:
    raise SystemExit(f"blob mismatch for {p}: {actual} != {expected}")
print(f"PASS blob {p.name}: {actual}")
PY
}

echo "===== DOWNLOAD + VERIFY ====="
for item in "${FILES[@]}"; do
  rel=${item%%:*}
  sha=${item##*:}
  out="$TMP/$rel"
  mkdir -p "$(dirname "$out")"
  curl -fsSL --retry 3 -o "$out" "$RAW/$rel"
  verify_blob "$out" "$sha"
done

echo "===== BACKUP CURRENT UI ====="
for item in "${FILES[@]}"; do
  rel=${item%%:*}
  if [[ -f "$APP_DIR/$rel" ]]; then
    mkdir -p "$BACKUP/$(dirname "$rel")"
    cp -a "$APP_DIR/$rel" "$BACKUP/$rel"
  fi
done
if [[ -f "$APP_DIR/backend/templates/core/dashboard.html" ]]; then
  mkdir -p "$BACKUP/backend/templates/core"
  cp -a "$APP_DIR/backend/templates/core/dashboard.html" "$BACKUP/backend/templates/core/dashboard.html"
  touch "$BACKUP/.dashboard-template-existed"
fi

echo "===== APPLY CORNIX-LIKE UI HOTFIX ====="
APPLIED=1
for item in "${FILES[@]}"; do
  rel=${item%%:*}
  install -D -m 0644 -o "$APP_USER" -g "$APP_USER" "$TMP/$rel" "$APP_DIR/$rel"
done

# The legacy dashboard template is deliberately removed so it cannot render again.
rm -f "$APP_DIR/backend/templates/core/dashboard.html"

cd "$APP_DIR"
echo "===== DJANGO CHECK ====="
runuser -u "$APP_USER" -- env   DJANGO_SETTINGS_MODULE=config.settings.server   HOME=/opt/cryptosniper   "$APP_DIR/.venv/bin/python" backend/manage.py check

echo "===== COLLECT STATIC ====="
runuser -u "$APP_USER" -- env   DJANGO_SETTINGS_MODULE=config.settings.server   HOME=/opt/cryptosniper   "$APP_DIR/.venv/bin/python" backend/manage.py collectstatic --noinput

echo "===== RESTART WEB ====="
systemctl restart cryptosniper-web.service
systemctl is-active --quiet cryptosniper-web.service

echo "===== VERIFY ROUTES ====="
code=$(curl -sS -o /dev/null -w '%{http_code}' -H 'Host: srun.ir' -H 'X-Forwarded-Proto: https' http://127.0.0.1:18881/dashboard/)
[[ "$code" == "302" ]] || { echo "ERROR: /dashboard/ expected 302, got $code"; exit 1; }

app_code=$(curl -sS -o /dev/null -w '%{http_code}' -H 'Host: srun.ir' -H 'X-Forwarded-Proto: https' http://127.0.0.1:18881/app/)
[[ "$app_code" == "302" || "$app_code" == "200" ]] || { echo "ERROR: /app/ unexpected HTTP $app_code"; exit 1; }

echo
echo "HOTFIX_OK"
echo "Legacy dashboard template removed."
echo "Dashboard redirects to: /cryptosniper/app/#/overview"
echo "Cornix-like shell is now the permanent primary UI."
echo "Backup: $BACKUP"
