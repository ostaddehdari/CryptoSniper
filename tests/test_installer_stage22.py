from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts/cryptosniper-stage22-run.sh"


def test_stage22_installer_preserves_telegram_and_keeps_live_disabled():
    text = INSTALLER.read_text()
    assert "'LIVE_TRADING_ENABLED': 'false'" in text
    assert "run_telegram_listener" in text
    assert "STAGE21_SOURCE_COMMIT=e315e1983bb916ed8867a721b583e9b2c55eb93a" in text
    assert (
        "STAGE21_ARCHIVE_SHA256=8a44ba2e8e1d61806a122d93bf92f6e3eccc85fa291fc3f51c327469141e0d41"
        in text
    )
    assert "Stage22 v0.22.0rc1" in text


def test_stage22_installer_is_exact_source_pinned_before_publication():
    text = INSTALLER.read_text()
    assert "SOURCE_COMMIT=__SOURCE_COMMIT__" in text
    assert "OFFICIAL_STAGE22_ARCHIVE_SHA256=__STAGE22_ARCHIVE_SHA256__" in text
    assert "__BLOB_TELEGRAM_BACKFILL__" in text
    assert "__BLOB_SIGNAL_OUTCOMES__" in text
    assert "__BLOB_MARKET_HISTORY__" in text
    assert "Stage01-21 source" in text
