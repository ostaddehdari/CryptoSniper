"""Telegram dedup/edit/delete handling; Stage23 stops at review/plan creation."""

import hashlib
import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.exchanges.models import ExchangeMarket, UserExchangeAccount
from apps.tradeplans.service import approve_plan, create_draft

from .ai import analyze_signal
from .channel_parser import select_channel_template
from .models import Signal, TelegramChannel, TelegramChannelTemplate, TelegramMessage
from .parsing import assess
from .services import _revision, receive_signal, transition, update_parsed


def _current_text(signal):
    revision = signal.raw_signal.revisions.order_by("-version").first()
    return revision.text if revision else signal.raw_signal.original_text


def _suggestion(channel, signal, template=None, template_result=None):
    result = None
    if channel.parse_mode in {TelegramChannel.ParseMode.TEMPLATE, TelegramChannel.ParseMode.HYBRID}:
        if template_result is None:
            _, template_result = select_channel_template(
                _current_text(signal), channel.templates.filter(enabled=True), channel.template
            )
        result = assess(template_result)
    incomplete = not result or result.get("warnings")
    if channel.parse_mode == TelegramChannel.ParseMode.AI or (
        channel.parse_mode == TelegramChannel.ParseMode.HYBRID and incomplete
    ):
        ai_result = analyze_signal(signal)
        if ai_result:
            ai_result.setdefault("all_targets", ai_result.get("execution_targets", []))
            ai_result.setdefault("extra_targets", [])
            ai_result.setdefault("entry_range", None)
            ai_result.setdefault("futures_mentioned", False)
            result = assess(ai_result)
            result["technical_confidence"] = min(
                result["technical_confidence"], int(ai_result.get("confidence", 0))
            )
    return result


def _message_kind(text, template, parsed):
    if template:
        return template.message_kind
    folded = text.casefold()
    if any(marker in folded for marker in ("cancel", "لغو", "کنسل")):
        return TelegramChannelTemplate.MessageKind.CANCEL
    if any(marker in folded for marker in ("result", "نتیجه", "tp hit", "target hit")):
        return TelegramChannelTemplate.MessageKind.RESULT
    if any(marker in folded for marker in ("update", "آپدیت", "جابجایی حد ضرر")):
        return TelegramChannelTemplate.MessageKind.UPDATE
    if parsed.get("pair") or parsed.get("execution_targets"):
        return TelegramChannelTemplate.MessageKind.SIGNAL
    return TelegramChannelTemplate.MessageKind.NOISE


@transaction.atomic
def _store_suggestion(signal, parsed, reason):
    locked = Signal.objects.select_for_update().select_related("raw_signal").get(pk=signal.pk)
    locked.parsed_payload = {
        **parsed,
        "last_parsed_raw_revision": locked.raw_signal.revision_number,
    }
    locked.parser_version = str(parsed.get("parser_version", "telegram-v1"))[:40]
    locked.technical_confidence = int(parsed.get("technical_confidence", 0))
    locked.status = Signal.Status.NEEDS_REVIEW
    locked.review_reason = reason
    locked.revision += 1
    locked.save()
    _revision(locked, owner=locked.owner, reason=reason)
    return locked


def _paper_account_and_market(channel, pair):
    account = (
        UserExchangeAccount.objects.for_user(channel.owner)
        .select_related("exchange")
        .filter(
            environment="paper",
            exchange__adapter_code="simulator",
            status="connected",
            trading_enabled=True,
        )
        .first()
    )
    if not account:
        return None, None
    market = ExchangeMarket.objects.filter(
        exchange=account.exchange, symbol=pair, market_type="spot", active=True
    ).first()
    return account, market


def _try_full_auto_paper(channel, signal, parsed):
    # Stage23: simulator/Paper automation is retired. Telegram always stops at review/plan creation.
    return None


def ingest_telegram_message(
    channel_id,
    message_id,
    text,
    *,
    edited=False,
    occurred_at=None,
    ingestion_kind="live",
    advance_live_cursor=True,
    allow_automation=True,
):
    channel = (
        TelegramChannel.objects.select_related("owner", "source")
        .prefetch_related("templates")
        .get(pk=channel_id)
    )
    matched_template, preliminary = select_channel_template(
        text, channel.templates.filter(enabled=True), channel.template
    )
    kind = _message_kind(text, matched_template, preliminary)
    external_id = f"{channel.peer_id}:{message_id}"
    checksum = hashlib.sha256(text.encode()).hexdigest()
    if kind == TelegramChannelTemplate.MessageKind.NOISE:
        event, created = TelegramMessage.objects.get_or_create(
            channel=channel,
            message_id=message_id,
            defaults={
                "owner": channel.owner,
                "text_checksum": checksum,
                "message_kind": kind,
                "matched_template": matched_template,
                "occurred_at": occurred_at,
            },
        )
        if advance_live_cursor and message_id > channel.live_message_id:
            TelegramChannel.objects.filter(pk=channel.pk).update(
                last_message_id=message_id, live_message_id=message_id
            )
        return {"signal_id": None, "created": created, "revised": False, "kind": kind}
    signal, _, revised = receive_signal(
        channel.owner,
        channel.source,
        text=text,
        payload={
            "peer_id": channel.peer_id,
            "message_id": message_id,
            "edited": bool(edited),
            "occurred_at": occurred_at.isoformat() if occurred_at else None,
            "ingestion_kind": ingestion_kind,
        },
        external_id=external_id,
    )
    event, created = TelegramMessage.objects.get_or_create(
        channel=channel,
        message_id=message_id,
        defaults={
            "owner": channel.owner,
            "text_checksum": checksum,
            "raw_signal": signal.raw_signal,
            "occurred_at": occurred_at,
            "message_kind": kind,
            "matched_template": matched_template,
        },
    )
    if revised:
        event.revision += 1
        event.text_checksum = checksum
        event.edited_at = occurred_at or timezone.now()
        event.save(update_fields=("revision", "text_checksum", "edited_at"))
    if advance_live_cursor and message_id > channel.live_message_id:
        TelegramChannel.objects.filter(pk=channel.pk).update(
            last_message_id=message_id, live_message_id=message_id
        )
    if created or revised:
        parsed = _suggestion(channel, signal, matched_template, preliminary)
        if parsed:
            signal = _store_suggestion(
                signal,
                parsed,
                "پیام Telegram تحلیل شد؛ تا عبور سیاست کانال نیازمند بازبینی است.",
            )
            if allow_automation:
                _try_full_auto_paper(channel, signal, parsed)
    return {"signal_id": signal.pk, "created": created, "revised": revised, "kind": kind}


def mark_telegram_deleted(channel_id, message_ids):
    now = timezone.now()
    return TelegramMessage.objects.filter(
        channel_id=channel_id, message_id__in=list(message_ids), deleted_at__isnull=True
    ).update(deleted_at=now)
