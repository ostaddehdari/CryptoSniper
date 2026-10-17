#!/usr/bin/env bash
# CryptoSniper Stage 12 v0.12.0rc1 — Ubuntu 24.04 fresh install / safe upgrade.
# Usage: sudo bash /tmp/run.sh [/tmp/CryptoSniper-Stage12-v0.12.0rc1.zip]
# Validate only (no installation): bash run.sh --check /path/to/package.zip
# Installation and verification output is appended to runlog.txt beside this script.
# Installs Stage 12 (exchange center/paper); real orders remain disabled.
set -Eeuo pipefail
umask 077

# Change these BEFORE the first installation if necessary.
SERVER_HOST=srun.ir
URL_PREFIX=/cryptosniper
WEB_PORT=18881
PG_PORT=55432
REDIS_PORT=6389
APP_USER=cryptosniper
APP_ROOT=/opt/cryptosniper
APP_DIR=$APP_ROOT/app
CONFIG_DIR=/etc/cryptosniper
STATE_DIR=/var/lib/cryptosniper
LOGIN_FILE=/root/cryptosniper-login.txt
SOURCE_COMMIT=__SOURCE_COMMIT__
PREVIOUS_SOURCE_COMMIT=acde2adbe6a37d0ab875e7aff078beae4e7c6907
STAGE08_SOURCE_COMMIT=04d84c0e5ef75155bce32a173c2441e20f0f5080
STAGE06_SOURCE_COMMIT=2718263fb39c37e615a667ead65b039c9f659a58
STAGE05_SOURCE_COMMIT=156018079c4a85c0079bf12643973f439f05786e
STAGE04_SOURCE_COMMIT=c6914089372791a973f062f68dad4264bb78094a
STAGE03_SOURCE_COMMIT=ed499fce19142b16d10fdf2ef7d798223485aa73
STAGE02_SOURCE_COMMIT=5797b95a3170a4b986de5493ea4072a40a1dccd2
STAGE01_SOURCE_COMMIT=ac1f74fe8a22a226e60283cbbd1b1a610e70d5de
PREVIOUS_ARCHIVE_SHA256=d582c227dac0b7fb68a460c4a2e030e117460fd849a525813ee2e1007c311be8
STAGE08_ARCHIVE_SHA256=24a5ff7a700b2c56cca80af10681617bb1a8f22b9533757bc6fe8c2e2ad14fbd
STAGE06_ARCHIVE_SHA256=c3febb83e3224ca3aa9137983294432a2f71902b29b4b633434e1c56239900c3
STAGE05_ARCHIVE_SHA256=5f1a5f3a41b66ca3a552e0515414685b0b67e7cc01a6c9a957ee638895872d15
STAGE04_ARCHIVE_SHA256=bcc30b79c4990f27f287bab303ba2aee4d8c7e121cce249b18cb50cea4d96b73
STAGE03_ARCHIVE_SHA256=38c96027f503f38a71cddb807e89db9d5aeaa1081b2cd7ed87a3c11158fd4f93
STAGE02_ARCHIVE_SHA256=1298e0d4ee4ce86f3af82f9f9033f5414381195f392b82e025ea563532209333
STAGE01_ARCHIVE_SHA256=721c58cbf752fdd585550781f09ecd6175b586af0dd432e3435a71ce4f9245df
OLDER_STAGE03_ARCHIVE_SHA256=9e51c6649d42a672ba4c14c43770e0e9e102d29005b7c1ddc3f16b4b89f27f19
OFFICIAL_STAGE12_ARCHIVE_SHA256=__STAGE12_ARCHIVE_SHA256__

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
LOG_FILE=${LOG_FILE:-$SCRIPT_DIR/runlog.txt}
touch "$LOG_FILE"
chmod 600 "$LOG_FILE"
exec > >(tee -a "$LOG_FILE") 2>&1
report_error() {
    local status=$1 line=$2
    trap - ERR
    if [[ -n ${APP_BACKUP:-} && -d ${APP_BACKUP:-} ]]; then
        printf '\nRolling application files back to the preserved previous release...\n'
        for service in web orders reports beat signals market-data trailing alerts maintenance; do
            systemctl stop "cryptosniper-$service.service" 2>/dev/null || true
        done
        failed_dir=""
        if [[ -d $APP_DIR ]]; then
            failed_dir="$APP_ROOT/failed-stage12-$(date +%Y%m%d-%H%M%S)"
            mv "$APP_DIR" "$failed_dir" || true
        fi
        mv "$APP_BACKUP" "$APP_DIR" || true
        if [[ -n ${UNIT_BACKUP:-} && -d $UNIT_BACKUP ]]; then
            for unit_name in web orders reports beat signals market-data trailing alerts maintenance; do
                unit_path="/etc/systemd/system/cryptosniper-$unit_name.service"
                if [[ -f $UNIT_BACKUP/cryptosniper-$unit_name.service ]]; then
                    cp -a "$UNIT_BACKUP/cryptosniper-$unit_name.service" "$unit_path"
                else
                    systemctl disable "cryptosniper-$unit_name.service" 2>/dev/null || true
                    rm -f "$unit_path"
                fi
            done
            systemctl daemon-reload || true
        fi
        for service in redis web orders reports beat; do
            systemctl restart "cryptosniper-$service.service" 2>/dev/null || true
        done
        printf 'ROLLBACK: previous application restored.'
        if [[ -n $failed_dir ]]; then printf ' Failed release retained at %s' "$failed_dir"; fi
        printf '\n'
    fi
    printf '\nFAILED: line %s, exit %s. Log: %s\n' "$line" "$status" "$LOG_FILE"
    exit "$status"
}
trap 'report_error "$?" "$LINENO"' ERR
TMP_DIR=""
APP_BACKUP=""
UNIT_BACKUP=""
cleanup() { if [[ -n "$TMP_DIR" ]]; then rm -rf -- "$TMP_DIR"; fi; }
trap cleanup EXIT
fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
step() { printf '\n===== %s | %s =====\n' "$*" "$(date -Is)"; }

