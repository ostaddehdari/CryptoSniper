#!/usr/bin/env bash
# CryptoSniper: single-command, pinned verified deployment artifact.
# Usage: curl -fsSL https://raw.githubusercontent.com/ostaddehdari/CryptoSniper/main/scripts/deploy.sh -o /tmp/cryptosniper-deploy.sh && sudo bash /tmp/cryptosniper-deploy.sh
# Only the SHA256-verified Stage29 React ZIP and installer from the official release are executed.
set -Eeuo pipefail
umask 077

RELEASE_TAG='stage29-react-v0.29.0rc1-deploy-r1'
ZIP_NAME='CryptoSniper-Stage29-React-v0.29.0rc1-r1.zip'
INSTALLER_NAME='cryptosniper-stage29-react-run.sh'
ZIP_SHA256='5271407b985ea0b47dfa400fbc7cacab89167156191759c8eed0f08fc2dab1e1'
INSTALLER_SHA256='45aa55e3c494fa0ddb878cca261e6cc8825220cba7e5dcc4d68eb039c77b8ad7'
SOURCE_COMMIT='69fb18cc5591ecbd8f80f648c8ad0ed0c45545ae'
RELEASE_BASE="https://github.com/ostaddehdari/CryptoSniper/releases/download/$RELEASE_TAG"
MODE="${1:-install}"
if [[ "$MODE" != 'install' && "$MODE" != '--check' ]]; then
    echo 'Usage: bash cryptosniper-deploy.sh [--check]' >&2
    exit 2
fi
if [[ "$EUID" -ne 0 ]]; then
    echo 'ERROR: Run as root (sudo bash /tmp/cryptosniper-deploy.sh).' >&2
    exit 1
fi
for cmd in curl sha256sum mktemp bash python3; do
    command -v "$cmd" >/dev/null || { echo "ERROR: Missing $cmd" >&2; exit 1; }
done

WORKDIR="$(mktemp -d /tmp/cryptosniper-release.XXXXXXXX)"
trap 'rm -rf -- "$WORKDIR"' EXIT
echo "Downloading the official $RELEASE_TAG assets built from source $SOURCE_COMMIT..."
curl --fail --location --show-error --silent --retry 3 \
    --output "$WORKDIR/$ZIP_NAME" "$RELEASE_BASE/$ZIP_NAME"
curl --fail --location --show-error --silent --retry 3 \
    --output "$WORKDIR/$INSTALLER_NAME" "$RELEASE_BASE/$INSTALLER_NAME"

printf '%s  %s\n' "$ZIP_SHA256" "$WORKDIR/$ZIP_NAME" | sha256sum --check --status ||
    { echo 'ERROR: ZIP checksum mismatch. Nothing was installed.' >&2; exit 1; }
printf '%s  %s\n' "$INSTALLER_SHA256" "$WORKDIR/$INSTALLER_NAME" | sha256sum --check --status ||
    { echo 'ERROR: Installer checksum mismatch. Nothing was installed.' >&2; exit 1; }

echo 'PASS: exact pinned SHA256 for both files.'
bash -n "$WORKDIR/$INSTALLER_NAME"
bash "$WORKDIR/$INSTALLER_NAME" --check "$WORKDIR/$ZIP_NAME"
if [[ "$MODE" == '--check' ]]; then
    echo 'CHECK_OK: downloaded, verified, no installation.'
    exit 0
fi

echo 'Running the verified Stage29 React installer; preserving existing managed installation data.'
LOG_FILE=/root/cryptosniper-stage29-react-runlog.txt \
    bash "$WORKDIR/$INSTALLER_NAME" "$WORKDIR/$ZIP_NAME"
echo 'DEPLOY_OK: https://srun.ir/cryptosniper/auth/login/'
