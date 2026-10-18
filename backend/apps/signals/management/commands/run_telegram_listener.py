import asyncio

from django.core.management.base import BaseCommand

from apps.signals.telegram_client import run_all_listeners


class Command(BaseCommand):
    help = "Run authorized Telegram account listeners with bounded catch-up and dedup."

    def handle(self, *args, **options):
        self.stdout.write("Starting configured Telegram listeners; secrets are not logged.")
        asyncio.run(run_all_listeners())