CHECK_ONLY=false
if [[ ${1:-} == --check ]]; then CHECK_ONLY=true; shift; fi
[[ $# -le 1 ]] || fail 'Usage: bash run.sh [--check] [package.zip]'
ARCHIVE=${1:-/tmp/CryptoSniper-Stage12-v0.12.0rc1.zip}
export SERVER_HOST URL_PREFIX WEB_PORT PG_PORT REDIS_PORT SOURCE_COMMIT
export STAGE08_SOURCE_COMMIT STAGE08_ARCHIVE_SHA256 PREVIOUS_SOURCE_COMMIT STAGE06_SOURCE_COMMIT STAGE05_SOURCE_COMMIT STAGE04_SOURCE_COMMIT STAGE03_SOURCE_COMMIT STAGE01_SOURCE_COMMIT STAGE02_SOURCE_COMMIT PREVIOUS_ARCHIVE_SHA256 STAGE06_ARCHIVE_SHA256 STAGE05_ARCHIVE_SHA256 STAGE04_ARCHIVE_SHA256 STAGE03_ARCHIVE_SHA256 STAGE02_ARCHIVE_SHA256 STAGE01_ARCHIVE_SHA256 OLDER_STAGE03_ARCHIVE_SHA256 OFFICIAL_STAGE12_ARCHIVE_SHA256
export APP_DIR APP_ROOT CONFIG_DIR STATE_DIR LOGIN_FILE

step 'VERIFY PACKAGE AND SETTINGS'
command -v python3 >/dev/null || fail 'Python 3 is required to validate the archive.'
python3 - "$ARCHIVE" <<'PY'
import hashlib, ipaddress, os, re, stat, sys, tomllib, zipfile
from pathlib import Path, PurePosixPath
path = Path(sys.argv[1])
if not path.is_file():
    raise SystemExit(f'ZIP not found: {path}')
actual_sha256 = hashlib.file_digest(path.open('rb'), 'sha256').hexdigest()
if actual_sha256 != os.environ['OFFICIAL_STAGE12_ARCHIVE_SHA256']:
    raise SystemExit(
        'Incorrect Stage12 ZIP (SHA-256 mismatch). Download the EXACT release asset '
        'CryptoSniper-Stage12-v0.12.0rc1.zip from '
        'https://github.com/ostaddehdari/CryptoSniper/releases/tag/stage12-v0.12.0rc1-deploy '
        f'(received SHA256: {actual_sha256}). Nothing was changed.'
    )
# Pin the release by checking the Git blob SHA-1 of independent immutable files.
# GitHub-generated ZIP bytes can vary even while source contents stay identical.
trusted_blobs = {
    'pyproject.toml': '__BLOB_PYPROJECT__',
    'uv.lock': '__BLOB_UVLOCK__',
    'docs/progress.json': '__BLOB_PROGRESS__',
    'backend/apps/trading/exits_engine.py': '__BLOB_EXITS_ENGINE__',
    'backend/apps/operations/recovery.py': '__BLOB_RECOVERY__',
    'backend/apps/alerts/engine.py': '__BLOB_ALERT_ENGINE__',
}

host = os.environ['SERVER_HOST']
try:
    ipaddress.IPv4Address(host)
except ValueError:
    if not re.fullmatch(r'(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}', host):
        raise SystemExit('SERVER_HOST must be an IPv4 address or DNS hostname, without port/path.')
with zipfile.ZipFile(path) as z:
    if z.testzip() is not None:
        raise SystemExit('ZIP integrity check failed.')
    seen = set()
    for item in z.infolist():
        if item.filename in seen:
            raise SystemExit('Duplicate archive member.')
        seen.add(item.filename)
        if item.file_size > 150 * 1024 * 1024:
            raise SystemExit('Unexpectedly large archive member.')
        p = PurePosixPath(item.filename)
        if p.is_absolute() or '..' in p.parts or not p.parts or p.parts[0] != 'CryptoSniper':
            raise SystemExit('Unsafe ZIP path.')
        if stat.S_ISLNK(item.external_attr >> 16):
            raise SystemExit('ZIP symbolic links are not allowed.')
        if {'.env', '.git', '.venv', '__pycache__', '.runtime'} & set(p.parts):
            raise SystemExit('ZIP contains private/generated files.')
    for name in ('backend/manage.py', 'uv.lock', 'docs/setup.md', 'backend/config/settings/production.py'):
        z.getinfo('CryptoSniper/' + name)
    project = tomllib.loads(z.read('CryptoSniper/pyproject.toml').decode())
    if project['project']['version'] != '0.12.0rc1':
        raise SystemExit('Unexpected project version.')
    for relative_path, expected_hash in trusted_blobs.items():
        data = z.read('CryptoSniper/' + relative_path)
        git_hash = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        if git_hash != expected_hash:
            raise SystemExit('Stage12 Git source content mismatch: ' + relative_path)
print('PASS: pinned Stage12 source blobs, safe paths and version 0.12.0rc1.')
print(f'HTTPS URL: https://{host}{os.environ["URL_PREFIX"]}/auth/login/')
PY
[[ -f /etc/os-release ]] || fail 'Ubuntu 24.04 is required.'
# shellcheck disable=SC1091
source /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 ]] || fail 'This installer supports Ubuntu 24.04 only.'
if $CHECK_ONLY; then
    printf '\nCHECK_OK: archive and Ubuntu version validated; nothing was installed.\n'
    exit 0
fi
[[ $EUID -eq 0 ]] || fail 'Run with sudo bash /tmp/run.sh'
[[ $(ps -p 1 -o comm=) == systemd ]] || fail 'An Ubuntu VPS with systemd is required.'
command -v flock >/dev/null || fail 'flock is required.'
exec 9>/run/cryptosniper-install.lock
flock -n 9 || fail 'Another CryptoSniper installer is running.'
TMP_DIR=$(mktemp -d /tmp/cryptosniper-install.XXXXXXXX)

step 'VERIFY EXISTING SRUN.IR HTTPS NGINX CONFIGURATION'
command -v nginx >/dev/null || fail 'An existing Nginx HTTPS site for srun.ir is required.'
systemctl is-active --quiet nginx || fail 'The existing Nginx service is not active.'
# This helper finds only the active srun.ir:443 server block. It never replaces a whole vhost.
cat > "$TMP_DIR/nginx-route.py" <<'PY'
import hashlib, json, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path

