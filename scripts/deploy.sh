#!/usr/bin/env bash
# CryptoSniper: single-command, pinned release deployment.
# Usage: curl -fsSL https://raw.githubusercontent.com/ostaddehdari/CryptoSniper/main/scripts/deploy.sh -o /tmp/cryptosniper-deploy.sh && sudo bash /tmp/cryptosniper-deploy.sh
# Only the SHA256-verified official GitHub release ZIP and installer are executed.
set -Eeuo pipefail
umask 077

RELEASE_TAG='stage03-v0.3.0rc1-deploy'
ZIP_NAME='CryptoSniper-Stage03-v0.3.0rc1.zip'
INSTALLER_NAME='cryptosniper-stage03-run.sh'
ZIP_SHA256='38c96027f503f38a71cddb807e89db9d5aeaa1081b2cd7ed87a3c11158fd4f93'
INSTALLER_SHA256='44d00517540754e72106598c9f1d90f858cc3d34ef37a49649e695e8049b6ea8'
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
echo "Downloading the official $RELEASE_TAG release to a private temporary directory..."
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

echo 'Running the verified Stage03 installer; preserving existing managed installation data.'
LOG_FILE=/root/cryptosniper-stage03-runlog.txt \
    bash "$WORKDIR/$INSTALLER_NAME" "$WORKDIR/$ZIP_NAME"
echo 'DEPLOY_OK: https://srun.ir/cryptosniper/auth/login/'
