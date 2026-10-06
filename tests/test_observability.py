import json
import logging
from uuid import UUID

from apps.core.observability import RedactingJsonFormatter, correlation_id


def test_correlation_header_is_validated_and_context_cleared(client):
    response = client.get("/health/live/", HTTP_X_CORRELATION_ID="not-a-valid-id")
    UUID(response["X-Correlation-ID"])
    assert correlation_id.get() == "-"


def test_secret_and_url_credentials_are_redacted(settings):
    record = logging.LogRecord(
        "probe",
        logging.ERROR,
        "",
        0,
        "redis://alice:very-private@host/1 token=also-private " + settings.SECRET_KEY,
        (),
        None,
    )
    result = json.loads(RedactingJsonFormatter().format(record))
    assert "very-private" not in result["message"]
    assert "also-private" not in result["message"]
    assert settings.SECRET_KEY not in result["message"]
    assert result["correlation_id"] == "-"