SNIPPET = Path('/etc/nginx/snippets/cryptosniper-location.conf')
INCLUDE = f'include {SNIPPET};'
MARKER = '# Managed by CryptoSniper Stage12 installer'
KNOWN_MARKERS = ('# Managed by CryptoSniper Stage01 installer', '# Managed by CryptoSniper Stage02 installer', '# Managed by CryptoSniper Stage03 installer', '# Managed by CryptoSniper Stage04 installer', '# Managed by CryptoSniper Stage05 installer', '# Managed by CryptoSniper Stage06 installer', '# Managed by CryptoSniper Stage07 installer', '# Managed by CryptoSniper Stage08 installer', '# Managed by CryptoSniper Stage09 installer', MARKER)
plan_path = Path(sys.argv[2])

def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()

def blocks(text):
    # Ignore comments and quoted brace characters; retain byte offsets for insertion.
    pattern = r'''"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\#[^\n]*|[{};]|(?:\\.|\$\{[^}]*\}|[^\s{};\#])+'''
    root = {'header': [], 'directives': [], 'children': []}
    stack = [root]
    statement = []
    for match in re.finditer(pattern, text):
        token = match.group()
        if token.startswith('#'):
            continue
        if token == '{':
            child = {'header': statement, 'directives': [], 'children': []}
            stack[-1]['children'].append(child)
            stack.append(child)
            statement = []
        elif token == '}':
            if len(stack) == 1 or statement:
                raise SystemExit('Unsupported/unbalanced Nginx configuration; no automatic edit.')
            stack.pop()['close'] = match.start()
        elif token == ';':
            stack[-1]['directives'].append(statement)
            statement = []
        else:
            statement.append(token.strip('\"\''))
    if len(stack) != 1 or statement:
        raise SystemExit('Unsupported/unbalanced Nginx configuration; no automatic edit.')
    def walk(node):
        yield node
        for child in node['children']:
            yield from walk(child)
    return list(walk(root))

def atomic_write(path, text, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.cryptosniper-')
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(text)
        os.chmod(name, mode)
        if path.exists():
            old = path.stat()
            os.chown(name, old.st_uid, old.st_gid)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)

action = sys.argv[1]
if action == 'plan':
    result = subprocess.run(['nginx', '-T'], text=True, capture_output=True)
    if result.returncode:
        raise SystemExit('The existing Nginx configuration failed validation; no changes were made.')
    paths = set(re.findall(r'^# configuration file (.+):$', result.stdout, re.M))
    candidates = []
    for filename in paths:
        path = Path(filename).resolve()
        text = path.read_text()
        for node in blocks(text):
            if node['header'] != ['server']:
                continue
            names = [d for d in node['directives'] if d and d[0] == 'server_name']
            listens = [d for d in node['directives'] if d and d[0] == 'listen']
            if not any('srun.ir' in d[1:] for d in names):
                continue
            if not any(len(d) > 1 and re.search(r'(^|:)443$', d[1]) and 'ssl' in d for d in listens):
                continue
            if any(d and d[0] == 'return' for d in node['directives']):
                raise SystemExit('The srun.ir TLS server has a server-wide return; automatic subpath routing is unsafe.')
            if any(c['header'] and c['header'][0] == 'location' and any('/cryptosniper' in t for t in c['header']) for c in node['children']):
                raise SystemExit('An existing inline /cryptosniper route was found; it was not overwritten.')
            candidates.append({'path': str(path), 'hash': digest(text), 'close': node['close'],
                               'included': ['include', str(SNIPPET)] in node['directives']})
    selected = os.environ.get('NGINX_VHOST')
    if selected:
        candidates = [c for c in candidates if c['path'] == str(Path(selected).resolve())]
    if len(candidates) != 1:
        raise SystemExit('Expected exactly one active srun.ir HTTPS server block. Set NGINX_VHOST to its config path if ambiguous.')
    if SNIPPET.exists() and not SNIPPET.read_text().startswith(KNOWN_MARKERS):
        raise SystemExit('An unmanaged CryptoSniper Nginx snippet exists; it was not overwritten.')
    # Included snippets may also contain an old app route; refuse to shadow them.
    for filename in paths:
        path = Path(filename).resolve()
        if path == SNIPPET or path == Path(candidates[0]['path']):
            continue
        if re.search(r'\blocation\s+(?:[=~^*]+\s+)?[\"\']?/cryptosniper(?:/|\s|[\"\'])', path.read_text()):
            raise SystemExit('An unmanaged included /cryptosniper route exists; it was not overwritten.')
    plan_path.write_text(json.dumps(candidates[0]))
    print('PASS: existing srun.ir HTTPS virtual host identified and configuration validated.')
elif action == 'apply':
    plan = json.loads(plan_path.read_text())
    path = Path(plan['path'])
    original = path.read_text()
    if digest(original) != plan['hash']:
        raise SystemExit('Nginx config changed during installation; no automatic edit was made.')
    backup = Path(os.environ['CONFIG_DIR']) / 'backups' / (time.strftime('%Y%m%d-%H%M%S') + '-' + str(os.getpid()))
    backup.mkdir(parents=True, mode=0o700)
    shutil.copy2(path, backup / 'vhost.conf')
    existed = SNIPPET.exists()
    if existed:
        shutil.copy2(SNIPPET, backup / 'snippet.conf')
    plan.update({'backup': str(backup), 'snippet_existed': existed})
    plan_path.write_text(json.dumps(plan))
    snippet = f'''{MARKER}
location = /cryptosniper {{
    return 308 /cryptosniper/;
}}
location ^~ /cryptosniper/ {{
    proxy_pass http://127.0.0.1:{os.environ['WEB_PORT']}/;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-Host "";
    proxy_redirect off;
    proxy_read_timeout 65s;
}}
'''
    atomic_write(SNIPPET, snippet)
    if not plan['included']:
        offset = plan['close']
        atomic_write(path, original[:offset] + '    ' + INCLUDE + '\n' + original[offset:], path.stat().st_mode & 0o777)
    print(f'Nginx backup: {backup}')
elif action == 'rollback':
    plan = json.loads(plan_path.read_text())
    if 'backup' not in plan:
        raise SystemExit('No Nginx changes to roll back.')
    backup = Path(plan['backup'])
    target = Path(plan['path'])
    atomic_write(target, (backup / 'vhost.conf').read_text(), (backup / 'vhost.conf').stat().st_mode & 0o777)
    if plan['snippet_existed']:
        atomic_write(SNIPPET, (backup / 'snippet.conf').read_text())
    else:
        SNIPPET.unlink(missing_ok=True)
    print('Previous Nginx configuration restored.')
else:
    raise SystemExit('Unknown Nginx helper action.')
