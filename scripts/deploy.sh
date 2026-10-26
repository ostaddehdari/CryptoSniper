#!/usr/bin/env bash
# CryptoSniper: single-command, pinned verified deployment artifact.
# Usage: curl -fsSL https://raw.githubusercontent.com/ostaddehdari/CryptoSniper/stage31-final-management/scripts/deploy.sh -o /tmp/cryptosniper-deploy.sh && sudo bash /tmp/cryptosniper-deploy.sh
# Only the SHA256-verified Stage31 React ZIP and installer from the official release are executed.
set -Eeuo pipefail
umask 077

RELEASE_TAG='stage31-react-v0.31.0rc1-deploy-r2'
ZIP_NAME='CryptoSniper-Stage31-React-v0.31.0rc1-r2.zip'
INSTALLER_NAME='cryptosniper-stage31-react-run.sh'
ZIP_SHA256='16a7398accfca2f35ec28fdea5dff5b0460fa340db36c0e7209b04656a8d2108'
INSTALLER_SHA256='686df0e0279e97b2fda3ac901223effc0ae91d116a8c5d10a10e4d2865c3f984'
SOURCE_COMMIT='dc1e88ce99bfcf48c6500e559788be63f65136a0'
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

echo 'Running the verified Stage31 React installer; preserving existing managed installation data.'
LOG_FILE=/root/cryptosniper-stage31-react-runlog.txt \
    bash "$WORKDIR/$INSTALLER_NAME" "$WORKDIR/$ZIP_NAME"
echo 'DEPLOY_OK: https://srun.ir/cryptosniper/auth/login/'
