import json
import os

from django.core.management.base import BaseCommand, CommandError

from apps.operations.backups import create_backup


class Command(BaseCommand):
    help = "Create an authenticated encrypted PostgreSQL backup and apply retention."

    def add_arguments(self, parser):
        parser.add_argument("--weekly", action="store_true")

    def handle(self, *args, **options):
        passphrase = os.environ.get("CRYPTOSNIPER_BACKUP_PASSPHRASE", "")
        if not passphrase:
            raise CommandError("CRYPTOSNIPER_BACKUP_PASSPHRASE is required.")
        result = create_backup(passphrase, weekly=options["weekly"])
        self.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True))
        if not result["offsite_path"]:
            self.stderr.write(
                "WARNING: encrypted backup created; offsite destination is not configured."
            )
