import json

from django.core.management.base import BaseCommand, CommandError

from apps.operations.release import release_candidate_status


class Command(BaseCommand):
    help = "Measure deployment, host and process evidence for a staging/production candidate."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true")
        parser.add_argument("--probe-host", action="store_true")
        parser.add_argument("--allow-partial", action="store_true")

    def handle(self, *args, **options):
        report = release_candidate_status(probe_host=options["probe_host"])
        if options["json"]:
            self.stdout.write(json.dumps(report, ensure_ascii=False, sort_keys=True))
        else:
            self.stdout.write(
                f"release={report['release']} environment={report['environment']} "
                f"status={report['status']}"
            )
        if report["status"] != "ready" and not options["allow_partial"]:
            raise CommandError("Release candidate lacks measured host/process evidence.")
