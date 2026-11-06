#!/usr/bin/env bash
# CryptoSniper: single-command, pinned verified deployment artifact.
# Usage: curl -fsSL https://raw.githubusercontent.com/ostaddehdari/CryptoSniper/stage34-live-exchange/scripts/deploy.sh -o /tmp/cryptosniper-deploy.sh && sudo bash /tmp/cryptosniper-deploy.sh
# Only the SHA256-verified Stage34 React ZIP and installer from the official release are executed.
set -Eeuo pipefail
umask 077

RELEASE_TAG='stage34-react-v0.34.0rc1-deploy-r1'
ZIP_NAME='CryptoSniper-Stage34-React-v0.34.0rc1-r1.zip'
INSTALLER_NAME='cryptosniper-stage34-react-run.sh'
ZIP_SHA256='fdd11ed84e15c35e84b4803b482c2c2acccf5b88845ed2e53b8121b7a88aaf43'
INSTALLER_SHA256='b64728c1211fa1ec0002e10fae46a8af7b55571a9e72cca6b93a9476dcab9b70'
SOURCE_COMMIT='7ce55a59b07519ba84a948058fd4ee84942ba414'
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

echo 'Running the verified Stage34 React installer; preserving existing managed installation data.'
LOG_FILE=/root/cryptosniper-stage34-react-runlog.txt \
    bash "$WORKDIR/$INSTALLER_NAME" "$WORKDIR/$ZIP_NAME"
echo 'DEPLOY_OK: https://srun.ir/cryptosniper/auth/login/'
