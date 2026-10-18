import json
import os

from django.core.management.base import BaseCommand, CommandError

from apps.operations.backups import verify_restore


class Command(BaseCommand):
    help = "Decrypt and restore a backup only into a dedicated verification database."

    def add_arguments(self, parser):
        parser.add_argument("archive")
        parser.add_argument("--target", required=True)
        parser.add_argument("--keep-database", action="store_true")

    def handle(self, *args, **options):
        passphrase = os.environ.get("CRYPTOSNIPER_BACKUP_PASSPHRASE", "")
        if not passphrase:
            raise CommandError("CRYPTOSNIPER_BACKUP_PASSPHRASE is required.")
        result = verify_restore(
            options["archive"],
            passphrase,
            options["target"],
            keep_database=options["keep_database"],
        )
        self.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True))
