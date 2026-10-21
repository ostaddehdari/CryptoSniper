# نصب Stage23 روی سرور فعلی

این بسته برای مسیر فعلی `/opt/cryptosniper/app` ساخته شده است.

## نصب

```bash
tar -xzf /root/cryptosniper-stage23-live-ui.tar.gz -C /root/
cd /root/cryptosniper-stage23-live-ui
bash deploy/install.sh
```

نصب قبل از هر تغییری یک بکاپ timestamped در `/opt/cryptosniper/backups/` می‌سازد.

## بررسی

```bash
bash deploy/verify.sh
```

## Rollback

```bash
bash deploy/rollback.sh "$(cat /root/cryptosniper-stage23-last-backup.txt)"
```

`LIVE_TRADING_ENABLED` توسط installer تغییر داده نمی‌شود. Seed Phrase و Private Key نیز در Wallet Center ذخیره نمی‌شوند.
