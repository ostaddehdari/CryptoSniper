import base64
import json
import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError


@dataclass(frozen=True)
class KeyMaterial:
    version: int
    key: bytes


def _parse_keys():
    parsed = {}
    for value in settings.EXCHANGE_CREDENTIAL_KEYS:
        try:
            version_text, encoded = value.split(":", 1)
            version = int(version_text)
            key = base64.urlsafe_b64decode(encoded.encode())
        except (ValueError, TypeError) as error:
            raise ImproperlyConfigured(
                "EXCHANGE_CREDENTIAL_KEYS entries must use version:urlsafe-base64 format."
            ) from error
        if version < 1 or len(key) != 32 or version in parsed:
            raise ImproperlyConfigured(
                "Each exchange credential key must have a unique positive version and 32 bytes."
            )
        parsed[version] = key
    return parsed


class CredentialVault:
    """Authenticated encryption for exchange credentials with rotation support."""

    def __init__(self):
        self.keys = _parse_keys()
        if not self.keys:
            raise ImproperlyConfigured(
                "EXCHANGE_CREDENTIAL_KEYS is required before saving exchange credentials."
            )

    @property
    def active(self):
        version = max(self.keys)
        return KeyMaterial(version=version, key=self.keys[version])

    @staticmethod
    def aad(account):
        return f"cryptosniper:exchange:{account.owner_id}:{account.exchange.code}".encode()

    def encrypt(self, account, credentials):
        allowed = {
            "api_key",
            "api_secret",
            "passphrase",
            "no_withdrawal_confirmed",
            "ip_restricted_confirmed",
        }
        if not isinstance(credentials, dict) or set(credentials) - allowed:
            raise ValidationError("ساختار اطلاعات اتصال معتبر نیست.")
        normalized = {
            key: str(value).strip()
            for key, value in credentials.items()
            if value is not None and str(value).strip()
        }
        required = (
            {"api_key"}
            if account.exchange.adapter_code == "nobitex"
            else {"api_key", "api_secret", "passphrase"}
            if account.exchange.adapter_code == "weex"
            else {"api_key", "api_secret"}
        )
        if account.exchange.adapter_code != "simulator" and not required.issubset(normalized):
            raise ValidationError("API Key و Secret برای این اتصال لازم است.")
        plaintext = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()
        nonce = os.urandom(12)
        material = self.active
        ciphertext = AESGCM(material.key).encrypt(nonce, plaintext, self.aad(account))
        payload = base64.urlsafe_b64encode(nonce + ciphertext).decode()
        return material.version, payload

    def decrypt(self, account):
        key = self.keys.get(account.credential_key_version)
        if key is None:
            raise ImproperlyConfigured("Credential key version is unavailable.")
        try:
            raw = base64.urlsafe_b64decode(account.credentials_encrypted.encode())
            plaintext = AESGCM(key).decrypt(raw[:12], raw[12:], self.aad(account))
            value = json.loads(plaintext)
        except (ValueError, InvalidTag, json.JSONDecodeError) as error:
            raise ValidationError("اطلاعات رمزنگاری‌شده قابل اعتبارسنجی نیست.") from error
        if not isinstance(value, dict):
            raise ValidationError("ساختار اطلاعات رمزنگاری‌شده معتبر نیست.")
        return value


def set_account_credentials(account, credentials):
    vault = CredentialVault()
    version, encrypted = vault.encrypt(account, credentials)
    api_key = str(credentials.get("api_key", ""))
    account.credential_hint = f"•••• {api_key[-4:]}" if api_key else "بدون کلید"
    account.credential_key_version = version
    account.credentials_encrypted = encrypted


def get_account_credentials(account):
    return CredentialVault().decrypt(account)


def rotate_account_credentials(account):
    credentials = get_account_credentials(account)
    set_account_credentials(account, credentials)
    account.save(
        update_fields=(
            "credentials_encrypted",
            "credential_hint",
            "credential_key_version",
            "updated_at",
        )
    )
    return account.credential_key_version


def revoke_account_credentials(account):
    """Cryptographically revoke a connection and remove its recoverable secret."""

    account.credentials_encrypted = ""
    account.credential_hint = "حذف‌شده"
    account.trading_enabled = False
    account.status = account.Status.DISABLED
    account.permissions = {}
    account.save(
        update_fields=(
            "credentials_encrypted",
            "credential_hint",
            "trading_enabled",
            "status",
            "permissions",
            "updated_at",
        )
    )


def encrypted_credentials_backup(accounts, passphrase):
    """Return a portable encrypted backup; plaintext and passphrase never leave memory."""

    if not isinstance(passphrase, str) or len(passphrase) < 16:
        raise ValidationError("عبارت پشتیبان باید دست‌کم ۱۶ نویسه باشد.")
    records = []
    for account in accounts.select_related("exchange").order_by("pk"):
        records.append(
            {
                "exchange": account.exchange.code,
                "label": account.label,
                "environment": account.environment,
                "credentials": get_account_credentials(account),
            }
        )
    plaintext = json.dumps(
        {"format": "cryptosniper-credentials-v1", "records": records},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    salt, nonce = os.urandom(16), os.urandom(12)
    key = Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(passphrase.encode())
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, b"cryptosniper-backup-v1")
    return json.dumps(
        {
            "format": "cryptosniper-encrypted-backup-v1",
            "kdf": "scrypt-n32768-r8-p1",
            "salt": base64.urlsafe_b64encode(salt).decode(),
            "nonce": base64.urlsafe_b64encode(nonce).decode(),
            "ciphertext": base64.urlsafe_b64encode(ciphertext).decode(),
        },
        separators=(",", ":"),
    ).encode()
