"""Store original input exactly as provided; idempotency scoped by owner AND source."""

import hashlib
import json

from django.core.exceptions import ValidationError
from django.db import transaction

from .models import RawSignal, RawSignalRevision, SignalSource
from .sources import InboundEnvelope, ensure_ingress_allowed


def _digest(envelope):
    if not isinstance(envelope.text, str) or not envelope.text.strip():
        raise ValidationError("متن اصلی ورودی لازم است.")
    if len(envelope.text) > 40000 or len(envelope.external_id) > 160:
        raise ValidationError("طول متن یا شناسه خارجی بیش از حد مجاز است.")
    if not isinstance(envelope.payload, dict):
        raise ValidationError("Payload باید یک شیء JSON باشد.")
    serialized = json.dumps(
        {"text": envelope.text, "payload": envelope.payload},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    if len(serialized.encode()) > 150000:
        raise ValidationError("حجم ورودی بیش از حد مجاز است.")
    return hashlib.sha256(serialized.encode()).hexdigest()


@transaction.atomic
def ingest(owner, source, envelope: InboundEnvelope):
    """(raw, created, revised). User intent must NOT be executed at ingestion."""
    locked = SignalSource.objects.select_for_update().get(pk=source.pk, owner=owner)
    ensure_ingress_allowed(locked)
    checksum = _digest(envelope)
    duplicate = (
        RawSignal.objects.select_for_update()
        .filter(owner=owner, source=locked, checksum=checksum)
        .first()
    )
    if duplicate:
        return duplicate, False, False

    if envelope.external_id:
        old = (
            RawSignal.objects.select_for_update()
            .filter(owner=owner, source=locked, external_id=envelope.external_id)
            .first()
        )
        if old:
            if old.revisions.filter(checksum=checksum).exists():
                return old, False, False
            # Historical input is append-only, never replace original bytes.
            number = old.revision_number + 1
            RawSignalRevision.objects.create(
                raw_signal=old,
                version=number,
                text=envelope.text,
                payload=envelope.payload,
                checksum=checksum,
                received_version=envelope.received_version,
            )
            old.revision_number = number
            old.save(update_fields=("revision_number",))
            return old, False, True

    raw = RawSignal.objects.create(
        owner=owner,
        source=locked,
        original_text=envelope.text,
        original_payload=envelope.payload,
        checksum=checksum,
        external_id=envelope.external_id,
        received_version=envelope.received_version,
    )
    RawSignalRevision.objects.create(
        raw_signal=raw,
        version=1,
        text=envelope.text,
        payload=envelope.payload,
        checksum=checksum,
        received_version=envelope.received_version,
    )
    return raw, True, False
