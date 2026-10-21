import hashlib

import pytest

from apps.exchanges.adapters import ProviderRejectedError
from apps.exchanges.bitunix import BitunixAdapter


class CaptureTransport:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def request(self, method, url, headers=None, body=None, timeout=10):
        self.calls.append(
            {
                "method": method,
                "url": url,
                "headers": dict(headers or {}),
                "body": body,
                "timeout": timeout,
            }
        )
        return self.payload


def test_bitunix_exposes_provider_code_and_safe_hint():
    transport = CaptureTransport(
        {"code": 10004, "msg": "ip is not in whitelist", "data": None}
    )
    adapter = BitunixAdapter(
        credentials={"api_key": "key", "api_secret": "secret"},
        environment="live",
        transport=transport,
        clock=lambda: 1724285700000,
    )
    with pytest.raises(ProviderRejectedError) as error:
        adapter.validate_credentials()
    assert error.value.code == "bitunix_10004"
    assert "whitelist" in str(error.value).lower()
    assert "secret" not in str(error.value).lower()


def test_bitunix_get_signature_uses_sorted_query_with_equals():
    transport = CaptureTransport({"code": 0, "data": {"price": "1"}})
    adapter = BitunixAdapter(
        credentials={"api_key": "key", "api_secret": "secret"},
        environment="live",
        transport=transport,
        clock=lambda: 1724285700000,
    )
    # Make nonce deterministic for the signature assertion.
    import apps.exchanges.bitunix as bitunix_module

    original = bitunix_module.secrets.token_hex
    bitunix_module.secrets.token_hex = lambda _: "00112233445566778899aabbccddeeff"
    try:
        adapter._request(
            "GET",
            "/probe",
            {"uid": 200, "id": 1},
            signed=True,
        )
    finally:
        bitunix_module.secrets.token_hex = original

    call = transport.calls[0]
    assert call["url"].endswith("/probe?id=1&uid=200")
    query_signature = "id=1uid=200"
    digest = hashlib.sha256(
        (
            "00112233445566778899aabbccddeeff"
            + "1724285700000"
            + "key"
            + query_signature
        ).encode()
    ).hexdigest()
    expected = hashlib.sha256((digest + "secret").encode()).hexdigest()
    assert call["headers"]["sign"] == expected
    assert call["headers"]["api-key"] == "key"