PY
python3 "$TMP_DIR/nginx-route.py" plan "$TMP_DIR/nginx-plan.json"

step 'CHECK EXISTING INSTALLATION AND PORTS'
MANAGED=false
if [[ -f $CONFIG_DIR/install.json ]]; then
    python3 - <<'PY'
import json, os
from pathlib import Path
state = json.loads((Path(os.environ['CONFIG_DIR']) / 'install.json').read_text())
expected = {key: os.environ[key] for key in ('SERVER_HOST', 'URL_PREFIX', 'WEB_PORT', 'PG_PORT', 'REDIS_PORT')}
if any(state.get(key) != value for key, value in expected.items()):
    raise SystemExit('Existing installer configuration differs. No automatic upgrade/configuration replacement.')
if state.get('SOURCE_COMMIT') not in {os.environ['STAGE01_SOURCE_COMMIT'], os.environ['STAGE02_SOURCE_COMMIT'], os.environ['STAGE03_SOURCE_COMMIT'], os.environ['STAGE04_SOURCE_COMMIT'], os.environ['STAGE05_SOURCE_COMMIT'], os.environ['STAGE06_SOURCE_COMMIT'], os.environ['STAGE08_SOURCE_COMMIT'], os.environ['PREVIOUS_SOURCE_COMMIT'], os.environ['SOURCE_COMMIT']}:
    raise SystemExit('Existing installation source is not a supported Stage01/Stage02/Stage12 release.')
print('Existing managed installation detected; private configuration, database and login will be preserved.')
PY
    MANAGED=true
else
    [[ ! -e $APP_ROOT && ! -e $CONFIG_DIR && ! -e $STATE_DIR ]] || fail 'An unmanaged CryptoSniper directory exists; inspect it before installation.'
    ! id "$APP_USER" >/dev/null 2>&1 || fail 'An unmanaged cryptosniper user already exists.'
    [[ ! -e /etc/postgresql/16/cryptosniper ]] || fail 'An unmanaged PostgreSQL cryptosniper cluster exists.'
    [[ ! -e $LOGIN_FILE ]] || fail 'A pre-existing login file exists; inspect it before installation.'
    for name in web orders reports beat redis signals market-data trailing alerts maintenance; do
        [[ ! -e /etc/systemd/system/cryptosniper-$name.service ]] || fail "An unmanaged service exists: cryptosniper-$name"
    done
fi
command -v ss >/dev/null || fail 'The ss command (iproute2) is required.'
for port in "$WEB_PORT" "$PG_PORT" "$REDIS_PORT"; do
    if [[ -n $(ss -H -ltn "sport = :$port") ]] && ! $MANAGED; then
        fail "Port $port is already in use. Existing services have not been stopped."
    fi
done

step 'INSTALL SYSTEM DEPENDENCIES'
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends python3.12 python3.12-venv postgresql-16 postgresql-client-16 redis-server redis-tools ca-certificates curl openssl
if ! $MANAGED; then
    useradd --system --user-group --home-dir "$APP_ROOT" --shell /usr/sbin/nologin "$APP_USER"
    install -d -m 750 -o root -g "$APP_USER" "$APP_ROOT" "$CONFIG_DIR"
    install -d -m 750 -o "$APP_USER" -g "$APP_USER" "$STATE_DIR" "$STATE_DIR/redis" "$STATE_DIR/beat" "$STATE_DIR/cache"
    python3 - <<'PY'
import json, os
from pathlib import Path
state = {key: os.environ[key] for key in ('SERVER_HOST', 'URL_PREFIX', 'WEB_PORT', 'PG_PORT', 'REDIS_PORT', 'SOURCE_COMMIT')}
path = Path(os.environ['CONFIG_DIR']) / 'install.json'
path.write_text(json.dumps(state, indent=2) + '\n')
path.chmod(0o600)
PY
fi

ARCHIVE_SHA256=$(sha256sum "$ARCHIVE" | awk '{print $1}')
export ARCHIVE_SHA256
step 'INSTALL PINNED STAGE12 SOURCE; PRESERVE PRIVATE CONFIGURATION'
UNIT_BACKUP="$CONFIG_DIR/backups/units-$(date +%Y%m%d-%H%M%S)-$$"
mkdir -p "$UNIT_BACKUP"
for unit_name in web orders reports beat signals market-data trailing alerts maintenance; do
    unit_path="/etc/systemd/system/cryptosniper-$unit_name.service"
    if [[ -f $unit_path ]]; then cp -a "$unit_path" "$UNIT_BACKUP/"; fi
done
CURRENT_ARCHIVE_SHA=""
if [[ -f $APP_DIR/.installed-source.sha256 ]]; then
    CURRENT_ARCHIVE_SHA=$(cat "$APP_DIR/.installed-source.sha256")
fi
if [[ $CURRENT_ARCHIVE_SHA != "$ARCHIVE_SHA256" ]]; then
    if [[ -n $CURRENT_ARCHIVE_SHA && $CURRENT_ARCHIVE_SHA != "$PREVIOUS_ARCHIVE_SHA256" && $CURRENT_ARCHIVE_SHA != "$STAGE08_ARCHIVE_SHA256" && $CURRENT_ARCHIVE_SHA != "$STAGE06_ARCHIVE_SHA256" && $CURRENT_ARCHIVE_SHA != "$STAGE05_ARCHIVE_SHA256" && $CURRENT_ARCHIVE_SHA != "$STAGE04_ARCHIVE_SHA256" && $CURRENT_ARCHIVE_SHA != "$STAGE03_ARCHIVE_SHA256" && $CURRENT_ARCHIVE_SHA != "$STAGE02_ARCHIVE_SHA256" && $CURRENT_ARCHIVE_SHA != "$STAGE01_ARCHIVE_SHA256" && $CURRENT_ARCHIVE_SHA != "$OLDER_STAGE03_ARCHIVE_SHA256" ]]; then
        fail 'Existing application checksum is not an allowed Stage01/02/03 source; no files were replaced.'
    fi
    python3 - "$ARCHIVE" "$TMP_DIR" <<'PY'
import sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as z:
    z.extractall(sys.argv[2])
