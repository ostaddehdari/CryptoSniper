#!/usr/bin/env bash
# CryptoSniper: single-command, pinned verified deployment artifact.
# Usage: curl -fsSL https://raw.githubusercontent.com/ostaddehdari/CryptoSniper/main/scripts/deploy.sh -o /tmp/cryptosniper-deploy.sh && sudo bash /tmp/cryptosniper-deploy.sh
# Only the SHA256-verified Stage18 ZIP and installer at an immutable Git commit are executed.
set -Eeuo pipefail
umask 077

RELEASE_TAG='stage18-v0.18.0rc1-deploy'
ZIP_NAME='CryptoSniper-Stage18-v0.18.0rc1.zip'
INSTALLER_NAME='cryptosniper-stage18-run.sh'
ZIP_SHA256='fc097c2cad84f7e014c01db69d39852ca4999d08bfef2bdc7d1fc9045b5b856d'
INSTALLER_SHA256='62735789f52832fea017e552a9868c37761a3f16b733d99c2e9ed869853defa5'
ASSET_COMMIT='3b031e210560c0085b71909808f9a30aa480a4c2'
RELEASE_BASE="https://raw.githubusercontent.com/ostaddehdari/CryptoSniper/$ASSET_COMMIT/release-assets/$RELEASE_TAG"
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
echo "Downloading the verified $RELEASE_TAG artifact from immutable commit $ASSET_COMMIT..."
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

echo 'Running the verified Stage18 installer; preserving existing managed installation data.'
LOG_FILE=/root/cryptosniper-stage18-runlog.txt \
    bash "$WORKDIR/$INSTALLER_NAME" "$WORKDIR/$ZIP_NAME"
echo 'DEPLOY_OK: https://srun.ir/cryptosniper/auth/login/'
