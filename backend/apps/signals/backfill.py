"""Resumable Telethon archive import; historical messages can never launch trades."""

import asyncio
from datetime import timedelta

from celery import shared_task
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from telethon.errors import FloodWaitError

from .models import TelegramBackfillJob
from .telegram_client import _client
from .telegram_ingestion import ingest_telegram_message
from .telegram_security import get_telegram_credentials


def start_backfill(channel, *, batch_size=100):
    if not 20 <= batch_size <= 500:
        raise ValidationError("اندازه بسته آرشیو باید بین ۲۰ تا ۵۰۰ باشد.")
    active = channel.backfill_jobs.filter(status__in=("pending", "running", "paused")).first()
    if active:
        active.status = TelegramBackfillJob.Status.PENDING
        active.last_error = ""
        active.retry_at = None
        active.save(update_fields=("status", "last_error", "retry_at", "updated_at"))
        return active, False
    job = TelegramBackfillJob.objects.create(
        owner=channel.owner,
        channel=channel,
        batch_size=batch_size,
    )
    return job, True


def pause_backfill(job):
    if job.status in {TelegramBackfillJob.Status.PENDING, TelegramBackfillJob.Status.RUNNING}:
        job.status = TelegramBackfillJob.Status.PAUSED
        job.save(update_fields=("status", "updated_at"))
    return job


async def _fetch_batch(job):
    values = get_telegram_credentials(job.channel.account)
    client = _client(values)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            raise ValidationError("Telegram session معتبر نیست.")
        entity = await client.get_input_entity(job.channel.peer_id)
        upper = job.upper_message_id
        if not upper:
            latest = await client.get_messages(entity, limit=1)
            upper = int(latest[0].id) if latest else 0
        rows = []
        async for message in client.iter_messages(
            entity,
            min_id=job.cursor_message_id,
            limit=job.batch_size,
            reverse=True,
        ):
            if message.id > upper:
                break
            rows.append(
                {
                    "id": int(message.id),
                    "text": message.raw_text or "",
                    "date": message.date,
                }
            )
        return upper, rows
    finally:
        await client.disconnect()


@shared_task(name="signals.telegram_backfill_batch")
def process_backfill_batch(job_id):
    job = TelegramBackfillJob.objects.select_related("channel__account").get(pk=job_id)
    if job.status not in {TelegramBackfillJob.Status.PENDING, TelegramBackfillJob.Status.RUNNING}:
        return {"status": job.status}
    job.status = TelegramBackfillJob.Status.RUNNING
    job.started_at = job.started_at or timezone.now()
    job.save(update_fields=("status", "started_at", "updated_at"))
    try:
        upper, rows = asyncio.run(_fetch_batch(job))
    except FloodWaitError as error:
        job.status = TelegramBackfillJob.Status.PENDING
        job.last_error = "telegram_flood_wait"
        job.retry_at = timezone.now() + timedelta(seconds=error.seconds)
        job.save(update_fields=("status", "last_error", "retry_at", "updated_at"))
        process_backfill_batch.apply_async(args=[job.pk], countdown=error.seconds, queue="signals")
        return {"status": job.status, "retry_after": error.seconds}
    except (ValidationError, OSError, TimeoutError):
        job.status = TelegramBackfillJob.Status.FAILED
        job.last_error = "telegram_archive_unavailable"
        job.save(update_fields=("status", "last_error", "updated_at"))
        return {"status": job.status}

    imported = skipped = 0
    cursor = job.cursor_message_id
    for row in rows:
        cursor = max(cursor, row["id"])
        if not row["text"].strip():
            skipped += 1
            continue
        result = ingest_telegram_message(
            job.channel_id,
            row["id"],
            row["text"],
            occurred_at=row["date"],
            ingestion_kind="archive",
            advance_live_cursor=False,
            allow_automation=False,
        )
        imported += int(result["created"])

    with transaction.atomic():
        locked = TelegramBackfillJob.objects.select_for_update().get(pk=job.pk)
        if locked.status == TelegramBackfillJob.Status.PAUSED:
            return {"status": locked.status}
        locked.upper_message_id = upper
        locked.cursor_message_id = cursor
        locked.scanned_messages += len(rows)
        locked.imported_messages += imported
        locked.skipped_messages += skipped
        complete = not rows or cursor >= upper
        if complete:
            locked.status = TelegramBackfillJob.Status.COMPLETED
            locked.completed_at = timezone.now()
        else:
            locked.status = TelegramBackfillJob.Status.PENDING
        locked.last_error = ""
        locked.retry_at = None
        locked.save()
    if not complete:
        process_backfill_batch.apply_async(args=[job.pk], queue="signals")
    return {"status": locked.status, "cursor": cursor, "upper": upper, "imported": imported}
