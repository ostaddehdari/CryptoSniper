from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts/cryptosniper-stage21-run.sh"


def test_stage21_installer_keeps_live_disabled_and_runs_telegram_supervisor():
    text = INSTALLER.read_text()
    assert "'LIVE_TRADING_ENABLED': 'false'" in text
    assert "run_telegram_listener" in text
    assert (
        "for name in web orders reports beat signals market-data "
        "trailing alerts maintenance telegram" in text
    )
    assert "Stage21 v0.21.0rc1" in text


def test_stage21_installer_is_release_pinned_before_publication():
    text = INSTALLER.read_text()
    assert "SOURCE_COMMIT=__SOURCE_COMMIT__" in text
    assert "OFFICIAL_STAGE21_ARCHIVE_SHA256=__STAGE21_ARCHIVE_SHA256__" in text
    assert (
        "STAGE20_ARCHIVE_SHA256="
        "a7264790d9f26d3d8cdb9727603b3d44982c7a040db1154edabef0f5bb83ce55" in text
    )
    assert "Stage01-20 source" in text