PY
    printf '%s\n' "$ARCHIVE_SHA256" > "$TMP_DIR/CryptoSniper/.installed-source.sha256"
    if [[ -d $APP_DIR ]]; then
        cp -p "$APP_DIR/.env" "$TMP_DIR/CryptoSniper/.env"
        install -d -m 750 -o root -g "$APP_USER" "$APP_ROOT/backups"
        APP_BACKUP="$APP_ROOT/backups/app-stage-prev-$(date +%Y%m%d-%H%M%S)"
        for service in web orders reports beat signals market-data trailing alerts maintenance; do
            systemctl stop "cryptosniper-$service.service" 2>/dev/null || true
        done
        mv "$APP_DIR" "$APP_BACKUP"
    fi
    mv "$TMP_DIR/CryptoSniper" "$APP_DIR"
    chown -R "$APP_USER:$APP_USER" "$APP_DIR"
fi
[[ -f $APP_DIR/.installed-source.sha256 ]] || fail 'Application source marker is missing.'
[[ $(cat "$APP_DIR/.installed-source.sha256") == "$ARCHIVE_SHA256" ]] || fail 'Application source belongs to a different version.'

if [[ ! -e $APP_DIR/.env ]]; then
    python3 - <<'PY'
import os, secrets
from pathlib import Path
env = {
    'DJANGO_SETTINGS_MODULE': 'config.settings.server',
    'DJANGO_SECRET_KEY': secrets.token_urlsafe(64),
    'DJANGO_ALLOWED_HOSTS': os.environ['SERVER_HOST'] + ',127.0.0.1,localhost',
    'DATABASE_URL': f'postgresql://cryptosniper:{secrets.token_hex(32)}@127.0.0.1:{os.environ["PG_PORT"]}/cryptosniper',
    'DJANGO_CSRF_TRUSTED_ORIGINS': f'https://{os.environ["SERVER_HOST"]}',
    'DJANGO_SECURE_SSL_REDIRECT': 'true',
    'DJANGO_PROXY_SSL_HEADER': 'true',
    'DJANGO_HSTS_SECONDS': '0',
    'LOG_LEVEL': 'INFO',
    'EXCHANGE_CREDENTIAL_KEYS': '1:' + __import__('base64').urlsafe_b64encode(secrets.token_bytes(32)).decode('ascii'),
}
redis_secret = secrets.token_hex(32)
for key, db in (('REDIS_CACHE_URL', 0), ('CELERY_BROKER_URL', 1), ('CELERY_RESULT_BACKEND', 2)):
    env[key] = f'redis://:{redis_secret}@127.0.0.1:{os.environ["REDIS_PORT"]}/{db}'
path = Path(os.environ['APP_DIR']) / '.env'
path.write_text('\n'.join(f'{k}={v}' for k, v in env.items()) + '\n')
path.chmod(0o640)
print('Private production .env generated; secrets are not printed.')
PY
fi
# Stage02 had no exchange keyring; upgrade private configuration without resetting secrets.
python3 - "$APP_DIR/.env" <<'PY'
import base64, secrets, sys
from pathlib import Path
path = Path(sys.argv[1])
lines = path.read_text().splitlines()
if not any(line.startswith('EXCHANGE_CREDENTIAL_KEYS=') for line in lines):
    with path.open('a') as handle:
        handle.write('EXCHANGE_CREDENTIAL_KEYS=1:' + base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('ascii') + '\n')
    print('Generated encrypted-exchange keyring in private .env.')
else:
    print('Preserved existing encrypted-exchange keyring.')
PY
chown "root:$APP_USER" "$APP_DIR/.env"
chmod 640 "$APP_DIR/.env"
# Deployment-only settings for the existing srun.ir HTTPS virtual host.
# Nginx removes /cryptosniper/ before forwarding; Django restores it when generating URLs.
cat > "$APP_DIR/backend/config/settings/server.py" <<'PY'
from .production import *

FORCE_SCRIPT_NAME = "/cryptosniper"
STATIC_URL = "/cryptosniper/static/"
SESSION_COOKIE_NAME = "cryptosniper_sessionid"
CSRF_COOKIE_NAME = "cryptosniper_csrftoken"
SESSION_COOKIE_PATH = "/cryptosniper/"
CSRF_COOKIE_PATH = "/cryptosniper/"
PY
chown "root:$APP_USER" "$APP_DIR/backend/config/settings/server.py"
chmod 640 "$APP_DIR/backend/config/settings/server.py"

# uv is isolated from the server's system Python. Application dependencies use uv.lock.
if [[ ! -x $APP_ROOT/tools/bin/uv ]]; then
    python3.12 -m venv "$APP_ROOT/tools"
    "$APP_ROOT/tools/bin/pip" install --disable-pip-version-check 'uv==0.12.23'
fi
# The installer runs with umask 077; make the isolated uv environment executable
# by the dedicated service account on both fresh and resumed installations.
chown -R "root:$APP_USER" "$APP_ROOT/tools"
chmod -R u=rwX,g=rX,o= "$APP_ROOT/tools"
runuser -u "$APP_USER" -- test -x "$APP_ROOT/tools/bin/uv" \
    || fail 'The dedicated application user cannot execute uv.'
run_app() {
    runuser -u "$APP_USER" -- env DJANGO_SETTINGS_MODULE=config.settings.server UV_CACHE_DIR="$STATE_DIR/cache" "$@"
}
cd "$APP_DIR"
run_app "$APP_ROOT/tools/bin/uv" sync --frozen --no-dev --python /usr/bin/python3.12

step 'DEDICATED POSTGRESQL CLUSTER'
if [[ ! -e /etc/postgresql/16/cryptosniper ]]; then
    pg_createcluster 16 cryptosniper --port "$PG_PORT" --start-conf auto -- --auth-host=scram-sha-256 --auth-local=peer
else
    PG_PORT=$(pg_conftool -s 16 cryptosniper show port)
    [[ $PG_PORT =~ ^[0-9]+$ ]] || fail 'Existing dedicated PostgreSQL port is invalid.'
    export PG_PORT
fi
# Some VPS systemd builds do not reliably adopt the daemon forked by
# postgresql@.service. Run this dedicated cluster in the foreground under its
# own Type=simple unit so systemd always tracks the real PostgreSQL process.
PG_DATA_DIR=/var/lib/postgresql/16/cryptosniper
PG_CONFIG_FILE=/etc/postgresql/16/cryptosniper/postgresql.conf
pg_conftool 16 cryptosniper set shared_buffers 64MB

