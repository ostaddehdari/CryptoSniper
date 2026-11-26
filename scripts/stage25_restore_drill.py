"""Exercise an encrypted backup and isolated PostgreSQL restore with synthetic data in CI."""

import os
import secrets
import tempfile
from pathlib import Path

import django
import psycopg
from psycopg import sql

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")
django.setup()

from apps.accounts.models import AuditLog  # noqa: E402
from apps.operations.backups import create_backup, verify_restore  # noqa: E402
from django.conf import settings  # noqa: E402
from django.utils import timezone  # noqa: E402

TARGET = "cryptosniper_restore_stage25_ci"


def main():
    admin_url = os.environ["HOSTING_RESTORE_ADMIN_URL"]
    passphrase = secrets.token_urlsafe(32)
    marker = secrets.token_hex(16)
    event = AuditLog.objects.create(
        event_type="stage25.restore_drill",
        metadata={"marker": marker, "amount": "123456789.1234567890123456"},
    )
    event_time = event.created_at
    assert timezone.is_aware(event_time)

    with tempfile.TemporaryDirectory(prefix="cryptosniper-s25-ci-") as directory:
        settings.HOSTING_BACKUP_DIR = Path(directory)
        settings.HOSTING_BACKUP_OFFSITE_DIR = ""
        settings.HOSTING_RESTORE_ADMIN_URL = admin_url
        archive = create_backup(passphrase)["path"]
        try:
            result = verify_restore(archive, passphrase, TARGET, keep_database=True)
            # The restore function has already verified the migration ledger.
            with psycopg.connect(
                dbname=TARGET,
                user=settings.DATABASES["default"]["USER"],
                password=settings.DATABASES["default"]["PASSWORD"],
                host=settings.DATABASES["default"].get("HOST") or "127.0.0.1",
                port=settings.DATABASES["default"].get("PORT") or "5432",
            ) as restored:
                row = restored.execute(
                    "SELECT metadata, created_at FROM accounts_auditlog WHERE id = %s",
                    (event.pk,),
                ).fetchone()
            assert row is not None
            assert row[0] == {"marker": marker, "amount": "123456789.1234567890123456"}
            assert row[1] == event_time
            assert result["status"] == "verified" and result["migrations"] > 0
            assert result["audit_rows"] > 0
            print("S25 isolated encrypted restore: synthetic audit/decimal/UTC/migrations verified")
        finally:
            with psycopg.connect(admin_url, autocommit=True) as admin:
                admin.execute(
                    sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                        sql.Identifier(TARGET)
                    )
                )


if __name__ == "__main__":
    main()
