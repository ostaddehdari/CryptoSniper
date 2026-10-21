"""Interactive, encrypted Telethon login smoke test.

API hash and Telegram password are read with getpass and never printed. The resulting Telethon
StringSession is stored through CryptoSniper's encrypted Telegram credential vault.
"""

import asyncio
import getpass
import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.signals.models import TelegramAccount
from apps.signals.telegram_client import available_channels, complete_login, request_login_code


class Command(BaseCommand):
    help = "Request Telegram login code, complete Telethon authorization, and list channels."

    def add_arguments(self, parser):
        parser.add_argument("--username", required=True)
        parser.add_argument("--phone", required=True)

    def handle(self, *args, **options):
        User = get_user_model()
        try:
            owner = User.objects.get(username=options["username"])
        except User.DoesNotExist as exc:
            raise CommandError("CryptoSniper user was not found.") from exc

        account, _ = TelegramAccount.objects.get_or_create(owner=owner)
        phone = str(options["phone"]).strip()
        api_id_raw = input("Telegram api_id: ").strip()
        api_hash = getpass.getpass("Telegram api_hash (hidden): ").strip()
        if not api_id_raw.isdigit() or not api_hash:
            raise CommandError("api_id/api_hash are required.")

        self.stdout.write("Requesting Telegram verification code; secrets are not logged...")
        asyncio.run(request_login_code(account, int(api_id_raw), api_hash, phone))
        account.refresh_from_db()
        self.stdout.write(
            self.style.WARNING(
                "Verification requested. Telegram may deliver the code inside Telegram or by another "
                "method chosen by Telegram. Do not paste the code into chat."
            )
        )

        code = getpass.getpass("Telegram verification code (hidden): ").strip()
        connected = asyncio.run(complete_login(account, code))
        account.refresh_from_db()
        if not connected and account.status == TelegramAccount.Status.AWAITING_PASSWORD:
            password = getpass.getpass("Telegram 2FA password (hidden): ")
            connected = asyncio.run(complete_login(account, "", password))
            account.refresh_from_db()

        if not connected or account.status != TelegramAccount.Status.CONNECTED:
            raise CommandError(f"Telegram authorization incomplete: status={account.status}")

        channels = asyncio.run(available_channels(account))
        self.stdout.write(self.style.SUCCESS(f"Telegram connected. Channels/groups found: {len(channels)}"))
        self.stdout.write(json.dumps(channels, ensure_ascii=False, indent=2))
        self.stdout.write(
            "Next: open CryptoSniper > Telegram, refresh channels, choose the signal channel, "
            "then start archive from the first accessible message."
        )