# pg_conftool writes string quoting differently across Debian releases. Write
# these two string settings explicitly and remove any invalid values left by a
# previous installer run (for example a hostname containing literal quotes).
python3 - "$PG_CONFIG_FILE" <<'PY'
import re
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
keys = ("listen_addresses", "unix_socket_directories")
lines = [
    line
    for line in text.splitlines()
    if not any(re.match(rf"^[ \t]*{re.escape(key)}[ \t]*=", line) for key in keys)
]
lines.extend(
    (
        "listen_addresses = '127.0.0.1'",
        "unix_socket_directories = '/var/run/postgresql'",
    )
)
path.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
chown postgres:postgres "$PG_CONFIG_FILE"
chmod 0644 "$PG_CONFIG_FILE"

systemctl disable --now postgresql@16-cryptosniper.service 2>/dev/null || true
systemctl stop cryptosniper-postgres.service 2>/dev/null || true

# A managed host may already use the preferred high port. Relocate only this
# stopped, dedicated cluster and keep the generated password/database intact.
if [[ -n $(ss -H -ltn "sport = :$PG_PORT") ]]; then
    selected_port=''
    for ((candidate=55432; candidate<=55531; candidate++)); do
        if [[ -z $(ss -H -ltn "sport = :$candidate") ]]; then
            selected_port=$candidate
            break
        fi
    done
    [[ -n $selected_port ]] || fail 'No free PostgreSQL port is available in 55432-55531.'
    PG_PORT=$selected_port
    export PG_PORT
    pg_conftool 16 cryptosniper set port "$PG_PORT"
    printf 'PostgreSQL port conflict avoided; dedicated port selected: %s\n' "$PG_PORT"
fi

# Synchronize only the local port in private configuration. Passwords are
# neither regenerated nor printed.
python3 - <<'PY'
import json, os, re
from pathlib import Path

env_path = Path(os.environ['APP_DIR']) / '.env'
text = env_path.read_text()
pattern = r'(?m)^(DATABASE_URL=postgresql://cryptosniper:[a-f0-9]{64}@127\.0\.0\.1:)\d+(/cryptosniper(?:\?[^\n]*)?)$'
updated, count = re.subn(pattern, rf'\g<1>{os.environ["PG_PORT"]}\g<2>', text)
if count != 1:
    raise SystemExit('Private DATABASE_URL has an unsupported format; refusing automatic port edit.')
env_path.write_text(updated)
env_path.chmod(0o640)

install_path = Path(os.environ['CONFIG_DIR']) / 'install.json'
if install_path.exists():
    data = json.loads(install_path.read_text())
    data['PG_PORT'] = os.environ['PG_PORT']
    install_path.write_text(json.dumps(data, indent=2) + '\n')
    install_path.chmod(0o600)
PY
chown "root:$APP_USER" "$APP_DIR/.env"

install -d -m 2775 -o postgres -g postgres /var/run/postgresql
install -d -m 1775 -o root -g postgres /var/log/postgresql
touch /var/log/postgresql/postgresql-16-cryptosniper.log
chown postgres:adm /var/log/postgresql/postgresql-16-cryptosniper.log
chmod 640 /var/log/postgresql/postgresql-16-cryptosniper.log
chown -R postgres:postgres "$PG_DATA_DIR"
chmod 700 "$PG_DATA_DIR"
printf 'manual\n' > /etc/postgresql/16/cryptosniper/start.conf

# Remove only a demonstrably stale PID file belonging to this dedicated data
# directory. Never disturb a running PostgreSQL process.
if [[ -f $PG_DATA_DIR/postmaster.pid ]]; then
    read -r pg_pid < "$PG_DATA_DIR/postmaster.pid" || pg_pid=''
    if [[ ! $pg_pid =~ ^[0-9]+$ ]] || ! kill -0 "$pg_pid" 2>/dev/null; then
        rm -f "$PG_DATA_DIR/postmaster.pid"
    elif ! tr '\0' ' ' < "/proc/$pg_pid/cmdline" 2>/dev/null | grep -Fq -- "$PG_DATA_DIR"; then
        fail 'PostgreSQL PID file points to an unrelated live process; refusing automatic removal.'
    fi
fi

cat > /etc/systemd/system/cryptosniper-postgres.service <<EOF
[Unit]
Description=CryptoSniper Stage12 dedicated PostgreSQL
After=network.target
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
Type=simple
User=postgres
Group=postgres
ExecStart=/usr/lib/postgresql/16/bin/postgres -D $PG_DATA_DIR -c config_file=$PG_CONFIG_FILE
ExecReload=/bin/kill -HUP \$MAINPID
KillMode=mixed
KillSignal=SIGINT
TimeoutStartSec=120
TimeoutStopSec=120
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
if ! systemctl enable --now cryptosniper-postgres.service; then
    systemctl --no-pager --full status cryptosniper-postgres.service || true
    journalctl --no-pager -u cryptosniper-postgres.service -n 40 || true
    fail 'Dedicated PostgreSQL service failed to start.'
fi
for _ in {1..30}; do
    pg_isready -q -h 127.0.0.1 -p "$PG_PORT" && break
    sleep 1
done
if ! pg_isready -q -h 127.0.0.1 -p "$PG_PORT"; then
    systemctl --no-pager --full status cryptosniper-postgres.service || true
    journalctl --no-pager -u cryptosniper-postgres.service -n 60 || true
    if [[ -f /var/log/postgresql/postgresql-16-cryptosniper.log ]]; then
        printf '\n----- PostgreSQL cluster log -----\n'
        tail -n 60 /var/log/postgresql/postgresql-16-cryptosniper.log || true
    fi
    fail 'Dedicated PostgreSQL did not become ready.'
fi
# Do not log SQL or its error details: provisioning contains a generated DB password.
if ! python3 - <<'PY' | runuser -u postgres -- psql -X -q -h /var/run/postgresql -p "$PG_PORT" -d postgres > "$TMP_DIR/database-output" 2>&1
import re
from pathlib import Path
from urllib.parse import urlsplit
env = dict(line.split('=', 1) for line in Path('.env').read_text().splitlines() if '=' in line and not line.startswith('#'))
password = urlsplit(env['DATABASE_URL']).password
if not password or not re.fullmatch('[a-f0-9]{64}', password):
    raise SystemExit('Generated database password format differs; refusing automatic provisioning.')
