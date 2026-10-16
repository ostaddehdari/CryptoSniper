import re

import pytest
from apps.exchanges.models import Exchange, UserExchangeAccount
from apps.exchanges.security import (
    get_account_credentials,
    rotate_account_credentials,
    set_account_credentials,
)
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.test import override_settings


@pytest.mark.django_db
def test_credentials_are_authenticated_encrypted_and_never_saved_plaintext(django_user_model):
    owner = django_user_model.objects.create_user(username="vault-owner")
    exchange = Exchange.objects.create(code="vault", name="Vault", adapter_code="vault")
    account = UserExchangeAccount(owner=owner, exchange=exchange, label="کلید اصلی")
    credentials = {"api_key": "public-key-1234", "api_secret": "top-secret-value"}
    set_account_credentials(account, credentials)
    account.save()
    account.refresh_from_db()
    assert "top-secret-value" not in account.credentials_encrypted
    assert "public-key-1234" not in account.credentials_encrypted
    assert account.credential_hint == "•••• 1234"
    assert get_account_credentials(account) == credentials
    account.credentials_encrypted = account.credentials_encrypted[:-2] + "AA"
    with pytest.raises(ValidationError):
        get_account_credentials(account)


@pytest.mark.django_db
def test_key_rotation_reencrypts_with_highest_version(django_user_model):
    owner = django_user_model.objects.create_user(username="rotation-owner")
    exchange = Exchange.objects.create(code="rotation", name="Rotation", adapter_code="rotation")
    account = UserExchangeAccount(owner=owner, exchange=exchange, label="گردش کلید")
    set_account_credentials(account, {"api_key": "key-5678", "api_secret": "secret"})
    account.save()
    old_ciphertext = account.credentials_encrypted
    key_two = "YWJjZGVmMDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODk="
    with override_settings(
        EXCHANGE_CREDENTIAL_KEYS=[
            "1:MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
            "2:" + key_two,
        ]
    ):
        assert rotate_account_credentials(account) == 2
        assert account.credentials_encrypted != old_ciphertext
        assert get_account_credentials(account)["api_secret"] == "secret"


def test_missing_keyring_fails_closed():
    with override_settings(EXCHANGE_CREDENTIAL_KEYS=[]), pytest.raises(ImproperlyConfigured):
        from apps.exchanges.security import CredentialVault

        CredentialVault()


def test_example_does_not_contain_a_real_exchange_key():
    text = open(".env.example", encoding="utf-8").read()
    assert not re.search(r"^EXCHANGE_CREDENTIAL_KEYS=.+", text, re.MULTILINE)
