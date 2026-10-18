"""Stage19 encrypted backup, retention and restore-boundary tests."""

import json
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidTag


def test_encrypted_backup_round_trip_and_authentication(settings, tmp_path):
    from apps.operations.backups import decrypt_file, encrypt_file

    settings.RELEASE_VERSION = "0.20.0rc1"
    settings.SOURCE_REVISION = "backup-test"
    source = tmp_path / "database.dump"
    source.write_bytes((b"private-postgres-dump\0" * 10000) + b"audit-preserved")
    encrypted = tmp_path / "database.csbk"
    digest = encrypt_file(source, encrypted, "correct horse battery staple")
    assert b"private-postgres-dump" not in encrypted.read_bytes()
    restored = tmp_path / "restored.dump"
    header = decrypt_file(encrypted, restored, "correct horse battery staple")
    assert restored.read_bytes() == source.read_bytes()
    assert header["release"] == "0.20.0rc1"
    assert len(digest) == 64
    damaged = bytearray(encrypted.read_bytes())
    damaged[-20] ^= 1
    encrypted.write_bytes(damaged)
    with pytest.raises((ValueError, InvalidTag)):
        decrypt_file(encrypted, tmp_path / "bad.dump", "correct horse battery staple")


def test_backup_invokes_pg_dump_without_password_in_arguments(settings, tmp_path):
    from apps.operations.backups import create_backup

    settings.HOSTING_BACKUP_DIR = tmp_path
    settings.HOSTING_BACKUP_OFFSITE_DIR = ""
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        Path(command[command.index("--file") + 1]).write_bytes(b"PGDMP\0private")

    result = create_backup("correct horse battery staple", runner=fake_run)
    command, kwargs = calls[0]
    assert "pg_dump" == command[0]
    assert settings.DATABASES["default"]["PASSWORD"] not in command
    assert kwargs["env"]["PGPASSWORD"] == settings.DATABASES["default"]["PASSWORD"]
    assert Path(result["path"]).is_file() and result["offsite_path"] is None
    manifest = json.loads(Path(result["path"] + ".json").read_text())
    assert manifest["encrypted"] == "AES-256-GCM+scrypt"


def test_retention_deletes_only_named_regular_archives(tmp_path):
    from apps.operations.backups import prune_backups

    for index in range(5):
        (tmp_path / f"cryptosniper-daily-2026010{index}T000000Z.csbk").write_bytes(b"x")
    unrelated = tmp_path / "keep-me.txt"
    unrelated.write_text("safe")
    removed = prune_backups(tmp_path, keep_daily=2, keep_weekly=1)
    assert len(removed) == 3
    assert unrelated.read_text() == "safe"


@pytest.mark.parametrize("target", ["cryptosniper", "postgres", "restore_test", "bad-name"])
def test_restore_refuses_production_or_unscoped_database(target):
    from apps.operations.backups import verify_restore

    with pytest.raises(ValueError, match="dedicated"):
        verify_restore("missing", "correct horse battery staple", target)


def test_restore_requires_separate_admin_connection(settings):
    from apps.operations.backups import verify_restore

    settings.HOSTING_RESTORE_ADMIN_URL = ""
    with pytest.raises(ValueError, match="HOSTING_RESTORE_ADMIN_URL"):
        verify_restore("missing", "correct horse battery staple", "cryptosniper_restore_acceptance")