print('\\set ON_ERROR_STOP on')
print("DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='cryptosniper') THEN CREATE ROLE cryptosniper LOGIN; END IF; END $$;")
print(f"ALTER ROLE cryptosniper PASSWORD '{password}' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;")
print("SELECT 'CREATE DATABASE cryptosniper OWNER cryptosniper' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='cryptosniper')\\gexec")
PY
then
    fail 'Dedicated database provisioning failed. Password-bearing SQL output was withheld.'
fi
rm -f "$TMP_DIR/database-output"

step 'DEDICATED REDIS CONFIGURATION'
python3 - <<'PY'
import os, re
from pathlib import Path
from urllib.parse import urlsplit
env = dict(line.split('=', 1) for line in Path('.env').read_text().splitlines() if '=' in line and not line.startswith('#'))
password = urlsplit(env['REDIS_CACHE_URL']).password
if not password or not re.fullmatch('[a-f0-9]{64}', password):
    raise SystemExit('Generated Redis password format differs; refusing automatic provisioning.')
text = f'''bind 127.0.0.1
protected-mode yes
port {os.environ['REDIS_PORT']}
daemonize no
supervised no
dir {os.environ['STATE_DIR']}/redis
appendonly yes
appendfsync everysec
requirepass {password}
logfile ""
'''
path = Path(os.environ['CONFIG_DIR']) / 'redis.conf'
path.write_text(text)
path.chmod(0o640)
PY
chown "root:$APP_USER" "$CONFIG_DIR/redis.conf"
write_unit() {
    local name=$1 description=$2 command=$3
    cat > "/etc/systemd/system/cryptosniper-$name.service" <<EOF
[Unit]
Description=CryptoSniper Stage12 $description
After=network.target cryptosniper-postgres.service cryptosniper-redis.service
Requires=cryptosniper-postgres.service cryptosniper-redis.service

[Service]
Type=simple
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
Environment=DJANGO_SETTINGS_MODULE=config.settings.server
Environment=HOME=$APP_ROOT
EnvironmentFile=$APP_DIR/.env
ExecStart=$command
Restart=on-failure
RestartSec=5
TimeoutStopSec=60
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$STATE_DIR
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
}
# Redis has its own unit, so there is no ordering dependency on itself.
cat > /etc/systemd/system/cryptosniper-redis.service <<EOF
[Unit]
Description=CryptoSniper Stage12 dedicated Redis
After=network.target
[Service]
Type=simple
User=$APP_USER
Group=$APP_USER
ExecStart=/usr/bin/redis-server $CONFIG_DIR/redis.conf
Restart=on-failure
RestartSec=5
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$STATE_DIR/redis
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now cryptosniper-redis.service

step 'MIGRATIONS, STATIC FILES AND FIRST LOGIN'
run_app "$APP_DIR/.venv/bin/python" backend/manage.py check
run_app "$APP_DIR/.venv/bin/python" backend/manage.py migrate --noinput
run_app "$APP_DIR/.venv/bin/python" backend/manage.py collectstatic --noinput
if [[ ! -e $LOGIN_FILE ]]; then
    python3 - <<'PY'
import json, os, secrets
from pathlib import Path
password = secrets.token_urlsafe(24)
url = f'https://{os.environ["SERVER_HOST"]}{os.environ["URL_PREFIX"]}/auth/login/'
Path(os.environ['LOGIN_FILE']).write_text(f'URL: {url}\nUsername: admin\nPassword: {password}\n')
Path(os.environ['LOGIN_FILE']).chmod(0o600)
path = Path(os.environ['CONFIG_DIR']) / 'admin-bootstrap.json'
path.write_text(json.dumps({'username': 'admin', 'password': password}))
path.chmod(0o640)
PY
fi
# If the previous run stopped before account creation, resume from the private bootstrap file.
if [[ -f $CONFIG_DIR/admin-bootstrap.json ]]; then
    chown "root:$APP_USER" "$CONFIG_DIR/admin-bootstrap.json"
    run_app "$APP_DIR/.venv/bin/python" backend/manage.py shell <<'PY'
import json
from pathlib import Path
from django.contrib.auth import get_user_model
data = json.loads(Path('/etc/cryptosniper/admin-bootstrap.json').read_text())
User = get_user_model()
if User.objects.filter(username=data['username']).exists():
    user = User.objects.get(username=data['username'])
    if not (user.is_superuser and user.check_password(data['password'])):
        raise SystemExit('The bootstrap username already exists with different credentials; it was not reset.')
else:
    User.objects.create_superuser(username=data['username'], email='', password=data['password'])
print('Initial administrator created; password is stored privately, outside runlog.txt.')
PY
    rm -f "$CONFIG_DIR/admin-bootstrap.json"
fi

