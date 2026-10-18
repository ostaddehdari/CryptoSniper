"""Telethon authorization and listener orchestration with sanitized failures."""

import asyncio

from asgiref.sync import sync_to_async
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.utils import timezone
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError, SessionPasswordNeededError
from telethon.sessions import StringSession

from .models import SignalSource, TelegramAccount, TelegramChannel
from .telegram_ingestion import ingest_telegram_message, mark_telegram_deleted
from .telegram_security import get_telegram_credentials, set_telegram_credentials


def _client(values):
    return TelegramClient(
        StringSession(values.get("session", "")),
        int(values["api_id"]),
        values["api_hash"],
        connection_retries=1,
        request_retries=1,
        timeout=15,
        flood_sleep_threshold=30,
    )


async def request_login_code(account, api_id, api_hash, phone):
    values = {"api_id": api_id, "api_hash": api_hash, "phone": phone}
    client = _client(values)
    try:
        await client.connect()
        sent = await client.send_code_request(phone)
        values.update({"session": client.session.save(), "phone_code_hash": sent.phone_code_hash})
        set_telegram_credentials(account, values)
        account.status = TelegramAccount.Status.AWAITING_CODE
        account.last_error = ""
        account.save()
    except FloodWaitError as error:
        raise ValidationError(
            f"Telegram FloodWait؛ {error.seconds} ثانیه بعد تلاش کنید."
        ) from error
    except Exception as error:
        raise ValidationError("Telegram درخواست ورود را نپذیرفت.") from error
    finally:
        await client.disconnect()


async def complete_login(account, code, password=""):
    values = get_telegram_credentials(account)
    client = _client(values)
    try:
        await client.connect()
        try:
            await client.sign_in(
                phone=values["phone"], code=code, phone_code_hash=values["phone_code_hash"]
            )
        except SessionPasswordNeededError:
            if not password:
                account.status = TelegramAccount.Status.AWAITING_PASSWORD
                account.save(update_fields=("status", "updated_at"))
                return False
            await client.sign_in(password=password)
        values["session"] = client.session.save()
        values.pop("phone_code_hash", None)
        set_telegram_credentials(account, values)
        account.status = TelegramAccount.Status.CONNECTED
        account.connected_at = timezone.now()
        account.last_error = ""
        account.save()
        return True
    except Exception as error:
        raise ValidationError("کد یا رمز Telegram پذیرفته نشد.") from error
    finally:
        await client.disconnect()


async def available_channels(account):
    values = get_telegram_credentials(account)
    client = _client(values)
    result = []
    try:
        await client.connect()
        if not await client.is_user_authorized():
            raise ValidationError("Telegram session معتبر نیست.")
        async for dialog in client.iter_dialogs(limit=500):
            if dialog.is_channel or dialog.is_group:
                result.append(
                    {
                        "peer_id": int(dialog.id),
                        "title": str(dialog.name)[:160],
                        "username": str(getattr(dialog.entity, "username", "") or "")[:80],
                    }
                )
    finally:
        await client.disconnect()
    return result


def configure_channel(owner, account, peer_id, title, username="", **policy):
    source, _ = SignalSource.objects.get_or_create(
        owner=owner,
        method=SignalSource.Method.TELEGRAM,
        name=f"Telegram · {title}"[:80],
    )
    channel, _ = TelegramChannel.objects.update_or_create(
        owner=owner,
        peer_id=peer_id,
        defaults={
            "account": account,
            "source": source,
            "title": title,
            "username": username,
            **policy,
        },
    )
    return channel


async def listen_account(account_id):
    account = await sync_to_async(TelegramAccount.objects.get)(pk=account_id)
    values = await sync_to_async(get_telegram_credentials)(account)
    channels = await sync_to_async(list)(
        TelegramChannel.objects.filter(account=account, enabled=True).values(
            "id", "peer_id", "last_message_id", "max_catchup"
        )
    )
    if not channels:
        return
    by_peer = {int(row["peer_id"]): row for row in channels}
    client = _client(values)

    @client.on(events.NewMessage(chats=list(by_peer)))
    async def on_new(event):
        row = by_peer.get(int(event.chat_id))
        text = event.raw_text or ""
        if row and text.strip():
            await sync_to_async(ingest_telegram_message)(
                row["id"], event.id, text, occurred_at=event.date
            )

    @client.on(events.MessageEdited(chats=list(by_peer)))
    async def on_edit(event):
        row = by_peer.get(int(event.chat_id))
        text = event.raw_text or ""
        if row and text.strip():
            await sync_to_async(ingest_telegram_message)(
                row["id"], event.id, text, edited=True, occurred_at=event.date
            )

    @client.on(events.MessageDeleted(chats=list(by_peer)))
    async def on_delete(event):
        row = by_peer.get(int(event.chat_id))
        if row:
            await sync_to_async(mark_telegram_deleted)(row["id"], event.deleted_ids)

    await client.connect()
    if not await client.is_user_authorized():
        await sync_to_async(TelegramAccount.objects.filter(pk=account_id).update)(
            status=TelegramAccount.Status.ERROR, last_error="session_not_authorized"
        )
        await client.disconnect()
        return
    for row in channels:
        entity = await client.get_input_entity(row["peer_id"])
        messages = []
        async for message in client.iter_messages(
            entity,
            min_id=row["last_message_id"],
            limit=row["max_catchup"],
            reverse=True,
        ):
            if message.raw_text and message.raw_text.strip():
                messages.append(message)
        for message in messages:
            await sync_to_async(ingest_telegram_message)(
                row["id"], message.id, message.raw_text, occurred_at=message.date
            )
    await client.run_until_disconnected()


async def run_all_listeners():
    """Supervise dynamic accounts and refresh channel policy at most every five minutes."""

    async def account_loop(account_id):
        while True:
            connected = await sync_to_async(
                TelegramAccount.objects.filter(
                    pk=account_id, status=TelegramAccount.Status.CONNECTED
                ).exists
            )()
            if not connected:
                return
            try:
                await asyncio.wait_for(listen_account(account_id), timeout=300)
            except TimeoutError:
                pass
            except Exception:
                await asyncio.sleep(10)

    running = {}
    while True:
        ids = set(
            await sync_to_async(list)(
                TelegramAccount.objects.filter(status=TelegramAccount.Status.CONNECTED).values_list(
                    "pk", flat=True
                )
            )
        )
        for account_id in ids - set(running):
            running[account_id] = asyncio.create_task(account_loop(account_id))
        for account_id in set(running) - ids:
            running.pop(account_id).cancel()
        for account_id, task in list(running.items()):
            if task.done():
                running.pop(account_id)
        await sync_to_async(cache.set)(
            "telegram_listener_heartbeat",
            {"seen_at": timezone.now().isoformat(), "accounts": len(ids)},
            60,
        )
        await asyncio.sleep(20)
