"""Authenticated encryption for Telethon API identity and StringSession state."""

import base64
import json
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError


def _keys():
    parsed = {}
    for value in settings.TELEGRAM_CREDENTIAL_KEYS:
        try:
            version_text, encoded = value.split(":", 1)
            version = int(version_text)
            key = base64.urlsafe_b64decode(encoded.encode())
        except (ValueError, TypeError) as error:
            raise ImproperlyConfigured(
                "TELEGRAM_CREDENTIAL_KEYS must use version:urlsafe-base64."
            ) from error
        if version < 1 or len(key) != 32 or version in parsed:
            raise ImproperlyConfigured("Telegram keys need unique versions and 32-byte values.")
        parsed[version] = key
    if not parsed:
        raise ImproperlyConfigured("TELEGRAM_CREDENTIAL_KEYS is required for Telegram.")
    return parsed


def _aad(account):
    return f"cryptosniper:telegram:{account.owner_id}".encode()


def set_telegram_credentials(account, values):
    allowed = {"api_id", "api_hash", "phone", "session", "phone_code_hash"}
    normalized = {
        key: str(value).strip()
        for key, value in values.items()
        if key in allowed and value is not None and str(value).strip()
    }
    if not {"api_id", "api_hash", "phone"}.issubset(normalized):
        raise ValidationError("API ID، API Hash و شماره تلفن لازم است.")
    keys = _keys()
    version = max(keys)
    nonce = os.urandom(12)
    plaintext = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
    encrypted = AESGCM(keys[version]).encrypt(nonce, plaintext, _aad(account))
    account.credential_key_version = version
    account.credentials_encrypted = base64.urlsafe_b64encode(nonce + encrypted).decode()
    phone = normalized["phone"]
    account.phone_hint = "••••" + phone[-4:]


def get_telegram_credentials(account):
    keys = _keys()
    key = keys.get(account.credential_key_version)
    if key is None or not account.credentials_encrypted:
        raise ValidationError("Telegram credential در دسترس نیست.")
    try:
        raw = base64.urlsafe_b64decode(account.credentials_encrypted.encode())
        plaintext = AESGCM(key).decrypt(raw[:12], raw[12:], _aad(account))
        values = json.loads(plaintext)
    except (ValueError, InvalidTag, json.JSONDecodeError) as error:
        raise ValidationError("Telegram credential قابل رمزگشایی نیست.") from error
    if not isinstance(values, dict):
        raise ValidationError("ساختار Telegram credential نامعتبر است.")
    return values


def revoke_telegram_credentials(account):
    account.credentials_encrypted = ""
    account.phone_hint = ""
    account.status = account.Status.DISCONNECTED
    account.last_error = ""
    account.save(
        update_fields=("credentials_encrypted", "phone_hint", "status", "last_error", "updated_at")
    )
