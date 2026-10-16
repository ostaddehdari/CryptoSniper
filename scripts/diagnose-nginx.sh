#!/usr/bin/env bash
# Read-only CryptoSniper /cryptosniper Nginx route diagnostics.
# No config modifications, reloads, service restarts or credentials are read.
set -uo pipefail
export LC_ALL=C
echo 'DIAG=CRYPTOSNIPER_NGINX_READ_ONLY_V1'

probe() {
    local label="$1"
    shift
    printf '%s: ' "$label"
    curl --silent --show-error --insecure --max-time 12 --output /dev/null \
         --write-out 'http_code=%{http_code} remote_ip=%{remote_ip}\n' "$@" || echo 'PROBE_FAILED'
}

echo '=== LOCAL DJANGO ==='
probe DJANGO_LOGIN -H 'Host: srun.ir' -H 'X-Forwarded-Proto: https' \
      http://127.0.0.1:18881/auth/login/
probe DJANGO_READY -H 'Host: srun.ir' -H 'X-Forwarded-Proto: https' \
      http://127.0.0.1:18881/health/ready/

echo '=== HTTPS ORIGIN ==='
probe LOCAL_NGINX_LOGIN --resolve 'srun.ir:443:127.0.0.1' \
      https://srun.ir/cryptosniper/auth/login/
probe LOCAL_NGINX_READY --resolve 'srun.ir:443:127.0.0.1' \
      https://srun.ir/cryptosniper/health/ready/

echo '=== LISTENERS ==='
command -v ss >/dev/null && ss -H -ltn '( sport = :443 )' || true

echo '=== NGINX VALIDATION AND RELEVANT DIRECTIVES ==='
nginx -t 2>&1 | tail -n 8
python3 - <<'PY'
import re
import subprocess

r = subprocess.run(['nginx', '-T'], capture_output=True, text=True, timeout=30)
if r.returncode:
    print('NGINX_DUMP_UNAVAILABLE')
    raise SystemExit(0)
parts = re.split(r'(?m)^# configuration file (.+):\s*$', r.stdout)
count = 0
for i in range(1, len(parts), 2):
    name, body = parts[i], parts[i + 1]
    if not re.search(r'(?<![\w.-])srun\.ir(?![\w.-])|cryptosniper', body, re.I):
        continue
    # Only show structural directives, not sensitive data, passwords, certificates or keys.
    print('CONFIG_FILE:', name)
    print('HAS_SRUN_HOST:', bool(re.search(r'^\s*server_name\s+[^;]*\bsrun\.ir\b', body, re.M)))
    print('HAS_CRYPTOSNIPER:', 'cryptosniper' in body.lower())
    shown = 0
    for n, line in enumerate(body.splitlines(), 1):
        stripped = line.strip()
        match = re.match(r'^(listen|server_name|location|include|root|try_files|return)\s+', stripped)
        if not match and 'cryptosniper' not in stripped.lower():
            continue
        if stripped.startswith('#') or any(token in stripped.lower() for token in ('password', 'secret', 'token', 'private_key', 'api_key')):
            continue
        if len(stripped) > 240:
            stripped = stripped[:240] + '...'
        # Paths, hostnames and generic routing directives only; no proxy credentials.
        print(f'  {n}: {stripped}')
        shown += 1
        if shown >= 70:
            print('  ... OUTPUT_TRUNCATED')
            break
    count += 1
    if count >= 12:
        print('MORE_FILES_OMITTED')
        break
print('NGINX_RELEVANT_FILES=', count)
PY
echo 'DIAG_END=READ_ONLY'
