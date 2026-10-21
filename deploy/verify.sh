#!/usr/bin/env bash
set -u
BASE="${1:-https://srun.ir/cryptosniper}"
echo "== health =="
curl -fsS "$BASE/health/live/" || true; echo
curl -fsS "$BASE/health/ready/" || true; echo
echo "== headers =="
curl -sSI "$BASE/" | head -20
echo "== services =="
systemctl --no-pager --plain --type=service --state=running | grep 'cryptosniper-' || true
