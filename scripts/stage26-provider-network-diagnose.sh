#!/usr/bin/env bash
set -Eeuo pipefail

echo "===== DNS ====="
getent ahosts apiv2.nobitex.ir || true
getent ahosts apiv2.nobitex.ir || true
echo

echo "===== CURL IPV4 ====="
curl -4 -sSvk --connect-timeout 8 --max-time 15   https://apiv2.nobitex.ir/v3/orderbook/USDTIRT   -o /tmp/nobitex-usdtirt-v4.json 2>/tmp/nobitex-v4.stderr || true
printf 'HTTP/TLS stderr:\n'
sed -n '1,80p' /tmp/nobitex-v4.stderr
printf '\nBody preview:\n'
head -c 600 /tmp/nobitex-usdtirt-v4.json 2>/dev/null || true
echo; echo

echo "===== CURL IPV6 ====="
curl -6 -sSvk --connect-timeout 8 --max-time 15   https://apiv2.nobitex.ir/v3/orderbook/USDTIRT   -o /tmp/nobitex-usdtirt-v6.json 2>/tmp/nobitex-v6.stderr || true
sed -n '1,80p' /tmp/nobitex-v6.stderr
echo

echo "===== OPENSSL SNI ====="
timeout 12 openssl s_client   -connect apiv2.nobitex.ir:443   -servername apiv2.nobitex.ir   -brief </dev/null 2>&1 | sed -n '1,80p' || true
echo

echo "===== PYTHON URL ====="
python3 - <<'PY'
import json, socket, ssl, urllib.request

host = "apiv2.nobitex.ir"
try:
    print("getaddrinfo:", socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM))
except Exception as e:
    print("DNS_ERROR", type(e).__name__, str(e)[:180])

url = "https://apiv2.nobitex.ir/v3/orderbook/USDTIRT"
try:
    with urllib.request.urlopen(url, timeout=12) as r:
        raw = r.read(1000)
        print("HTTP", r.status, "bytes", len(raw))
        print(raw.decode("utf-8", "replace")[:800])
except Exception as e:
    print("URL_ERROR", type(e).__name__, str(e)[:240])
PY
echo

echo "===== CRYPTOSNIPER ACCOUNT STATE ====="
APP=/opt/cryptosniper/app
set -a
source "$APP/.env"
set +a
export DJANGO_SETTINGS_MODULE=config.settings.server
cd "$APP/backend"
"$APP/.venv/bin/python" manage.py shell -c '
from apps.exchanges.models import UserExchangeAccount
for a in UserExchangeAccount.objects.select_related("exchange").order_by("pk"):
    print(a.pk, a.exchange.code, a.label, a.status, a.trading_enabled, a.last_error_code, a.last_error_message[:120])
'