step 'PERSISTENT WEB AND WORKER SERVICES'
write_unit web 'web behind HTTPS Nginx' "$APP_DIR/.venv/bin/gunicorn --chdir $APP_DIR/backend config.wsgi:application --bind 127.0.0.1:$WEB_PORT --workers 2 --timeout 60 --forwarded-allow-ips 127.0.0.1 --access-logfile - --error-logfile -"
# systemd specifiers must be escaped as %% to pass %h through to Celery.
write_unit orders 'independent orders worker' "$APP_DIR/.venv/bin/celery --workdir $APP_DIR/backend -A config worker -Q orders --concurrency=1 -n orders@%%h --loglevel=INFO"
write_unit reports 'reports worker' "$APP_DIR/.venv/bin/celery --workdir $APP_DIR/backend -A config worker -Q reports --concurrency=1 -n reports@%%h --loglevel=INFO"
for queue_name in signals market_data trailing alerts maintenance; do
    unit_name=${queue_name//_/-}
    write_unit "$unit_name" "independent $queue_name worker" "$APP_DIR/.venv/bin/celery --workdir $APP_DIR/backend -A config worker -Q $queue_name --concurrency=1 -n $queue_name@%%h --loglevel=INFO"
done
write_unit beat 'single Beat scheduler' "$APP_DIR/.venv/bin/celery --workdir $APP_DIR/backend -A config beat --schedule $STATE_DIR/beat/celerybeat-schedule --loglevel=INFO"
systemctl daemon-reload
for name in web orders reports beat signals market-data trailing alerts maintenance; do
    systemctl enable "cryptosniper-$name.service"
    systemctl restart "cryptosniper-$name.service"
done
step 'LOCAL WEB CHECKS'
curl --fail --silent --show-error --retry 10 --retry-connrefused --retry-delay 1 --max-time 10 \
    -H "Host: $SERVER_HOST" -H 'X-Forwarded-Proto: https' "http://127.0.0.1:$WEB_PORT/health/ready/"
printf '\n'
curl --fail --silent --show-error --max-time 10 \
    -H "Host: $SERVER_HOST" -H 'X-Forwarded-Proto: https' "http://127.0.0.1:$WEB_PORT/auth/login/" > "$TMP_DIR/login.html"
grep -q '/cryptosniper/static/' "$TMP_DIR/login.html" || fail 'Static URL prefix verification failed.'
grep -q 'action="/cryptosniper/auth/login/"' "$TMP_DIR/login.html" || fail 'Login form URL prefix verification failed.'
run_app "$APP_DIR/.venv/bin/python" backend/manage.py check_infrastructure --timeout 30
run_app "$APP_DIR/.venv/bin/python" backend/manage.py shell <<'PY'
import time
from django.core.cache import cache
cache.delete('worker_heartbeat')
deadline = time.monotonic() + 45
while time.monotonic() < deadline:
    if cache.get('worker_heartbeat'):
        print('PASS: Beat dispatched a heartbeat; an independent worker recorded it in Redis.')
        break
    time.sleep(1)
else:
    raise SystemExit('FAIL: No Beat/worker heartbeat within 45 seconds.')
PY
run_app "$APP_DIR/.venv/bin/python" backend/manage.py shell <<'PYQUEUES'
import time
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from apps.operations.models import WorkerHeartbeat
for attempt in range(50):
    fresh = set(WorkerHeartbeat.objects.filter(seen_at__gte=timezone.now()-timedelta(seconds=95)).values_list('queue', flat=True))
    if set(settings.OPERATION_QUEUES) <= fresh:
        print('PASS: all seven queues have fresh, independently consumed heartbeat receipts.')
        break
    time.sleep(1)
else:
    raise SystemExit('FAIL: at least one queue has no recent heartbeat receipt.')
PYQUEUES
for name in redis web orders reports beat signals market-data trailing alerts maintenance; do
    systemctl is-active --quiet "cryptosniper-$name.service"
    printf 'PASS: cryptosniper-%s active\n' "$name"
done
step 'CONNECT THE SRUN.IR SUBPATH WITH BACKUP AND ROLLBACK'
if ! python3 "$TMP_DIR/nginx-route.py" apply "$TMP_DIR/nginx-plan.json"; then
    if grep -q '"backup"' "$TMP_DIR/nginx-plan.json"; then
        python3 "$TMP_DIR/nginx-route.py" rollback "$TMP_DIR/nginx-plan.json"
    fi
    fail 'Nginx route installation did not complete.'
fi
if ! nginx -t || ! systemctl reload nginx; then
    python3 "$TMP_DIR/nginx-route.py" rollback "$TMP_DIR/nginx-plan.json"
    if nginx -t; then systemctl reload nginx || true; fi
    fail 'Nginx validation/reload failed; previous configuration was restored.'
fi
# Validate that Nginx actually loaded the new route. Reload is asynchronous:
# one immediate HTTPS request may hit an old worker and return a false 404.
# Allow old workers time to drain; never keep a broken route in production.
if ! nginx -T > "$TMP_DIR/nginx-loaded.conf" 2>/dev/null ||
   ! grep -Fq 'location ^~ /cryptosniper/' "$TMP_DIR/nginx-loaded.conf"; then
    python3 "$TMP_DIR/nginx-route.py" rollback "$TMP_DIR/nginx-plan.json"
    if nginx -t; then systemctl reload nginx || true; fi
    fail 'Nginx did not load the CryptoSniper location snippet; config restored.'
fi

# Request the loopback HTTPS origin, not an external TLS edge. The origin's
# certificate can be edge-only, so --insecure applies only to this localhost probe.
# Never submit credentials or request private account information from this probe.
probe_nginx_route() {
    local route="$1" label="$2" attempt code
    for ((attempt=1; attempt<=30; attempt++)); do
        code=$(curl --insecure --silent --output /dev/null \
            --write-out '%{http_code}' --max-time 5 \
            --resolve "$SERVER_HOST:443:127.0.0.1" \
            "https://$SERVER_HOST$URL_PREFIX$route" 2>/dev/null) || code="000"
        if [[ "$code" == "200" ]]; then
            printf 'PASS: Nginx %s HTTP 200 after attempt %s.\n' "$label" "$attempt"
            return 0
        fi
        if (( attempt == 1 || attempt % 5 == 0 )); then
            printf 'WAIT: Nginx %s returned HTTP %s (attempt %s/30).\n' "$label" "$code" "$attempt"
        fi
        sleep 1
    done
    return 1
}
if ! probe_nginx_route '/health/ready/' 'readiness' ||
   ! probe_nginx_route '/auth/login/' 'login'; then
    python3 "$TMP_DIR/nginx-route.py" rollback "$TMP_DIR/nginx-plan.json"
    if nginx -t; then systemctl reload nginx || true; fi
    fail 'HTTPS subpath still failed after 30 attempts; previous Nginx route restored. App services remain installed. Run scripts/diagnose-nginx.sh.'
fi
printf '\nPASS: HTTPS subpath and login through the local Nginx origin.\n'
python3 - <<'PY'
import json, os
from pathlib import Path
state = {key: os.environ[key] for key in ('SERVER_HOST', 'URL_PREFIX', 'WEB_PORT', 'PG_PORT', 'REDIS_PORT', 'SOURCE_COMMIT')}
path = Path(os.environ['CONFIG_DIR']) / 'install.json'
path.write_text(json.dumps(state, indent=2) + '\n')
path.chmod(0o600)
PY
APP_BACKUP=""
printf '\nINSTALL_OK: CryptoSniper Stage12 v0.12.0rc1\n'
printf 'Login: https://%s%s/auth/login/\n' "$SERVER_HOST" "$URL_PREFIX"
printf 'Private login credentials: %s (root only; not printed in this log)\n' "$LOGIN_FILE"
printf 'Installer log: %s\n' "$LOG_FILE"
printf 'Service logs: journalctl -u cryptosniper-web -u cryptosniper-orders -u cryptosniper-reports -u cryptosniper-beat\n'
printf 'Nginx uses the existing srun.ir HTTPS certificate; no temporary certificate was created.\n'
printf 'Stage12: seven independent queues, durable Paper recovery, price/trade alerts and notifications; Binance real order writes remain disabled.\n'
