"""Security boundary helpers shared by configuration-facing applications."""

import ipaddress
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator


def validate_public_https_url(value: str) -> None:
    """Reject URLs that could turn an operator setting into an SSRF primitive.

    DNS resolution is intentionally not performed here: outbound clients must also
    pin/revalidate the resolved address at connection time.  This validator keeps
    stored configuration free from credentials, local names and literal private
    addresses.
    """

    if not value:
        return
    URLValidator(schemes=("https",))(value)
    parsed = urlsplit(value)
    if parsed.username or parsed.password:
        raise ValidationError("نشانی خارجی نباید شامل نام کاربری یا رمز باشد.")
    hostname = (parsed.hostname or "").rstrip(".").casefold()
    if not hostname or hostname == "localhost" or hostname.endswith((".localhost", ".local")):
        raise ValidationError("نشانی محلی برای تنظیمات خارجی مجاز نیست.")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return
    if not address.is_global:
        raise ValidationError("نشانی خصوصی، loopback یا link-local مجاز نیست.")
