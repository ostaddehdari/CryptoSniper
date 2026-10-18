import json

from django.core.checks import run_checks
from django.core.management.base import BaseCommand, CommandError

from apps.core.deployment import deployment_status


class Command(BaseCommand):
    help = "Fail closed unless DB/Redis, migrations and collected static match this deployment."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **options):
        errors = run_checks(include_deployment_checks=True)
        if errors:
            raise CommandError(
                "Django deployment checks failed: " + ", ".join(e.id for e in errors)
            )
        report = deployment_status(include_migrations=True)
        if options["json"]:
            self.stdout.write(json.dumps(report, ensure_ascii=False, sort_keys=True))
        if report["status"] != "ready":
            raise CommandError("Deployment is incomplete; inspect JSON status and service logs.")
        self.stdout.write(
            self.style.SUCCESS(
                f"PASS deployment {report['release']} source={report['source_revision']}"
            )
        )
