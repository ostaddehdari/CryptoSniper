from types import SimpleNamespace

import pytest
from apps.signals.ai import _validated
from apps.signals.channel_parser import apply_channel_template, complete_extraction
from apps.signals.telegram_security import (
    get_telegram_credentials,
    set_telegram_credentials,
)
from django.core.exceptions import ValidationError


def test_channel_alias_template_keeps_parser_deterministic():
    parsed = apply_channel_template(
        "BTC/USDT\nجهت ورود: 65000\nدفاع: 60000\nخروج: 70000\nBUY",
        {
            "version": "desk-1",
            "aliases": {"entry": ["جهت ورود"], "stop": ["دفاع"], "target": ["خروج"]},
        },
    )
    assert complete_extraction(parsed)
    assert parsed["pair"] == "BTC/USDT"
    assert parsed["entry"] == "65000"
    assert parsed["stop_loss"] == "60000"
    assert parsed["execution_targets"] == ["70000"]


def test_channel_template_rejects_unbounded_or_unknown_aliases():
    with pytest.raises(ValidationError):
        apply_channel_template("BTC/USDT", {"aliases": {"unknown": ["x"]}})
    with pytest.raises(ValidationError):
        apply_channel_template("BTC/USDT", {"aliases": {"entry": ["x" * 41]}})


def test_ai_schema_is_data_only_and_clamps_confidence():
    result = _validated(
        {
            "pair": "BTC/USDT",
            "side": "long",
            "entry": "65000",
            "stop_loss": "60000",
            "execution_targets": ["70000"],
            "confidence": 140,
            "tool_call": {"withdraw": True},
        }
    )
    assert result["confidence"] == 100
    assert "tool_call" not in result


def test_telegram_credentials_are_encrypted_and_owner_bound(settings):
    settings.TELEGRAM_CREDENTIAL_KEYS = ["1:MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="]
    account = SimpleNamespace(
        owner_id=7,
        credential_key_version=1,
        credentials_encrypted="",
        phone_hint="",
    )
    values = {
        "api_id": "123",
        "api_hash": "top-secret-hash",
        "phone": "+989121234567",
        "session": "top-secret-session",
    }
    set_telegram_credentials(account, values)
    assert "top-secret" not in account.credentials_encrypted
    assert account.phone_hint == "••••4567"
    assert get_telegram_credentials(account) == values
    account.owner_id = 8
    with pytest.raises(ValidationError):
        get_telegram_credentials(account)


def test_telegram_verification_code_is_never_persisted(settings):
    settings.TELEGRAM_CREDENTIAL_KEYS = ["1:MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="]
    account = SimpleNamespace(
        owner_id=9,
        credential_key_version=1,
        credentials_encrypted="",
        phone_hint="",
    )
    set_telegram_credentials(
        account,
        {
            "api_id": "123",
            "api_hash": "secret-hash",
            "phone": "+989121234567",
            "session": "session",
            "phone_code_hash": "telegram-challenge",
            "code": "91827",
            "password": "should-not-persist",
        },
    )
    stored = get_telegram_credentials(account)
    assert "code" not in stored
    assert "password" not in stored
    assert "91827" not in account.credentials_encrypted
