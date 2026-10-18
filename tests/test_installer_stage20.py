import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts/cryptosniper-stage20-run.sh"


def test_stage20_installer_shell_and_upgrade_contract():
    subprocess.run(["bash", "-n", str(INSTALLER)], check=True)
    source = INSTALLER.read_text()
    assert "Stage20 v0.20.0rc1" in source
    assert "STAGE18_SOURCE_COMMIT=" in source and "STAGE18_ARCHIVE_SHA256=" in source
    assert "range(1, 21)" in source
    assert "CRYPTOSNIPER_SOURCE_REVISION" in source
    assert "CRYPTOSNIPER_ENVIRONMENT" in source


def test_stage20_installer_activates_encrypted_backup_timers_without_inline_secret():
    source = INSTALLER.read_text()
    assert "cryptosniper-backup-daily.timer" in source
    assert "cryptosniper-backup-weekly.timer" in source
    assert "backup_deployment --weekly" in source
    assert "secrets.token_urlsafe(48)" in source
    assert "CRYPTOSNIPER_BACKUP_PASSPHRASE=committed" not in source
    assert "HOSTING_RESTORE_ADMIN_URL=" not in source
